"""
Keeping the request alive between the POST and the worker that runs it.

An in-process runner closes over the request object and needs none of this. A queued
run does: the closure cannot cross a process boundary, and the message that can is
capped at 64 KiB while a real export is megabytes. So the request is written to the
document store when the job is accepted, and read back by whichever worker picks the
message up.

It is filed under a reserved prefix rather than beside the artefacts, because it is
not one — it is the run's *input*, it is customer data, and nothing should list a
tenant's reports and find a payload among them.

Deleted once the run reaches a terminal state. Leaving it would double the storage a
tenant's data occupies and keep a full copy of the export around long after the report
it produced.
"""
from __future__ import annotations

import logging

from ..api.models.documents import JSON_CONTENT_TYPE
from ..storage import DocumentStore, StorageError
from .base import JobStoreError

__all__ = ["PREFIX", "delete_request", "load_request", "save_request"]

logger = logging.getLogger(__name__)

# Reserved. ``build_key`` starts every artefact key with a tenant slug, and a slug is
# lowercase alphanumeric and hyphens — so a leading underscore cannot collide with one.
PREFIX = "_pending"


def _key(job_id: str) -> str:
    if not job_id.isalnum():
        raise JobStoreError(f"Refusing a non-alphanumeric job id: {job_id!r}")
    return f"{PREFIX}/{job_id}.json"


async def save_request(store: DocumentStore | None, job_id: str, body: str) -> None:
    """Persist the request so a worker in another process can run it.

    Raises ``JobStoreError`` when it cannot be stored — and the route must let that
    reach the caller as a failure. A job whose input was never written is one the
    worker will dequeue, fail to load, and mark failed; refusing on the POST is the
    honest answer, and the caller can retry immediately.
    """
    if store is None:
        raise JobStoreError(
            "Queued runs need a document store to hold the request, and none is "
            "configured. Set the storage settings, or run with the in-process "
            "dispatcher."
        )
    try:
        await store.put(_key(job_id), body.encode("utf-8"), JSON_CONTENT_TYPE)
    except StorageError as exc:
        raise JobStoreError(f"Could not store the request for {job_id!r}: {exc}") from exc


async def load_request(store: DocumentStore | None, job_id: str) -> str:
    """Read the request back. Raises ``JobStoreError`` if it is gone."""
    if store is None:
        raise JobStoreError("No document store is configured; the request cannot be read.")
    try:
        return (await store.get(_key(job_id))).decode("utf-8")
    except StorageError as exc:
        raise JobStoreError(
            f"The request for job {job_id!r} could not be read: {exc}. It may have "
            "been cleaned up after the run finished."
        ) from exc


async def delete_request(store: DocumentStore | None, job_id: str) -> None:
    """Drop the stored request. Best effort — never fails a finished run.

    Both shipped backends — ``local`` and ``blob`` — offer a ``delete``, so in
    practice the request is removed. It is still looked up rather than called
    directly because ``DocumentStore`` is a two-method Protocol on purpose: a
    third-party backend without a delete leaves the payload for its storage
    lifecycle policy to age out, rather than failing a run that has already finished.
    """
    if store is None:
        return
    remove = getattr(store, "delete", None)
    if not callable(remove):
        logger.debug(
            "[%s] The document store has no delete; the pending request will age out "
            "under the storage lifecycle policy.", job_id,
        )
        return
    try:
        await remove(_key(job_id))
    except Exception as exc:
        logger.warning("[%s] Could not remove the pending request: %s", job_id, exc)
