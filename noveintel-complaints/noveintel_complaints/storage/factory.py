"""
Which backend to use.

One function, and the only place a backend name is turned into an implementation. A
new provider is a class plus a branch here — and for Azure specifically, not even
that: nothing under ``noveintel_complaints/`` may import ``azure.*``, so the Functions wrapper at the
project root builds its own store and injects it into ``app.state``, bypassing this
entirely. That is the point of the seam.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import get_storage_settings
from .base import DocumentStore, StorageError
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

    raise StorageError(
        f"Unknown storage backend {settings.backend!r}. "
        "NOVECOMP_STORAGE_BACKEND accepts 'local'."
    )
