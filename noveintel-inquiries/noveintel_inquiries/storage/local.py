"""
The filesystem store — the stand-in until real blob storage exists.

It behaves exactly as a blob backend does from the outside: artefacts are written
somewhere the API does not serve, and the caller gets a reference it resolves itself.
Only the scheme of that reference differs, and even that is configurable.

By default ``url`` is a ``file:`` URI, which is honest — the object really is on the
service's disk — and directly usable by anything co-located, such as ``scripts/
smoke.py``. Set ``public_base_url`` and it emits ``<base>/<container>/<key>`` instead,
at which point the contract is byte-identical to production and the URL is genuinely
fetchable if you point something at the directory:

    python -m http.server 10000 -d storage

Swapping this for the real thing is one class implementing the same two methods.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path, PurePosixPath

from ..api.models.documents import DocumentRef
from .base import StorageError

__all__ = ["LocalDirectoryStore"]


def _io_path(path: Path) -> Path:
    """The form of a path to hand the filesystem.

    Everywhere but Windows, itself. On Windows the legacy 260-character ``MAX_PATH``
    applies unless a path carries the ``\\\\?\\`` extended-length prefix, and a key is
    around 100 characters before the store's root is counted — so a root a few
    directories deep is enough to make writes fail with "the filename or extension is
    too long". A real blob backend has no such limit, so this stand-in should not
    invent one.

    Only for I/O. ``DocumentRef.url`` is built from the plain path, because the
    prefixed form does not make a sensible ``file:`` URI.
    """
    if os.name != "nt":
        return path
    absolute = Path(os.path.abspath(path))
    if str(absolute).startswith("\\\\"):  # already prefixed, or a UNC share
        return absolute
    return Path(f"\\\\?\\{absolute}")


class LocalDirectoryStore:
    """A ``DocumentStore`` backed by a directory on the service's own disk."""

    def __init__(
        self,
        root: Path | str,
        container: str = "reports",
        public_base_url: str | None = None,
    ) -> None:
        # Absolute from the outset. The default root is relative ("storage"), and a
        # relative path has no ``file:`` URI — so leaving it as given would make every
        # reference fail on the default configuration. Resolved once here rather than
        # per call, so a later chdir cannot move the store out from under a run.
        self.root = Path(root).absolute()
        self.container = container
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None

    # ── The contract ──────────────────────────────────────────────────────────

    async def put(self, key: str, data: bytes, content_type: str) -> DocumentRef:
        path = self._path(key)
        try:
            await asyncio.to_thread(self._write, path, data)
        except OSError as exc:
            raise StorageError(
                f"Could not write {path}: {exc.strerror or exc}"
            ) from exc

        return DocumentRef(
            container=self.container,
            key=key,
            filename=PurePosixPath(key).name,
            content_type=content_type,
            size_bytes=len(data),
            url=self._url(key, path),
            # A file on disk has no expiry, and inventing one would be a lie a caller
            # would act on. A SAS-minting backend fills this in.
            expires_at=None,
        )

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(_io_path(path).read_bytes)
        except OSError as exc:
            raise StorageError(f"Could not read {path}: {exc.strerror or exc}") from exc

    # ── Internals ─────────────────────────────────────────────────────────────

    def _path(self, key: str) -> Path:
        """Resolve a key to a path, refusing any that would escape the container.

        Keys are built by ``build_key`` from a slug, a date and a hex id, so none of
        what is refused here can currently happen. The guard exists because the day a
        key is derived from caller-supplied text, a traversal is a write anywhere the
        process can reach — and that day should not depend on someone remembering this
        file.

        The check is deliberately lexical rather than a ``resolve()`` comparison. A
        blob key is a POSIX-ish string, not a path on this machine, so inspecting its
        segments is the honest test — and it does not touch the filesystem, which
        matters because a run uploads several artefacts concurrently and a
        ``resolve()`` racing a sibling's ``mkdir`` can come back in a form that fails
        the comparison for a perfectly good key.
        """
        pure = PurePosixPath(key)
        parts = pure.parts
        # A bare "." segment is dropped by PurePosixPath, so it never reaches here and
        # is not an escape anyway; ".." is the only segment that climbs.
        if (
            not parts
            or pure.is_absolute()
            or ".." in parts
            or any(c in key for c in ("\\", ":"))
        ):
            raise StorageError(f"Refusing a key that escapes the container: {key!r}")
        return self.root / self.container / Path(*parts)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        target = _io_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def _url(self, key: str, path: Path) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/{self.container}/{key}"
        return path.as_uri()
