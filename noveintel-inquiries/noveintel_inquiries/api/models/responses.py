"""
``InquiriesBundle`` — everything one inquiries run produces.

The pipeline runs six stages: schema validation, rule classification, model
classification of what the rules could not settle, pattern and friction analysis,
guidebook gap analysis, and artefact generation. This is what comes out the far end.

``documents`` carries references, not content. Artefacts are uploaded to storage and
the caller fetches them from there; this service never serves file bytes, so there is
no download route to look for. That also keeps the bundle small regardless of how
large the report gets, and a caller who only wants the figures pays nothing for the
documents.

Storage is the one part of a run that can fail on its own without the rest being
worthless, so it fails softly: a failure leaves ``documents`` partial or empty and
records why in ``warnings``, rather than throwing away six stages of analysis. Check
``warnings`` before assuming everything is there.

``metrics`` is the deterministic ground truth — the classified case counts, the
distributions, the friction and gap tables as the pipeline computed them. The prose
in ``report`` is written by the model *around* those figures, so ``metrics`` is the
artefact to check the narrative against. They are both in the bundle for exactly that
reason.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .charts import ChartSpec
from .documents import DocumentRef
from .enums import Language
from .period import Period
from .usage import RunUsage

__all__ = ["BundleWarning", "RunDocuments", "InquiriesBundle"]


class BundleWarning(BaseModel):
    """Something went wrong that did not cost the run.

    Distinct from ``ErrorBody`` in ``api.errors`` on purpose: that one is a terminal
    failure and arrives instead of a bundle, this one arrives inside a successful
    result alongside everything that did work.
    """

    code: str = Field(
        description=(
            "Stable machine-readable identifier — branch on this, not on the message. "
            "'document_storage_failed' means an artefact was built but could not be "
            "stored, and is absent from ``documents``. "
            "'english_export_unavailable' means the English translation did not "
            "complete, so no English report was produced. "
            "'pricing_not_configured' means the run's tokens were counted but could "
            "not be priced. "
            "'human_review_required' means some cases could not be classified with "
            "confidence and are flagged in the workbook. "
            "'partial_analysis' means a non-fatal stage produced less than expected — "
            "an empty friction map, say — and the affected report sections are thinner."
        )
    )
    message: str = Field(description="What happened, for a log or an operator.")
    detail: Any | None = Field(
        default=None,
        description=(
            "Structured context where there is any — the count and case ids behind a "
            "'human_review_required', for instance."
        ),
    )


class RunDocuments(BaseModel):
    """The artefacts one run filed in storage.

    ``report`` keeps module 01's ``dict[Language, DocumentRef]`` shape so a consumer
    that already reads one module's documents reads this one's unchanged. The other
    two fields are this module's own: a inquiries run also emits a per-case workbook and
    the report's underlying JSON, and neither has a language pair to key on the same
    way.
    """

    report: dict[Language, DocumentRef] = Field(
        default_factory=dict,
        description=(
            "The Word reports, keyed by language. Normally both; Arabic alone when "
            "the English translation was unavailable, and a language is missing when "
            "storing it failed. ``warnings`` says which."
        ),
    )
    workbook: DocumentRef | None = Field(
        default=None,
        description=(
            "The Excel workbook of every classified case, with the audit columns the "
            "report's counts can be verified against with a COUNTIF. Null when it "
            "could not be stored."
        ),
    )
    report_data: dict[Language, DocumentRef] = Field(
        default_factory=dict,
        description=(
            "The report's underlying JSON, keyed by language — the same structure the "
            "Word document was rendered from. For a consumer that wants to render the "
            "report itself rather than hand a reader a .docx."
        ),
    )


class InquiriesBundle(BaseModel):
    """The complete output of a inquiries analysis run."""

    run_id: str = Field(
        description=(
            "Identifies this run. Quote it when reporting a problem: every log line "
            "the run produced carries it, and it appears in each stored artefact's "
            "key, so it is what ties a response, a log trail and a file on disk "
            "together. Freshly generated per call — two runs of an identical request "
            "get different ids, which is what stops a re-run overwriting documents "
            "still being fetched."
        )
    )
    period: Period = Field(description="The reporting window the run covers.")
    total_cases: int = Field(
        ge=0,
        description=(
            "Cases the run analysed, after validation. The denominator every "
            "percentage in the report is taken over."
        ),
    )
    metrics: dict[str, Any] = Field(
        description=(
            "The deterministic output of the pipeline: classified case counts and "
            "distributions, the friction map, the gap table, the validated FAQs, the "
            "notification opportunities. Every figure the report prints comes from "
            "here, and this is the artefact to check the prose against."
        )
    )
    charts: list[ChartSpec] = Field(
        default_factory=list,
        description=(
            "Renderer-agnostic specs for the report's charts. The number varies with "
            "the data, so select by ``key`` and never by position or list length."
        ),
    )
    report: dict[Language, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "The generated report as structured data, keyed by language — the nine "
            "sections with their prose, tables and chart references. This is what the "
            "Word documents were rendered from, offered directly so a consumer can "
            "render its own."
        ),
    )
    documents: RunDocuments = Field(
        default_factory=RunDocuments,
        description=(
            "Where the run's artefacts were stored. Fetch them from storage — from "
            "each reference's ``url``, or by resolving its ``container`` and ``key`` "
            "yourself. There is no download route."
        ),
    )
    usage: RunUsage = Field(
        description=(
            "What the run's Core42 calls consumed, in total and per stage. Covers the "
            "model calls only — not validation, Excel assembly or storage. ``cost`` is "
            "null when no rates are configured."
        )
    )
    warnings: list[BundleWarning] = Field(
        default_factory=list,
        description=(
            "Non-fatal problems during the run. Empty on a clean run. A caller that "
            "needs the documents should check this rather than assume they are all "
            "present."
        ),
    )
    primary_language: Language = Field(
        description=(
            "The language the caller asked for in options.language. This marks which "
            "was requested, not which was produced — check ``documents``, since an "
            "English request is still answered with an Arabic-only bundle when the "
            "translation could not be completed."
        )
    )
