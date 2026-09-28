"""
The in-process job store — honest for one worker, and explicit about what it is not.

Job state lives in a dict guarded by an ``asyncio.Lock``, and every change is mirrored
to a JSON file under the configured directory. The mirror is what lets an operator see
what a worker is doing without a debugger, and what lets a restarted worker tell a
caller the truth about a job it was running.

**It is not durable, and it does not pretend to be.** A worker that dies mid-run loses
the run. On restart the mirror is read back and any job still marked ``running`` is
reported ``failed`` with a ``worker_restarted`` code — not resumed. Resuming half a
pipeline would stitch stage 4 of one process onto stage 5 of another and produce a
report whose figures came from two different runs, which is worse than an honest
failure the caller can retry.

**It is per worker.** Two workers behind a load balancer do not see each other's jobs,
so a poll can 404 against the worker that did not accept the job. Run one worker, or
pin polls to the accepting instance, or put a shared store behind this Protocol. The
README says the same thing where an operator will read it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from ..api.models.enums import JobStatus
from ..api.models.jobs import JobError, JobState
from .base import JobNotFound, JobStoreError

__all__ = ["LocalJobStore"]

logger = logging.getLogger(__name__)


class LocalJobStore:
    """A ``JobStore`` held in this process's memory and mirrored to disk."""

    def __init__(self, directory: Path | str, ttl_sec: float = 86_400.0) -> None:
        # Absolute from the outset, so a later chdir cannot move the mirror out from
        # under a run that is still writing to it.
        self.dir = Path(directory).absolute()
        self.ttl_sec = ttl_sec
        self._jobs: dict[str, JobState] = {}
        self._finished_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def recover(self) -> int:
        """Read the mirror back and fail anything that was mid-run. Returns the count.

        Called once at startup, synchronously, before the app serves anything — so it
        does not take the lock, because nothing else can be running yet.

        A job found ``queued`` or ``running`` belonged to a process that is gone. It
        is marked failed rather than restarted: see the module docstring.
        """
        if not self.dir.is_dir():
            return 0

        recovered = 0
        for path in sorted(self.dir.glob("*.json")):
            try:
                state = JobState.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception as exc:
                # A half-written mirror file from a process killed mid-write. It
                # describes a job that is gone either way, so it is dropped rather
                # than allowed to fail startup.
                logger.warning("Discarding unreadable job mirror %s: %s", path.name, exc)
                path.unlink(missing_ok=True)
                continue

            if state.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                state.status = JobStatus.FAILED
                state.finished_at = datetime.now(timezone.utc)
                state.error = JobError(
                    code="worker_restarted",
                    message=(
                        "The worker running this job restarted before it finished. "
                        "The run was abandoned rather than resumed; retrying is safe."
                    ),
                    stage=state.stage,
                )
                state.message = None
                self._write_mirror(state)
                recovered += 1

            self._jobs[state.job_id] = state
            if state.finished_at is not None:
                self._finished_at[state.job_id] = time.monotonic()

        if recovered:
            logger.warning(
                "Failed %d job(s) that were mid-run when the worker restarted.",
                recovered,
            )
        return recovered

    # ── The contract ──────────────────────────────────────────────────────────

    async def create(self, state: JobState) -> None:
        async with self._lock:
            self._jobs[state.job_id] = state
            await asyncio.to_thread(self._write_mirror, state)

    async def get(self, job_id: str) -> JobState:
        async with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                raise JobNotFound(f"No job {job_id!r}.")
            # Returned by value. The caller is about to serialise it while the run
            # keeps mutating its own copy, and a shared object would let a field
            # change between two lines of the response.
            return state.model_copy(deep=True)

    async def update(self, state: JobState) -> None:
        async with self._lock:
            if state.job_id not in self._jobs:
                raise JobNotFound(f"No job {state.job_id!r}.")
            self._jobs[state.job_id] = state
            if state.finished_at is not None:
                self._finished_at.setdefault(state.job_id, time.monotonic())
            await asyncio.to_thread(self._write_mirror, state)

    async def purge_expired(self) -> int:
        """Drop finished jobs whose TTL has run out.

        Age is measured from when this process saw the job finish, not from the
        job's own ``finished_at``. After a restart those are the same thing to
        within the downtime, and using the monotonic clock means a system clock
        adjustment cannot make a job immortal or drop one early.
        """
        cutoff = time.monotonic() - self.ttl_sec
        async with self._lock:
            expired = [
                job_id
                for job_id, finished in self._finished_at.items()
                if finished < cutoff
            ]
            for job_id in expired:
                self._jobs.pop(job_id, None)
                self._finished_at.pop(job_id, None)
                await asyncio.to_thread(self._drop_mirror, job_id)
        if expired:
            logger.info("Purged %d expired job record(s).", len(expired))
        return len(expired)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _mirror_path(self, job_id: str) -> Path:
        # Job ids are hex generated here, never caller-supplied, so there is nothing
        # to traverse with. Asserted rather than assumed, because the day an id comes
        # from a caller this is a write anywhere the process can reach.
        if not job_id.isalnum():
            raise JobStoreError(f"Refusing a non-alphanumeric job id: {job_id!r}")
        return self.dir / f"{job_id}.json"

    def _write_mirror(self, state: JobState) -> None:
        path = self._mirror_path(state.job_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Written to a sibling and renamed, so a reader — the recovery pass after
            # a crash, or an operator watching the directory — never sees a half file.
            # os.replace is atomic within a filesystem.
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                state.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
            )
            tmp.replace(path)
        except OSError as exc:
            # The mirror is a diagnostic, not the source of truth: the in-memory
            # record is. Losing the mirror must not lose the run.
            logger.warning(
                "Could not mirror job %s to disk: %s", state.job_id, exc.strerror or exc
            )

    def _drop_mirror(self, job_id: str) -> None:
        try:
            self._mirror_path(job_id).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove job mirror %s: %s", job_id, exc)
