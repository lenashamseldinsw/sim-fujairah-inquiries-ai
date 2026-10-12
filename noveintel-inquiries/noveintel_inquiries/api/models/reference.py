"""
Reference lists and run history — the tables a run reads besides the cases.

The Domain Definition Sheet §7 routes these to Module 03's reference-list amendment
(OCL). Until that store exists the platform sends them on the request, like the
identity pack.

* **taxonomy** — *required*. The service catalogue: main services and the
  sub-classifications under each (codebook O → N), with assignment signals. Either
  the catalogue itself or the name of a built-in preset; ``"adpf_codebook_v1"`` is
  the ADPF classification codebook v1 (13 main services, learned from 11,799
  labelled cases).
* **faq_catalogue** — optional. Enables FAQ coverage and priority FAQs.
* **vocabulary** — optional. Tenant wording overrides; omitted means the ADPF list
  the Prerequisites ship as the default, sent as ``{}`` means none.
* **transactions** — optional, period-stamped. Enables inquiries per 100 transactions.
* **guidebook** — optional. The service guidebook the digital-gap analysis (S5) is
  checked against. Without it S5's gap table is omitted with a data note.
* **umbrellas** — optional. The tenant's confirmed umbrella set, carried forward so
  the next period assigns to the same umbrellas first.

``history`` is the comparison basis (R9): the platform serves the stored snapshot of
an earlier run instead of a JSON upload. Every bundle returns a ``snapshot`` shaped
the same way, for the platform to store and send back next period.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FaqEntry",
    "GuidebookEntry",
    "Guidebook",
    "History",
    "PeriodSnapshot",
    "ReferenceLists",
    "SubClassification",
    "MainService",
    "Taxonomy",
    "TaxonomyExample",
    "TaxonomyPreset",
    "TransactionRow",
    "Umbrella",
    "UmbrellaSet",
    "VocabularyOverrides",
]

TaxonomyPreset = Literal["adpf_codebook_v1"]


class SubClassification(BaseModel):
    """N — one sub-classification under a main service."""

    name_ar: str
    name_en: str | None = None
    code: str | None = None
    signals: list[str] = Field(
        default_factory=list,
        description="Words or phrases in the description or resolution that point to "
        "this sub-classification. Feeds the rule chain and the model's codebook.",
    )


class MainService(BaseModel):
    """O — one main service family."""

    name_ar: str
    name_en: str | None = None
    code: str | None = None
    signals: list[str] = Field(default_factory=list)
    guidance: str | None = Field(
        default=None,
        description="One line for the classifier: when a case belongs here.",
    )
    crm_service_aliases: list[str] = Field(
        default_factory=list,
        description="Recorded CRM service tags (U5) that correspond to this main "
        "service — the catalogue crosswalk RECORDED_VS_TRUE is computed on.",
    )
    sub_classifications: list[SubClassification] = Field(min_length=1)


class TaxonomyExample(BaseModel):
    """A reviewed case, redacted — a worked example of the tenant's practice."""

    description: str
    resolution: str = ""
    main_service: str
    sub_classification: str
    root_cause: str | None = None


class Taxonomy(BaseModel):
    """The tenant's classification taxonomy: main services → sub-classifications."""

    id: str | None = None
    version: str | None = None
    main_services: list[MainService] = Field(min_length=1)
    crm_service_map: dict[str, str] = Field(
        default_factory=dict,
        description="Recorded CRM service tag → main service name. Merged with each "
        "main service's crm_service_aliases.",
    )
    edge_cases: list[str] = Field(
        default_factory=list,
        description="Codebook edge-case rules, given to the classifier verbatim.",
    )
    other_service: str | None = Field(
        default=None,
        description="The catch-all main service («أخرى»). Detected by name when omitted.",
    )
    examples: list[TaxonomyExample] = Field(
        default_factory=list,
        max_length=120,
        description="Reviewed, redacted cases given to the classifier as worked examples of "
        "the tenant's practice — the reviewers' decisions where the signals alone are "
        "ambiguous. Two or three per sub-classification is enough.",
    )


class FaqEntry(BaseModel):
    """One question in the tenant's FAQ catalogue."""

    question_ar: str
    answer_ar: str | None = None
    question_en: str | None = None
    answer_en: str | None = None
    main_service: str | None = None
    keywords: list[str] = Field(default_factory=list)


class VocabularyOverrides(BaseModel):
    """Words to avoid → the tenant's required wording, per language."""

    ar: dict[str, str] = Field(default_factory=dict)
    en: dict[str, str] = Field(default_factory=dict)


class TransactionRow(BaseModel):
    """Service transaction volumes for the period (the optional second dataset)."""

    main_service: str
    sub_service: str | None = None
    service_code: str | None = None
    total_requests: float = Field(ge=0)
    completed_requests: float | None = None
    rejected_requests: float | None = None
    taxonomy_main_service: str | None = Field(
        default=None,
        description="The taxonomy main service this row joins to, when its own name "
        "differs. Defaults to a name match.",
    )
    taxonomy_sub_classification: str | None = Field(
        default=None,
        description="The taxonomy sub-classification this row joins to.",
    )
    counts_in_denominator: bool = Field(
        default=True,
        description="Open item 2: whether this service counts in the overall "
        "inquiries-per-100-transactions denominator.",
    )


class GuidebookEntry(BaseModel):
    """One service or section of the guidebook, in whatever shape it was exported."""

    model_config = ConfigDict(extra="allow")

    title: str
    text: str = ""
    section: str | None = None


class Guidebook(BaseModel):
    """The tenant's service guidebook (S5's reference).

    Accepts the generic shape (``entries``) or the Fujairah ``guidebook_final.json``
    shape (``document`` / ``sections`` / ``services`` / ``faq``) unchanged.
    """

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    pages: int | None = None
    year: str | None = None
    topics: list[str] = Field(default_factory=list)
    entries: list[GuidebookEntry] = Field(default_factory=list)
    document: dict[str, Any] | None = None
    sections: list[dict[str, Any]] | None = None
    services: list[dict[str, Any]] | None = None
    faq: list[dict[str, Any]] | None = None


class Umbrella(BaseModel):
    """One confirmed umbrella (thematic bundle)."""

    id: str
    name_ar: str
    name_en: str | None = None
    meaning_ar: str | None = None
    meaning_en: str | None = None


class UmbrellaSet(BaseModel):
    """The tenant's confirmed umbrella set, carried forward."""

    version: str | None = None
    umbrellas: list[Umbrella] = Field(default_factory=list)


class ReferenceLists(BaseModel):
    """The tenant's reference lists for this run."""

    taxonomy: Taxonomy | TaxonomyPreset | None = Field(
        default=None,
        description="**Required.** The classification taxonomy, or the name of a "
        "built-in preset ('adpf_codebook_v1').",
    )
    faq_catalogue: list[FaqEntry] | None = None
    vocabulary: VocabularyOverrides | None = Field(
        default=None,
        description="Omitted: the ADPF default list. {}: no overrides.",
    )
    transactions: list[TransactionRow] | None = None
    guidebook: Guidebook | None = None
    umbrellas: UmbrellaSet | None = None


class PeriodSnapshot(BaseModel):
    """The comparable figures of one run, as stored by the platform."""

    model_config = ConfigDict(extra="allow")

    label_ar: str
    label_en: str | None = None
    total_cases: int = Field(ge=0)
    classified: int | None = None
    within_deadline_pct: float | None = None
    digital_share_pct: float | None = None
    reclassification_rate: float | None = None
    channel_pct: dict[str, float] = Field(default_factory=dict)
    bundle_counts: dict[str, int] = Field(default_factory=dict)
    contact_type_counts: dict[str, int] = Field(default_factory=dict)
    main_service_counts: dict[str, int] = Field(default_factory=dict)


class History(BaseModel):
    """Stored runs to compare against (R9). The platform serves these."""

    previous_period: PeriodSnapshot | None = None
    same_period_last_year: PeriodSnapshot | None = None
