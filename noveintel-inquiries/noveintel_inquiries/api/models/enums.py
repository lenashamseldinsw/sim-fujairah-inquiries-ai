"""
Closed vocabularies for the Customer Inquiries Analytics API contract.

These are versioned, public option sets — named enums so callers can import the
constants and so the generated JSON Schema carries named components. Data-level
vocabularies (service name, department, channel, sub-classification) are deliberately
NOT enums: they are open per-tenant sets the pipeline normalises downstream, and an
enum would reject a tenant that added a service last week.

``Language`` and ``PeriodGranularity`` are byte-identical to module 01's, on purpose.
``ReportSection`` and ``JobStatus`` are this module's own.
"""
from __future__ import annotations

from enum import StrEnum

__all__ = ["JobStatus", "Language", "PeriodGranularity", "ReportSection", "SECTION_IDS"]


class Language(StrEnum):
    """Output language of a generated document. One language per document."""

    AR = "ar"
    EN = "en"


class PeriodGranularity(StrEnum):
    """Reporting period granularity.

    Offered to the caller when the data spans several months. When omitted from the
    request, the granularity is derived from the span of the case dates.
    """

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"


class ReportSection(StrEnum):
    """A section of the generated report — the Definition Sheet's S0–S11.

    S0–S9 are the nine Fujairah sections with the cover; S10 and S11 are the optional
    ADPF sections, present only when root-cause extraction (X8) is on. Match on these
    values, never on position: a section whose optional input is absent is omitted
    (with a data note), so positions shift between runs.
    """

    COVER = "cover"                                # S0
    EXECUTIVE_SUMMARY = "executive_summary"        # S1
    METHODOLOGY = "methodology"                    # S2
    CLASSIFICATION_MAP = "classification_map"      # S3
    CUSTOMER_JOURNEY = "customer_journey"          # S4
    DIGITAL_GAPS = "digital_gaps"                  # S5
    DIGITAL_TRANSFORMATION = "digital_transformation"  # S6
    AI_USE_CASES = "ai_use_cases"                  # S7
    IMPROVEMENT_ROADMAP = "improvement_roadmap"    # S8
    CONCLUSION = "conclusion"                      # S9
    ROOT_CAUSES = "root_causes"                    # S10 (X8)
    SERVICE_FOCUS = "service_focus"                # S11 (X8)


SECTION_IDS: dict[ReportSection, str] = {
    section: f"S{index}" for index, section in enumerate(ReportSection)
}


class JobStatus(StrEnum):
    """Where an analysis job has got to.

    A inquiries run makes dozens of sequential model calls across six stages and does
    not fit the 230-second ceiling Azure puts on an HTTP response, so the work route
    accepts a job and answers immediately. This is what a poll gets back.

    ``QUEUED`` and ``RUNNING`` mean keep polling. ``SUCCEEDED``, ``FAILED`` and
    ``CANCELLED`` are terminal — the job will not change again, and a poll after one
    of those is wasted.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
