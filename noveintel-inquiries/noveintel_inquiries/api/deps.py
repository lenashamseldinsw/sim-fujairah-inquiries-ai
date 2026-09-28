"""
What the routes are handed.

Every dependency here exists to be overridden: the stores so tests can write to a
temporary directory instead of the repository, the runner so a test can drive a job
to completion without a model gateway, the settings so a test can change a limit
without touching the environment.

The shape differs from module 01's in one way worth naming. That service builds a
*narrative client* per request, because the client counts one run's tokens and a
shared one would add concurrent runs together. Here the pipeline owns its own Core42
client — a module-level singleton in ``core42.client``, with a process-wide in-flight
cap — and accounting is per run through the token ledger the pipeline resets at the
start of each. So there is no per-request client to inject; what the routes need is
the job layer.
"""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, Request, status

from ..config import ApiSettings, get_api_settings
from ..jobs import JobRunner, JobStore
from ..storage import DocumentStore
from .errors import ApiError

__all__ = [
    "ApiSettingsDep",
    "DocumentStoreDep",
    "JobRunnerDep",
    "JobStoreDep",
    "get_document_store",
    "get_job_runner",
    "get_job_store",
    "require_api_key",
]


def get_document_store(request: Request) -> DocumentStore | None:
    """Return the process-wide document store built at startup, or ``None``.

    Absence returns ``None`` rather than raising, and deliberately so. Without a
    store there is still a full set of metrics, chart specs and report data — so the
    run proceeds and records a warning against the artefacts it could not store.
    """
    return getattr(request.app.state, "document_store", None)


def get_job_store(request: Request) -> JobStore:
    """Return the process-wide job store built at startup.

    Unlike the document store, absence here *is* fatal: without somewhere to record a
    job there is nothing to hand the caller and nothing for them to poll. Answering
    503 is the honest response, rather than accepting work that can never be reported
    on.
    """
    store = getattr(request.app.state, "job_store", None)
    if store is None:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "not_configured",
            "The job store is unavailable, so no run can be accepted. Check "
            "the service log from startup and the job directory's permissions.",
        )
    return store


def get_job_runner(request: Request) -> JobRunner:
    """Return the process-wide job runner built at startup.

    Fatal in its absence for the same reason as the store: without it an accepted job
    would sit in ``queued`` forever, which is worse than refusing the work.
    """
    runner = getattr(request.app.state, "job_runner", None)
    if runner is None:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "not_configured",
            "The job runner is unavailable, so no run can be accepted. Check the "
            "service log from startup.",
        )
    return runner


DocumentStoreDep = Annotated[DocumentStore | None, Depends(get_document_store)]
JobStoreDep = Annotated[JobStore, Depends(get_job_store)]
JobRunnerDep = Annotated[JobRunner, Depends(get_job_runner)]
ApiSettingsDep = Annotated[ApiSettings, Depends(get_api_settings)]


def require_api_key(
    settings: ApiSettingsDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Enforce the app-level API key, when one is configured.

    Unset means unenforced, which is the right default for the two places this runs
    behind something else: Azure Functions checks its own function key before a
    request reaches the app, and an on-prem deployment usually sits behind the
    client's gateway. Set it anywhere the app is directly reachable.

    ``compare_digest`` rather than ``==`` so the comparison does not leak the key's
    length or its matching prefix through timing.
    """
    configured = settings.api_key
    if not configured:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, configured):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "unauthorized",
            "A valid X-API-Key header is required.",
        )
