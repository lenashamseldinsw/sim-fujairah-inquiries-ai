"""
The classification taxonomy, indexed for the rule chain, the model and the engine.

The tenant's service catalogue is the taxonomy (Prerequisites §6.2): main services
(codebook O) with sub-classifications nested under each (N). A request names a
built-in preset or sends its own catalogue; either way the run works from one
``TaxonomyIndex``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..api.models.reference import Taxonomy
from .text import clean_label, fold_header, fold_text

__all__ = ["TaxonomyIndex", "load_taxonomy", "PRESETS"]

_RESOURCES = Path(__file__).resolve().parent.parent / "resources"
PRESETS = {"adpf_codebook_v1": _RESOURCES / "taxonomy_adpf_codebook_v1.json"}

_OTHER_NAMES = {fold_text("أخرى"), fold_text("اخرى"), fold_text("other")}


@dataclass
class TaxonomyIndex:
    """Lookups over one taxonomy."""

    taxonomy: Taxonomy
    label: str
    main_names: list[str] = field(default_factory=list)
    sub_names: list[str] = field(default_factory=list)
    sub_to_mains: dict[str, list[str]] = field(default_factory=dict)
    main_to_subs: dict[str, list[str]] = field(default_factory=dict)
    english: dict[str, str] = field(default_factory=dict)
    main_signals: dict[str, list[str]] = field(default_factory=dict)
    sub_signals: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    crosswalk: dict[str, str] = field(default_factory=dict)
    other_service: str | None = None
    _folded_main: dict[str, str] = field(default_factory=dict)
    _folded_sub: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, taxonomy: Taxonomy, label: str) -> "TaxonomyIndex":
        index = cls(taxonomy=taxonomy, label=label)
        for main in taxonomy.main_services:
            name = clean_label(main.name_ar)
            index.main_names.append(name)
            index._folded_main[fold_text(name)] = name
            if main.name_en:
                index.english[name] = main.name_en
            index.main_signals[name] = [fold_text(s) for s in main.signals if s]
            subs: list[str] = []
            for sub in main.sub_classifications:
                sub_name = clean_label(sub.name_ar)
                subs.append(sub_name)
                index.sub_to_mains.setdefault(sub_name, []).append(name)
                index._folded_sub.setdefault(fold_text(sub_name), sub_name)
                if sub.name_en:
                    index.english.setdefault(sub_name, sub.name_en)
                index.sub_signals[(name, sub_name)] = [fold_text(s) for s in sub.signals if s]
                if sub_name not in index.sub_names:
                    index.sub_names.append(sub_name)
            index.main_to_subs[name] = subs
            for alias in main.crm_service_aliases:
                index.crosswalk[fold_header(alias)] = name
        for tag, main_name in taxonomy.crm_service_map.items():
            resolved = index.main(main_name)
            if resolved:
                index.crosswalk.setdefault(fold_header(tag), resolved)
        other = taxonomy.other_service and index.main(taxonomy.other_service)
        if not other:
            other = next((m for m in index.main_names if fold_text(m) in _OTHER_NAMES), None)
        index.other_service = other
        return index

    # ── Lookups ───────────────────────────────────────────────────────────────
    def main(self, name: object) -> str | None:
        """The canonical main-service name a label refers to, or None."""
        if not name:
            return None
        return self._folded_main.get(fold_text(name))

    def sub(self, name: object) -> str | None:
        if not name:
            return None
        return self._folded_sub.get(fold_text(name))

    def is_valid_pair(self, main: str | None, sub: str | None) -> bool:
        return bool(main and sub and sub in self.main_to_subs.get(main, []))

    def mains_for_sub(self, sub: str) -> list[str]:
        return self.sub_to_mains.get(sub, [])

    def en(self, name: str) -> str | None:
        return self.english.get(name)

    def has_english(self, names: list[str]) -> bool:
        """Whether every name the report prints has an English rendering."""
        return all(self.english.get(n) for n in names if n)

    def crosswalk_main(self, recorded_service: object) -> str | None:
        """The main service a recorded CRM service tag corresponds to.

        The catalogue crosswalk first; then a bilingual tag ("EN - AR") is split and
        each half tried against the main-service and sub-classification names.
        """
        if not recorded_service:
            return None
        text = str(recorded_service)
        hit = self.crosswalk.get(fold_header(text))
        if hit:
            return hit
        for part in _split_bilingual(text):
            direct = self.main(part)
            if direct:
                return direct
            sub = self.sub(part)
            if sub and len(self.mains_for_sub(sub)) == 1:
                return self.mains_for_sub(sub)[0]
        return None


def _split_bilingual(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("–", "-").split("-") if p.strip()]
    return parts or [text]


@lru_cache(maxsize=4)
def _preset(name: str) -> Taxonomy:
    data = json.loads(PRESETS[name].read_text(encoding="utf-8"))
    return Taxonomy.model_validate(data)


def load_taxonomy(value: Taxonomy | str) -> TaxonomyIndex:
    """Index a request's taxonomy — a catalogue, or a preset's name."""
    if isinstance(value, str):
        if value not in PRESETS:
            raise ValueError(f"Unknown taxonomy preset {value!r}.")
        taxonomy = _preset(value)
        return TaxonomyIndex.build(taxonomy, label=f"{value} ({taxonomy.version or 'v1'})")
    label = value.id or "tenant catalogue"
    if value.version:
        label = f"{label} ({value.version})"
    return TaxonomyIndex.build(value, label=label)
