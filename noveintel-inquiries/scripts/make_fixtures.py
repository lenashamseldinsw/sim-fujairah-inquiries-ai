#!/usr/bin/env python
"""
Turn a tenant's Excel export into ready-to-POST request bodies.

In production the NoveIntelligence data home maps a tenant's headers onto the universal
columns and calls the service with records; this script plays that part for testing.
It finds the table (every sheet, header rows 0–5), maps each header through the
service's own column registry — the same folded matching the API applies — and lets
``--map`` override any header the registry does not know or should read differently:

    uv run python scripts/make_fixtures.py export.xlsx --out fixtures/ \\
        --map "الخدمة الرئيسية=label_main_service" --taxonomy adpf_codebook_v1 --x8

It writes:

    happy.json           the first --sample rows — the one to POST first
    full.json            every row, with the English report
    missing_column.json  a required column removed, to see the 422
    empty.json           no records, to see the contract reject it

Settings default to the documented defaults with X2 = 2 working days, X3 = the entity
process KPI and X4 = inquiries and service requests; change them in the files.
Nothing here is imported by the service, and ``.funcignore`` keeps it out of a
deployment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from noveintel_inquiries.models import (  # noqa: E402
    REQUIRED_COLUMNS,
    GenerateInquiriesReportRequest,
    canonical_key,
    missing_fields_message,
    missing_required_fields,
)

REQUIRED = {c.name for c in REQUIRED_COLUMNS}


def mapper(overrides: dict[str, str]):
    def key(header: object) -> str:
        raw = " ".join(str(header).split())
        return overrides.get(raw) or canonical_key(raw)
    return key


def read_export(path: Path, header: int | None, sheet: str | None, key) -> Any:
    """The sheet and header row yielding the most rows with every required column."""
    import pandas as pd

    book = pd.ExcelFile(path)
    best, best_rows, chosen = None, -1, None
    for name in ([sheet] if sheet else book.sheet_names):
        for candidate in ([header] if header is not None else [0, 1, 2, 3, 4, 5]):
            try:
                frame = pd.read_excel(path, sheet_name=name, header=candidate)
            except Exception:
                continue
            if not REQUIRED <= {key(c) for c in frame.columns}:
                continue
            rows = len(frame.dropna(how="all"))
            if rows > best_rows:
                best, best_rows, chosen = frame, rows, (name, candidate)
    if best is None:
        raise SystemExit(
            f"No sheet in {path.name} carries every required column {sorted(REQUIRED)} after "
            "mapping. Pass --map 'Header=canonical' for the ones the registry does not know."
        )
    print(f"Using sheet {chosen[0]!r} with header row {chosen[1]} — {best_rows} rows.")
    return best


def to_records(frame: Any, key) -> list[dict[str, Any]]:
    import pandas as pd

    records = []
    for _, row in frame.iterrows():
        record: dict[str, Any] = {}
        for column, value in row.items():
            name = key(column)
            if pd.isna(value):
                record[name] = None
            else:
                record[name] = value.isoformat() if hasattr(value, "isoformat") else (
                    value if isinstance(value, (int, float)) else str(value)
                )
        if any(v is not None for v in record.values()):
            records.append(record)
    return records


def body(records: list[dict[str, Any]], args: argparse.Namespace, **options: Any) -> dict[str, Any]:
    return {
        "records": records,
        "settings": {
            "timeliness_target_working_days": 2,
            "timeliness_framework": "entity_process_kpi",
            "case_type_scope": args.scope,
            "root_cause_extraction": args.x8,
        },
        "reference_lists": {"taxonomy": args.taxonomy},
        "entity": {"name_ar": args.entity_ar, "name_en": args.entity_en},
        "options": {"language": "ar", "include_english": False, **options},
    }


def write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"  {path.name:<24} {len(payload.get('records', [])):>6} record(s)  {path.stat().st_size / 1024:>8.1f} KiB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("export", type=Path)
    parser.add_argument("--out", type=Path, default=Path("fixtures"))
    parser.add_argument("--sheet", default=None)
    parser.add_argument("--header", type=int, default=None)
    parser.add_argument("--sample", type=int, default=25)
    parser.add_argument("--map", action="append", default=[], metavar="HEADER=FIELD",
                        help="Map a header to a canonical field; repeatable.")
    parser.add_argument("--taxonomy", default="adpf_codebook_v1",
                        help="A preset name, or a path to a catalogue JSON.")
    parser.add_argument("--scope", default="inquiries_and_service_requests")
    parser.add_argument("--x8", action="store_true", help="Turn root-cause extraction on.")
    parser.add_argument("--entity-ar", default="الجهة")
    parser.add_argument("--entity-en", default="Entity")
    args = parser.parse_args()

    overrides = dict(item.split("=", 1) for item in args.map)
    if Path(args.taxonomy).is_file():
        args.taxonomy = json.loads(Path(args.taxonomy).read_text(encoding="utf-8"))
    key = mapper(overrides)
    records = to_records(read_export(args.export, args.header, args.sheet, key), key)
    if not records:
        raise SystemExit("The export produced no records.")

    request = GenerateInquiriesReportRequest.model_validate(body(records[:5], args))
    missing = missing_required_fields(request)
    if missing:
        print("  warning: " + missing_fields_message(missing))

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Writing fixtures to {args.out}/")
    write(args.out / "happy.json", body(records[: args.sample], args))
    write(args.out / "full.json", body(records, args, include_english=True))
    write(args.out / "missing_column.json",
          body([{k: v for k, v in r.items() if k != "resolution_text"} for r in records[:5]], args))
    write(args.out / "empty.json", body([], args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
