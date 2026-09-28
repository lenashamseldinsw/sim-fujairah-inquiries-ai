"""
Azure Functions wrapper.

The service is the FastAPI app; this puts it on a platform and supplies the two
things the platform can do that the app cannot: deliver a queue message, and redeliver
one whose handler died.

**Everything Azure-specific is in this file.** Nothing under ``noveintel_inquiries/`` imports
``azure.*`` — a test enforces it by scanning the source — so deleting this file and
``host.json`` leaves a complete uvicorn deployment.

Three things are easy to get wrong:

* ``host.json`` must set ``routePrefix`` to an empty string. The default prefixes
  every route with ``/api``, which FastAPI knows nothing about, so every request
  would 404.
* ``AuthLevel.FUNCTION`` makes the platform check a function key before a request
  reaches the app, which is why ``NOVEINQ_API_KEY`` is normally left unset here.
  Setting both simply means a caller presents two keys.
* The HTTP function and the queue function must agree about where jobs live. Both
  read ``NOVEINQ_JOB_*``, so set ``NOVEINQ_JOB_BACKEND=table`` — with ``local``
  the queue worker writes to its own process memory and the HTTP instance serving
  the poll never sees it.

## How a durable run works

    POST /v1/<flow>   the HTTP function writes the job to Table Storage, stores the
                      request in the document store, enqueues the job id, returns 202
    queue trigger     run_analysis_job picks the message up and calls execute_job,
                      which rebuilds the request and runs all six stages
    GET /v1/jobs/{id} any instance reads the job row and reports progress or the result

A handler that dies does not acknowledge its message, so the platform redelivers it
and another worker starts the run again *from the beginning* — the stages are not
checkpointed, and resuming half a pipeline would produce a report whose figures came
from two different runs. After ``maxDequeueCount`` attempts the message lands on the
poison queue, where ``run_analysis_job_poison`` marks the job failed so nobody is left
polling a run that will never finish.

Set ``functionTimeout`` in ``host.json`` above the longest run you expect; the 230s
HTTP ceiling does not apply to a queue trigger, which is the whole point.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import azure.functions as func

from noveintel_inquiries.api.app import app as fastapi_app
from noveintel_inquiries.api.models import GenerateInquiriesReportRequest
from noveintel_inquiries.config import get_job_settings
from noveintel_inquiries.jobs import (
    JobStoreError,
    QueueDispatcher,
    QueueSender,
    create_job_store,
    execute_job,
    fail_job,
)
from noveintel_inquiries.api.models.jobs import JobError
from noveintel_inquiries.storage import create_document_store

logger = logging.getLogger(__name__)

app = func.FunctionApp()

_settings = get_job_settings()
QUEUE_NAME = _settings.queue_name
POISON_QUEUE = f"{_settings.queue_name}-poison"
# The Functions bindings name an *app setting*, not a value, so the connection string
# is referenced by the variable the deployment sets.
CONNECTION_SETTING = "NOVEINQ_JOB_CONNECTION_STRING"


class _AzureQueueSender(QueueSender):
    """Puts a message on a Storage queue.

    Lives here rather than in the package because it is the one part of the job layer
    that needs the Azure SDK. ``QueueDispatcher`` takes it as a collaborator, so the
    package stays SDK-free and this stays five lines of glue.
    """

    def __init__(self, connection_string: str, queue_name: str) -> None:
        from azure.storage.queue import QueueClient, TextBase64EncodePolicy

        # Base64, because the Functions queue trigger expects it by default and a
        # plain-text message is delivered as an unreadable blob otherwise.
        self._client = QueueClient.from_connection_string(
            connection_string, queue_name,
            message_encode_policy=TextBase64EncodePolicy(),
        )
        try:
            self._client.create_queue()
        except Exception:
            # Already there, which is the normal case after the first deployment.
            pass

    def send(self, message: str) -> None:
        self._client.send_message(message)


@app.function_name("http_app")
@app.route(route="{*route}", auth_level=func.AuthLevel.FUNCTION)
async def http_app(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Serve the FastAPI app, with the queue dispatcher injected on first use.

    Injected here rather than in the app's lifespan because building it needs the
    Azure SDK — see the module docstring. The app starts with an in-process runner and
    this replaces it, the same way a real document-store backend would be injected.
    """
    _ensure_dispatcher()
    return await func.AsgiMiddleware(fastapi_app).handle_async(req, context)


def _ensure_dispatcher() -> None:
    """Swap the in-process runner for a queue dispatcher, once, if configured."""
    state = fastapi_app.state
    if getattr(state, "_dispatcher_installed", False):
        return
    state._dispatcher_installed = True

    settings = get_job_settings()
    if settings.dispatch != "queue":
        return

    connection = settings.connection_string or os.environ.get(CONNECTION_SETTING, "")
    if not connection.strip():
        logger.error(
            "Dispatch is 'queue' but %s is empty; runs will execute in this worker "
            "and will not survive a restart.", CONNECTION_SETTING,
        )
        return

    try:
        state.job_runner = QueueDispatcher(_AzureQueueSender(connection, QUEUE_NAME))
        logger.info("Runs will be dispatched to the %r queue.", QUEUE_NAME)
    except Exception as exc:
        logger.error("Could not build the queue dispatcher: %s. Staying in-process.", exc)


@app.function_name("run_analysis_job")
@app.queue_trigger(
    arg_name="msg", queue_name=QUEUE_NAME, connection=CONNECTION_SETTING
)
def run_analysis_job(msg: func.QueueMessage) -> None:
    """Run one queued analysis to completion.

    Synchronous by signature and running its own loop inside, because the Functions
    Python worker gives an async queue trigger no long-lived loop of its own to share
    with the HTTP app.

    **Raises only when the outcome could not be recorded.** The host treats an
    exception as a failed delivery and redelivers, which is right when the job store
    was unreachable and wrong for a run that genuinely failed — retrying a stage-5
    failure would just fail four more times and then poison-queue a job already
    correctly marked failed. ``execute_job`` records those and returns normally.
    """
    job_id = _job_id(msg)
    if job_id is None:
        return

    logger.info("[%s] Dequeued.", job_id)
    asyncio.run(
        execute_job(
            job_id,
            jobs=create_job_store(),
            store=_document_store(),
            request_type=GenerateInquiriesReportRequest,
        )
    )


@app.function_name("run_analysis_job_poison")
@app.queue_trigger(
    arg_name="msg", queue_name=POISON_QUEUE, connection=CONNECTION_SETTING
)
def run_analysis_job_poison(msg: func.QueueMessage) -> None:
    """Mark a job failed after its message exhausted every delivery attempt.

    Without this, a run that dies the same way every time leaves a caller polling a
    job stuck at ``running`` forever — the one outcome worse than a failure.
    """
    job_id = _job_id(msg)
    if job_id is None:
        return

    logger.error("[%s] Poison-queued; recording the job as failed.", job_id)
    asyncio.run(
        fail_job(
            create_job_store(),
            job_id,
            JobError(
                code="delivery_failed",
                message=(
                    "The run could not be completed after several attempts and was "
                    "abandoned. Retrying is safe; check the worker logs for this job "
                    "id to see why it kept failing."
                ),
            ),
        )
    )


def _job_id(msg: func.QueueMessage) -> str | None:
    """The job id from a queue message, or None if the message is unusable.

    A malformed message is logged and swallowed rather than raised on: raising would
    have the host redeliver it until it poison-queues, and no number of retries will
    make a message parse.
    """
    try:
        payload = json.loads(msg.get_body().decode("utf-8"))
        job_id = payload["job_id"]
    except Exception as exc:
        logger.error("Discarding an unreadable queue message: %s", exc)
        return None
    if not isinstance(job_id, str) or not job_id.isalnum():
        logger.error("Discarding a message with a bad job id: %r", job_id)
        return None
    return job_id


def _document_store():
    """The document store, or None — a run without one still produces an analysis."""
    try:
        return create_document_store()
    except Exception as exc:
        logger.error("No document store: %s", exc)
        return None
