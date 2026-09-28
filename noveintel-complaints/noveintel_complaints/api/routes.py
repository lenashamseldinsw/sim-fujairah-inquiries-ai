"""
The routes.

Five: two that say whether the service works, one that checks a payload cheaply, one
that accepts a run, and one that reports on it.

The work route is the departure from module 01. That service returns a finished report
on the POST, because two model calls fit inside Azure's 230-second response ceiling. A
complaints run does not — six stages, dozens of sequential calls, minutes on a real export
— so this one records a job, answers ``202`` and hands back an id to poll. The porting
guide's §5.6 says to do exactly this when a run cannot fit in the budget, and
everything else about the service is that guide's shape unchanged.

Because of that, there is no ``http_budget_sec`` and no ``504`` anywhere here: no
request is held open long enough to need one. A run that overruns is bounded by
``NOVECOMP_JOB_MAX_RUNTIME_SEC`` and reported as a failed job, which a caller learns
from a poll rather than from a dropped connection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from ..api.models.enums import JobStatus
from ..config import get_pricing_settings, get_settings, get_storage_settings
from ..jobs import JobNotFound
from ..pipeline import generate_report, new_run_id, validate_records
from .deps import (
    ApiSettingsDep,
    DocumentStoreDep,
    JobRunnerDep,
    JobStoreDep,
    require_api_key,
)
from .errors import ApiError, ErrorResponse
from .models import JobAccepted, JobState, GenerateComplaintsReportRequest

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter()

# Roughly how long a run takes per record, from observed runs. Used only to give a
# caller something to pace its polling by — it is stated as an estimate and labelled
# as one on the model, because contention at the gateway moves it by a lot.
_SECONDS_PER_RECORD = 0.35
_BASE_SECONDS = 90


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
    "/v1/complaints/validate",
    tags=["complaints"],
    summary="Check a payload without running the analysis",
    response_model=dict,
    dependencies=[Depends(require_api_key)],
    responses={
        400: {"model": ErrorResponse, "description": "The records cannot be analysed"},
        401: {"model": ErrorResponse, "description": "Missing or wrong API key"},
        422: {"model": ErrorResponse, "description": "The body failed validation"},
    },
)
async def validate(complaints: GenerateComplaintsReportRequest, settings: ApiSettingsDep) -> dict:
    """Run the schema validator alone and report what it found.

    Milliseconds, no model call and no cost. It exists because the work route is
    asynchronous: without this the only way to discover a missing column is to start a
    run and poll until it fails, which is a slow way to find a typo.

    A 200 here means the analysis will be *accepted* — the columns are present and the
    period resolves. It is not a promise that the run will succeed: stages 3 to 6
    depend on the model gateway, and no amount of validation anticipates that.

    ``period`` is null with ``period_error`` set when no record carried a readable
    date. The run is still accepted in that case; the report simply carries a weaker
    period label.
    """
    _reject_oversized(complaints, settings)
    try:
        return validate_records(complaints)
    except ValueError as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "unprocessable_records", str(exc)
        ) from exc


@router.post(
    "/v1/complaints",
    tags=["complaints"],
    summary="Start a complaints analysis",
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
    complaints: GenerateComplaintsReportRequest,
    jobs: JobStoreDep,
    runner: JobRunnerDep,
    store: DocumentStoreDep,
    settings: ApiSettingsDep,
) -> JobAccepted:
    """Accept a run and answer immediately with an id to poll.

    **This does not return a report.** It returns a ``job_id``; poll
    ``GET /v1/jobs/{job_id}`` and read ``result`` once ``status`` is ``succeeded``.
    Expect minutes rather than seconds: the pipeline classifies every case, analyses
    patterns and gaps, then writes nine report sections and — unless you turn it off —
    translates all of them.

    ``estimated_seconds`` on the response is a rough figure for pacing a poll loop.
    Polling every 10 to 15 seconds is sensible; polling every second only adds load.

    **``options.include_english=false`` roughly halves the run.** The English
    translation is a full pass over all nine sections and is the single largest block
    of tokens in a run. Turn it off unless an English document is actually wanted.

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
    _reject_oversized(complaints, settings)

    job_id = new_run_id()
    state = JobState(
        job_id=job_id,
        status=JobStatus.QUEUED,
        created_at=datetime.now(timezone.utc),
        progress=0.0,
        message="Queued.",
    )
    await jobs.create(state)

    async def run(progress) -> object:
        return await generate_report(
            complaints, store=store, progress=progress, run_id=job_id
        )

    runner.submit(job_id, run)

    logger.info(
        "[%s] Accepted a run: %d records, english=%s.",
        job_id, len(complaints.records), complaints.options.include_english,
    )

    return JobAccepted(
        job_id=job_id,
        status=JobStatus.QUEUED,
        poll_url=f"/v1/jobs/{job_id}",
        created_at=state.created_at,
        estimated_seconds=_estimate(complaints),
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


def _reject_oversized(request: GenerateComplaintsReportRequest, settings: ApiSettingsDep) -> None:
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
            "NOVECOMP_MAX_RECORDS if the worker has the memory for it.",
            detail={
                "records": len(request.records),
                "max_records": settings.max_records,
            },
        )


def _estimate(request: GenerateComplaintsReportRequest) -> int | None:
    """A rough runtime, for pacing a poll loop. Never a promise."""
    count = len(request.records)
    if not count:
        return None
    seconds = _BASE_SECONDS + count * _SECONDS_PER_RECORD
    if not request.options.include_english:
        # The translation pass is roughly a third of a run's wall clock.
        seconds *= 0.65
    return int(seconds)
