"""
Which job backend to use.

One function, and the only place a backend name is turned into an implementation —
the same shape as ``storage.factory``, and for the same reason. The routes only ever
see the Protocol, so adding a backend moves nothing else.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import get_job_settings
from .base import JobStore, JobStoreError
from .local import LocalJobStore
from .table_storage import TableStorageJobStore

__all__ = ["create_job_store"]


@lru_cache(maxsize=1)
def create_job_store() -> JobStore:
    """Build the process-wide job store from the environment.

    Cached because the local backend *is* the process's job state — building a second
    one would give a poll a store that has never seen the job it is asking about.
    """
    settings = get_job_settings()

    if settings.backend == "local":
        return LocalJobStore(directory=settings.dir, ttl_sec=settings.ttl_sec)

    if settings.backend == "table":
        if not settings.connection_string.strip():
            raise JobStoreError(
                "The 'table' job backend needs NOVEINQ_JOB_CONNECTION_STRING. "
                "Use 'UseDevelopmentStorage=true' against Azurite, or set "
                "NOVEINQ_JOB_BACKEND=local."
            )
        return TableStorageJobStore(
            connection_string=settings.connection_string,
            table_name=settings.table_name,
            ttl_sec=settings.ttl_sec,
        )

    raise JobStoreError(
        f"Unknown job backend {settings.backend!r}. "
        "NOVEINQ_JOB_BACKEND accepts 'local' or 'table'."
    )
