"""
The job seam.

A inquiries run is minutes of sequential model calls and cannot be held open on an HTTP
response, so the work route accepts a job and the caller polls. This package is what
holds that job, and it is a ``Protocol`` for the same reason ``storage`` is: the
in-process implementation is honest for one worker, a real deployment wants something
durable, and neither should be able to see the other.

Records here are ``JobState`` — the contract model — rather than a private shape, so
a poll is a read and a serialisation, with nothing in between to disagree about.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models.jobs import JobState

__all__ = ["JobNotFound", "JobStore", "JobStoreError"]


class JobStoreError(Exception):
    """A backend could not record or retrieve a job.

    Every implementation wraps its own failures in this, so the API layer has one
    thing to catch and callers never see a provider's exception type.
    """


class JobNotFound(JobStoreError):
    """No job with that id, or it has passed its TTL and been dropped.

    The two are deliberately not distinguished. A caller polling an id that has
    expired and a caller polling an id that never existed both need the same answer —
    404 — and telling them apart would mean keeping the ids of expired jobs forever,
    which is the thing the TTL exists to avoid.
    """


@runtime_checkable
class JobStore(Protocol):
    """Somewhere job state lives between the request that started it and the poll."""

    async def create(self, state: JobState) -> None:
        """Record a new job. Raises ``JobStoreError`` if it could not be written."""
        ...

    async def get(self, job_id: str) -> JobState:
        """Return the job's current state.

        Raises ``JobNotFound`` when there is no such job, ``JobStoreError`` for any
        other failure.
        """
        ...

    async def update(self, state: JobState) -> None:
        """Replace a job's state wholesale.

        Wholesale rather than field by field because the caller already holds the
        state it read, and a partial update across two workers would interleave into
        a record neither of them wrote.
        """
        ...

    async def purge_expired(self) -> int:
        """Drop finished jobs past their TTL. Returns how many were removed."""
        ...
