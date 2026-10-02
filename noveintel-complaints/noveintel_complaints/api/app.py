"""
The application object, and what has to be true before it serves anything.

``create_app`` is separate from the module-level ``app`` so every test builds its own
instance and overrides its dependencies without touching a shared one. The Azure
wrapper and uvicorn both take the module-level instance.

The lifespan's rule is: **record failures, never raise.** A collaborator that cannot
be built leaves a log line and a ``None`` in ``app.state``, and ``/ready`` reports it.
Raising here turns a missing environment variable into a crash loop, and a crash loop
produces worse diagnostics than a 503 that names the problem.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from ..config import get_api_settings, get_job_settings, get_settings
from ..jobs import JobRunner, create_job_store
from ..storage import create_document_store
from .errors import register_exception_handlers
from .routes import router

__all__ = ["app", "create_app"]

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}

DESCRIPTION = """
Turns a period's شكاوى المتعاملين cases into an analysed report: a six-stage pipeline
classifies every case, finds the patterns and friction points behind them, checks
each against the service guidebook, and writes an Arabic and English report plus a
per-case workbook.

**Runs are asynchronous.** `POST /v1/complaints` answers `202` with a `job_id`; poll
`GET /v1/jobs/{job_id}` until `status` is terminal and read `result`. A run takes
minutes — far past the 230 seconds Azure allows an HTTP response — which is why it is
not returned inline.

Check a payload first with `POST /v1/complaints/validate`: it runs the schema
validator alone, costs nothing, and answers in milliseconds.

Artefacts are uploaded to storage and the result carries references. This service
never serves file bytes, so there is no download route.
""".strip()


def _configure_logging(level_name: str) -> None:
    """Give the service a log handler, unless the host has already given it one.

    Uvicorn leaves the root logger alone, so without this every INFO line the pipeline
    writes is dropped and the service runs silently.

    Skipped when a host has already configured logging: on Azure Functions that
    handler ships records to Application Insights, and replacing it loses them.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    requested = (level_name or "").strip().upper()
    level = requested if requested in _LEVELS else "INFO"
    logging.basicConfig(level=level, format=LOG_FORMAT, stream=sys.stdout)
    root.setLevel(level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the process-wide collaborators, and tear the runner down cleanly."""
    app.state.document_store = None
    app.state.job_store = None
    app.state.job_runner = None

    # Resolved at startup so a missing key shows in the log and on /ready, rather
    # than deep inside a stage minutes into a caller's first run.
    try:
        settings = get_settings()
        logger.info(
            "Core42 settings resolved — model %s, bulk tier %s.",
            settings.model, settings.model_fast or settings.model,
        )
    except Exception as exc:
        logger.error("Starting without usable Core42 settings: %s", exc)

    try:
        app.state.document_store = create_document_store()
    except Exception as exc:
        logger.error("Starting without a document store: %s", exc)

    try:
        job_settings = get_job_settings()
        store = create_job_store()
        # Anything left mid-run by a process that died is failed here rather than
        # resumed — see jobs/local.py. Done before the app serves, so no poll can
        # catch a job in the state the previous process left it in.
        recover = getattr(store, "recover", None)
        if callable(recover):
            recover()
        app.state.job_store = store

        # Where the run executes. A queue dispatcher needs a queue client, which
        # means the Azure SDK, which must not be imported from inside the package.
        # So the host supplies one: ``function_app.py`` puts a factory on
        # ``app.state.job_runner_factory`` before the app starts, and it is called
        # here with the job store. Anywhere else — uvicorn, tests, on-prem — there is
        # no factory and runs execute in-process.
        app.state.job_runner = None
        factory = getattr(app.state, "job_runner_factory", None)
        if job_settings.dispatch == "queue" and callable(factory):
            try:
                app.state.job_runner = factory(store)
            except Exception as exc:
                # Falling back keeps the service usable; the log says runs will now
                # die with this worker instead of being redelivered.
                logger.error(
                    "Could not build the queue dispatcher (%s); runs will execute "
                    "in this worker and will not survive a restart.", exc,
                )
        elif job_settings.dispatch == "queue":
            logger.warning(
                "%s_JOB_DISPATCH=queue, but no queue client was supplied — runs will "
                "execute in-process. On Azure function_app.py supplies one.",
                "NOVECOMP",
            )
        if app.state.job_runner is None:
            app.state.job_runner = JobRunner(
                store,
                max_concurrent=job_settings.max_concurrent,
                max_runtime_sec=job_settings.max_runtime_sec,
            )
        logger.info(
            "Job store ready — backend %s, runs via %s, %d concurrent run(s), "
            "%.0fs ceiling.",
            job_settings.backend,
            type(app.state.job_runner).__name__,
            job_settings.max_concurrent,
            job_settings.max_runtime_sec,
        )
    except Exception as exc:
        # Fatal for the work routes but not for the process: /health still answers,
        # /ready reports it, and an operator gets a running container to look at
        # rather than a restart loop.
        logger.error("Starting without a job store: no run can be accepted. %s", exc)

    try:
        yield
    finally:
        runner = app.state.job_runner
        if runner is not None:
            # Running jobs are cancelled and given a moment to record that they
            # stopped, so a caller polling one gets 'cancelled' rather than a record
            # frozen at 'running' forever.
            await runner.shutdown()


def create_app() -> FastAPI:
    """Build an application instance. Separate from ``app`` so tests can have their own."""
    try:
        _configure_logging(get_api_settings().log_level)
    except Exception:
        # Settings themselves can fail to resolve; that is reported on /ready, and
        # logging the failure needs logging to exist first.
        _configure_logging("INFO")

    app = FastAPI(
        title="NoveIntelligence — Customer Complaints Analytics",
        version="0.1.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    # Bundles are large — the report as data in two languages, plus the metrics — and
    # compress well, being mostly text.
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
