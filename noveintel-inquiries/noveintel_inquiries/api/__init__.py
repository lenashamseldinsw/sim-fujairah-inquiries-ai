"""
NoveIntelligence — Customer Inquiries Analytics API.

The routes sit in ``app.py``, ``routes.py``, ``deps.py`` and ``errors.py``. The
typed contract they serve is ``noveintel_inquiries.models`` — a package of its own,
not part of this one, because the engine, the job layer and storage are built on it
and none of them is the web layer. The pipeline lives at
``noveintel_inquiries.pipeline``.

This module re-exports the models and nothing more. Importing it must not require
FastAPI — the contract is useful to a caller building a request who will never run the
service, so the web layer stays behind ``noveintel_inquiries.api.app``.
"""
from __future__ import annotations

from ..models import (
    NOVEAI_MAGENTA,
    NOVEAI_NAVY,
    STATUS_COLORS,
    AnalysisOptions,
    BrandColors,
    BundleWarning,
    ChartKey,
    ChartKind,
    ChartSeries,
    ChartSpec,
    DocumentRef,
    EntityInfo,
    JobAccepted,
    JobError,
    JobState,
    JobStatus,
    Language,
    Period,
    PeriodGranularity,
    ReportSection,
    RunDocuments,
    RunUsage,
    StageUsage,
    InquiriesBundle,
    InquiryRecord,
    GenerateInquiriesReportRequest,
)

__all__ = [
    "NOVEAI_MAGENTA",
    "NOVEAI_NAVY",
    "STATUS_COLORS",
    "AnalysisOptions",
    "BrandColors",
    "BundleWarning",
    "ChartKey",
    "ChartKind",
    "ChartSeries",
    "ChartSpec",
    "DocumentRef",
    "EntityInfo",
    "JobAccepted",
    "JobError",
    "JobState",
    "JobStatus",
    "Language",
    "Period",
    "PeriodGranularity",
    "ReportSection",
    "RunDocuments",
    "RunUsage",
    "StageUsage",
    "InquiriesBundle",
    "InquiryRecord",
    "GenerateInquiriesReportRequest",
]
