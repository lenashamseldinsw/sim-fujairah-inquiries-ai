"""
Rows → embeddable chunks, each cell carried with its column name.

``42 | 2024-03-01 | North | 18500`` means nothing to an embedding model;
``Document: Sales | Sheet: Orders | Order ID: 42 | Date: 2024-03-01 | Region: North |
Revenue: 18500`` keeps every value attached to what it is. The document and sheet
names lead each chunk because they are often the only place a row's subject is
written down (a sheet called «خدمات المؤمن عليهم» says who every row is about).

For the embedded text only, whitespace inside a value is collapsed and tatweel
(«ـ», U+0640 — stretching, no meaning: «مؤمـن عليـه» is «مؤمن عليه») is removed, so
it does not change how a word tokenises. The stored ``fields`` keep the cell
exactly as read, line breaks included. ``normalize_text`` is applied to search
queries too.

A row too long for one embedding is split on its longest field: every part repeats
the row's other fields and names the split one ``Column (part 2/3)``, so no part
loses the row's context. Ids are content-addressed (document, sheet, text), so a
re-ingest finds unchanged rows wherever they moved and embeds only what changed.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .excel import Row, Sheet, Workbook

__all__ = ["Chunk", "chunk_workbook", "normalize_text", "row_chunks"]

SEPARATOR = " | "
# ≈ 2–3k tokens of Arabic: well inside either model's input limit (8,191 tokens for
# Embeddings 3 Large, 32k for Qwen3 Embedding), and a row this long is rare.
MAX_CHARS = 6000


@dataclass
class Chunk:
    id: str
    document_id: str
    sheet: str
    sheet_hidden: bool
    row_number: int
    part: int
    parts: int
    text: str
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "sheet": self.sheet,
            "sheet_hidden": self.sheet_hidden,
            "row_number": self.row_number,
            "part": self.part,
            "parts": self.parts,
            "fields": self.fields,
            # jsonb stores object keys in its own order; this keeps the sheet's.
            "columns": list(self.fields),
        }


def normalize_text(value: Any) -> str:
    return " ".join(str(value).replace("\u0640", "").split())


def _pieces(text: str, size: int) -> list[str]:
    """Cut ``text`` into pieces of at most ``size`` characters, at a space when one is near."""
    out: list[str] = []
    while len(text) > size:
        cut = text.rfind(" ", int(size * 0.8), size)
        cut = cut if cut > 0 else size
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out


def _chunk_id(document_id: str, sheet: str, text: str) -> str:
    return hashlib.sha256(f"{document_id}\x1f{sheet}\x1f{text}".encode()).hexdigest()[:32]


def row_chunks(
    document: str,
    sheet: Sheet,
    row: Row,
    *,
    exclude_columns: Iterable[str] = (),
    max_chars: int = MAX_CHARS,
) -> list[Chunk]:
    excluded = {" ".join(c.split()) for c in exclude_columns}
    cells = [(name, normalize_text(value)) for name, value in row.values.items() if name not in excluded]
    cells = [(name, value) for name, value in cells if value]
    if not cells:
        return []
    prefix = f"Document: {document}{SEPARATOR}Sheet: {sheet.name}"
    whole = SEPARATOR.join([prefix, *(f"{n}: {v}" for n, v in cells)])

    def make(text: str, part: int, parts: int) -> Chunk:
        return Chunk(
            id=_chunk_id(document, sheet.name, text),
            document_id=document,
            sheet=sheet.name,
            sheet_hidden=sheet.hidden,
            row_number=row.number,
            part=part,
            parts=parts,
            text=text,
            fields=dict(row.values),
        )

    if len(whole) <= max_chars:
        return [make(whole, 1, 1)]

    longest = max(range(len(cells)), key=lambda i: len(cells[i][1]))
    name, value = cells[longest]
    rest = len(whole) - len(f"{name}: {value}")
    room = max(max_chars - rest - len(f"{name} (part 99/99): "), max_chars // 4)
    pieces = _pieces(value, room)
    chunks = []
    for i, piece in enumerate(pieces, 1):
        parts = [f"{n}: {v}" if j != longest else f"{name} (part {i}/{len(pieces)}): {piece}"
                 for j, (n, v) in enumerate(cells)]
        chunks.append(make(SEPARATOR.join([prefix, *parts]), i, len(pieces)))
    return chunks


def chunk_workbook(
    workbook: Workbook,
    document_id: str,
    *,
    exclude_columns: Iterable[str] = (),
    max_chars: int = MAX_CHARS,
) -> tuple[list[Chunk], int]:
    """Every row of every sheet as chunks, and how many duplicate rows were folded.

    Two rows of one sheet with identical content are one chunk (the first row
    number is kept): embedding the same text twice only skews a search.
    """
    exclude_columns = list(exclude_columns)
    chunks: list[Chunk] = []
    seen: set[str] = set()
    duplicates = 0
    for sheet in workbook.sheets:
        for row in sheet.rows:
            for chunk in row_chunks(document_id, sheet, row, exclude_columns=exclude_columns, max_chars=max_chars):
                if chunk.id in seen:
                    duplicates += 1
                    continue
                seen.add(chunk.id)
                chunks.append(chunk)
    return chunks, duplicates
