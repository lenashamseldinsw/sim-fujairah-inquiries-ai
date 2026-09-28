"""
Handing a run to a queue instead of running it here.

``JobRunner`` executes a run on this worker's event loop. That is right for local
development and for a single always-on instance, and wrong for anything else: the run
dies with the worker, and nothing redelivers it.

``QueueDispatcher`` is the same seam with the work sent elsewhere. It records nothing
about how the message is delivered — that is the host's business — and it satisfies
the same two-method shape the routes already depend on, so swapping one for the other
changes no route and no test.

**The pairing that makes a run durable** is this class plus a queue trigger:

    POST /v1/<flow>  →  job written to Table Storage, message enqueued  →  202
                        the Functions host delivers the message to a
                        queue-triggered function, which calls generate_report
                        and writes the result back to the same job row

A handler that dies mid-run does not acknowledge its message, so the queue redelivers
it and another worker picks the run up from the start. After ``maxDequeueCount``
attempts the message lands on the poison queue, and the host's poison handler marks
the job failed rather than leaving a caller polling forever. Neither of those is
possible with an in-process runner, and both are why this exists.

**A redelivered run starts over; it does not resume.** Resuming half a pipeline would
stitch one process's stage 4 onto another's stage 5 and produce a report whose figures
came from two different runs. The stages are not checkpointed and should not pretend
to be.
"""
from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from .base import JobStoreError

__all__ = ["QueueDispatcher", "QueueSender"]

logger = logging.getLogger(__name__)

# A queue message caps at 64 KiB, and a real export is far larger — so the message
# carries the job id alone and the request is read from wherever the route put it.
# Inlining the payload would cap a run at a few hundred records.
MAX_MESSAGE_BYTES = 48_000


class QueueSender:
    """What a dispatcher needs from a queue: somewhere to put one message.

    A Protocol in spirit, a class in practice so the Azure implementation can be
    injected by ``function_app.py`` without this module knowing the SDK exists —
    the same arrangement ``DocumentStore`` uses, and for the same reason: nothing
    under the package may import ``azure.*``.
    """

    def send(self, message: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class QueueDispatcher:
    """A ``JobRunner``-shaped object that enqueues rather than executes.

    It presents ``submit`` and ``shutdown``, which is all the routes use, so
    ``deps.get_job_runner`` can hand back either this or a ``JobRunner`` and nothing
    downstream can tell the difference.
    """

    # Read by the work route: a queued run executes elsewhere, so the request has
    # to be persisted for the worker. ``JobRunner`` does not set this, because its
    # closure already holds the request.
    needs_stored_request = True

    def __init__(self, sender: QueueSender) -> None:
        self._sender = sender

    def submit(
        self,
        job_id: str,
        run: Callable[[Callable[..., None]], Awaitable[object]],
    ) -> None:
        """Enqueue the job. ``run`` is deliberately ignored.

        The closure cannot cross a process boundary, so what is sent is the job id and
        the worker on the other side rebuilds the run from the stored request. That
        asymmetry is why this is a separate class rather than a flag on ``JobRunner``:
        pretending a callable could be queued would be a lie that only failed in
        production.
        """
        message = json.dumps({"job_id": job_id, "v": 1}, separators=(",", ":"))
        if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:  # pragma: no cover
            raise JobStoreError("The queue message is too large; this should not happen.")
        try:
            self._sender.send(message)
        except Exception as exc:
            # The job row already exists and says 'queued'. If the enqueue fails the
            # caller would poll it forever, so the failure has to surface now, as a
            # 5xx on the POST, rather than as a job that never starts.
            raise JobStoreError(
                f"Could not enqueue job {job_id!r}: {exc}. The run was not started."
            ) from exc
        logger.info("[%s] Enqueued for a worker to pick up.", job_id)

    async def shutdown(self, timeout: float = 10.0) -> None:
        """Nothing to cancel: this worker is not running anything.

        Present so the app's lifespan can call it without caring which of the two it
        has.
        """
        return None
