"""
Rendering the engine's labels in the report language.

The engine works in canonical Arabic names. For the English report every printed
label needs an English form, and where it comes from depends on whose label it is:

* **catalogue names** (main services, sub-classifications) come only from the
  tenant's English column — the Domain 01 ruling: where a translation is missing the
  English export is unavailable, never machine-translated;
* **platform vocabulary** (contact types, timeliness labels, channels, months) is
  fixed here;
* **recorded values** that arrive bilingual ("Information - معلومات") use their
  English half;
* **AI-generated labels** (root causes, umbrella names without a confirmed English
  name, departments, severity values) are translated once per run by
  ``narratives.translate``, because no tenant column carries them.
"""
from __future__ import annotations

from .compute import Umbrella
from .parse import split_bilingual
from .taxonomy import TaxonomyIndex
from .wording import CONTACT_TYPE_EN, NOT_PROVIDED, PROVENANCE, PROVENANCE_EN, UNCLASSIFIED, channel_label

__all__ = ["Localizer", "missing_catalogue_english"]

_FIXED_EN = {
    UNCLASSIFIED["ar"]: UNCLASSIFIED["en"],
    NOT_PROVIDED["ar"]: NOT_PROVIDED["en"],
    "غير محدد": "Unspecified",
    "—": "—",
    **{PROVENANCE[k]: PROVENANCE_EN[k] for k in PROVENANCE},
}


class Localizer:
    def __init__(self, lang: str, tax: TaxonomyIndex, umbrellas: list[Umbrella],
                 translations: dict[str, str] | None = None) -> None:
        self.lang = lang
        self.tax = tax
        self.umbrella_en = {u.name_ar: u.name_en for u in umbrellas if u.name_en}
        self.translations = translations or {}

    def name(self, label: object) -> str:
        if label is None:
            return ""
        text = str(label)
        if self.lang == "ar":
            # Recorded values can arrive in English («Phone», "Information - معلومات").
            en, ar = split_bilingual(text)
            if en and ar:
                return ar
            if en and not ar:
                channel = channel_label(text, "ar")
                if channel != text:
                    return channel
            return text
        for lookup in (
            self.tax.en(text),
            self.umbrella_en.get(text),
            CONTACT_TYPE_EN.get(text),
            _FIXED_EN.get(text),
            self.translations.get(text),
        ):
            if lookup:
                return lookup
        en, ar = split_bilingual(text)
        if en and ar:
            return en
        channel = channel_label(text, "en")
        if channel != text:
            return channel
        return text

    def names(self, labels: list) -> list[str]:
        return [self.name(x) for x in labels or []]


def missing_catalogue_english(tax: TaxonomyIndex, printed: list[str]) -> list[str]:
    """Catalogue names the report prints that have no English rendering."""
    catalogue = set(tax.main_names) | set(tax.sub_names)
    return sorted({n for n in printed if n in catalogue and not tax.en(n)})
