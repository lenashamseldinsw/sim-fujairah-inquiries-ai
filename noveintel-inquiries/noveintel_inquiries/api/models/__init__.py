"""The public contract for the Customer Inquiries Analytics API — input and output.

One flat namespace. Everything a caller needs to build a request or read a result is
importable from here, and importing it pulls in nothing but pydantic — no FastAPI, no
pandas. A caller writing an integration against this module should never have to
install the service to see its shape.
"""
from __future__ import annotations

from ._coercion import OptionalFlag, OptionalStr, RequiredStr, is_blank
from .charts import ChartKey, ChartKind, ChartSeries, ChartSpec
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
    BrandColors,
    EntityInfo,
)
from .enums import JobStatus, Language, PeriodGranularity, ReportSection
from .jobs import JobAccepted, JobError, JobState
from .period import Period
from .records import (
    HARD_REQUIRED_COLUMNS,
    InquiryRecord,
    records_to_frame,
)
from .requests import LARGE_RUN_RECORDS, AnalysisOptions, GenerateInquiriesReportRequest
from .responses import BundleWarning, RunDocuments, InquiriesBundle
from .usage import RunUsage, StageUsage

__all__ = [
    "DOCX_CONTENT_TYPE",
    "HARD_REQUIRED_COLUMNS",
    "JSON_CONTENT_TYPE",
    "LARGE_RUN_RECORDS",
    "NOVEAI_MAGENTA",
    "NOVEAI_NAVY",
    "STATUS_COLORS",
    "XLSX_CONTENT_TYPE",
    "AnalysisOptions",
    "BrandColors",
    "BundleWarning",
    "ChartKey",
    "ChartKind",
    "ChartSeries",
    "ChartSpec",
    "DocumentRef",
    "EntityInfo",
    "GenerateInquiriesReportRequest",
    "InquiriesBundle",
    "InquiryRecord",
    "JobAccepted",
    "JobError",
    "JobState",
    "JobStatus",
    "Language",
    "OptionalFlag",
    "OptionalStr",
    "Period",
    "PeriodGranularity",
    "ReportSection",
    "RequiredStr",
    "RunDocuments",
    "RunUsage",
    "StageUsage",
    "is_blank",
    "records_to_frame",
]
