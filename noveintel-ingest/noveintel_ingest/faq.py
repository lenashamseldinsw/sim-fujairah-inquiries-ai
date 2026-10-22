"""
A FAQ sheet → the inquiries service's ``reference.faq_catalogue``.

The inquiries pipeline takes the tenant's published FAQs as a reference list on
the request (``[{question_ar, answer_ar?, question_en?, answer_en?, main_service?,
keywords[]}]``). This turns a workbook into that list, with no model call, so the
same file feeds the vector store and the pipeline.

Columns are found by header unless named: a question column has "question" or
«سؤال» in its header, an answer column "answer", «إجابة», «جواب» or «الصيغة
المقترحة» (the reviewed wording, which is the answer). English and Arabic are told
apart by "English"/"Arabic" in the header, or by the script of the values. When no
sheet is named, the one visible sheet with a question and an answer column is
used; hidden sheets only when there is no visible one — a hidden sheet is usually
a draft.

``main_service`` is copied from the service column when one is named. The engine
restricts a catalogue entry to that main service only when the name is one of the
taxonomy's; any other name — a TAMM service title, say — makes the entry apply to
every service, so passing it through is harmless.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .excel import Sheet, Workbook, read_workbook

__all__ = ["faq_catalogue", "find_faq_columns"]

_QUESTION = re.compile(r"question|سؤال|السؤال|الاسئلة|الأسئلة", re.IGNORECASE)
_ANSWER = re.compile(r"answer|إجابة|الإجابة|اجابة|جواب|الجواب|الصيغة المقترحة", re.IGNORECASE)
_ARABIC = re.compile(r"[؀-ۿ]")


def _language(sheet: Sheet, column: str) -> str:
    lowered = column.lower()
    if "english" in lowered or "انجليزي" in column or "الإنجليزية" in column:
        return "en"
    if "arabic" in lowered or "عربي" in column or "العربية" in column:
        return "ar"
    values = [str(r.values[column]) for r in sheet.rows[:30] if column in r.values]
    arabic = sum(bool(_ARABIC.search(v)) for v in values)
    return "ar" if arabic * 2 >= len(values) else "en"


def find_faq_columns(sheet: Sheet) -> dict[str, str]:
    """Role (question_ar, answer_ar, question_en, answer_en) → header, first match wins."""
    found: dict[str, str] = {}
    for column in sheet.header:
        role = "question" if _QUESTION.search(column) else "answer" if _ANSWER.search(column) else None
        if role:
            found.setdefault(f"{role}_{_language(sheet, column)}", column)
    return found


def _pick_sheet(workbook: Workbook) -> Sheet:
    candidates = [s for s in workbook.sheets if "question_ar" in find_faq_columns(s)]
    visible = [s for s in candidates if not s.hidden]
    pool = visible or candidates
    if len(pool) == 1:
        return pool[0]
    if not pool:
        raise ValueError("No sheet has an Arabic question column; name the sheet and columns explicitly.")
    raise ValueError(f"Several sheets look like FAQ lists ({', '.join(s.name for s in pool)}); name one with sheet=.")


def faq_catalogue(
    source: str | Path | Workbook,
    *,
    sheet: str | None = None,
    question_ar: str | None = None,
    answer_ar: str | None = None,
    question_en: str | None = None,
    answer_en: str | None = None,
    main_service: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The catalogue entries, and a note of which sheet and columns they came from."""
    workbook = source if isinstance(source, Workbook) else read_workbook(source)
    target = workbook.sheet(sheet) if sheet else _pick_sheet(workbook)
    columns = find_faq_columns(target)
    explicit = {"question_ar": question_ar, "answer_ar": answer_ar, "question_en": question_en,
                "answer_en": answer_en, "main_service": main_service}
    columns.update({k: v for k, v in explicit.items() if v})
    missing = [v for v in columns.values() if v not in target.header]
    if missing:
        raise ValueError(f"Sheet {target.name!r} has no column(s) {missing}; it has: {target.header}")
    if "question_ar" not in columns:
        raise ValueError(f"No Arabic question column found in {target.name!r}; pass question_ar=.")

    entries: list[dict[str, Any]] = []
    skipped = 0
    for row in target.rows:
        entry: dict[str, Any] = {}
        for key, column in columns.items():
            value = row.values.get(column)
            if value is not None and str(value).strip():
                entry[key] = str(value).strip()
        if not entry.get("question_ar"):
            skipped += 1
            continue
        entry["keywords"] = []
        entries.append(entry)
    source_note = {
        "sheet": target.name,
        "sheet_hidden": target.hidden,
        "columns": dict(columns),
        "entries": len(entries),
        "rows_without_question": skipped,
    }
    return entries, source_note
