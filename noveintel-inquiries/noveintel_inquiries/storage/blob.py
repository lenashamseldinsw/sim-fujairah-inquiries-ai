"""
The Azure Blob Storage document store, for Azure deployments.

What it gives you over the local store, and why an Azure deployment needs it:

* **Every instance sees the same files.** The local store writes to one server's
  disk. On Azure the instance that accepts a run, the queue worker that executes it,
  and the instance serving the poll can all be different machines — and the worker
  has to read the request the HTTP instance stored. Only shared storage makes that
  work.
* **Callers get links they can actually open.** A local reference is a ``file:`` URI
  pointing at the server's disk. A blob reference is an https URL with a time-limited
  SAS token, and ``expires_at`` says when it stops working.

**On-prem installs never touch this.** The SDK is imported inside ``_sdk``, not at
module scope, so this module — and the whole package — imports on a machine with no
Azure library installed. The default backend is ``local``, and the SDK only arrives
with the ``azure`` extra.

The sync SDK is used on a worker thread rather than the SDK's async client, which
would add an aiohttp dependency for no gain — uploads here are a handful of files per
run, not a hot path.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Any

from ..models.documents import DocumentRef
from .base import StorageError

__all__ = ["BlobDocumentStore"]

logger = logging.getLogger(__name__)


def _sdk() -> Any:
    """The blob SDK, or a ``StorageError`` that says how to get it."""
    try:
        return importlib.import_module("azure.storage.blob")
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise StorageError(
            "The 'blob' storage backend needs azure-storage-blob, which is not "
            "installed. Install the 'azure' extra, or use the 'local' backend — "
            "which is what an on-prem install should use."
        ) from exc


class BlobDocumentStore:
    """A ``DocumentStore`` backed by an Azure Blob Storage container."""

    def __init__(
        self,
        connection_string: str,
        container: str,
        sas_ttl_sec: int = 7 * 86_400,
    ) -> None:
        if not connection_string.strip():
            raise StorageError("The 'blob' backend needs a connection string.")
        self._connection_string = connection_string
        self.container = container
        self.sas_ttl_sec = sas_ttl_sec
        self._client: Any = None
        self._container_ready = False

    # ── The contract ──────────────────────────────────────────────────────────

    async def put(self, key: str, data: bytes, content_type: str) -> DocumentRef:
        _check_key(key)
        return await asyncio.to_thread(self._put, key, data, content_type)

    async def get(self, key: str) -> bytes:
        _check_key(key)
        return await asyncio.to_thread(self._get, key)

    async def delete(self, key: str) -> None:
        """Remove an object. Not part of the ``DocumentStore`` Protocol.

        Used to clean up a run's stored request once the run has finished — that
        request is a full copy of the caller's export, and keeping it serves no one.
        A missing object is not an error: deleting something already gone is the
        outcome the caller wanted.
        """
        _check_key(key)
        await asyncio.to_thread(self._delete, key)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _service(self) -> Any:
        if self._client is None:
            sdk = _sdk()
            try:
                self._client = sdk.BlobServiceClient.from_connection_string(
                    self._connection_string
                )
            except Exception as exc:
                raise StorageError(f"Could not connect to blob storage: {exc}") from exc
        return self._client

    def _container(self) -> Any:
        container = self._service().get_container_client(self.container)
        if not self._container_ready:
            try:
                container.create_container()
            except Exception as exc:
                # Already there — the normal case after the first run.
                if type(exc).__name__ != "ResourceExistsError":
                    raise StorageError(
                        f"Could not create container {self.container!r}: {exc}"
                    ) from exc
            self._container_ready = True
        return container

    def _put(self, key: str, data: bytes, content_type: str) -> DocumentRef:
        sdk = _sdk()
        blob = self._container().get_blob_client(key)
        filename = PurePosixPath(key).name
        try:
            blob.upload_blob(
                data,
                overwrite=True,
                content_settings=sdk.ContentSettings(
                    content_type=content_type,
                    # So a browser following the link saves "report_ar.docx" rather
                    # than a name derived from the URL and its SAS query string.
                    content_disposition=f'attachment; filename="{filename}"',
                ),
            )
        except Exception as exc:
            raise StorageError(f"Could not upload {key}: {exc}") from exc

        url, expires_at = self._link(blob, key)
        return DocumentRef(
            container=self.container,
            key=key,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            url=url,
            expires_at=expires_at,
        )

    def _link(self, blob: Any, key: str) -> tuple[str, datetime | None]:
        """A download link, time-limited where the credentials allow one.

        A SAS token is signed with the account key, so it can only be minted when the
        connection string carries one. Without it — a SAS-only connection string, say
        — the plain blob URL is returned with no expiry, which a caller can only use
        if it has its own access to the account. That is reported honestly as
        ``expires_at=None`` rather than inventing a lifetime.
        """
        account_key = getattr(self._service().credential, "account_key", None)
        if not account_key:
            return blob.url, None

        sdk = _sdk()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.sas_ttl_sec)
        try:
            token = sdk.generate_blob_sas(
                account_name=blob.account_name,
                container_name=self.container,
                blob_name=key,
                account_key=account_key,
                permission=sdk.BlobSasPermissions(read=True),
                expiry=expires_at,
            )
        except Exception as exc:
            logger.warning("Could not sign a download link for %s: %s", key, exc)
            return blob.url, None
        return f"{blob.url}?{token}", expires_at

    def _get(self, key: str) -> bytes:
        try:
            return self._container().get_blob_client(key).download_blob().readall()
        except Exception as exc:
            raise StorageError(f"Could not read {key}: {exc}") from exc

    def _delete(self, key: str) -> None:
        try:
            self._container().get_blob_client(key).delete_blob()
        except Exception as exc:
            if type(exc).__name__ == "ResourceNotFoundError":
                return
            raise StorageError(f"Could not delete {key}: {exc}") from exc


def _check_key(key: str) -> None:
    """Refuse a key that is not a plain relative path.

    A blob key cannot climb out of its container the way a filesystem path can, but
    applying the local store's rule keeps the two backends interchangeable: a key one
    accepts, the other accepts too.
    """
    pure = PurePosixPath(key)
    if (
        not pure.parts
        or pure.is_absolute()
        or ".." in pure.parts
        or any(c in key for c in ("\\", ":"))
    ):
        raise StorageError(f"Refusing a key that escapes the container: {key!r}")
