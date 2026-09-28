"""
Closed vocabularies for the Customer Complaints Analytics API contract.

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

__all__ = ["JobStatus", "Language", "PeriodGranularity", "ReportSection"]


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
    """A section of the generated report, matching the document's own structure.

    Nine sections, produced by stage 6. Match on these values rather than on
    position — the same contract ``ChartKey`` carries, and for the same reason: a
    tenant whose data yields no friction points gets a report with one section fewer,
    and a consumer indexing by position would then read the wrong one.
    """

    EXECUTIVE_SUMMARY = "executive_summary"
    METHODOLOGY = "methodology"
    WORKLOAD_MAP = "workload_map"
    CUSTOMER_JOURNEY = "customer_journey"
    DIGITAL_GAPS = "digital_gaps"
    DIGITAL_TRANSFORMATION = "digital_transformation"
    AI_USE_CASES = "ai_use_cases"
    IMPROVEMENT_ROADMAP = "improvement_roadmap"
    CONCLUSION = "conclusion"


class JobStatus(StrEnum):
    """Where an analysis job has got to.

    A complaints run makes dozens of sequential model calls across six stages and does
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
