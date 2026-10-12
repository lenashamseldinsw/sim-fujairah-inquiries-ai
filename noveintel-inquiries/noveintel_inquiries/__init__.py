"""
NoveIntelligence — Customer Inquiries Analytics (Domain Analytics 03).

Turns a period's customer-inquiry cases into an analysed report, in three layers
(Prerequisites §0):

1. **Parser + engine** (``engine/``) — cleans the cases and computes every number,
   on frozen labels. Pure code.
2. **Classifier** (``classification/``) — labels each case (contact type, main
   service, sub-classification, and with X8 a root cause and umbrella) under the
   tenant's taxonomy and the codebooks, with confidence and provenance; routes the
   uncertain ones to review.
3. **Narrative writer** (``narratives/``) — writes prose around the engine's figures
   and never a figure of its own.

``analysis/`` finds the qualitative items the nine-section report tables — journey
frictions, FAQ candidates, notification opportunities, guidebook gaps — and the
engine counts them. ``report/`` assembles S0–S11 and renders the Word reports and the
companion workbook.

    from noveintel_inquiries import generate_report, validate_records

    validate_records(request)        # parse only: no model call, no cost
    bundle = await generate_report(request, store=store)

    bundle.metrics["KPI"]            # the engine's figures
    bundle.narratives["ar"]          # the prose, per language
    bundle.documents.report["ar"]    # where the .docx was put

Over HTTP a run is asynchronous — ``POST /v1/inquiries`` returns a job to poll.
"""
from __future__ import annotations

from typing import Any

__all__ = ["generate_report", "new_run_id", "validate_records"]


def __getattr__(name: str) -> Any:
    # Lazy, so importing the contract (``api.models``) never pulls in pandas or the
    # pipeline — a caller building a request needs neither.
    if name in __all__:
        from . import pipeline

        return getattr(pipeline, name)
    raise AttributeError(name)
