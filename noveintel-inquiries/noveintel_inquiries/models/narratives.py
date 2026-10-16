"""
The narrative layer's output — prose only, never a figure the engine did not give.

``InquiriesReportNarratives`` is the Full Report Prompt §4 schema, field for field.
(The Prerequisites call it "30 fields"; the list the same document gives has 29, and
all 29 are here.) Strict structured output has no optional fields — a conditional
field is returned empty when its input is absent (Domain 01 ruling).

``SectionNarratives`` carries the prose the nine-section report needs and the ADPF
schema has no slot for: the recorded-vs-actual reading of S3, the journey, gap and
transformation sections (S4–S6), and the AI use cases (S7). Those sections are
disabled (``sections.SECTIONS``), so it is empty in every run; when one is enabled it is
written by the same model, under the same system prompt and the same hard rules.
Which section prints which field is ``sections.SECTIONS``.

Every count printed beside these — an initiative's ``addresses_cases``, a use case's
impact — is filled in by the engine from the reference the model chose, never taken
from the model's own number.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

__all__ = [
    "AiUseCase",
    "BundleNarrative",
    "Effort",
    "Horizon",
    "Initiative",
    "InquiriesReportNarratives",
    "ReportNarratives",
    "SectionNarratives",
    "ServiceFocusNarrative",
]


class Horizon(StrEnum):
    IMMEDIATE = "immediate"   # 30 days
    SHORT = "short"           # 1–3 months
    MEDIUM = "medium"         # 3–6 months


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ServiceFocusNarrative(BaseModel):
    service: str
    overview: str
    why_this_service: str
    sub_class_narrative: str
    bundle_narrative: str


class BundleNarrative(BaseModel):
    bundle: str
    narrative: str


class Initiative(BaseModel):
    title: str
    horizon: Horizon
    bundle_ref: str = Field(
        description="The reference this initiative addresses — an umbrella id when "
        "root causes are on, otherwise a friction, gap or notification id from the "
        "context's INITIATIVE_SOURCES."
    )
    addresses_cases: int = Field(
        ge=0, description="Filled from the referenced item's count by the engine."
    )
    description: str


class InquiriesReportNarratives(BaseModel):
    """Full Report Prompt §4 — the fields the narrative model returns."""

    intro_statement: str
    executive_summary: str
    comparative_analysis: str = Field(description="Empty when there is no previous period.")
    statistics_intro: str
    monthly_narrative: str
    main_service_narrative: str
    sub_service_narrative: str
    transactions_ratio_narrative: str = Field(description="Empty without INQ_PER_100_TX.")
    channel_narrative: str
    recorded_vs_true_narrative: str
    timeliness_narrative: str
    service_focus_narratives: list[ServiceFocusNarrative]
    root_causes_intro: str
    bundle_distribution_narrative: str
    bundle_by_service_narrative: str
    bundle_narratives: list[BundleNarrative]
    top_root_causes_narrative: str
    timeliness_by_bundle_narrative: str
    digital_opportunity_narrative: str = Field(
        description="Empty without FAQ or service-catalogue inputs."
    )
    priority_faqs: list[str]
    roadmap_intro: str
    initiatives: list[Initiative]
    key_findings: list[str]
    recommendations: list[str]
    closing_statement: str
    methodology_note: str
    event_narratives: list[str]
    friction_points: list[str]
    top_service_short: str


class AiUseCase(BaseModel):
    title: str
    function: str
    source_ref: str = Field(description="An id from the context's INITIATIVE_SOURCES.")
    effort: Effort
    impact_cases: int = Field(
        default=0, ge=0, description="Filled from the referenced item by the engine."
    )


class SectionNarratives(BaseModel):
    """Prose for the nine-section report that the ADPF schema has no field for."""

    contact_type_narrative: str = Field(description="S3 — actual contact-type mix.")
    reclassification_narrative: str = Field(
        description="S3 — recorded type vs actual type; 'eligible for smart re-classification'."
    )
    out_of_scope_narrative: str = Field(
        description="S3 — complaints / incidents / compliments detected inside scope. "
        "Empty when none were detected."
    )
    department_narrative: str = Field(description="S3 — empty without a department column.")
    journey_narrative: str = Field(description="S4 — the journey frictions.")
    digital_gaps_narrative: str = Field(description="S5 — empty without a guidebook.")
    gap_root_causes_narrative: str = Field(description="S5.2 — empty without a guidebook.")
    digital_transformation_narrative: str = Field(description="S6.")
    ai_use_cases_intro: str = Field(description="S7.")
    ai_use_cases: list[AiUseCase]


class ReportNarratives(BaseModel):
    """Both parts, for one language."""

    report: InquiriesReportNarratives
    sections: SectionNarratives
