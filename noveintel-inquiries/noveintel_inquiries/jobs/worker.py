"""
Running a job that arrived on a queue.

One function, and it is the whole other half of the queue pairing. ``function_app.py``
hands it a job id and this rebuilds the run from what the route stored: the request
from the document store, the job record from the job store.

It is in the package rather than in the Azure wrapper on purpose. The wrapper should
be the five lines that adapt a trigger to a call; everything about *what a run is*
belongs here, where it can be tested without a Functions host.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from ..api.models.enums import JobStatus
from ..api.models.jobs import JobError, JobState
from ..exceptions import StageFailure
from ..pipeline import generate_report
from ..storage import DocumentStore
from .base import JobNotFound, JobStore, JobStoreError
from .payloads import delete_request, load_request
from .runner import ProgressReporter

__all__ = ["execute_job", "fail_job"]

logger = logging.getLogger(__name__)


def _publisher(jobs: JobStore, job_id: str):
    """A coroutine that writes one progress update for this job.

    The same shape ``JobRunner._publisher`` builds, kept separate rather than shared
    because that one closes over the runner's own store handle and this one does not.
    A late update from a run that has already finished is dropped: applying it would
    move a terminal job back to running.
    """
    from .runner import _stage_from_message

    async def publish(fraction: float, message_ar: str | None,
                      message_en: str | None) -> None:
        try:
            state = await jobs.get(job_id)
        except JobNotFound:
            return
        if state.status is not JobStatus.RUNNING:
            return
        state.progress = max(0.0, min(1.0, float(fraction)))
        state.message = message_en or message_ar or state.message
        state.stage = _stage_from_message(message_en) or state.stage
        await jobs.update(state)

    return publish


async def execute_job(
    job_id: str,
    *,
    jobs: JobStore,
    store: DocumentStore | None,
    request_type: type,
) -> None:
    """Run one queued job to completion and record the outcome.

    ``request_type`` is passed in rather than imported so this module stays the same
    in both services — the only thing that differs between them is which request model
    the stored JSON parses as.

    **Raises on failure to record the outcome, and only then.** The Functions host
    treats an exception as a failed delivery and redelivers the message, which is
    exactly right when the job store was unreachable and wrong for everything else —
    so a failed *run* is recorded and returns normally. Retrying a run that failed
    because stage 5 found no gaps would just fail again, four more times, and then
    poison-queue a job that was already correctly marked failed.
    """
    try:
        state = await jobs.get(job_id)
    except JobNotFound:
        # Purged, or never written. Nothing to report to and nothing to run; swallow
        # it so the message is acknowledged rather than redelivered forever.
        logger.warning("[%s] Dequeued a job that no longer exists; dropping it.", job_id)
        return

    if state.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
        # A redelivery of a message whose run already finished — the handler completed
        # but the acknowledgement was lost. Re-running would spend a second run's
        # tokens to overwrite a good result.
        logger.info("[%s] Already %s; ignoring the redelivery.", job_id, state.status.value)
        return

    state.status = JobStatus.RUNNING
    state.started_at = datetime.now(timezone.utc)
    state.message = "Starting the pipeline."
    await jobs.update(state)

    try:
        body = await load_request(store, job_id)
        request = request_type.model_validate_json(body)
    except (JobStoreError, ValueError) as exc:
        logger.error("[%s] Could not rebuild the run: %s", job_id, exc)
        await fail_job(
            jobs, job_id,
            JobError(
                code="request_unavailable",
                message=(
                    "The stored request for this job could not be read, so the run "
                    f"could not be started: {exc}"
                ),
            ),
            store=store,
        )
        return

    # The pipeline reports stage boundaries from the worker thread it runs on, so the
    # updates are bridged back onto this loop — the same arrangement JobRunner uses,
    # and the reason a caller polling a queued run sees the same progress as a local one.
    reporter = ProgressReporter(
        asyncio.get_running_loop(), _publisher(jobs, job_id)
    )

    try:
        bundle = await generate_report(
            request, store=store, progress=reporter, run_id=job_id
        )
    except StageFailure as exc:
        await fail_job(
            jobs, job_id,
            JobError(code="stage_failed", message=str(exc), stage=exc.stage),
            store=store,
        )
        return
    except ValueError as exc:
        await fail_job(
            jobs, job_id,
            JobError(code="unprocessable_records", message=str(exc)),
            store=store,
        )
        return
    except Exception as exc:
        # The message is the type rather than the text: an unhandled failure can carry
        # a fragment of the caller's data, and this reaches them through a poll.
        logger.exception("[%s] Run failed: %s", job_id, type(exc).__name__)
        await fail_job(
            jobs, job_id,
            JobError(
                code="internal_error",
                message=f"The run failed with an unhandled {type(exc).__name__}.",
            ),
            store=store,
        )
        return

    state = await jobs.get(job_id)
    state.status = JobStatus.SUCCEEDED
    state.finished_at = datetime.now(timezone.utc)
    state.progress = 1.0
    state.stage = None
    state.message = "Complete."
    state.result = bundle
    await jobs.update(state)

    # The export is no longer needed, and it is the caller's customer data.
    await delete_request(store, job_id)
    logger.info("[%s] Queued run complete.", job_id)


async def fail_job(
    jobs: JobStore,
    job_id: str,
    error: JobError,
    store: DocumentStore | None = None,
) -> None:
    """Mark a job failed, whatever state it was in, and drop its stored request.

    Also the poison-queue handler's entry point: a message that exhausted its
    deliveries names a job someone is still polling, and leaving it at ``running``
    forever is the one outcome worse than a failure.

    Pass ``store`` and the run's stored request is deleted once the failure is
    recorded. That request is a full copy of the caller's export; a failed run has no
    more use for it than a successful one, and nothing will ever read it again —
    a failure recorded here is final, the queue does not redeliver it.
    """
    try:
        state = await jobs.get(job_id)
    except JobNotFound:
        logger.warning("[%s] Cannot record a failure: the job is gone.", job_id)
        return
    state.status = JobStatus.FAILED
    state.finished_at = datetime.now(timezone.utc)
    state.stage = None
    state.message = None
    state.error = error
    await jobs.update(state)
    logger.error("[%s] Recorded as failed: %s", job_id, error.code)
    # Only after the failure is safely recorded. Had the update raised, the queue
    # would redeliver — and the retry would need this request.
    if store is not None:
        await delete_request(store, job_id)
