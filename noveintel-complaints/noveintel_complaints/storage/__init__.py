"""
Where finished artefacts go.

A run builds up to five files — the Arabic and English Word reports, their underlying
JSON, and the per-case Excel workbook — and uploads them; the result carries
references, not bytes. This package is the seam that makes the destination swappable:
a filesystem directory today, a blob container once one is provisioned, with no change
to the pipeline or to the contract a caller sees.
"""
from __future__ import annotations

from .base import (
    DOCX_CONTENT_TYPE,
    DocumentStore,
    StorageError,
    build_key,
    slugify,
)
from .factory import create_document_store
from .local import LocalDirectoryStore

__all__ = [
    "DOCX_CONTENT_TYPE",
    "DocumentStore",
    "LocalDirectoryStore",
    "StorageError",
    "build_key",
    "create_document_store",
    "slugify",
]
