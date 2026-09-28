"""
The entry points: records in, a bundle out.

Two of them, and the difference matters to a caller deciding what to spend.

``validate_records`` runs stage 1 alone. No model call, no cost, a fraction of a
second — it answers "will this export be accepted?" before a caller commits to a run
that takes minutes. An async API needs this: without it the only way to discover a
missing column is to start a job and poll until it fails.

``generate_report`` runs all six stages and is the real work.

Both are thin. The analysis itself is the vendored pipeline in ``stages/``, unchanged
from the application this was ported from, and that is deliberate: the stages are the
thing under parity test, and rewriting them to fit a new shape would have thrown the
parity away. What lives here is what the port added — a run id, per-stage logging,
the tenant identity pack, usage accounting, and storing the artefacts softly.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .api.models import (
    DOCX_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    BundleWarning,
    ChartSeries,
    ChartSpec,
    EntityInfo,
    Language,
    Period,
    RunDocuments,
    RunUsage,
    StageUsage,
    ComplaintsBundle,
    GenerateComplaintsReportRequest,
    records_to_frame,
)
from .exceptions import StageFailure
from .config import get_pricing_settings
from .engine import period_from_datetimes
from .storage import DocumentStore, StorageError, build_key

__all__ = ["generate_report", "new_run_id", "validate_records"]

logger = logging.getLogger(__name__)

# The artefacts a run files, and what each is stored as.
_ARTEFACT_TYPES = {
    ".docx": DOCX_CONTENT_TYPE,
    ".xlsx": XLSX_CONTENT_TYPE,
    ".json": JSON_CONTENT_TYPE,
}


def new_run_id() -> str:
    """A fresh id for one run.

    Twelve hex characters: short enough to paste into a support ticket, wide enough
    that two runs starting in the same second do not collide. It is the job id, the
    log correlation id and part of every stored artefact's key, so one string ties a
    response, a log trail and a file on disk together.
    """
    return uuid.uuid4().hex[:12]


@contextmanager
def _step(run_id: str, description: str) -> Iterator[None]:
    """Log one step's start, end and duration, and tell cancellation from failure.

    Cancellation is separated out because it is not a fault: a job cancelled on
    shutdown would otherwise log a stack trace per stage and read like six errors.
    """
    logger.info("[%s] %s…", run_id, description)
    started = time.monotonic()
    try:
        yield
    except asyncio.CancelledError:
        logger.info(
            "[%s] %s cancelled after %.1fs.", run_id, description,
            time.monotonic() - started,
        )
        raise
    except Exception as exc:
        logger.error(
            "[%s] %s failed after %.1fs: %s",
            run_id, description, time.monotonic() - started, exc,
        )
        raise
    else:
        logger.info(
            "[%s] %s done in %.1fs.", run_id, description,
            time.monotonic() - started,
        )


# ── Tenant identity ───────────────────────────────────────────────────────────


def _materialise_branding(entity: EntityInfo, workdir: Path) -> dict[str, Any]:
    """Flatten the request's identity pack into what the document builders read.

    The logo is the awkward part. It arrives as base64 over HTTP, and the Word builder
    wants a path, so it is written into this run's own temporary directory — not a
    shared one — and torn down with it. A run therefore cannot see another run's logo
    even if both are in flight on the same worker.

    A logo that will not decode is dropped with a warning rather than failing the run.
    A cover without a logo is a cosmetic shortcoming; six stages of analysis thrown
    away over a malformed data URI is not a trade anyone would choose.
    """
    branding: dict[str, Any] = {
        "name_ar": entity.name_ar,
        "name_en": entity.name_en,
        "name_short": entity.name_short,
        "center_name_ar": entity.center_name_ar,
        "center_name_en": entity.center_name_en,
        "closing_statement": entity.closing_statement,
        "logo_path": None,
    }

    # ``brand`` is passed on ONLY when the caller actually set it, and the difference
    # matters. ``BrandColors`` defaults to the NoveAI platform palette — it is a
    # shared contract model and must not carry any one organisation's colours — but
    # the report's own design palette is neither NoveAI's nor a tenant's. So an
    # absent ``brand`` has to stay absent all the way to the builder, which then
    # renders in the design the report has always used. Sending the defaults here
    # instead would repaint every existing report in NoveAI navy.
    if "brand" in entity.model_fields_set:
        branding["brand"] = {
            "primary": entity.brand.primary,
            "secondary": entity.brand.secondary,
        }

    try:
        data = entity.logo_bytes()
    except (ValueError, OSError, binascii.Error) as exc:
        logger.warning("Ignoring an unreadable tenant logo: %s", exc)
        return branding

    if not data:
        return branding

    if entity.logo_path:
        # Already a path on this machine; the builder can read it where it is.
        branding["logo_path"] = entity.logo_path
        return branding

    logo = workdir / "logo.png"
    try:
        logo.write_bytes(data)
    except OSError as exc:
        logger.warning("Could not write the tenant logo to %s: %s", logo, exc)
        return branding

    branding["logo_path"] = str(logo)
    return branding


# ── Usage ─────────────────────────────────────────────────────────────────────


def _summarise_usage(ledger: dict[str, Any]) -> tuple[RunUsage, list[BundleWarning]]:
    """Turn the pipeline's token ledger into the contract's usage figures.

    The ledger comes from ``core42.tokens``, which the pipeline resets at the start of
    every run and appends to from every stage. Its own ``cost_usd`` is computed from
    the Core42 layer's built-in default rates; it is deliberately *not* used here.
    Cost on the contract is computed from the rates this deployment was configured
    with, and is null when there are none — an unpriced run and a free one are
    different facts, and a default rate quietly reported as truth is the way a bad
    number reaches a finance report.
    """
    pricing = get_pricing_settings()
    warnings: list[BundleWarning] = []

    input_tokens = int(ledger.get("input_tokens") or 0)
    output_tokens = int(ledger.get("output_tokens") or 0)
    calls = int(ledger.get("calls") or 0)

    def price(inp: int, out: int) -> float | None:
        if not pricing.configured:
            return None
        return (
            inp / 1_000_000 * (pricing.input_cost_per_1m or 0.0)
            + out / 1_000_000 * (pricing.output_cost_per_1m or 0.0)
        )

    if calls and not pricing.configured:
        warnings.append(
            BundleWarning(
                code="pricing_not_configured",
                message=(
                    "The run's tokens were counted but could not be priced: set "
                    "CORE42_INPUT_COST_PER_1M and CORE42_OUTPUT_COST_PER_1M. The "
                    "token figures are unaffected."
                ),
            )
        )

    by_stage: dict[str, StageUsage] = {}
    for stage, figures in (ledger.get("by_stage") or {}).items():
        stage_in = int(figures.get("input_tokens") or 0)
        stage_out = int(figures.get("output_tokens") or 0)
        by_stage[str(stage)] = StageUsage(
            calls=int(figures.get("calls") or 0),
            input_tokens=stage_in,
            output_tokens=stage_out,
            cost=price(stage_in, stage_out),
        )

    usage = RunUsage(
        tokens=input_tokens + output_tokens,
        cost=price(input_tokens, output_tokens),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        calls=calls,
        model=ledger.get("model"),
        by_stage=by_stage,
    )
    return usage, warnings


# ── Charts ────────────────────────────────────────────────────────────────────


def _collect_charts(report: dict[str, Any]) -> list[ChartSpec]:
    """Pull the chart definitions out of the generated report, keyed and typed.

    The pipeline attaches charts to the subsections that print them, so they are
    gathered by walking the report rather than read from one list. Each carries the
    ``key`` its builder stamped on it; one without a key is a chart added to a stage
    without a ``ChartKey`` member, and it is skipped rather than guessed at — a
    mislabelled chart is worse than a missing one, because a consumer renders it
    under the wrong heading.

    English titles and categories fall back to the Arabic. A chart the translation
    did not reach still renders in an English document, in Arabic, which is what the
    Word builder does too — better a legible chart than an empty frame.
    """
    from .api.models import ChartKey

    known = {key.value for key in ChartKey}
    specs: list[ChartSpec] = []
    seen: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for chart in node.get("charts") or []:
                if isinstance(chart, dict):
                    take(chart)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    def take(chart: dict[str, Any]) -> None:
        key = chart.get("key")
        if key not in known or key in seen:
            return
        seen.add(key)

        categories = [str(c) for c in (chart.get("categories") or [])]
        series = [
            ChartSeries(
                name_ar=str(s.get("name") or ""),
                name_en=str(s.get("name_en") or s.get("name") or ""),
                values=[float(v or 0) for v in (s.get("data") or [])],
            )
            for s in (chart.get("series") or [])
            if isinstance(s, dict)
        ]
        kind = str(chart.get("type") or "bar").lower()
        specs.append(
            ChartSpec(
                key=key,
                kind=kind if kind in _CHART_KINDS else "bar",
                title_ar=str(chart.get("title") or ""),
                title_en=str(chart.get("title_en") or chart.get("title") or ""),
                categories_ar=categories,
                categories_en=[
                    str(c) for c in (chart.get("categories_en") or categories)
                ],
                series=series,
                colors=[str(c) for c in (chart.get("colors") or [])],
            )
        )

    visit(report)
    return specs


_CHART_KINDS = {"bar", "column", "pie", "doughnut", "line", "stacked_bar"}


# ── Metrics ───────────────────────────────────────────────────────────────────


def _collect_metrics(state: Any) -> dict[str, Any]:
    """The deterministic ground truth, lifted off the finished pipeline state.

    This is what the porting guide's rule 3 asks for in a pipeline whose layers do not
    cleanly separate: the figures the stages computed, carried in the response so a
    reader can check the model's prose against them rather than take it on trust.

    Everything here is a count, a rate or a table the stages produced. Nothing is
    recomputed — recomputing would create a second source of truth that could
    disagree with the document, which is the problem this is meant to solve.
    """

    def dump(items: Any) -> list[dict[str, Any]]:
        """Pydantic rows to plain dicts; anything else through unchanged."""
        out: list[dict[str, Any]] = []
        for item in items or []:
            out.append(item.model_dump() if hasattr(item, "model_dump") else item)
        return out

    total = int(getattr(state, "total_cases", 0) or 0)
    classified = getattr(state, "all_classified", None) or []

    contact_types: dict[str, int] = {}
    original_types: dict[str, int] = {}
    channels: dict[str, int] = {}
    departments: dict[str, int] = {}
    for case in classified:
        actual = getattr(case, "actual_contact_type", None)
        if actual:
            contact_types[actual] = contact_types.get(actual, 0) + 1
        original = getattr(case, "case_type", None)
        if original and str(original).strip():
            original_types[original] = original_types.get(original, 0) + 1
        channel = getattr(case, "case_channel", None)
        if channel:
            channels[channel] = channels.get(channel, 0) + 1
        admin = getattr(case, "admin", None)
        if admin:
            departments[admin] = departments.get(admin, 0) + 1

    return {
        "total_cases": total,
        "classified_cases": len(classified),
        "rule_classified_count": int(getattr(state, "rule_classified_count", 0) or 0),
        "llm_queue_count": int(getattr(state, "llm_queue_count", 0) or 0),
        "human_review_count": int(getattr(state, "human_review_count", 0) or 0),
        "reclassified_count": int(getattr(state, "reclassified_count", 0) or 0),
        "reclassification_rate": float(
            getattr(state, "reclassification_rate", 0.0) or 0.0
        ),
        "contact_type_counts": contact_types,
        "original_contact_type_counts": original_types,
        "channel_counts": channels,
        "department_counts": departments,
        "patterns": dump(getattr(state, "patterns", None)),
        "journey_map": dump(getattr(state, "journey_map", None)),
        "validated_faqs": dump(getattr(state, "validated_faqs", None)),
        "gap_table": dump(getattr(state, "gap_table", None)),
        "notification_opportunities": list(
            getattr(state, "notification_opportunities", None) or []
        ),
        "proactive_notification_case_count": int(
            getattr(state, "proactive_notification_case_count", 0) or 0
        ),
        "month_year": getattr(state, "month_year", None),
        "guidebook": {
            "pages": getattr(state, "guidebook_pages", None),
            "faq_count": getattr(state, "guidebook_faq_count", None),
            "year": getattr(state, "guidebook_year", None),
            "topics": list(getattr(state, "guidebook_topics", None) or []),
        },
    }


# ── Storage ───────────────────────────────────────────────────────────────────


async def _store_artefacts(
    run_id: str,
    entity: EntityInfo,
    period: Period,
    files: dict[str, Path],
    store: DocumentStore | None,
) -> tuple[RunDocuments, list[BundleWarning]]:
    """Upload what the run produced, and survive not being able to.

    Storage is the one part of a run that can fail on its own without the rest being
    worthless — six stages of analysis are still six stages of analysis — so a failure
    here is a warning inside a successful result, never an exception. The porting
    guide's rule 4, and the reason ``documents`` can come back partial.

    Uploads run concurrently: there are up to five files and they are independent.
    """
    documents = RunDocuments()
    warnings: list[BundleWarning] = []

    if store is None:
        warnings.append(
            BundleWarning(
                code="document_storage_failed",
                message=(
                    "No document store is configured, so the run's artefacts were not "
                    "kept. The analysis is complete and is in this result; the files "
                    "are not retrievable. Check the service log from startup."
                ),
                detail={"artefacts": sorted(files)},
            )
        )
        return documents, warnings

    async def upload(slot: str, path: Path) -> tuple[str, Any]:
        data = await asyncio.to_thread(path.read_bytes)
        key = build_key(entity, period, run_id, path.name)
        return slot, await store.put(
            key, data, _ARTEFACT_TYPES.get(path.suffix, "application/octet-stream")
        )

    pending = [
        upload(slot, path)
        for slot, path in files.items()
        if path.exists() and path.stat().st_size > 0
    ]
    results = await asyncio.gather(*pending, return_exceptions=True)

    failed: list[str] = []
    for outcome in results:
        if isinstance(outcome, BaseException):
            if isinstance(outcome, (StorageError, OSError)):
                logger.error("[%s] Could not store an artefact: %s", run_id, outcome)
                failed.append(str(outcome))
                continue
            raise outcome
        slot, ref = outcome
        if slot == "workbook":
            documents.workbook = ref
        elif slot.startswith("report_data_"):
            documents.report_data[Language(slot.rsplit("_", 1)[1])] = ref
        elif slot.startswith("report_"):
            documents.report[Language(slot.rsplit("_", 1)[1])] = ref

    if failed:
        warnings.append(
            BundleWarning(
                code="document_storage_failed",
                message=(
                    f"{len(failed)} artefact(s) were built but could not be stored "
                    "and are absent from ``documents``. The analysis in this result "
                    "is complete and unaffected."
                ),
                detail={"failures": failed},
            )
        )
    return documents, warnings


# ── Entry points ──────────────────────────────────────────────────────────────


def validate_records(request: GenerateComplaintsReportRequest) -> dict[str, Any]:
    """Run stage 1 alone and report what it found. No model call, no cost.

    This exists because the work route is asynchronous. Without it, the only way for a
    caller to learn that its export is missing a column is to start a job, wait, and
    read the failure off a poll — which is a poor way to discover a typo. This answers
    the same question in milliseconds.

    Raises ``ValueError`` when stage 1 rejects the data, which the route renders as
    ``400 unprocessable_records``.
    """
    from .stages.stage1_validator import run_stage1
    from .stages.state import PipelineState

    frame = records_to_frame(request.records)
    state = run_stage1(PipelineState(), frame)

    period: Period | None = None
    period_error: str | None = None
    try:
        period = _resolve_period(request)
    except ValueError as exc:
        period_error = str(exc)

    return {
        "total_cases": int(getattr(state, "total_cases", 0) or 0),
        "columns": list(getattr(state, "original_columns", None) or frame.columns),
        "schema": getattr(state, "validated_schema", None) or {},
        "period": period,
        "period_error": period_error,
    }


def _resolve_period(request: GenerateComplaintsReportRequest) -> Period:
    """The reporting window, from whichever date field this flow records."""
    values = [
        getattr(record, "date_opened", None) for record in request.records
    ]
    return period_from_datetimes(
        [v for v in values if v], request.options.granularity
    )


async def generate_report(
    request: GenerateComplaintsReportRequest,
    *,
    store: DocumentStore | None = None,
    progress: Callable[..., None] | None = None,
    run_id: str | None = None,
) -> ComplaintsBundle:
    """Run all six stages and return the bundle.

    Synchronous work on a thread: the stages are ordinary blocking code that fans out
    with ``ThreadPoolExecutor`` internally, so running them inline on the event loop
    would stall every other request this worker is serving.

    ``progress`` is the orchestrator's own callback signature — ``(fraction,
    message_ar, message_en)`` — and is called from that worker thread. The job layer
    bridges it back onto the loop; a library caller can pass anything callable, or
    nothing.

    Raises ``StageFailure`` when a stage reports it could not finish, and ``ValueError``
    when the data itself is unusable. Everything else — storage, pricing, a missing
    English translation — is a warning in the returned bundle.
    """
    run_id = run_id or new_run_id()
    period = _resolve_period(request)
    language = request.options.language

    logger.info(
        "[%s] Starting a complaints run: %d records, %s, english=%s.",
        run_id, len(request.records), period.label_en,
        request.options.include_english,
    )

    with tempfile.TemporaryDirectory(prefix=f"complaints-{run_id}-") as tmp:
        workdir = Path(tmp)
        branding = _materialise_branding(request.entity, workdir)

        state, warnings = await asyncio.to_thread(
            _run_stages, request, run_id, workdir, branding, progress
        )

        report: dict[Language, dict[str, Any]] = {}
        if getattr(state, "report_json", None):
            report[Language.AR] = state.report_json
        if getattr(state, "report_json_en", None):
            report[Language.EN] = state.report_json_en
        elif request.options.include_english:
            warnings.append(
                BundleWarning(
                    code="english_export_unavailable",
                    message=(
                        "The English translation did not complete, so no English "
                        "report or document was produced. The Arabic report is "
                        "unaffected. This is usually a gateway failure during the "
                        "translation pass; retrying the run is safe."
                    ),
                )
            )

        documents, store_warnings = await _store_artefacts(
            run_id, request.entity, period, _artefact_paths(workdir, report), store
        )
        warnings.extend(store_warnings)

    usage, usage_warnings = _summarise_usage(_read_ledger())
    warnings.extend(usage_warnings)

    human_review = int(getattr(state, "human_review_count", 0) or 0)
    if human_review:
        warnings.append(
            BundleWarning(
                code="human_review_required",
                message=(
                    f"{human_review} case(s) could not be classified with confidence "
                    "and are flagged for review in the workbook. They are counted in "
                    "the totals; their category is the model's best guess."
                ),
                detail={"count": human_review},
            )
        )

    charts = _collect_charts(report.get(Language.AR) or {})

    logger.info(
        "[%s] Finished: %d cases, %d chart(s), %d token(s) over %d call(s), %s.",
        run_id,
        int(getattr(state, "total_cases", 0) or 0),
        len(charts),
        usage.tokens,
        usage.calls,
        "unpriced" if usage.cost is None else f"${usage.cost:.4f}",
    )

    return ComplaintsBundle(
        run_id=run_id,
        period=period,
        total_cases=int(getattr(state, "total_cases", 0) or 0),
        metrics=_collect_metrics(state),
        charts=charts,
        report=report,
        documents=documents,
        usage=usage,
        warnings=warnings,
        primary_language=language,
    )


def _artefact_paths(workdir: Path, report: dict[Language, dict]) -> dict[str, Path]:
    """Which files the run produced, by the slot each occupies in ``RunDocuments``."""
    files = {
        "report_ar": workdir / "report_ar.docx",
        "workbook": workdir / "cases.xlsx",
        "report_data_ar": workdir / "report_ar_data.json",
    }
    if Language.EN in report:
        files["report_en"] = workdir / "report_ar_en.docx"
        files["report_data_en"] = workdir / "report_ar_data_en.json"
    return files


def _read_ledger() -> dict[str, Any]:
    """This run's token ledger from the vendored Core42 layer."""
    from .core42 import token_summary

    try:
        return token_summary()
    except Exception as exc:  # the ledger is diagnostics; never fail a run for it
        logger.warning("Could not read the token ledger: %s", exc)
        return {}


def _run_stages(
    request: GenerateComplaintsReportRequest,
    run_id: str,
    workdir: Path,
    branding: dict[str, Any],
    progress: Callable[..., None] | None,
) -> tuple[Any, list[BundleWarning]]:
    """Drive the six stages to completion. Blocking — always called on a thread.

    The orchestrator reports each stage as ``(success, message)`` rather than raising,
    so a failure has to be turned into one. ``StageFailure`` carries the stage name,
    which is what an operator asks for first and what the job record surfaces as
    ``error.stage``.

    ``initialize_state`` is called before the run and not after: it clears any state
    file left behind by a previous run under the same id. Stale state carried into
    stage 6 was a real defect in the application this was ported from — a failed
    stage 4 left an empty friction map that the next run then reported as fact.
    """
    from .stages.orchestrator import PipelineOrchestrator

    warnings: list[BundleWarning] = []

    with _step(run_id, "Building the input frame"):
        frame = records_to_frame(request.records)

    orchestrator = PipelineOrchestrator(
        api_key=_core42_key(), temp_dir=str(workdir / "state")
    )
    orchestrator.initialize_state(run_id)

    # Set after initialisation, which replaces the state object wholesale.
    orchestrator.state.branding = branding

    with _step(run_id, "Running stages 1-6"):
        results = orchestrator.run_full_pipeline(
            df=frame,
            excel_path=str(workdir / "cases.xlsx"),
            word_path=str(workdir / "report_ar.docx"),
            language="ar",
            progress_callback=progress,
            include_english=request.options.include_english,
            methodology_path=_methodology_path(),
        )

    if not results.get("success"):
        stage, message = _first_failure(results)
        raise StageFailure(stage, message)

    # A stage that succeeded but produced less than it should have is reported rather
    # than hidden: the affected report sections are thinner, and a reader comparing
    # the document against the metrics deserves to know why.
    state = orchestrator.state
    if not getattr(state, "journey_map", None):
        warnings.append(
            BundleWarning(
                code="partial_analysis",
                message=(
                    "Stage 4 found no friction points, so the customer-journey "
                    "section is thinner than usual. This is expected on a small or "
                    "very uniform export and is not a failure."
                ),
                detail={"missing": "journey_map"},
            )
        )

    return state, warnings


def _first_failure(results: dict[str, Any]) -> tuple[str, str]:
    """Name the stage that failed and what it said.

    The orchestrator returns every stage it attempted, so the first unsuccessful one
    is the cause and anything after it never ran. Falling back to the errors list
    covers a failure recorded before any stage was entered.
    """
    for stage, outcome in (results.get("stages") or {}).items():
        if not outcome.get("success"):
            return str(stage), str(outcome.get("message") or "The stage failed.")
    errors = results.get("errors") or ["The pipeline failed before any stage ran."]
    return "unknown", str(errors[0])


def _methodology_path() -> str | None:
    """The complaints methodology document the orchestrator loads before stage 1.

    Vendored into the package at ``resources/`` so it ships with the deployment
    rather than being looked up relative to a checkout. Returns ``None`` when it is
    absent: the orchestrator treats the methodology as optional and logs a warning,
    and a run without it produces a report whose methodology section is thinner —
    which is better than refusing to run at all.
    """
    candidate = (
        Path(__file__).parent / "resources" / "complaints-management-methodology-v4.json"
    )
    return str(candidate) if candidate.exists() else None


def _core42_key() -> str:
    """The gateway credential the stages expect to be handed.

    The vendored Core42 client reads its own configuration from the environment and
    ignores what it is given, but the orchestrator's stages still take an ``api_key``
    argument and several check it for emptiness before doing work. Reading it from
    the same settings keeps that check honest rather than passing a placeholder that
    would let a misconfigured deployment fail deep inside stage 6 instead of at
    startup.
    """
    from .core42 import get_settings as core42_settings

    return core42_settings().api_key
