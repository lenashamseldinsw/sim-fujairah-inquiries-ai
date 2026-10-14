"""The public contract for the Customer Inquiries Analytics API — input and output.

One flat namespace. Everything a caller needs to build a request or read a result is
importable from here, and importing it pulls in nothing but pydantic — no FastAPI, no
pandas.
"""
from __future__ import annotations

from ._coercion import OptionalFlag, OptionalNumber, OptionalStr, RequiredStr, is_blank
from .charts import ChartKey, ChartKind, ChartSeries, ChartSpec
from .columns import (
    COLUMNS,
    LABEL_COLUMNS,
    REQUIRED_COLUMNS,
    SENSITIVE_COLUMNS,
    ColumnSpec,
    resolve_header,
)
from .documents import (
    DOCX_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    DocumentRef,
)
from .entity import (
    NOVEAI_MAGENTA,
    NOVEAI_NAVY,
    STATUS_COLORS,
    TIMELINESS_COLORS,
    BrandColors,
    EntityInfo,
)
from .enums import NUMBERED_SECTIONS, SECTION_TITLES, JobStatus, Language, PeriodGranularity, ReportSection
from .jobs import JobAccepted, JobError, JobState
from .narratives import (
    AiUseCase,
    BundleNarrative,
    Effort,
    Horizon,
    Initiative,
    InquiriesReportNarratives,
    ReportNarratives,
    SectionNarratives,
    ServiceFocusNarrative,
)
from .period import Period
from .records import HARD_REQUIRED_COLUMNS, InquiryRecord, canonical_key
from .reference import (
    FaqEntry,
    Guidebook,
    History,
    MainService,
    PeriodSnapshot,
    ReferenceLists,
    SubClassification,
    Taxonomy,
    TransactionRow,
    Umbrella,
    UmbrellaSet,
    VocabularyOverrides,
)
from .requests import (
    LARGE_RUN_RECORDS,
    AnalysisOptions,
    GenerateInquiriesReportRequest,
    MissingField,
    missing_fields_message,
    missing_required_fields,
)
from .responses import (
    BundleWarning,
    ClassificationSummary,
    InquiriesBundle,
    DeepReview,
    RunDocuments,
    UmbrellaProposal,
)
from .settings import (
    CaseTypeScope,
    ComparisonBasis,
    DigitalChannelDefinition,
    FrameworkId,
    FrameworkSelection,
    RecordedType,
    TenantSettings,
    TimelinessFramework,
)
from .usage import RunUsage, StageUsage

__all__ = [
    "COLUMNS",
    "DOCX_CONTENT_TYPE",
    "HARD_REQUIRED_COLUMNS",
    "JSON_CONTENT_TYPE",
    "LABEL_COLUMNS",
    "LARGE_RUN_RECORDS",
    "NOVEAI_MAGENTA",
    "NOVEAI_NAVY",
    "REQUIRED_COLUMNS",
    "NUMBERED_SECTIONS",
    "SECTION_TITLES",
    "SENSITIVE_COLUMNS",
    "STATUS_COLORS",
    "TIMELINESS_COLORS",
    "XLSX_CONTENT_TYPE",
    "AiUseCase",
    "AnalysisOptions",
    "BrandColors",
    "BundleNarrative",
    "BundleWarning",
    "CaseTypeScope",
    "ChartKey",
    "ChartKind",
    "ChartSeries",
    "ChartSpec",
    "ClassificationSummary",
    "ColumnSpec",
    "ComparisonBasis",
    "DigitalChannelDefinition",
    "DocumentRef",
    "Effort",
    "EntityInfo",
    "FaqEntry",
    "FrameworkId",
    "FrameworkSelection",
    "GenerateInquiriesReportRequest",
    "Guidebook",
    "History",
    "Horizon",
    "InquiriesBundle",
    "InquiriesReportNarratives",
    "InquiryRecord",
    "Initiative",
    "JobAccepted",
    "JobError",
    "JobState",
    "JobStatus",
    "Language",
    "MainService",
    "MissingField",
    "OptionalFlag",
    "OptionalNumber",
    "OptionalStr",
    "Period",
    "PeriodGranularity",
    "PeriodSnapshot",
    "RecordedType",
    "ReferenceLists",
    "ReportNarratives",
    "ReportSection",
    "RequiredStr",
    "DeepReview",
    "RunDocuments",
    "RunUsage",
    "SectionNarratives",
    "ServiceFocusNarrative",
    "StageUsage",
    "SubClassification",
    "Taxonomy",
    "TenantSettings",
    "TimelinessFramework",
    "TransactionRow",
    "Umbrella",
    "UmbrellaProposal",
    "UmbrellaSet",
    "VocabularyOverrides",
    "canonical_key",
    "is_blank",
    "missing_fields_message",
    "missing_required_fields",
    "resolve_header",
]
