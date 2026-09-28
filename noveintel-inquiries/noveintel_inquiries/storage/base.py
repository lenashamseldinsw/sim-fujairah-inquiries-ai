"""
The storage seam.

One ``Protocol`` with two methods, and the key layout every backend shares. This is
the whole abstraction: a backend needs to put bytes somewhere and say where they went,
and — for tests and dev tooling — read them back.

A ``Protocol`` rather than a base class because the implementations have nothing to
inherit. It also means an Azure backend can live outside this package, which it must:
nothing under ``noveintel_inquiries/`` may import ``azure.*``, so the Functions wrapper at the
project root builds that store and injects it.

``put`` is async because a real backend is network I/O, and it is called from inside
the async pipeline. The local implementation still honours that by writing on a worker
thread rather than blocking the event loop.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from ..api.models.documents import DOCX_CONTENT_TYPE, DocumentRef
from ..api.models.entity import EntityInfo
from ..api.models.period import Period

__all__ = [
    "DOCX_CONTENT_TYPE",
    "DocumentStore",
    "StorageError",
    "build_key",
    "slugify",
]

_NON_SLUG = re.compile(r"[^a-z0-9]+")
_SLUG_MAX = 60


class StorageError(Exception):
    """A backend could not store or retrieve an artefact.

    Every implementation wraps its own failures in this — an ``OSError`` from the
    filesystem, an SDK error from a blob client — so the pipeline has one thing to
    catch and callers never see a provider's exception type.
    """


@runtime_checkable
class DocumentStore(Protocol):
    """Somewhere finished artefacts go."""

    async def put(self, key: str, data: bytes, content_type: str) -> DocumentRef:
        """Store ``data`` at ``key`` and return how to reach it.

        Overwrites whatever was at that key. Keys carry a per-run id, so in practice
        nothing is ever overwritten except by a retry of the same run.

        Raises ``StorageError`` if the object could not be written.
        """
        ...

    async def get(self, key: str) -> bytes:
        """Read back the object at ``key``.

        Exists for tests and for dev tooling that wants the bytes without going
        through a URL. It is deliberately *not* wired to any route: the API does not
        serve artefact content, callers fetch from storage.

        Raises ``StorageError`` if the object is missing or unreadable.
        """
        ...


def slugify(value: str) -> str:
    """Reduce a name to something safe in a blob key, a bucket path and a filesystem.

    Non-ASCII collapses away entirely, which is why this is only ever applied to
    ``name_en`` — running it over an Arabic name would leave nothing.
    """
    slug = _NON_SLUG.sub("-", value.strip().lower()).strip("-")
    return slug[:_SLUG_MAX].strip("-") or "entity"


def build_key(
    entity: EntityInfo, period: Period, run_id: str, name: str
) -> str:
    """Compose the key one artefact is stored under.

        <entity-slug>/<period-start>/<run-id>/<name>

    Ordered widest-first so the natural prefix listings are the useful ones: every
    run for a tenant, then every run for a period. The period's start date rather
    than the generation date, because that is what identifies the report —
    re-running last quarter's analysis tomorrow should still file under last quarter.

    ``run_id`` keeps two runs over the same period from colliding, so a re-run never
    overwrites an artefact a caller may still be fetching.

    ``name`` is the filename including its extension — ``report_ar.docx``,
    ``cases.xlsx``, ``report_ar.json``. Unlike module 01, a run here produces more
    than one kind of artefact, so the name is passed rather than derived from a
    language alone.
    """
    return f"{slugify(entity.name_en)}/{period.start.isoformat()}/{run_id}/{name}"
