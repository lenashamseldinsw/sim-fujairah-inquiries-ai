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

__all__ = ["JobStatus", "Language", "PeriodGranularity", "ReportSection", "NUMBERED_SECTIONS", "SECTION_TITLES"]


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
    """A section of the generated report, in report order — the structure of the
    ADPF Q2 2026 sample output, which the BO confirmed as the report's sections.

    The five numbered sections (01–05) are numbered at render time among those shown,
    so hiding one does not leave a gap. Match on these values, never on position.

    Sections of the Definition Sheet's nine-section template that the sample does not
    have — the customer-journey section (its friction points are an appendix here),
    the guidebook digital-gap analysis, the digital-transformation plan and the AI use
    cases — are retired for now; their code is commented out, not deleted.
    """

    COVER = "cover"
    EXECUTIVE_SUMMARY = "executive_summary"
    STATISTICS = "statistics"                                        # Section 01
    SERVICE_FOCUS = "service_focus"                                  # Section 02 (X8)
    ROOT_CAUSES = "root_causes"                                      # Section 03 (X8)
    DIGITAL_CONTENT_OPPORTUNITIES = "digital_content_opportunities"  # Section 04
    IMPROVEMENT_ROADMAP = "improvement_roadmap"                      # Section 05
    CONCLUSION = "conclusion"
    APPENDICES = "appendices"   # methodology · qualitative observations · journey friction points
    # Retired with the Definition Sheet's template (BO, 2026-10-14):
    # METHODOLOGY = "methodology"                  — now the first appendix
    # CLASSIFICATION_MAP = "classification_map"    — now STATISTICS
    # CUSTOMER_JOURNEY = "customer_journey"        — friction points now an appendix
    # DIGITAL_GAPS = "digital_gaps"                — its digital-content part is Section 04
    # DIGITAL_TRANSFORMATION = "digital_transformation"
    # AI_USE_CASES = "ai_use_cases"


# Each section's title as the report prints it — the sample output's wording. A request
# names sections by key or by either title.
SECTION_TITLES: dict[ReportSection, dict[str, str]] = {
    ReportSection.COVER: {"ar": "الغلاف والمؤشرات", "en": "Cover and indicators"},
    ReportSection.EXECUTIVE_SUMMARY: {"ar": "الملخص التنفيذي", "en": "Executive summary"},
    ReportSection.STATISTICS: {"ar": "الإحصاءات العامة ولوحة المؤشرات", "en": "General statistics and indicator dashboard"},
    ReportSection.SERVICE_FOCUS: {"ar": "تركيز الخدمات ذات الأولوية", "en": "Priority service focus"},
    ReportSection.ROOT_CAUSES: {"ar": "الأسباب الجذرية وارتباطها بالخدمات", "en": "Root causes and their link to services"},
    ReportSection.DIGITAL_CONTENT_OPPORTUNITIES: {"ar": "فرص المحتوى الرقمي الموجَّه", "en": "Targeted digital-content opportunities"},
    ReportSection.IMPROVEMENT_ROADMAP: {"ar": "خارطة الطريق التحسينية المقترحة", "en": "Proposed improvement roadmap"},
    ReportSection.CONCLUSION: {"ar": "الخلاصة والتوصيات", "en": "Conclusion and recommendations"},
    ReportSection.APPENDICES: {"ar": "الملاحق", "en": "Appendices"},
}

# The five numbered sections, in order. Numbered 01, 02, … among those shown.
NUMBERED_SECTIONS: tuple[ReportSection, ...] = (
    ReportSection.STATISTICS,
    ReportSection.SERVICE_FOCUS,
    ReportSection.ROOT_CAUSES,
    ReportSection.DIGITAL_CONTENT_OPPORTUNITIES,
    ReportSection.IMPROVEMENT_ROADMAP,
)


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
