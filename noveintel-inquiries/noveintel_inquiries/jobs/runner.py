"""
What actually runs a job, and where.

The work route returns as soon as the job is recorded, so the run has to happen
somewhere else. That somewhere is an ``asyncio`` task on this worker's event loop,
which hands the synchronous pipeline to a thread and reports each stage back into the
job store as it goes.

Three things here are load-bearing:

**A semaphore, not a queue of workers.** ``max_concurrent`` bounds how many runs
execute at once; the rest sit in ``queued`` holding nothing but a slot in the store.
The Core42 layer already caps in-flight *requests* process-wide, so this is about
memory — each run holds its whole export in a dataframe — rather than gateway
pressure.

**The pipeline runs in a thread.** Its six stages are synchronous and fan out with
``ThreadPoolExecutor`` internally. Calling it on the event loop would block every
poll on this worker for the length of a run, which is precisely the failure the async
pattern exists to avoid.

**Cancellation is told apart from failure.** A run abandoned because the worker is
shutting down is reported ``cancelled``; one that exceeded ``max_runtime_sec`` is
``failed`` with a ``runtime_exceeded`` code. Both leave a terminal state behind, so a
caller polling forever is never the answer to either.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from ..api.models.enums import JobStatus
from ..api.models.jobs import JobError, JobState
from .base import JobNotFound, JobStore

__all__ = ["JobRunner", "ProgressReporter", "RunAbandoned", "runtime_exceeded"]

logger = logging.getLogger(__name__)

# A run reports progress from a worker thread. Handing each update to the event loop
# is cheap, but a stage that reports in a tight loop would still flood it, so updates
# closer together than this are dropped. Stage boundaries are seconds to minutes
# apart, so nothing a caller would see is lost.
_MIN_PROGRESS_INTERVAL_SEC = 0.5


class RunAbandoned(Exception):
    """Raised into a run's thread when nobody is waiting for it any more."""


def runtime_exceeded(max_runtime_sec: float) -> JobError:
    """The error recorded for a run that passed its ceiling, on either path."""
    return JobError(
        code="runtime_exceeded",
        message=(
            f"The run exceeded its {max_runtime_sec:.0f}s ceiling and was abandoned. "
            "Retrying is safe; a smaller export, or include_english=false, will "
            "finish sooner."
        ),
    )


class ProgressReporter:
    """The callback the pipeline calls, bridged onto the event loop.

    The orchestrator's ``progress_callback`` is invoked from the worker thread the
    pipeline runs in. It cannot touch the job store directly — that is guarded by an
    ``asyncio.Lock`` belonging to another loop — so each update is scheduled onto the
    loop with ``run_coroutine_threadsafe`` and not waited on. A progress update is
    advisory; blocking a pipeline stage on it would be the tail wagging the dog.

    It is also how an abandoned run is stopped. Timing out or cancelling the
    coroutine cannot stop the thread the stages run on — Python has no way to kill
    one — so the run would carry on spending tokens on a result nobody will read.
    Once ``abandon()`` is called, the next progress report raises ``RunAbandoned``
    in that thread, which ends the run at the next stage boundary.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        publish: Callable[[float, str | None, str | None], Awaitable[None]],
    ) -> None:
        self._loop = loop
        self._publish = publish
        self._last_at = 0.0
        self._abandoned = False

    def abandon(self) -> None:
        """Stop the run at its next progress report. Safe to call more than once."""
        self._abandoned = True

    def __call__(
        self, progress: float, message_ar: str | None = None, message_en: str | None = None
    ) -> None:
        if self._abandoned:
            raise RunAbandoned("The run was abandoned; stopping at a stage boundary.")
        now = self._loop.time() if self._loop.is_running() else 0.0
        if now and (now - self._last_at) < _MIN_PROGRESS_INTERVAL_SEC:
            return
        self._last_at = now
        try:
            asyncio.run_coroutine_threadsafe(
                self._publish(progress, message_ar, message_en), self._loop
            )
        except RuntimeError:
            # The loop is closing — the run is being torn down anyway, and a lost
            # progress update is not worth raising into a pipeline stage.
            logger.debug("Dropped a progress update: the event loop is closing.")


class JobRunner:
    """Runs accepted jobs off the request path and keeps the store up to date."""

    def __init__(
        self,
        store: JobStore,
        max_concurrent: int = 2,
        max_runtime_sec: float = 3_600.0,
    ) -> None:
        self._store = store
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_runtime_sec = max_runtime_sec
        self._tasks: set[asyncio.Task] = set()

    def submit(
        self,
        job_id: str,
        run: Callable[[Callable[..., None]], Awaitable[object]],
    ) -> None:
        """Start a job and return immediately.

        ``run`` is handed the progress callback and returns the finished bundle. It is
        a closure over the request rather than the request itself, so this class knows
        nothing about what a inquiries run contains.
        """
        task = asyncio.create_task(self._execute(job_id, run), name=f"job:{job_id}")
        # Held in a set because asyncio keeps only a weak reference to a running task:
        # without this the garbage collector can cancel a job mid-run.
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self, timeout: float = 10.0) -> None:
        """Cancel running jobs and wait briefly for them to record that they stopped.

        Called from the app's lifespan on the way down. The wait is short and bounded:
        the point is to leave a terminal state in the store where possible, not to let
        a wedged run hold up the worker's exit.
        """
        if not self._tasks:
            return
        logger.info("Cancelling %d running job(s) on shutdown.", len(self._tasks))
        for task in list(self._tasks):
            task.cancel()
        await asyncio.wait(list(self._tasks), timeout=timeout)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _execute(
        self,
        job_id: str,
        run: Callable[[Callable[..., None]], Awaitable[object]],
    ) -> None:
        async with self._semaphore:
            try:
                state = await self._store.get(job_id)
            except JobNotFound:
                # Purged between acceptance and its turn to run. Nothing to report to.
                logger.warning("Job %s vanished before it started; dropping it.", job_id)
                return

            state.status = JobStatus.RUNNING
            state.started_at = datetime.now(timezone.utc)
            state.message = "Starting the pipeline."
            await self._store.update(state)

            reporter = ProgressReporter(
                asyncio.get_running_loop(), self._publisher(job_id)
            )

            try:
                result = await asyncio.wait_for(
                    run(reporter), timeout=self._max_runtime_sec
                )
            except asyncio.CancelledError:
                await self._finish(
                    job_id,
                    JobStatus.CANCELLED,
                    error=JobError(
                        code="cancelled",
                        message=(
                            "The run was cancelled, usually because the worker was "
                            "shutting down. Retrying is safe."
                        ),
                    ),
                )
                raise
            except asyncio.TimeoutError:
                logger.error(
                    "[%s] Abandoned after %.0fs.", job_id, self._max_runtime_sec
                )
                await self._finish(
                    job_id,
                    JobStatus.FAILED,
                    error=runtime_exceeded(self._max_runtime_sec),
                )
            except Exception as exc:
                # The message is the exception's only where it was raised deliberately
                # by the pipeline; anything else is summarised. An unhandled failure
                # can carry a fragment of the caller's data, and this is readable over
                # the wire. The traceback goes to the log.
                logger.exception("[%s] Run failed: %s", job_id, type(exc).__name__)
                await self._finish(
                    job_id, JobStatus.FAILED, error=_classify(exc)
                )
            else:
                await self._finish(job_id, JobStatus.SUCCEEDED, result=result)
            finally:
                reporter.abandon()

    def _publisher(self, job_id: str):
        """A coroutine that writes one progress update, bound to this job."""

        async def publish(
            progress: float, message_ar: str | None, message_en: str | None
        ) -> None:
            try:
                state = await self._store.get(job_id)
            except JobNotFound:
                return
            if state.status is not JobStatus.RUNNING:
                # A late update from a thread belonging to a run that has already
                # finished or been cancelled. Applying it would move a terminal job.
                return
            state.progress = max(0.0, min(1.0, float(progress)))
            # The English message is the operator-facing one; the Arabic is for a UI
            # that wants it and can read it off the pipeline itself.
            state.message = message_en or message_ar or state.message
            state.stage = _stage_from_message(message_en) or state.stage
            await self._store.update(state)

        return publish

    async def _finish(
        self,
        job_id: str,
        status: JobStatus,
        result: object | None = None,
        error: JobError | None = None,
    ) -> None:
        try:
            state = await self._store.get(job_id)
        except JobNotFound:
            logger.warning("Job %s vanished before it could be finished.", job_id)
            return
        state.status = status
        state.finished_at = datetime.now(timezone.utc)
        state.stage = None
        state.error = error
        if result is not None:
            state.result = result  # type: ignore[assignment]  — the bundle model
            state.progress = 1.0
            state.message = "Complete."
        elif error is not None:
            state.message = None
        await self._store.update(state)


def _stage_from_message(message: str | None) -> str | None:
    """Pull 'stage3' out of 'Stage 3: AI Classification', or return None.

    The orchestrator's progress messages are the only place the current stage is
    named, and they are human text rather than a field. Parsing them is a compromise,
    not a design — but it is confined to this function, and a message that does not
    match simply leaves the stage as it was.
    """
    if not message:
        return None
    lowered = message.strip().casefold()
    if not lowered.startswith("stage"):
        return None
    rest = lowered[len("stage") :].lstrip(" :")
    digits = ""
    for char in rest:
        if char.isdigit():
            digits += char
        else:
            break
    return f"stage{digits}" if digits else None


def _classify(exc: Exception) -> JobError:
    """Turn a failure into the job's error record.

    ``ValueError`` is the pipeline's own refusal — unusable records, no resolvable
    period — and is the caller's to fix, so it keeps its message. ``StageFailure`` is
    what the entry point raises when a stage reports failure, and carries the stage
    name and its own code: ``upstream_error`` when the gateway was the cause,
    ``stage_failed`` otherwise. Anything else is summarised by type: an unhandled
    exception's text can contain a fragment of the caller's data.
    """
    from ..exceptions import StageFailure

    if isinstance(exc, StageFailure):
        return JobError(code=exc.code, message=str(exc), stage=exc.stage)
    if isinstance(exc, ValueError):
        return JobError(code="unprocessable_records", message=str(exc))
    return JobError(
        code="internal_error",
        message=f"The run failed with an unhandled {type(exc).__name__}.",
    )
