"""
Frozen labels — what an earlier run settled and the platform sent back.

Labels are frozen at compute and never overwritten (Prerequisites §1.B): a
re-classification is a new run. A record may arrive carrying some of D1–D8 from an
earlier pass, and the classifier fills only what is missing. Frozen fields are
validated against the taxonomy — a frozen sub-classification the catalogue does not
know is kept as given but counted, so a stale label is visible rather than silently
remapped.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..engine.compute import Umbrella
from ..engine.parse import Case
from ..engine.taxonomy import TaxonomyIndex
from ..engine.text import clean_label, fold_text
from ..engine.wording import CONTACT_TO_TYPE, CONTACT_TYPES, TRUE_TYPES

__all__ = ["FrozenReport", "UmbrellaRegistry", "apply_frozen", "provenance_key"]

_PROVENANCE_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("deep_review", ("يدوي", "مراجع", "human", "review", "manual", "deep")),
    ("auto_corrected", ("مصحح", "corrected")),
    ("auto", ("موثوق", "trusted", "قاعده", "rule", "auto", "duplicate", "مكرر")),
    ("draft", ("مسوده", "draft")),
    ("llm", ("نموذج", "model", "llm")),
]


def provenance_key(value: object) -> str | None:
    """The canonical provenance key for a recorded provenance label."""
    if value is None or not str(value).strip():
        return None
    folded = fold_text(value)
    for key, words in _PROVENANCE_WORDS:
        if any(fold_text(w) in folded for w in words):
            return key
    return None


def _contact_type(value: object) -> str | None:
    if not value:
        return None
    folded = fold_text(value)
    for t in CONTACT_TYPES:
        if fold_text(t) == folded:
            return t
    if "شكر" in folded or "ثناء" in folded or "compliment" in folded:
        return "شكر وثناء"
    if "شكو" in folded or "complaint" in folded:
        return "شكوى"
    if "طلب" in folded or "request" in folded:
        return "طلب خدمة"
    if "استفسار" in folded or "inquiry" in folded or "information" in folded:
        return "استفسار"
    return None


class UmbrellaRegistry:
    """Umbrella ids by name: the carried-forward set plus any frozen names."""

    def __init__(self, carried: list[Umbrella]) -> None:
        self.umbrellas: list[Umbrella] = list(carried)
        self._by_name = {fold_text(u.name_ar): u for u in carried}
        self._by_name.update({fold_text(u.name_en): u for u in carried if u.name_en})

    def id_for(self, name: str, *, new: bool = False) -> str:
        key = fold_text(name)
        if key in self._by_name:
            return self._by_name[key].id
        taken = {u.id for u in self.umbrellas}
        n = len(self.umbrellas) + 1
        while f"u{n}" in taken:
            n += 1
        umbrella = Umbrella(id=f"u{n}", name_ar=clean_label(name), new=new)
        self.umbrellas.append(umbrella)
        self._by_name[key] = umbrella
        return umbrella.id

    def get(self, uid: str) -> Umbrella | None:
        return next((u for u in self.umbrellas if u.id == uid), None)


@dataclass
class FrozenReport:
    cases_with_frozen_labels: int = 0
    unknown_main: int = 0
    unknown_sub: int = 0
    pairs_corrected: int = 0
    frozen_fields: dict[str, int] = field(default_factory=dict)


def apply_frozen(cases: list[Case], tax: TaxonomyIndex, registry: UmbrellaRegistry) -> FrozenReport:
    """Copy frozen labels onto each case. Returns what was found."""
    report = FrozenReport()
    for case in cases:
        frozen = case.frozen
        if not frozen:
            continue
        report.cases_with_frozen_labels += 1
        for key in frozen:
            report.frozen_fields[key] = report.frozen_fields.get(key, 0) + 1

        if "main_service" in frozen:
            name = tax.main(frozen["main_service"])
            if name is None:
                report.unknown_main += 1
                name = clean_label(frozen["main_service"])
            case.main_service = name
        if "sub_classification" in frozen:
            sub = tax.sub(frozen["sub_classification"])
            if sub is None:
                report.unknown_sub += 1
                sub = clean_label(frozen["sub_classification"])
            case.sub_classification = sub
            if case.main_service is None:
                mains = tax.mains_for_sub(sub)
                if len(mains) == 1:
                    case.main_service = mains[0]
        if "contact_type" in frozen:
            case.contact_type = _contact_type(frozen["contact_type"])
        if "true_type" in frozen:
            value = fold_text(frozen["true_type"]).replace(" ", "_")
            case.true_type = value if value in TRUE_TYPES else None
        if case.contact_type and not case.true_type:
            case.true_type = CONTACT_TO_TYPE.get(case.contact_type)
        if "reason" in frozen:
            case.reason = clean_label(frozen["reason"])
        if "confidence" in frozen:
            try:
                case.confidence = max(0.0, min(1.0, float(frozen["confidence"])))
            except (TypeError, ValueError):
                pass
        if "root_cause" in frozen:
            case.root_cause = clean_label(frozen["root_cause"])
        if "bundle" in frozen and str(frozen["bundle"]).strip():
            case.bundle = registry.id_for(str(frozen["bundle"]))
        case.provenance = provenance_key(frozen.get("provenance")) or (
            "deep_review" if case.main_service or case.contact_type else None
        )
    return report
