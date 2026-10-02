"""
Which backend to use.

One function, and the only place a backend name is turned into an implementation:
``local`` for an on-prem server with no cloud storage, ``blob`` for Azure. A new
provider is a class plus a branch here; nothing else moves, because callers only ever
see the ``DocumentStore`` Protocol and the references it returns.

Choosing ``local`` never needs an Azure package installed. The blob backend imports
its SDK inside its methods, which is what keeps the rule that nothing under the
package imports ``azure.*`` on import — and what lets one codebase serve both kinds
of deployment.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import get_storage_settings
from .base import DocumentStore, StorageError
from .blob import BlobDocumentStore
from .blob import _sdk as _blob_sdk
from .local import LocalDirectoryStore

__all__ = ["create_document_store"]


@lru_cache(maxsize=1)
def create_document_store() -> DocumentStore:
    """Build the process-wide document store from the environment.

    Cached because a real backend owns a connection pool and an authenticated client,
    and building one per run would re-authenticate on every call.
    """
    settings = get_storage_settings()

    if settings.backend == "local":
        return LocalDirectoryStore(
            root=settings.dir,
            container=settings.container,
            public_base_url=settings.public_base_url,
        )

    if settings.backend == "blob":
        if not settings.connection_string.strip():
            raise StorageError(
                "The 'blob' storage backend needs NOVECOMP_STORAGE_CONNECTION_STRING. "
                "On-prem, with no blob storage, use NOVECOMP_STORAGE_BACKEND=local."
            )
        # Checked here, at startup, rather than on the first upload. Without it a
        # missing SDK would surface minutes into a caller's first run, as an empty
        # ``documents``; this way the startup log says so and /ready reports the
        # store as unavailable before any work is accepted.
        _blob_sdk()
        return BlobDocumentStore(
            connection_string=settings.connection_string,
            container=settings.container,
            sas_ttl_sec=settings.sas_ttl_sec,
        )

    raise StorageError(
        f"Unknown storage backend {settings.backend!r}. "
        "NOVECOMP_STORAGE_BACKEND accepts 'local' or 'blob'."
    )
