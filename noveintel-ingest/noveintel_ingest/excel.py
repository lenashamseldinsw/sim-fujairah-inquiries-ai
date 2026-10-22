"""
Read every sheet of an Excel workbook into header-keyed rows.

Real workbooks are not clean tables, so the reader:

* finds the header row instead of assuming row 1 — a title or a blank row above
  the table is skipped (the first row, within the first ten, whose cells are mostly
  text and hold distinct values across at least half the widest row);
* fills merged ranges with their top-left value, so a merged header names every
  column it spans and a merged value applies to every row it covers;
* names blank headers ``Column C`` and de-duplicates repeated ones (``Notes``,
  ``Notes (2)``), and strips the stray whitespace headers carry;
* drops empty rows and columns, and rows that repeat the header (exports that
  print it on every page);
* keeps hidden sheets, flagged, because a hidden sheet is still the author's
  content — the caller decides whether it matters.

Values are kept as the reader saw them, turned to text only where a type has no
JSON form: dates become ISO strings and whole floats become ints.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

__all__ = ["Row", "Sheet", "Workbook", "read_workbook"]

SUPPORTED_SUFFIXES = (".xlsx", ".xlsm")
_HEADER_SCAN_ROWS = 10


@dataclass
class Row:
    number: int  # the Excel row number, 1-based — what a person looks up
    values: dict[str, Any]  # header → value, in column order, empty cells omitted


@dataclass
class Sheet:
    name: str
    hidden: bool
    header: list[str]
    header_row: int
    rows: list[Row] = field(default_factory=list)


@dataclass
class Workbook:
    path: Path
    sheets: list[Sheet]

    def sheet(self, name: str) -> Sheet:
        for sheet in self.sheets:
            if sheet.name == name or sheet.name.strip() == name.strip():
                return sheet
        raise KeyError(f"No sheet named {name!r}; the workbook has: {', '.join(s.name for s in self.sheets)}")


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time() else value.isoformat(timespec="seconds")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    return value


def _grid(ws) -> list[list[Any]]:
    """The sheet as a list of rows, merged ranges filled from their top-left cell."""
    grid = [[_clean(v) for v in row] for row in ws.iter_rows(values_only=True)]
    for merged in ws.merged_cells.ranges:
        top = merged.min_row - 1
        left = merged.min_col - 1
        if top >= len(grid) or left >= len(grid[top]):
            continue
        value = grid[top][left]
        for r in range(merged.min_row - 1, min(merged.max_row, len(grid))):
            for c in range(merged.min_col - 1, min(merged.max_col, len(grid[r]))):
                grid[r][c] = value
    return grid


def _header_index(grid: list[list[Any]]) -> int | None:
    widths = [sum(v is not None for v in row) for row in grid[:_HEADER_SCAN_ROWS]]
    if not widths or max(widths) == 0:
        return None
    widest = max(widths)
    for i, row in enumerate(grid[:_HEADER_SCAN_ROWS]):
        filled = [v for v in row if v is not None]
        if not filled:
            continue
        text_share = sum(isinstance(v, str) for v in filled) / len(filled)
        # Distinct values, not filled cells: a title merged across the table fills
        # every column with the same text and must not pass for a header.
        distinct = len({str(v) for v in filled})
        if distinct * 2 >= widest and (distinct > 1 or widest == 1) and text_share >= 0.5:
            return i
    return next(i for i, w in enumerate(widths) if w)


def _names(header_cells: list[Any]) -> list[str]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for i, value in enumerate(header_cells):
        name = " ".join(str(value).split()) if value is not None else f"Column {get_column_letter(i + 1)}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        names.append(name)
    return names


def _read_sheet(ws) -> Sheet:
    hidden = ws.sheet_state != "visible"
    grid = _grid(ws)
    at = _header_index(grid)
    if at is None:
        return Sheet(name=ws.title, hidden=hidden, header=[], header_row=0)
    body = grid[at + 1:]
    width = max((len(r) for r in grid), default=0)
    used = [c for c in range(width) if any(c < len(r) and r[c] is not None for r in [grid[at], *body])]
    header = _names([grid[at][c] if c < len(grid[at]) else None for c in used])
    raw_header = [grid[at][c] if c < len(grid[at]) else None for c in used]
    rows: list[Row] = []
    for offset, cells in enumerate(body):
        picked = [cells[c] if c < len(cells) else None for c in used]
        if all(v is None for v in picked) or picked == raw_header:
            continue
        rows.append(Row(
            number=at + 2 + offset,
            values={name: value for name, value in zip(header, picked) if value is not None},
        ))
    return Sheet(name=ws.title, hidden=hidden, header=header, header_row=at + 1, rows=rows)


def read_workbook(path: str | Path, *, include_hidden: bool = True) -> Workbook:
    """Every sheet of the workbook, in tab order. Chart sheets are skipped."""
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"{path.name}: unsupported file type {path.suffix!r} — expected one of {', '.join(SUPPORTED_SUFFIXES)}. "
            "Save a legacy .xls as .xlsx first."
        )
    # Not read_only: merged ranges are only available on a fully loaded sheet.
    # data_only: a formula cell is read as its cached value, which is what a reader sees.
    wb = load_workbook(path, data_only=True)
    try:
        sheets = [_read_sheet(ws) for ws in wb.worksheets if include_hidden or ws.sheet_state == "visible"]
    finally:
        wb.close()
    return Workbook(path=path, sheets=sheets)
