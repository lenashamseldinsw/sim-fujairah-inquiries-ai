"""
``InquiriesBundle`` — everything one inquiries run produces.

A run is three layers (Prerequisites §0): the **parser and engine** clean the cases
and compute every number; the **classifier** labels each case under the tenant's
taxonomy and the codebooks, with confidence and provenance, and routes the uncertain
ones to review; the **narrative writer** receives the engine's numbers and writes
prose only. The rule of thumb: the classifier may create labels, the engine alone
creates numbers, the narrative writer creates neither.

``metrics`` is the engine output — every key of Data Mapping §4 — and is the ground
truth the prose is checked against. ``narratives`` is the prose, per language.
``report`` is both assembled into the S0–S11 report the Word documents were drawn
from. ``documents`` carries references, not content: artefacts go to storage and a
storage failure is a warning, never a lost run.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .charts import ChartSpec
from .documents import DocumentRef
from .enums import Language
from .narratives import ReportNarratives
from .period import Period
from .reference import PeriodSnapshot
from .usage import RunUsage

__all__ = [
    "BundleWarning",
    "ClassificationSummary",
    "InquiriesBundle",
    "DeepReview",
    "RunDocuments",
    "UmbrellaProposal",
]


class BundleWarning(BaseModel):
    """Something went wrong, or is worth knowing, that did not cost the run."""

    code: str = Field(
        description=(
            "Stable identifier — branch on this. "
            "'document_storage_failed': an artefact was built but not stored. "
            "'english_export_unavailable': no English report — the English narrative "
            "failed, or the taxonomy carries no English names (Domain 01 ruling). "
            "'pricing_not_configured': tokens counted, cost unknown. "
            "'low_confidence_after_review': cases still below X6 after the deep AI review; "
            "they are counted with their best labels and listed in ``classification.deep_review``. "
            "'umbrellas_pending_confirmation': umbrellas were proposed this run and "
            "await the Domain Admin's confirmation. "
            "'narrative_unverified_figures': a figure in the prose did not match the "
            "engine output after a retry; it is listed in ``detail``. "
            "'narrative_incomplete': the model left out narrative fields even after a "
            "retry; they are empty in the report. "
            "'section_omitted': an optional input was absent, so a section or "
            "subsection was left out with a data note. "
            "'metric_gap': a framework indicator could not be computed from this "
            "export; the report recommends the field instead of printing zero."
        )
    )
    message: str
    detail: Any | None = None


class RunDocuments(BaseModel):
    """The artefacts one run filed in storage."""

    report: dict[Language, DocumentRef] = Field(
        default_factory=dict, description="The Word reports, keyed by language."
    )
    workbook: DocumentRef | None = Field(
        default=None,
        description="The companion workbook: summary, all cases, one sheet per actual "
        "contact type, the reclassification sheet, the deep-reviewed cases and the "
        "Domain 02 handoff sheet. Declared column order; no identity columns (R3, R10).",
    )
    report_data: dict[Language, DocumentRef] = Field(
        default_factory=dict,
        description="The report's JSON per language — what the Word document was drawn from.",
    )
    labels: DocumentRef | None = Field(
        default=None,
        description="Per-case labels (D1–D8, confidence, provenance, deep-review and "
        "low-confidence flags, duplicate source) as JSON — what the platform stores and "
        "sends back as frozen labels.",
    )


class DeepReview(BaseModel):
    """The deep review: a second, higher-effort AI pass («يدوي - مُراجع»).

    Not a human queue. Cases the first pass was unsure of (below X6, or with a broken
    rule) are re-classified by the reasoning model with more evidence.
    """

    reviewed: int = Field(ge=0, description="Cases that went through the deep review.")
    low_confidence: int = Field(ge=0, description="Cases still below X6 afterwards.")
    duplicates_reused: int = Field(
        ge=0, description="Cases whose labels were copied from an identical case («آلي - موثوق»)."
    )
    low_confidence_case_ids: list[str] = Field(
        default_factory=list,
        description="Up to the first 500 low-confidence ids; the labels document has all of them.",
    )
    truncated: bool = False


class UmbrellaProposal(BaseModel):
    """One umbrella as the discovery step left it."""

    id: str
    name_ar: str
    name_en: str
    meaning_ar: str = ""
    meaning_en: str = ""
    cases: int = Field(ge=0)
    new: bool = Field(description="Proposed this run; awaits Domain Admin confirmation.")
    member_root_causes: list[str] = Field(
        default_factory=list, description="Its most frequent root causes, for the DA's review."
    )


class ClassificationSummary(BaseModel):
    """What the classification layer did, for the platform's review surfaces."""

    taxonomy: str = Field(description="Which taxonomy the run used.")
    llm_threshold: float
    review_threshold: float
    provenance: dict[str, int] = Field(description="D6 split.")
    mean_confidence: float | None = None
    deep_review: DeepReview
    umbrella_set_version: str | None = None
    umbrellas: list[UmbrellaProposal] = Field(default_factory=list)


class InquiriesBundle(BaseModel):
    """The complete output of an inquiries analysis run."""

    run_id: str
    period: Period
    total_cases: int = Field(
        ge=0,
        description="|S| — in-scope cases after artefact rows, duplicates and the "
        "case-type scope. The one denominator every section reads (R2).",
    )
    metrics: dict[str, Any] = Field(
        description="The engine output: every Data Mapping §4 key (KPI, MONTHLY, "
        "CHANNEL, TIMELINESS, BUNDLE, … and the Fujairah-native RECORDED_VS_ACTUAL, "
        "JOURNEY_MAP, GAP_TABLE, VALIDATED_FAQS, …), FRAMEWORKS and PARSE_LOG."
    )
    narratives: dict[Language, ReportNarratives] = Field(
        default_factory=dict, description="The narrative layer's output, per language."
    )
    classification: ClassificationSummary
    charts: list[ChartSpec] = Field(default_factory=list)
    report: dict[Language, dict[str, Any]] = Field(default_factory=dict)
    documents: RunDocuments = Field(default_factory=RunDocuments)
    snapshot: PeriodSnapshot = Field(
        description="This run's comparable figures. Store it and send it back as "
        "``history`` next period (R9)."
    )
    usage: RunUsage
    warnings: list[BundleWarning] = Field(default_factory=list)
    primary_language: Language
