"""
``DocumentRef`` — where a finished artefact went, not the artefact itself.

A run uploads each document it produces to storage and hands back one of these. The
caller then fetches the bytes from storage directly; this service never serves file
content, which is why there is no download route anywhere in the API.

Two ways to resolve a reference are offered deliberately, because the two deployments
this has to serve want different ones. A hosted caller takes ``url`` and fetches it.
An on-prem caller that already holds its own storage endpoint and credentials — and
has no reason to trust a URL we minted — takes ``container`` and ``key`` and resolves
them itself. Both describe the same object.

Unlike module 01, a run here produces two *kinds* of artefact: the Word report and the
per-case Excel workbook. ``DocumentRef`` describes both; which is which is the key it
is filed under in the bundle, not a field on the reference.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

__all__ = ["DOCX_CONTENT_TYPE", "XLSX_CONTENT_TYPE", "JSON_CONTENT_TYPE", "DocumentRef"]

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
JSON_CONTENT_TYPE = "application/json"


class DocumentRef(BaseModel):
    """A stored document, addressed two ways."""

    container: str = Field(
        description=(
            "The container the object lives in — a blob container, a bucket, or the "
            "top-level directory of a filesystem store."
        )
    )
    key: str = Field(
        description=(
            "Path of the object within its container. Stable and unique per run; "
            "combine with the container to resolve the object against your own "
            "storage endpoint."
        )
    )
    filename: str = Field(
        description=(
            "Suggested filename when saving the document, without any path. The last "
            "segment of the key."
        )
    )
    content_type: str = Field(
        description="MIME type of the stored object — the .docx, .xlsx or JSON type."
    )
    size_bytes: int = Field(
        ge=0, description="Size of the stored object, so a caller can show progress."
    )
    url: str = Field(
        description=(
            "A URL that resolves to the object. Its scheme depends on the backend: an "
            "https URL from a blob store, a file: URI from the local filesystem store "
            "used until real storage is provisioned. Treat it as opaque."
        )
    )
    expires_at: datetime | None = Field(
        default=None,
        description=(
            "When ``url`` stops working, for a backend that mints time-limited links "
            "such as a SAS token or a presigned URL. Null means the URL does not "
            "expire — which is the case for the local filesystem store."
        ),
    )
