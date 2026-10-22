"""
Command line: ``uv run noveintel-ingest <command>`` (or ``python -m noveintel_ingest``).

  inspect        sheets, headers and the serialised text of the first rows — no model call
  ingest         embed a workbook into a collection (only changed rows are re-embedded)
  search         nearest rows to a question
  faq-catalogue  a FAQ sheet → the inquiries service's reference.faq_catalogue JSON
  collections    what the store holds
  drop           delete a collection, or one document from it
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .embed import EmbeddingError
from .store import StoreError

DEFAULT_COLLECTION = "documents"


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _inspect(args) -> None:
    from .excel import read_workbook
    from .ingest import default_document_id
    from .serialize import row_chunks

    wb = read_workbook(args.file)
    doc = args.document_id or default_document_id(args.file)
    for sheet in wb.sheets:
        state = "hidden" if sheet.hidden else "visible"
        print(f"\n━━ {sheet.name}  ({state}, header at row {sheet.header_row}, {len(sheet.rows)} rows)")
        print("   columns: " + " · ".join(sheet.header))
        for row in sheet.rows[: args.rows]:
            for chunk in row_chunks(doc, sheet, row, exclude_columns=args.exclude_column or ()):
                print(f"   [row {row.number}{f' part {chunk.part}/{chunk.parts}' if chunk.parts > 1 else ''}] {chunk.text}")


def _ingest(args) -> None:
    from .embed import make_embedder
    from .ingest import ingest_workbook

    report = ingest_workbook(
        args.file,
        collection=args.collection,
        document_id=args.document_id,
        embedder=make_embedder(args.model, args.dimensions),
        include_hidden=not args.skip_hidden,
        exclude_columns=args.exclude_column or (),
    )
    _print(report.as_dict())


def _search(args) -> None:
    from .ingest import search

    hits = search(args.query, collection=args.collection, k=args.k, document_id=args.document_id,
                  sheet=args.sheet, include_hidden=not args.skip_hidden)
    for hit in hits:
        print(f"\n{hit.score:.3f}  {hit.document_id} › {hit.sheet} › row {hit.row_number}")
        for name, value in hit.fields.items():
            print(f"   {name}: {' '.join(str(value).split())[:300]}")


def _faq(args) -> None:
    from .faq import faq_catalogue

    entries, note = faq_catalogue(
        args.file, sheet=args.sheet, question_ar=args.question_ar, answer_ar=args.answer_ar,
        question_en=args.question_en, answer_en=args.answer_en, main_service=args.service_column,
    )
    text = json.dumps(entries, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        _print({**note, "written_to": args.out})
    else:
        print(text)
        print(json.dumps(note, ensure_ascii=False), file=sys.stderr)


def _collections(args) -> None:
    from .store import open_store

    with open_store() as store:
        _print(store.collections())


def _drop(args) -> None:
    from .store import open_store

    with open_store() as store:
        if args.document_id:
            _print({"deleted_rows": store.delete_document(args.collection, args.document_id)})
        else:
            store.drop_collection(args.collection)
            _print({"dropped": args.collection})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="noveintel-ingest", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="Show what would be embedded, without embedding")
    p.add_argument("file")
    p.add_argument("--rows", type=int, default=3, help="Rows to show per sheet (default 3)")
    p.add_argument("--document-id")
    p.add_argument("--exclude-column", action="append", metavar="HEADER")
    p.set_defaults(run=_inspect)

    p = sub.add_parser("ingest", help="Embed a workbook into a collection")
    p.add_argument("file")
    p.add_argument("--collection", default=DEFAULT_COLLECTION)
    p.add_argument("--document-id", help="Default: the file name without extension")
    p.add_argument("--model", help="text-embedding-3-large (default) or qwen3-embedding; local-hash for offline tests")
    p.add_argument("--dimensions", type=int)
    p.add_argument("--skip-hidden", action="store_true", help="Leave hidden sheets out")
    p.add_argument("--exclude-column", action="append", metavar="HEADER",
                   help="Keep this column out of the embedded text (it is still stored). Repeatable.")
    p.set_defaults(run=_ingest)

    p = sub.add_parser("search", help="Nearest rows to a question")
    p.add_argument("query")
    p.add_argument("--collection", default=DEFAULT_COLLECTION)
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--document-id")
    p.add_argument("--sheet")
    p.add_argument("--skip-hidden", action="store_true")
    p.set_defaults(run=_search)

    p = sub.add_parser("faq-catalogue", help="A FAQ sheet → reference.faq_catalogue JSON")
    p.add_argument("file")
    p.add_argument("--sheet")
    p.add_argument("--question-ar")
    p.add_argument("--answer-ar")
    p.add_argument("--question-en")
    p.add_argument("--answer-en")
    p.add_argument("--service-column", help="Column copied into main_service")
    p.add_argument("-o", "--out")
    p.set_defaults(run=_faq)

    p = sub.add_parser("collections", help="List collections and their documents")
    p.set_defaults(run=_collections)

    p = sub.add_parser("drop", help="Delete a collection, or one document from it")
    p.add_argument("collection")
    p.add_argument("--document-id")
    p.set_defaults(run=_drop)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        args.run(args)
    except (EmbeddingError, StoreError, ValueError, KeyError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
