#!/usr/bin/env python
"""
Turn a real Excel export into ready-to-POST request bodies.

**This is where the spreadsheet knowledge went.** The Streamlit application read the
tenant's workbook itself — hunting for the right sheet, guessing the header row,
normalising column names. The service does none of that: it takes structured records,
and the parsing is the caller's (porting guide §2). This script is that caller, kept
here so the knowledge is not lost and so the test fixtures come from real data rather
than from something invented.

    uv run python scripts/make_fixtures.py path/to/export.xlsx --out fixtures/

It writes a body per case:

    happy.json          a small valid payload — the one to POST first
    full.json           every row, for a real timing run
    missing_column.json a required column removed, to see the 422 fold
    empty.json          no records, to see the contract reject it

Nothing here is imported by the service. It is excluded from the deployment package
by ``.funcignore``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# The script runs from the project root, where the package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from noveintel_complaints.api.models import HARD_REQUIRED_COLUMNS, ComplaintRecord  # noqa: E402
from noveintel_complaints.stages.stage1_validator import COLUMN_MAPPING  # noqa: E402

ENTITY = {
    "name_ar": "شرطة الفجيرة",
    "name_en": "Fujairah Police",
    "name_short": "Fujairah Police",
    "center_name_ar": "مركز الاتصال",
    "center_name_en": "Contact Centre",
}

# The alias each record field carries — the normalised Arabic column name. Read off
# the model rather than restated, so this script cannot drift from the contract.
ALIASES: dict[str, str] = {
    field.alias or name: name for name, field in ComplaintRecord.model_fields.items()
}

# A real export does not use the normalised names. It uses the tenant's display
# headings — ``رقم الطلب`` with a space, ``الحل `` with a trailing one, and the
# occasional typo the source system has always had. Stage 1 folds all of those onto
# the normalised name, and this script has to do the same thing *before* the model's
# aliases can match, or every column looks unknown.
#
# COLUMN_MAPPING is imported from the stage rather than copied, so a spelling added
# there is understood here without anyone remembering to update both.
def normalise(column: object) -> str:
    """A raw spreadsheet heading, folded to its normalised Arabic column name."""
    raw = str(column)
    return COLUMN_MAPPING.get(raw) or COLUMN_MAPPING.get(raw.strip()) or raw.strip()


def read_export(path: Path, header: int | None, sheet: str | None) -> Any:
    """Find the rows in a tenant's workbook.

    Two things make this awkward, and both are why it is a script rather than a
    route. The header is not always the first row — the complaints export puts it on
    row 5 — and a workbook often carries several sheets, of which the first is
    frequently a stale leftover. So when neither is specified, every sheet is tried
    at every plausible header row and the one yielding the most rows *that satisfy
    the required columns* wins.
    """
    import pandas as pd

    book = pd.ExcelFile(path)
    if sheet is not None and header is not None:
        return pd.read_excel(path, sheet_name=sheet, header=header)

    required = {
        alias for alias, field in ALIASES.items() if field in HARD_REQUIRED_COLUMNS
    }
    best, best_rows, chosen = None, -1, None
    for name in book.sheet_names:
        for candidate in ([header] if header is not None else [0, 1, 2, 3, 4, 5]):
            try:
                frame = pd.read_excel(path, sheet_name=name, header=candidate)
            except Exception:
                continue
            columns = {normalise(c) for c in frame.columns}
            if not required <= columns:
                continue
            rows = len(frame.dropna(how="all"))
            if rows > best_rows:
                best, best_rows, chosen = frame, rows, (name, candidate)

    if best is None:
        raise SystemExit(
            f"No sheet in {path.name} carries the required columns "
            f"{sorted(required)}. Sheets tried: {book.sheet_names}. "
            "Pass --sheet and --header to point at it explicitly."
        )
    print(f"Using sheet {chosen[0]!r} with header row {chosen[1]} — {best_rows} rows.")
    return best


def to_records(frame: Any) -> list[dict[str, Any]]:
    """Frame to records, keyed the way the API takes them.

    Emitted under the **snake_case** names rather than the Arabic aliases, because a
    fixture is read by people as much as by the service and the snake_case form is
    what an integrator writing against the OpenAPI document will see. Both are
    accepted; this is a readability choice, not a requirement.

    Columns the contract does not model are passed through under their own names —
    the API keeps them, and stage 1 counts them.
    """
    import pandas as pd

    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        record: dict[str, Any] = {}
        for column, value in row.items():
            normalised = normalise(column)
            key = ALIASES.get(normalised, normalised)
            # An empty cell is sent as null, not left out. Leaving it out tells the
            # API the column is missing from this record — which it is not; the
            # export has the column and this row's cell is blank. The pipeline keeps
            # such rows and the API accepts them, but only if they arrive as null.
            if pd.isna(value):
                record[key] = None
                continue
            record[key] = value.isoformat() if hasattr(value, "isoformat") else str(value)
        if any(v is not None for v in record.values()):
            records.append(record)
    return records


def body(records: list[dict[str, Any]], **options: Any) -> dict[str, Any]:
    """Wrap records in a full request body."""
    return {
        "records": records,
        "entity": ENTITY,
        "options": {"language": "ar", "include_english": False, **options},
    }


def write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    size = path.stat().st_size / 1024
    count = len(payload.get("records", []))
    print(f"  {path.name:<24} {count:>6} record(s)  {size:>8.1f} KiB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="The tenant's .xlsx export.")
    parser.add_argument("--out", type=Path, default=Path("fixtures"))
    parser.add_argument("--sheet", default=None, help="Sheet name, if autodetect fails.")
    parser.add_argument(
        "--header", type=int, default=None, help="0-based header row, if autodetect fails."
    )
    parser.add_argument(
        "--sample", type=int, default=25, help="Rows in the happy-path body."
    )
    args = parser.parse_args()

    if not args.export.is_file():
        raise SystemExit(f"No such file: {args.export}")

    records = to_records(read_export(args.export, args.header, args.sheet))
    if not records:
        raise SystemExit("The export produced no records.")

    # Validated here so a broken fixture is caught now rather than as a 422 later.
    invalid = 0
    for record in records:
        try:
            ComplaintRecord(**record)
        except Exception:
            invalid += 1
    if invalid:
        print(f"  warning: {invalid} of {len(records)} rows fail validation as-is.")

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Writing fixtures to {args.out}/")

    write(args.out / "happy.json", body(records[: args.sample]))
    write(args.out / "full.json", body(records, include_english=True))

    column = sorted(HARD_REQUIRED_COLUMNS)[0]
    stripped = [{k: v for k, v in r.items() if k != column} for r in records[:5]]
    write(args.out / "missing_column.json", body(stripped))

    write(args.out / "empty.json", body([]))

    print(
        "\nPOST happy.json to /v1/complaints/validate first — it costs nothing and "
        "tells you whether the payload will be accepted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
