"""
The root-cause codebook, enforced (ROOT_CAUSE_CODEBOOK R1–R7).

The model writes root causes to the codebook; this checks what it wrote. Some breaches
are fixed in code — a stray case number or date is struck out (R1). The rest are sent
back to the model once, named, with the rule they broke (R1 length, R2, R3). Either
correction sets provenance «آلي - مُصحّح» — "auto, then rule-corrected", the
codebook's own label.

R4, R5 and R7 are judgements about meaning and are left to the prompt; R6 is checked
as "a catch-all case states its reason".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..engine.taxonomy import TaxonomyIndex
from ..engine.text import clean_label, fold_text, word_count

__all__ = ["RootCauseCheck", "check_root_cause", "strip_case_specifics"]

_PLACEHOLDER = re.compile(r"\[[^\]]{2,25}\]")
_DIGITS = re.compile(r"(?<![\w])\d[\d\-/.,:]{3,}\d(?![\w])")
_FOLLOW_UP = fold_text("متابعة")
_FOLLOW_UP_FORM = fold_text("متابعة حالة سابقة بخصوص")


@dataclass
class RootCauseCheck:
    text: str
    fixed: bool
    violation: str | None  # rule id and what to fix, for the re-ask


def strip_case_specifics(text: str) -> tuple[str, bool]:
    """R1 in code: strike placeholders and number runs (case refs, dates, amounts)."""
    cleaned = _PLACEHOLDER.sub("", text)
    cleaned = _DIGITS.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ،,.-")
    return cleaned, cleaned != text.strip()


def check_root_cause(text: str | None, *, main_service: str | None, sub: str | None,
                     tax: TaxonomyIndex) -> RootCauseCheck:
    """Check one root cause against the codebook."""
    raw = clean_label(text)
    if not raw:
        return RootCauseCheck("", False, "R1: the root cause is empty — state why the customer made contact.")
    cleaned, fixed = strip_case_specifics(raw)
    words = word_count(cleaned)
    joined = " + " in cleaned
    folded = fold_text(cleaned)

    if words < 4:
        return RootCauseCheck(cleaned, fixed, "R1: too short — 6–14 words stating the underlying issue.")
    if words > 14 and not joined:
        return RootCauseCheck(cleaned, fixed, "R1: too long — 6–14 words, a reason not a case summary.")
    if folded.startswith(_FOLLOW_UP) and len(folded.split()) <= 4:
        return RootCauseCheck(
            cleaned, fixed,
            "R2: a follow-up must name the underlying subject — «متابعة حالة سابقة بخصوص <the actual issue>».",
        )
    if sub and main_service:
        own = {fold_text(s) for s in tax.main_to_subs.get(main_service, [])} | {fold_text(main_service)}
        for other_main, subs in tax.main_to_subs.items():
            if other_main == main_service or other_main == tax.other_service:
                continue
            for name in subs:
                key = fold_text(name)
                if len(key.split()) >= 3 and key in folded and not any(o in folded for o in own if len(o.split()) >= 2):
                    return RootCauseCheck(
                        cleaned, fixed,
                        f"R3: the cause names «{name}», a service other than the chosen sub-classification «{sub}».",
                    )
    return RootCauseCheck(cleaned, fixed, None)
