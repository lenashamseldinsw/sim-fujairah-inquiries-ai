"""
The narrative layer's output — prose only, never a figure the engine did not give.

``InquiriesReportNarratives`` is the Full Report Prompt §4 schema, field for field.
(The Prerequisites call it "30 fields"; the list the same document gives has 29, and
all 29 are here.) Strict structured output has no optional fields — a conditional
field is returned empty when its input is absent (Domain 01 ruling).

``SectionNarratives`` carries the prose the nine-section report needs and the ADPF
schema has no slot for: the recorded-vs-actual reading of S3, the journey, gap and
transformation sections (S4–S6), and the AI use cases (S7). It is written by the same
model, under the same system prompt and the same hard rules.

Every count printed beside these — an initiative's ``addresses_cases``, a use case's
impact — is filled in by the engine from the reference the model chose, never taken
from the model's own number.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .enums import ReportSection

__all__ = [
    "SECTION_FIELDS",
    "hidden_fields",
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


# Which report section prints each narrative field. A field of a section not shown is
# neither asked for nor kept, and is not translated — nor is a field that belongs to no
# current section. The 29 report fields map onto the sample output's sections one for
# one; the nine-section ``SectionNarratives`` fields belonged to the retired sections,
# so that part is no longer written at all (its mappings are kept below, commented).
SECTION_FIELDS: dict[ReportSection, dict[str, tuple[str, ...]]] = {
    ReportSection.COVER: {"report": ("top_service_short",)},
    ReportSection.EXECUTIVE_SUMMARY: {"report": ("intro_statement", "executive_summary", "comparative_analysis")},
    ReportSection.STATISTICS: {
        "report": ("statistics_intro", "monthly_narrative", "main_service_narrative", "sub_service_narrative",
                   "transactions_ratio_narrative", "channel_narrative", "recorded_vs_true_narrative",
                   "timeliness_narrative"),
        # Retired with the Fujairah subsections the sample's Section 01 does not have:
        # "sections": ("contact_type_narrative", "reclassification_narrative", "out_of_scope_narrative",
        #              "department_narrative"),
    },
    ReportSection.SERVICE_FOCUS: {"report": ("service_focus_narratives",)},
    ReportSection.ROOT_CAUSES: {
        "report": ("root_causes_intro", "bundle_distribution_narrative", "bundle_by_service_narrative",
                   "bundle_narratives", "top_root_causes_narrative", "timeliness_by_bundle_narrative"),
    },
    ReportSection.DIGITAL_CONTENT_OPPORTUNITIES: {"report": ("digital_opportunity_narrative", "priority_faqs")},
    ReportSection.IMPROVEMENT_ROADMAP: {"report": ("roadmap_intro", "initiatives")},
    ReportSection.CONCLUSION: {"report": ("key_findings", "recommendations", "closing_statement")},
    ReportSection.APPENDICES: {"report": ("methodology_note", "event_narratives", "friction_points")},
    # Retired sections (BO, 2026-10-14):
    # CUSTOMER_JOURNEY:       {"sections": ("journey_narrative",)}
    # DIGITAL_GAPS:           {"sections": ("digital_gaps_narrative", "gap_root_causes_narrative")}
    # DIGITAL_TRANSFORMATION: {"sections": ("digital_transformation_narrative",)}
    # AI_USE_CASES:           {"sections": ("ai_use_cases_intro", "ai_use_cases")}
}


def hidden_fields(shown: list[ReportSection] | set[ReportSection]) -> dict[str, set[str]]:
    """Per part, every narrative field that no shown section prints."""
    printed: dict[str, set[str]] = {"report": set(), "sections": set()}
    for section, parts in SECTION_FIELDS.items():
        if section in shown:
            for part, fields in parts.items():
                printed[part].update(fields)
    return {
        "report": set(InquiriesReportNarratives.model_fields) - printed["report"],
        "sections": set(SectionNarratives.model_fields) - printed["sections"],
    }
