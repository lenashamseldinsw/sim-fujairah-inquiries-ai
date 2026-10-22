"""
The pgvector store: one table per collection, bound to one embedding model.

A collection is a namespace of comparable vectors — every row in it was embedded
by the same model at the same size, because vectors from two models are not
comparable even at equal length. ``ingest_collections`` records each collection's
model and size, and a mismatched embedder is refused rather than mixed in.

Each chunk row keeps the embedded text, the original cells (``metadata.fields``,
JSON) and where the row came from (document, sheet, Excel row number), so a search
hit can be traced back to the cell a person would open.

Local testing needs no server: with no DSN, an embedded Postgres 16 + pgvector is
started in ``NOVEINGEST_PG_DATA_DIR`` (the ``local`` extra, ``pgserver``) and its
data persists there between runs. Production sets ``NOVEINGEST_PG_DSN`` to any
Postgres with the ``vector`` extension — the SQL is the same.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

from .serialize import Chunk
from .settings import get_settings

__all__ = ["Hit", "PgVectorStore", "StoreError", "open_store"]

# pgvector's HNSW index covers up to 2000 dimensions of the `vector` type.
_HNSW_MAX_DIMENSIONS = 2000
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


class StoreError(RuntimeError):
    pass


@dataclass
class Hit:
    id: str
    score: float  # cosine similarity, 1 = identical direction
    text: str
    document_id: str
    sheet: str
    row_number: int
    fields: dict[str, Any]
    metadata: dict[str, Any]


def _vec(v: np.ndarray | Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in v) + "]"


def _ordered_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    fields = metadata.get("fields") or {}
    order = metadata.get("columns") or list(fields)
    return {name: fields[name] for name in order if name in fields}


def _table(collection: str) -> str:
    if not _NAME.match(collection):
        raise StoreError(
            f"Collection name {collection!r} must be lowercase letters, digits and underscores, "
            "starting with a letter, at most 48 characters."
        )
    return f"ingest_{collection}"


def local_dsn(data_dir: str | Path) -> str:
    try:
        import pgserver
    except ImportError as exc:
        raise StoreError(
            "NOVEINGEST_PG_DSN is not set and the embedded Postgres is not installed. "
            "Either set NOVEINGEST_PG_DSN, or `uv sync --extra local` (Python 3.12)."
        ) from exc
    path = Path(data_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    # cleanup_mode="stop": the server stops when the last process using it exits;
    # the data directory is kept.
    return pgserver.get_server(path, cleanup_mode="stop").get_uri()


class PgVectorStore:
    def __init__(self, dsn: str):
        self.conn = psycopg.connect(dsn, autocommit=False)
        with self.conn.transaction():
            self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS ingest_collections (
                    name        text PRIMARY KEY,
                    model       text NOT NULL,
                    dimensions  integer NOT NULL,
                    created_at  timestamptz NOT NULL DEFAULT now()
                )""")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── collections ──────────────────────────────────────────────────────────

    def collection(self, name: str) -> tuple[str, int] | None:
        row = self.conn.execute(
            "SELECT model, dimensions FROM ingest_collections WHERE name = %s", (name,)
        ).fetchone()
        self.conn.commit()
        return (row[0], row[1]) if row else None

    def ensure_collection(self, name: str, model: str, dimensions: int) -> None:
        table = _table(name)
        existing = self.collection(name)
        if existing and existing != (model, dimensions):
            raise StoreError(
                f"Collection {name!r} holds {existing[0]} vectors of {existing[1]} dimensions; this embedder is "
                f"{model} at {dimensions}. Use another collection, or drop this one first."
            )
        if existing:
            return
        with self.conn.transaction():
            self.conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id           text PRIMARY KEY,
                    document_id  text NOT NULL,
                    sheet        text NOT NULL,
                    row_number   integer NOT NULL,
                    content      text NOT NULL,
                    metadata     jsonb NOT NULL,
                    embedding    vector({dimensions}) NOT NULL,
                    ingested_at  timestamptz NOT NULL DEFAULT now()
                )""")
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS {table}_doc ON {table} (document_id, sheet)")
            if dimensions <= _HNSW_MAX_DIMENSIONS:
                self.conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {table}_hnsw ON {table} USING hnsw (embedding vector_cosine_ops)"
                )
            self.conn.execute(
                "INSERT INTO ingest_collections (name, model, dimensions) VALUES (%s, %s, %s)",
                (name, model, dimensions),
            )

    def drop_collection(self, name: str) -> None:
        with self.conn.transaction():
            self.conn.execute(f"DROP TABLE IF EXISTS {_table(name)}")
            self.conn.execute("DELETE FROM ingest_collections WHERE name = %s", (name,))

    def collections(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT name, model, dimensions FROM ingest_collections ORDER BY name").fetchall()
        out = []
        for name, model, dims in rows:
            docs = self.conn.execute(
                f"SELECT document_id, count(*) FROM {_table(name)} GROUP BY document_id ORDER BY document_id"
            ).fetchall()
            out.append({"name": name, "model": model, "dimensions": dims, "documents": dict(docs)})
        self.conn.commit()
        return out

    # ── chunks ───────────────────────────────────────────────────────────────

    def existing_ids(self, collection: str, document_id: str) -> set[str]:
        rows = self.conn.execute(
            f"SELECT id FROM {_table(collection)} WHERE document_id = %s", (document_id,)
        ).fetchall()
        self.conn.commit()
        return {r[0] for r in rows}

    def sync_document(
        self,
        collection: str,
        document_id: str,
        new_chunks: Sequence[Chunk],
        vectors: np.ndarray,
        kept_chunks: Iterable[Chunk],
        stale_ids: Iterable[str],
    ) -> None:
        """In one transaction: insert the new chunks, refresh where the unchanged
        ones now sit (row number, sheet visibility), delete the ones gone from the file."""
        table = _table(collection)
        if len(new_chunks) != len(vectors):
            raise StoreError("Every new chunk needs exactly one vector.")
        with self.conn.transaction(), self.conn.cursor() as cur:
            stale = list(stale_ids)
            if stale:
                cur.execute(f"DELETE FROM {table} WHERE document_id = %s AND id = ANY(%s)", (document_id, stale))
            cur.executemany(
                f"""INSERT INTO {table} (id, document_id, sheet, row_number, content, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata,
                        row_number = EXCLUDED.row_number, embedding = EXCLUDED.embedding, ingested_at = now()""",
                [(c.id, c.document_id, c.sheet, c.row_number, c.text, Jsonb(c.metadata), _vec(v))
                 for c, v in zip(new_chunks, vectors)],
            )
            cur.executemany(
                f"UPDATE {table} SET row_number = %s, metadata = %s WHERE id = %s",
                [(c.row_number, Jsonb(c.metadata), c.id) for c in kept_chunks],
            )

    def delete_document(self, collection: str, document_id: str) -> int:
        with self.conn.transaction():
            cur = self.conn.execute(f"DELETE FROM {_table(collection)} WHERE document_id = %s", (document_id,))
            return cur.rowcount

    def search(
        self,
        collection: str,
        vector: np.ndarray,
        *,
        k: int = 5,
        document_id: str | None = None,
        sheet: str | None = None,
        include_hidden: bool = True,
    ) -> list[Hit]:
        where, params = [], []
        if document_id:
            where.append("document_id = %s")
            params.append(document_id)
        if sheet:
            where.append("sheet = %s")
            params.append(sheet)
        if not include_hidden:
            where.append("NOT (metadata->>'sheet_hidden')::boolean")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        literal = _vec(vector)
        rows = self.conn.execute(
            f"""SELECT id, 1 - (embedding <=> %s::vector), content, document_id, sheet, row_number, metadata
                FROM {_table(collection)} {clause}
                ORDER BY embedding <=> %s::vector LIMIT %s""",
            [literal, *params, literal, k],
        ).fetchall()
        self.conn.commit()
        return [
            Hit(id=r[0], score=float(r[1]), text=r[2], document_id=r[3], sheet=r[4], row_number=r[5],
                fields=_ordered_fields(r[6] or {}), metadata=r[6] or {})
            for r in rows
        ]

    def rows(self, collection: str, document_id: str) -> list[dict[str, Any]]:
        """Every stored row of a document, in sheet and row order — no vectors."""
        rows = self.conn.execute(
            f"""SELECT sheet, row_number, content, metadata FROM {_table(collection)}
                WHERE document_id = %s ORDER BY sheet, row_number, (metadata->>'part')::int""",
            (document_id,),
        ).fetchall()
        self.conn.commit()
        return [{"sheet": s, "row_number": n, "content": c, "fields": _ordered_fields(m)} for s, n, c, m in rows]


def open_store(dsn: str | None = None) -> PgVectorStore:
    settings = get_settings()
    return PgVectorStore(dsn or settings.pg_dsn or local_dsn(settings.pg_data_dir))
