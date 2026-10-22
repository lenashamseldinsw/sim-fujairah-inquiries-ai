"""
The ingestion flow: workbook → chunks → embeddings → pgvector, incrementally.

Re-ingesting a document embeds only the rows whose content changed. Chunk ids are
content-addressed, so the store already knows every unchanged row: those keep
their vector (their row number and metadata are refreshed in case they moved),
new or edited rows are embedded, and rows gone from the file are deleted — all in
one transaction, so a failed embedding call leaves the collection as it was.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .embed import Embedder, make_embedder
from .excel import read_workbook
from .serialize import MAX_CHARS, chunk_workbook, normalize_text
from .store import Hit, PgVectorStore, open_store

__all__ = ["IngestReport", "default_document_id", "ingest_workbook", "search"]

logger = logging.getLogger(__name__)


@dataclass
class SheetSummary:
    name: str
    hidden: bool
    header_row: int
    columns: list[str]
    rows: int


@dataclass
class IngestReport:
    collection: str
    document_id: str
    model: str
    dimensions: int
    sheets: list[SheetSummary] = field(default_factory=list)
    chunks: int = 0
    embedded: int = 0
    unchanged: int = 0
    deleted: int = 0
    duplicate_rows: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def default_document_id(path: str | Path) -> str:
    """The file name without its extension, whitespace collapsed — Arabic kept."""
    stem = unicodedata.normalize("NFC", Path(path).stem)
    return re.sub(r"\s+", " ", stem).strip()


def ingest_workbook(
    path: str | Path,
    *,
    collection: str,
    document_id: str | None = None,
    store: PgVectorStore | None = None,
    embedder: Embedder | None = None,
    include_hidden: bool = True,
    exclude_columns: Iterable[str] = (),
    max_chars: int = MAX_CHARS,
) -> IngestReport:
    document_id = document_id or default_document_id(path)
    embedder = embedder or make_embedder()
    owns_store = store is None
    store = store or open_store()
    try:
        workbook = read_workbook(path, include_hidden=include_hidden)
        chunks, duplicates = chunk_workbook(workbook, document_id, exclude_columns=exclude_columns, max_chars=max_chars)
        # A model mismatch is refused before anything is embedded; a new collection is
        # created only once the embedding has succeeded, so a refused key or model
        # leaves no empty collection bound to it.
        bound = store.collection(collection)
        if bound and bound != (embedder.model, embedder.dimensions):
            store.ensure_collection(collection, embedder.model, embedder.dimensions)  # raises with the reason
        existing = store.existing_ids(collection, document_id) if bound else set()
        new = [c for c in chunks if c.id not in existing]
        kept = [c for c in chunks if c.id in existing]
        stale = existing - {c.id for c in chunks}
        logger.info("%s: %d chunks — %d to embed, %d unchanged, %d stale",
                    document_id, len(chunks), len(new), len(kept), len(stale))
        vectors = embedder.embed_documents([c.text for c in new])
        store.ensure_collection(collection, embedder.model, embedder.dimensions)
        store.sync_document(collection, document_id, new, vectors, kept, stale)
        return IngestReport(
            collection=collection,
            document_id=document_id,
            model=embedder.model,
            dimensions=embedder.dimensions,
            sheets=[SheetSummary(s.name, s.hidden, s.header_row, s.header, len(s.rows)) for s in workbook.sheets],
            chunks=len(chunks),
            embedded=len(new),
            unchanged=len(kept),
            deleted=len(stale),
            duplicate_rows=duplicates,
        )
    finally:
        if owns_store:
            store.close()


def search(
    query: str,
    *,
    collection: str,
    k: int = 5,
    document_id: str | None = None,
    sheet: str | None = None,
    include_hidden: bool = True,
    store: PgVectorStore | None = None,
    embedder: Embedder | None = None,
) -> list[Hit]:
    """The ``k`` rows nearest the query. The query is embedded with the collection's
    own model — searching with another model's vector would return noise."""
    owns_store = store is None
    store = store or open_store()
    try:
        bound = store.collection(collection)
        if bound is None:
            raise KeyError(f"No collection named {collection!r}.")
        model, dimensions = bound
        embedder = embedder or make_embedder(model, dimensions)
        if (embedder.model, embedder.dimensions) != bound:
            raise ValueError(f"Collection {collection!r} was embedded with {model} at {dimensions} dimensions.")
        return store.search(collection, embedder.embed_query(normalize_text(query)), k=k, document_id=document_id,
                            sheet=sheet, include_hidden=include_hidden)
    finally:
        if owns_store:
            store.close()
