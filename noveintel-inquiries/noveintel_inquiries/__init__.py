"""
NoveIntelligence — Customer Inquiries Analytics.

Turns a period's استفسارات المتعاملين cases into an analysed report. Six stages: schema
validation, rule-based classification, model classification of what the rules could
not settle, pattern and friction analysis, guidebook gap analysis, and artefact
generation — an Arabic and English Word report, their underlying JSON, and a per-case
Excel workbook.

    from noveintel_inquiries import generate_report, validate_records
    from noveintel_inquiries.api import EntityInfo, GenerateInquiriesReportRequest
    from noveintel_inquiries.storage import LocalDirectoryStore

    request = GenerateInquiriesReportRequest(records=rows, entity=EntityInfo(...))

    validate_records(request)        # cheap: stage 1 only, no model call

    bundle = await generate_report(request, store=LocalDirectoryStore("storage"))

    bundle.metrics                   # the figures the stages computed
    bundle.report["ar"]              # the report as data
    bundle.documents.report["ar"].url  # where the .docx was put
    bundle.usage.by_stage            # which stage spent what
    bundle.run_id                    # ties this to its log trail

The artefacts are uploaded rather than returned inline, so the bundle carries
references and the bytes are fetched from storage:

    data = await store.get(bundle.documents.report["ar"].key)

Over HTTP the run is asynchronous — ``POST /v1/inquiries`` returns a job to poll —
because a run takes minutes. Called as a library, ``generate_report`` is just a long
coroutine and there is no job layer in the way.

Standalone: nothing here imports from the Streamlit application it was ported from.
"""
from __future__ import annotations

from .pipeline import generate_report, new_run_id, validate_records

__all__ = ["generate_report", "new_run_id", "validate_records"]
