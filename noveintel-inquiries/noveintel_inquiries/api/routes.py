"""
The routes.

Five: two that say whether the service works, one that checks a payload cheaply, one
that accepts a run, and one that reports on it.

The work route is the departure from module 01. That service returns a finished report
on the POST, because two model calls fit inside Azure's 230-second response ceiling. A
inquiries run does not — six stages, dozens of sequential calls, minutes on a real export
— so this one records a job, answers ``202`` and hands back an id to poll. The porting
guide's §5.6 says to do exactly this when a run cannot fit in the budget, and
everything else about the service is that guide's shape unchanged.

Because of that, there is no ``http_budget_sec`` and no ``504`` anywhere here: no
request is held open long enough to need one. A run that overruns is bounded by
``NOVEINQ_JOB_MAX_RUNTIME_SEC`` and reported as a failed job, which a caller learns
from a poll rather than from a dropped connection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from ..api.models.enums import JobStatus
from ..config import get_pricing_settings, get_settings, get_storage_settings
from ..jobs import JobNotFound, JobStoreError, save_request
from ..exceptions import MissingInputs
from ..pipeline import check_inputs, generate_report, new_run_id, resolve_period, validate_records
from .deps import (
    ApiSettingsDep,
    DocumentStoreDep,
    JobRunnerDep,
    JobStoreDep,
    require_api_key,
)
from .errors import ApiError, ErrorResponse, missing_inputs_error
from .models import JobAccepted, JobState, GenerateInquiriesReportRequest

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter()

# Roughly how long a run takes per record, from observed runs. Used only to give a
# caller something to pace its polling by — it is stated as an estimate and labelled
# as one on the model, because contention at the gateway moves it by a lot.
_BASE_SECONDS = 150


@router.get(
    "/health",
    tags=["operations"],
    summary="Liveness",
    response_model=dict,
)
async def health() -> dict:
    """Answer if the process is running. Nothing else — no settings, no network.

    Deliberately dependency-free: a liveness probe that fails when the model gateway
    is down would have the host restart a service whose only problem is elsewhere.
    """
    return {"status": "ok"}


@router.get(
    "/ready",
    tags=["operations"],
    summary="Readiness",
    response_model=dict,
    responses={503: {"model": ErrorResponse}},
)
async def ready(
    settings: ApiSettingsDep, store: DocumentStoreDep, jobs: JobStoreDep
) -> dict:
    """Answer whether the service can actually accept a run.

    That means configuration resolves and there is somewhere to record a job. It does
    not mean the gateway is reachable — checking that would cost a model call per
    probe.

    Storage and pricing are reported but neither decides the answer, because neither
    stops a run producing an answer: a broken store costs the artefacts and says so in
    the result's warnings, and missing rates cost the cost figure and likewise say so.
    Reporting both here is what makes them diagnosable from a probe rather than only
    from a run.

    The job store *does* decide it. Without one an accepted run could never be
    reported on, and accepting work we cannot answer for is worse than refusing it —
    which is why ``jobs`` is injected here rather than merely reported.
    """
    try:
        core = get_settings()
    except Exception as exc:  # pydantic-settings raises ValidationError
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "not_configured",
            f"Core42 settings are incomplete: {exc}",
        ) from exc

    try:
        storage = get_storage_settings()
        storage_status = {
            "backend": storage.backend,
            "container": storage.container,
            "available": store is not None,
        }
    except Exception as exc:
        storage_status = {
            "backend": None, "container": None, "available": False, "detail": str(exc),
        }

    try:
        pricing_configured = get_pricing_settings().configured
    except Exception:
        # An unreadable rate is reported the same way as an absent one: uncosted.
        pricing_configured = False

    return {
        "status": "ready",
        "model": core.model,
        "model_fast": core.model_fast or core.model,
        "auth_required": settings.api_key is not None,
        "max_records": settings.max_records,
        "storage": storage_status,
        "jobs": {"available": jobs is not None},
        "pricing_configured": pricing_configured,
    }


@router.post(
    "/v1/inquiries/validate",
    tags=["inquiries"],
    summary="Check a payload without running the analysis",
    response_model=dict,
    dependencies=[Depends(require_api_key)],
    responses={
        400: {"model": ErrorResponse, "description": "The records cannot be analysed"},
        401: {"model": ErrorResponse, "description": "Missing or wrong API key"},
        422: {"model": ErrorResponse, "description": "The body failed validation"},
    },
)
async def validate(inquiries: GenerateInquiriesReportRequest, settings: ApiSettingsDep) -> dict:
    """Parse the payload alone and report what a run would see.

    Milliseconds, no model call and no cost. A 200 means the run will be *accepted*:
    every required input arrived and the period resolves. The response carries the
    parse log — artefact rows, duplicates, the case-type scope, mapped and unmapped
    columns, present-but-empty columns — so a caller sees exactly which cases the
    report will count before it pays for the run.

    Refusals are the same a run would hit: ``422 missing_required_columns`` naming
    every missing column, setting or reference list, and ``400 unprocessable_records``
    when no opening date is readable.
    """
    _reject_oversized(inquiries, settings)
    try:
        return validate_records(inquiries)
    except MissingInputs as exc:
        raise missing_inputs_error(exc) from exc
    except ValueError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "unprocessable_records", str(exc)) from exc


@router.post(
    "/v1/inquiries",
    tags=["inquiries"],
    summary="Start a inquiries analysis",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
    responses={
        400: {"model": ErrorResponse, "description": "The records cannot be analysed"},
        401: {"model": ErrorResponse, "description": "Missing or wrong API key"},
        422: {
            "model": ErrorResponse,
            "description": (
                "The body failed validation. `missing_required_columns` when records "
                "omit a required key; `too_many_records` when the export exceeds the "
                "configured limit; `invalid_request` otherwise."
            ),
        },
        503: {"model": ErrorResponse, "description": "No job store or runner"},
    },
)
async def create_analysis(
    inquiries: GenerateInquiriesReportRequest,
    jobs: JobStoreDep,
    runner: JobRunnerDep,
    store: DocumentStoreDep,
    settings: ApiSettingsDep,
) -> JobAccepted:
    """Accept a run and answer immediately with an id to poll.

    **This does not return a report.** It returns a ``job_id``; poll
    ``GET /v1/jobs/{job_id}`` and read ``result`` once ``status`` is ``succeeded``.
    Expect minutes rather than seconds: the run classifies every case (the rule chain,
    then the model for what the rules cannot settle, and with root-cause extraction a
    root cause per case and the umbrella step), analyses frictions, FAQs and guidebook
    gaps, computes every figure, and writes the narrative in each language.

    ``estimated_seconds`` on the response is a rough figure for pacing a poll loop.
    Polling every 10 to 15 seconds is sensible; polling every second only adds load.

    **``options.include_english=false``** skips the English narrative and document.
    The English report is written natively, not translated, so it costs two model
    calls and a short label translation rather than a second full pass.

    The artefacts are uploaded to storage, not returned here — fetch them from each
    reference's ``url``, or resolve its ``container`` and ``key`` against your own
    storage endpoint. There is no download route: this service does not serve file
    bytes.

    Storing can fail on its own without costing the run. When it does the job still
    succeeds, ``documents`` is partial or empty, and ``warnings`` carries a
    ``document_storage_failed`` entry naming what is missing.

    Send the tenant logo as ``entity.logo_base64``. ``entity.logo_path`` is read from
    the *server's* filesystem, which is almost never what a caller means over HTTP —
    it fails soft, and the cover page simply renders without a logo.
    """
    _reject_oversized(inquiries, settings)
    # Refused now, not as a failed job minutes later: a missing required input and an
    # export with no readable opening date are the caller's to fix before any run.
    try:
        check_inputs(inquiries)
        resolve_period(inquiries)
    except MissingInputs as exc:
        raise missing_inputs_error(exc) from exc
    except ValueError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "unprocessable_records", str(exc)) from exc

    job_id = new_run_id()
    state = JobState(
        job_id=job_id,
        status=JobStatus.QUEUED,
        created_at=datetime.now(timezone.utc),
        progress=0.0,
        message="Queued.",
    )
    await jobs.create(state)

    # A queued run executes in another process, where this request object does not
    # exist — so it is stored for the worker to read back. Done before the message is
    # sent, or a worker could dequeue the job before its input was written.
    #
    # ``submit`` ignores ``run`` for a queue dispatcher; it is built anyway so the
    # in-process path stays a plain closure and neither branch is special-cased here.
    if getattr(runner, "needs_stored_request", False):
        try:
            # exclude_unset, not a full dump: the worker re-parses this, and a full
            # dump writes out every default — so a brand the caller never sent would
            # come back looking explicitly set, and the report would be repainted in
            # the NoveAI palette instead of its own design. What the caller sent, and
            # only that, is what must survive the round trip.
            await save_request(store, job_id, inquiries.model_dump_json(exclude_unset=True))
        except JobStoreError as exc:
            raise ApiError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "not_configured",
                f"The run could not be queued: {exc}",
            ) from exc

    async def run(progress) -> object:
        return await generate_report(
            inquiries, store=store, progress=progress, run_id=job_id
        )

    try:
        runner.submit(job_id, run)
    except JobStoreError as exc:
        # The job row says 'queued' but nothing will ever pick it up, so this has to
        # surface now rather than leaving the caller polling forever.
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "not_configured",
            f"The run was accepted but could not be dispatched: {exc}",
        ) from exc

    logger.info(
        "[%s] Accepted a run: %d records, english=%s.",
        job_id, len(inquiries.records), inquiries.options.include_english,
    )

    return JobAccepted(
        job_id=job_id,
        status=JobStatus.QUEUED,
        poll_url=f"/v1/jobs/{job_id}",
        created_at=state.created_at,
        estimated_seconds=_estimate(inquiries),
    )


@router.get(
    "/v1/jobs/{job_id}",
    tags=["jobs"],
    summary="Poll a run",
    response_model=JobState,
    dependencies=[Depends(require_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "Missing or wrong API key"},
        404: {"model": ErrorResponse, "description": "No such job, or it has expired"},
    },
)
async def get_job(job_id: str, jobs: JobStoreDep) -> JobState:
    """Report where a run has got to, and its result once it is finished.

    ``queued`` and ``running`` mean poll again. ``succeeded``, ``failed`` and
    ``cancelled`` are terminal — the job will not change again, and a further poll
    tells you nothing new.

    On ``succeeded``, ``result`` is the full bundle: the metrics, the chart specs, the
    report as data in each language, and references to every stored artefact. On
    ``failed``, ``error`` says what went wrong and which stage it was in.

    A 404 means either that there is no such job or that it has passed its TTL and
    been dropped. The two are deliberately not distinguished — telling them apart
    would mean keeping expired ids forever.

    **Jobs are held per worker.** With the local job backend a poll only finds a job
    on the instance that accepted it, so a multi-instance deployment needs sticky
    routing or a shared job store. The README says what to use instead.
    """
    try:
        return await jobs.get(job_id)
    except JobNotFound as exc:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "job_not_found",
            f"No job {job_id!r}. It was never accepted here, or it has expired.",
        ) from exc


def _reject_oversized(request: GenerateInquiriesReportRequest, settings: ApiSettingsDep) -> None:
    """Refuse an export larger than this deployment is configured to handle.

    Rejected up front rather than accepted into a job that would run for hours and
    then be killed by the runtime ceiling. The limit is about the worker's memory —
    the whole export is held in a dataframe — so raising it means checking the worker
    has the room.
    """
    if len(request.records) > settings.max_records:
        raise ApiError(
            422,
            "too_many_records",
            f"{len(request.records)} records exceeds this service's limit of "
            f"{settings.max_records}. Split the export by period, or raise "
            "NOVEINQ_MAX_RECORDS if the worker has the memory for it.",
            detail={
                "records": len(request.records),
                "max_records": settings.max_records,
            },
        )


def _estimate(request: GenerateInquiriesReportRequest) -> int | None:
    """A rough runtime, for pacing a poll loop. Never a promise.

    Classification dominates: roughly four cases in five go to the model in batches
    of 20, five at a time; root-cause extraction sends every case and adds the
    umbrella step.
    """
    count = len(request.records)
    if not count:
        return None
    per_case = 0.45 if request.settings.root_cause_extraction else 0.25
    seconds = _BASE_SECONDS + count * per_case
    if not request.options.include_english:
        seconds -= 30
    return int(seconds)
