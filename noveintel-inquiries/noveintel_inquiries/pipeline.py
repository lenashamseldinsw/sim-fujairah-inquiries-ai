"""
The entry points: a request in, a bundle out.

``validate_records`` parses only — no model call, no cost — and answers "will this be
accepted, and what will the run see?" before a caller commits to minutes of work.

``generate_report`` runs the three layers (Prerequisites §0):

    parse ─► classify (rules → model → review; X8: root causes → umbrellas)
          ─► analyse (frictions, FAQs, notifications, guidebook gaps)
          ─► compute (every number, on frozen labels)
          ─► narrate (AR and EN, prose only, checked against the numbers)
          ─► assemble S0–S11 ─► Word ×2, report JSON ×2, workbook, per-case labels

What lives here besides the wiring: the run id, per-step logging, the tenant identity
pack, usage accounting, failure classification, and storing artefacts softly.
"""
from __future__ import annotations

import asyncio
import binascii
import json
import logging
import re
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from .api.models import (
    DOCX_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    BundleWarning,
    ChartKey,
    ChartSeries,
    ChartSpec,
    ClassificationSummary,
    DeepReview,
    EntityInfo,
    GenerateInquiriesReportRequest,
    InquiriesBundle,
    Language,
    Period,
    ReportNarratives,
    RunDocuments,
    RunUsage,
    StageUsage,
    UmbrellaProposal,
    missing_required_fields,
)
from .api.models.enums import SECTION_IDS, ReportSection
from .api.models.narratives import hidden_fields
from .config import get_pricing_settings
from .engine.period import period_from_datetimes
from .exceptions import MissingInputs, StageFailure, UpstreamFailure
from .storage import DocumentStore, StorageError, build_key

__all__ = ["generate_report", "new_run_id", "validate_records", "check_inputs", "resolve_period"]

logger = logging.getLogger(__name__)

_ARTEFACT_TYPES = {".docx": DOCX_CONTENT_TYPE, ".xlsx": XLSX_CONTENT_TYPE, ".json": JSON_CONTENT_TYPE}
_REVIEW_IDS_INLINE = 500


def new_run_id() -> str:
    """Twelve hex characters: the job id, the log correlation id and part of every key."""
    return uuid.uuid4().hex[:12]


@contextmanager
def _step(run_id: str, description: str) -> Iterator[None]:
    logger.info("[%s] %s…", run_id, description)
    started = time.monotonic()
    try:
        yield
    except asyncio.CancelledError:
        logger.info("[%s] %s cancelled after %.1fs.", run_id, description, time.monotonic() - started)
        raise
    except Exception as exc:
        logger.error("[%s] %s failed after %.1fs: %s", run_id, description, time.monotonic() - started, exc)
        raise
    else:
        logger.info("[%s] %s done in %.1fs.", run_id, description, time.monotonic() - started)


# ── Inputs ────────────────────────────────────────────────────────────────────


def check_inputs(request: GenerateInquiriesReportRequest) -> None:
    """Refuse a request missing a required column, setting or the taxonomy."""
    missing = missing_required_fields(request)
    if missing:
        raise MissingInputs(missing)


def resolve_period(request: GenerateInquiriesReportRequest) -> Period:
    """The reporting window from the opening dates. ``ValueError`` when none is readable."""
    values = [r.opened_datetime for r in request.records if r.opened_datetime]
    return period_from_datetimes(values, request.options.granularity)


def _vocabulary(request: GenerateInquiriesReportRequest) -> dict[str, dict[str, str]]:
    from .engine.wording import DEFAULT_VOCABULARY

    supplied = request.reference_lists.vocabulary
    if supplied is None:
        return {k: dict(v) for k, v in DEFAULT_VOCABULARY.items()}
    return {"ar": dict(supplied.ar), "en": dict(supplied.en)}


# ── Tenant identity ───────────────────────────────────────────────────────────


def _materialise_branding(entity: EntityInfo, workdir: Path) -> dict[str, Any]:
    """The identity pack as the renderers read it. A bad logo is dropped, not fatal."""
    branding: dict[str, Any] = {
        "name_ar": entity.name_ar,
        "name_en": entity.name_en,
        "name_short": entity.name_short,
        "center_name_ar": entity.center_name_ar,
        "center_name_en": entity.center_name_en,
        "brand": {"primary": entity.brand.primary, "secondary": entity.brand.secondary},
        "logo_path": None,
    }
    try:
        data = entity.logo_bytes()
    except (ValueError, OSError, binascii.Error) as exc:
        logger.warning("Ignoring an unreadable tenant logo: %s", exc)
        return branding
    if not data:
        return branding
    if entity.logo_path:
        branding["logo_path"] = entity.logo_path
        return branding
    logo = workdir / "logo.png"
    try:
        logo.write_bytes(data)
        branding["logo_path"] = str(logo)
    except OSError as exc:
        logger.warning("Could not write the tenant logo to %s: %s", logo, exc)
    return branding


# ── Usage ─────────────────────────────────────────────────────────────────────


def _summarise_usage(ledger: dict[str, Any]) -> tuple[RunUsage, list[BundleWarning]]:
    """Tokens and cost, priced from this deployment's configured rates (or null)."""
    pricing = get_pricing_settings()
    warnings: list[BundleWarning] = []
    input_tokens = int(ledger.get("input_tokens") or 0)
    output_tokens = int(ledger.get("output_tokens") or 0)
    calls = int(ledger.get("calls") or 0)

    def price(inp: int, out: int) -> float | None:
        if not pricing.configured:
            return None
        return inp / 1_000_000 * (pricing.input_cost_per_1m or 0.0) + out / 1_000_000 * (pricing.output_cost_per_1m or 0.0)

    if calls and not pricing.configured:
        warnings.append(BundleWarning(
            code="pricing_not_configured",
            message="The run's tokens were counted but could not be priced: set CORE42_INPUT_COST_PER_1M "
                    "and CORE42_OUTPUT_COST_PER_1M. The token figures are unaffected.",
        ))
    by_stage = {
        str(stage): StageUsage(
            calls=int(f.get("calls") or 0),
            input_tokens=int(f.get("input_tokens") or 0),
            output_tokens=int(f.get("output_tokens") or 0),
            cost=price(int(f.get("input_tokens") or 0), int(f.get("output_tokens") or 0)),
        )
        for stage, f in (ledger.get("by_stage") or {}).items()
    }
    return RunUsage(
        tokens=input_tokens + output_tokens, cost=price(input_tokens, output_tokens),
        input_tokens=input_tokens, output_tokens=output_tokens, calls=calls,
        model=ledger.get("model"), by_stage=by_stage,
    ), warnings


# ── Charts ────────────────────────────────────────────────────────────────────


def _collect_charts(report: dict[str, Any]) -> list[ChartSpec]:
    """Every chart the report places, as renderer-agnostic specs, by key."""
    known = {k.value for k in ChartKey}
    specs: list[ChartSpec] = []
    seen: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for chart in node.get("charts") or []:
                key = chart.get("key")
                if key in known and key not in seen:
                    seen.add(key)
                    specs.append(ChartSpec(
                        key=key,
                        kind=chart.get("type", "bar"),
                        output_id=chart.get("output_id"),
                        title_ar=chart.get("title_ar", ""),
                        title_en=chart.get("title_en", ""),
                        categories_ar=chart.get("categories_ar", []),
                        categories_en=chart.get("categories_en", []),
                        series=[ChartSeries(name_ar=s.get("name_ar", ""), name_en=s.get("name_en", ""),
                                            values=[float(v or 0) for v in s.get("data", [])]) for s in chart.get("series", [])],
                        colors=chart.get("colors", []),
                    ))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(report)
    return specs


# ── Storage ───────────────────────────────────────────────────────────────────


async def _store_artefacts(run_id: str, entity: EntityInfo, period: Period, files: dict[str, Path],
                           store: DocumentStore | None) -> tuple[RunDocuments, list[BundleWarning]]:
    """Upload what the run produced. A storage failure is a warning, never a lost run."""
    documents = RunDocuments()
    warnings: list[BundleWarning] = []
    if store is None:
        warnings.append(BundleWarning(
            code="document_storage_failed",
            message="No document store is configured, so the run's artefacts were not kept. The analysis "
                    "is complete and is in this result; the files are not retrievable.",
            detail={"artefacts": sorted(files)},
        ))
        return documents, warnings

    async def upload(slot: str, path: Path):
        data = await asyncio.to_thread(path.read_bytes)
        key = build_key(entity, period, run_id, path.name)
        return slot, await store.put(key, data, _ARTEFACT_TYPES.get(path.suffix, "application/octet-stream"))

    pending = [upload(slot, p) for slot, p in files.items() if p.exists() and p.stat().st_size > 0]
    failed: list[str] = []
    for outcome in await asyncio.gather(*pending, return_exceptions=True):
        if isinstance(outcome, BaseException):
            if isinstance(outcome, (StorageError, OSError)):
                logger.error("[%s] Could not store an artefact: %s", run_id, outcome)
                failed.append(str(outcome))
                continue
            raise outcome
        slot, ref = outcome
        if slot == "workbook":
            documents.workbook = ref
        elif slot == "labels":
            documents.labels = ref
        elif slot.startswith("report_data_"):
            documents.report_data[Language(slot.rsplit("_", 1)[1])] = ref
        elif slot.startswith("report_"):
            documents.report[Language(slot.rsplit("_", 1)[1])] = ref
    if failed:
        warnings.append(BundleWarning(
            code="document_storage_failed",
            message=f"{len(failed)} artefact(s) were built but could not be stored and are absent from "
                    "``documents``. The analysis in this result is complete and unaffected.",
            detail={"failures": failed},
        ))
    return documents, warnings


# ── Validation ────────────────────────────────────────────────────────────────


def validate_records(request: GenerateInquiriesReportRequest) -> dict[str, Any]:
    """Parse only. No model call, no cost.

    Raises ``MissingInputs`` for a missing required field and ``ValueError`` when no
    opening date is readable — the same refusals a run would hit, found in milliseconds.
    """
    from .engine.parse import parse_records

    _tolerate_arabic_output()
    check_inputs(request)
    period = resolve_period(request)
    parsed = parse_records(request.records, request.settings,
                           (request.entity.name_ar, request.entity.name_en, request.entity.name_short or ""))
    return {
        "total_cases": parsed.log.in_scope_total,
        "period": period,
        "parse_log": parsed.log.as_dict(),
        "taxonomy": request.reference_lists.taxonomy if isinstance(request.reference_lists.taxonomy, str)
        else (request.reference_lists.taxonomy.id or "tenant catalogue"),
        "root_cause_extraction": request.settings.root_cause_extraction,
    }


# ── The run ───────────────────────────────────────────────────────────────────


@dataclass
class _RunOutput:
    metrics: dict[str, Any]
    narratives: dict[Language, ReportNarratives]
    reports: dict[Language, dict[str, Any]]
    classification: ClassificationSummary
    snapshot: dict[str, Any]
    files: dict[str, Path]
    warnings: list[BundleWarning] = field(default_factory=list)
    total_cases: int = 0


async def generate_report(
    request: GenerateInquiriesReportRequest,
    *,
    store: DocumentStore | None = None,
    progress: Callable[..., None] | None = None,
    run_id: str | None = None,
) -> InquiriesBundle:
    """Run the analysis and return the bundle.

    Raises ``MissingInputs`` / ``ValueError`` when the request cannot be analysed,
    ``UpstreamFailure`` when the model gateway failed the run, and ``StageFailure`` when
    a step could not finish for another reason. Everything else — storage, pricing, an
    English report that could not be written — is a warning in the bundle.
    """
    check_inputs(request)
    run_id = run_id or new_run_id()
    period = resolve_period(request)
    language = request.options.language
    logger.info("[%s] Starting an inquiries run: %d records, %s, english=%s, root causes=%s.",
                run_id, len(request.records), period.label_en, request.options.include_english,
                request.settings.root_cause_extraction)

    with tempfile.TemporaryDirectory(prefix=f"inquiries-{run_id}-") as tmp:
        workdir = Path(tmp)
        branding = _materialise_branding(request.entity, workdir)
        output, ledger = await asyncio.to_thread(_run_scoped, request, run_id, period, workdir, branding, progress)
        documents, store_warnings = await _store_artefacts(run_id, request.entity, period, output.files, store)

    warnings = output.warnings + store_warnings
    usage, usage_warnings = _summarise_usage(ledger)
    warnings += usage_warnings
    charts = _collect_charts(output.reports.get(Language.AR) or {})
    from .api.models import PeriodSnapshot

    logger.info("[%s] Finished: %d cases, %d chart(s), %d token(s) over %d call(s).",
                run_id, output.total_cases, len(charts), usage.tokens, usage.calls)
    return InquiriesBundle(
        run_id=run_id,
        period=period,
        total_cases=output.total_cases,
        metrics=output.metrics,
        narratives=output.narratives,
        classification=output.classification,
        charts=charts,
        report=output.reports,
        documents=documents,
        snapshot=PeriodSnapshot.model_validate(output.snapshot),
        usage=usage,
        warnings=warnings,
        primary_language=language,
    )


def _read_ledger() -> dict[str, Any]:
    from .core42 import token_summary

    try:
        return token_summary()
    except Exception as exc:
        logger.warning("Could not read the token ledger: %s", exc)
        return {}


def _tolerate_arabic_output() -> None:
    """Let stdout/stderr carry Arabic on a cp1252 Windows stream."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if encoding.replace("-", "").replace("_", "") == "utf8":
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass


def _run_scoped(request, run_id, period, workdir, branding, progress):
    """The blocking run, inside its own token ledger."""
    from .core42.tokens import run_scope

    from .jobs.runner import RunAbandoned

    _tolerate_arabic_output()
    with run_scope():
        try:
            output = _run(request, run_id, period, workdir, branding, progress)
        except (StageFailure, MissingInputs, ValueError, RunAbandoned):
            raise
        except Exception as exc:
            stage = getattr(exc, "_stage", "pipeline")
            logger.exception("[%s] %s failed", run_id, stage)
            if int(_read_ledger().get("gateway_failures") or 0):
                raise UpstreamFailure(stage) from exc
            raise StageFailure(stage, _caller_safe(stage, run_id)) from exc
        return output, _read_ledger()


def _caller_safe(stage: str, run_id: str) -> str:
    """Exception text can carry a fragment of a record; the caller gets the run id instead."""
    return f"{stage} failed with an internal error. The detail is in the service log under run id {run_id}."


@contextmanager
def _named(stage: str) -> Iterator[None]:
    try:
        yield
    except (StageFailure, MissingInputs):
        raise
    except Exception as exc:
        try:
            exc._stage = stage  # type: ignore[attr-defined]
        except AttributeError:
            pass
        raise


def _run(request: GenerateInquiriesReportRequest, run_id: str, period: Period, workdir: Path,
         branding: dict[str, Any], progress: Callable[..., None] | None) -> _RunOutput:
    from .analysis.analyse import analyse, guidebook_meta
    from .classification.classify import classify_cases, group_umbrellas
    from .core42.tokens import ScopedThreadPoolExecutor
    from .engine.compute import ComputeInputs, Umbrella, compute
    from .engine.frameworks import evaluate_frameworks
    from .engine.localize import Localizer, missing_catalogue_english
    from .engine.parse import parse_records
    from .engine.taxonomy import load_taxonomy
    from .engine.wording import PROVENANCE
    from .narratives.context import build_context
    from .narratives.translate import translate_labels
    from .narratives.writer import combine, translate_part, write_narratives
    from .report.assemble import assemble_report
    from .report.labels import SECTION_TITLES
    from .report.word import build_document
    from .report.workbook import write_workbook

    # Two stages report at once from here on (umbrellas beside the analysis, the
    # translation beside the documents), so progress only ever moves forward.
    progress_lock = threading.Lock()
    reached = [0.0]

    def report(fraction: float, ar: str, en: str) -> None:
        if not progress:
            return
        with progress_lock:
            if fraction < reached[0]:
                return
            reached[0] = fraction
        progress(fraction, ar, en)

    settings = request.settings
    refs = request.reference_lists
    entity = request.entity
    warnings: list[BundleWarning] = []
    vocab = _vocabulary(request)

    # ── Layer 1a: parse ───────────────────────────────────────────────────────
    report(0.05, "التحقق من البيانات وتنقيتها", "Stage 1: Parsing and cleansing the cases")
    with _step(run_id, "Parsing"), _named("parsing"):
        parsed = parse_records(request.records, settings, (entity.name_ar, entity.name_en, entity.name_short or ""))
        cases = parsed.cases
        if not cases:
            raise ValueError(
                "No case remained after removing rows without a case id, duplicates and cases outside the "
                f"case-type scope ({parsed.log.scope}). The parse log: {json.dumps(parsed.log.as_dict(), ensure_ascii=False)[:600]}"
            )
        tax = load_taxonomy(refs.taxonomy)

    # ── Layer 2: classify ─────────────────────────────────────────────────────
    carried = [
        Umbrella(id=u.id, name_ar=u.name_ar, name_en=u.name_en or "", meaning_ar=u.meaning_ar or "",
                 meaning_en=u.meaning_en or "", carried=True)
        for u in (refs.umbrellas.umbrellas if refs.umbrellas else [])
    ]
    report(0.1, "تصنيف الحالات", "Stage 2: Classifying the cases")
    with _step(run_id, "Classification"), _named("classification"):
        classified = classify_cases(cases, tax, settings, entity_name=entity.name_en, carried_umbrellas=carried,
                                    progress=report)
        if classified.routed_to_model and classified.model_unavailable == classified.routed_to_model:
            if int(_read_ledger().get("gateway_failures") or 0):
                raise UpstreamFailure("classification")
            raise StageFailure("classification", "The model returned no usable classification for any routed case.")

    # ── Which sections the tenant asked for, and what they need ───────────────
    shown = _resolve_sections(request.options.sections, settings, warnings)
    needs = _analysis_needed(shown)

    # ── Umbrellas and the qualitative analysis, side by side ──────────────────
    # The analysis needs the labels and the root causes, never the umbrellas, so the
    # umbrella grouping (sequential chunks) runs alongside it rather than before it.
    report(0.44, "تحليل رحلة المتعامل وتجميع الحزم", "Stage 3: Analysis and umbrella discovery")
    with _step(run_id, "Analysis and umbrella discovery"), ScopedThreadPoolExecutor(max_workers=2) as pool:
        umbrella_job = pool.submit(_staged, "classification", group_umbrellas, cases, classified, tax, settings,
                                   progress=report)
        analysis_job = pool.submit(_staged, "analysis", analyse, cases, entity=entity.name_en, vocabulary=vocab,
                                   faq_catalogue=refs.faq_catalogue, guidebook=refs.guidebook, progress=report,
                                   journey=needs["journey"], faqs=needs["faqs"], gaps=needs["gaps"])
        analysis = analysis_job.result()
        umbrella_job.result()
    umbrellas = classified.umbrellas
    for message in analysis.warnings + classified.warnings:
        warnings.append(BundleWarning(code="partial_analysis", message=message))

    # ── Layer 1b: compute ─────────────────────────────────────────────────────
    report(0.62, "احتساب المؤشرات", "Stage 4: Computing the figures")
    with _step(run_id, "Computing"), _named("computing"):
        frameworks = evaluate_frameworks(cases, settings, set(parsed.log.columns_mapped) - set(parsed.log.columns_present_but_empty))
        metrics = compute(ComputeInputs(
            cases=cases, settings=settings, taxonomy=tax, period=period, parse_log=parsed.log, reference=refs,
            history=request.history, umbrellas=umbrellas,
            umbrella_set_version=(refs.umbrellas.version if refs.umbrellas else None),
            frameworks=frameworks, entity_name_ar=entity.name_ar, entity_name_en=entity.name_en,
        ))
        metrics["JOURNEY_MAP"] = analysis.frictions
        metrics["NOTIFICATION_OPPORTUNITIES"] = analysis.notifications
        metrics["VALIDATED_FAQS"] = [
            {k: v for k, v in q.items() if k != "keywords"} | {"evidence_case_ids": q["evidence_case_ids"][:20]}
            for q in analysis.faqs
        ]
        metrics["GAP_TABLE"] = analysis.gaps
        metrics["PATTERNS"] = analysis.patterns
        if analysis.guidebook:
            metrics["GUIDEBOOK"] = analysis.guidebook
        metrics["CLASSIFICATION_QUALITY"]["routed_to_model"] = classified.routed_to_model
        metrics["CLASSIFICATION_QUALITY"]["model_unavailable"] = classified.model_unavailable
        snapshot = metrics.pop("_SNAPSHOT")

    sources = _initiative_sources(metrics, umbrellas)

    # ── English availability (Domain 01 ruling) ───────────────────────────────
    printed = list(metrics["MAIN_SERVICE"]["labels"]) + list(metrics["SUB_CLASS"]["labels"])
    missing_en = missing_catalogue_english(tax, printed)
    english_on = False
    if request.options.include_english:
        if missing_en:
            warnings.append(BundleWarning(
                code="english_export_unavailable",
                message="The taxonomy has no English name for some services the report prints, so the "
                        "English report is unavailable (Domain 01 ruling). Add name_en to the catalogue.",
                detail={"missing_english_names": missing_en[:50]},
            ))
        else:
            english_on = True

    sections_present = [x for x in _sections_present(metrics, settings) if x in shown]
    shown = [ReportSection.COVER] + sections_present
    hidden = hidden_fields(shown)
    ar_loc = Localizer("ar", tax, umbrellas, {})
    sources_en = [{**x, "name": x["name_en"] or x["name_ar"]} for x in sources]

    # ── Layer 3: the Arabic narrative; each part's translation starts as soon as
    #    that part is final, while the other part is still being written ────────
    translation_pool = ScopedThreadPoolExecutor(max_workers=2)
    translation_jobs: dict[str, Any] = {}
    english_side: dict[str, Any] = {}
    side_lock = threading.Lock()
    labels_job = None

    def english() -> dict[str, Any]:
        """The English localizer, context and glossary — built once, when first needed."""
        with side_lock:
            if not english_side:
                translations = labels_job.result() if labels_job else {}
                for u in umbrellas:
                    if not u.name_en and u.name_ar in translations:
                        u.name_en = translations[u.name_ar]
                en_loc = Localizer("en", tax, umbrellas, translations)
                english_side.update(
                    translations=translations, loc=en_loc,
                    context=build_context(
                        metrics, "en", en_loc, entity_name=entity.name_en, vision=entity.closing_statement,
                        sections=[SECTION_TITLES[x]["en"] for x in sections_present],
                        vocabulary=vocab["en"], initiative_sources=sources,
                    ) if english_on else None,
                    glossary=_glossary(metrics, tax, umbrellas, translations, entity, period, ar_loc, en_loc)
                    if english_on else {},
                )
            return english_side

    def start_translation(part_outcome) -> None:
        side = english()
        report(0.78, "ترجمة التقرير إلى الإنجليزية", "Stage 5: Writing the narrative; translating the finished parts")
        translation_jobs[part_outcome.part] = translation_pool.submit(
            _staged, "translation", translate_part, part_outcome.part, part_outcome.data,
            context=side["context"], glossary=side["glossary"], vocabulary=vocab["en"], sources=sources_en,
        )

    report(0.68, "كتابة التحليلات السردية", "Stage 5: Writing the narrative")
    try:
        with _step(run_id, "Arabic narrative and label translation"), ScopedThreadPoolExecutor(max_workers=2) as pool:
            context_ar = build_context(
                metrics, "ar", ar_loc, entity_name=entity.name_ar, vision=entity.closing_statement,
                sections=[SECTION_TITLES[x]["ar"] for x in sections_present],
                vocabulary=vocab["ar"], initiative_sources=sources,
            )
            labels_job = pool.submit(
                _staged, "narratives", translate_labels, _labels_to_translate(metrics, umbrellas, tax)
            ) if english_on else None
            narrative_job = pool.submit(
                _staged, "narratives", write_narratives, context_ar,
                root_causes=bool(metrics.get("BUNDLE")), vocabulary=vocab["ar"],
                sources=[{**x, "name": x["name_ar"]} for x in sources], hidden=hidden,
                on_part=start_translation if english_on else None,
            )
            outcome_ar = narrative_job.result()
            side = english()
        en_loc = side["loc"]
    except BaseException:
        translation_pool.shutdown(wait=False, cancel_futures=True)
        raise

    if outcome_ar.narratives is None:
        translation_pool.shutdown(wait=False, cancel_futures=True)
        if int(_read_ledger().get("gateway_failures") or 0):
            raise UpstreamFailure("narratives")
        raise StageFailure("narratives", "The Arabic narrative could not be written. The detail is in the service log under run id " + run_id + ".")
    narratives: dict[Language, ReportNarratives] = {Language.AR: outcome_ar.narratives}
    _narrative_warnings(warnings, "ar", outcome_ar)

    # ── Assemble and render — the Arabic side while the translation runs ──────
    report(0.82, "إعداد التقارير والملفات", "Stage 6: Building the documents")
    try:
        with _step(run_id, "Assembling the documents"), _named("documents"):
            gb_meta = guidebook_meta(refs.guidebook) if refs.guidebook else None
            sources_meta = {
                "taxonomy": {"label": tax.label, "main_services": len(tax.main_names), "sub_classifications": len(tax.sub_names)},
                "guidebook": gb_meta,
                "faq_catalogue": len(refs.faq_catalogue or []),
                "transactions": {"rows": len(refs.transactions), "total": sum(r.total_requests for r in refs.transactions if r.counts_in_denominator)} if refs.transactions else None,
                "umbrella_set": {"count": len(refs.umbrellas.umbrellas), "version": refs.umbrellas.version} if refs.umbrellas and refs.umbrellas.umbrellas else None,
            }
            new_umbrellas = [u for u in umbrellas if u.new]
            method = {
                "frozen": classified.frozen.cases_with_frozen_labels, "routed": classified.routed_to_model,
                "corrected": classified.corrected + classified.root_cause_fixes,
                "duplicates": classified.duplicates_reused, "deep_reviewed": classified.deep_reviewed,
                "low_confidence": classified.low_confidence,
                "root_causes": bool(metrics.get("BUNDLE")), "umbrellas": len(umbrellas), "new_umbrellas": len(new_umbrellas),
            }
            umbrella_meta = [
                {"id": u.id, "order": i, "meaning_ar": u.meaning_ar, "meaning_en": u.meaning_en}
                for i, u in enumerate(umbrellas)
            ]
            primary, secondary = entity.brand.primary, entity.brand.secondary
            reports: dict[Language, dict[str, Any]] = {}
            files: dict[str, Path] = {}

            def render(lang: Language, narr: ReportNarratives, loc: Localizer) -> None:
                data = assemble_report(
                    lang=lang.value, metrics=metrics, narratives=narr, loc=loc, en_loc=en_loc,
                    entity=entity, period=period, settings=settings, method=method, sources_meta=sources_meta,
                    initiative_sources=sources, umbrella_meta=umbrella_meta, primary=primary, secondary=secondary,
                    branding=branding, shown=shown,
                )
                reports[lang] = data
                json_path = workdir / f"report_{lang.value}_data.json"
                json_path.write_text(json.dumps({k: v for k, v in data.items() if k != "branding"}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                docx_path = workdir / f"report_{lang.value}.docx"
                build_document(data, docx_path)
                files[f"report_{lang.value}"] = docx_path
                files[f"report_data_{lang.value}"] = json_path

            render(Language.AR, outcome_ar.narratives, ar_loc)
            names = {u.id: u.name_ar for u in umbrellas}
            workbook_path = workdir / "cases.xlsx"
            # Owner names are staff names: carried only when agent-level reporting (X9) is on.
            workbook_columns = [
                c for c in parsed.log.columns_mapped
                if c not in ("owner", "resolved_by") or settings.agent_level_reporting
            ]
            write_workbook(workbook_path, cases, workbook_columns, metrics, names, primary)
            files["workbook"] = workbook_path
            labels_path = workdir / "labels.json"
            labels_path.write_text(json.dumps(_labels_document(run_id, cases, tax, settings, umbrellas, refs), ensure_ascii=False, default=str), encoding="utf-8")
            files["labels"] = labels_path

            if english_on:
                with _step(run_id, "Waiting for the English translation"):
                    parts = {part: job.result() for part, job in translation_jobs.items()}
                outcome_en = combine(parts) if len(parts) == 2 else None
                if outcome_en is None or outcome_en.narratives is None:
                    warnings.append(BundleWarning(
                        code="english_export_unavailable",
                        message="The English translation did not complete, so no English report was produced. "
                                "The Arabic report is unaffected; retrying the run is safe.",
                    ))
                else:
                    narratives[Language.EN] = outcome_en.narratives
                    _narrative_warnings(warnings, "en", outcome_en)
                    render(Language.EN, outcome_en.narratives, en_loc)
    finally:
        translation_pool.shutdown(wait=True, cancel_futures=True)
    queue = [c for c in cases if c.low_confidence]

    # ── Warnings worth surfacing ──────────────────────────────────────────────
    if queue:
        warnings.append(BundleWarning(
            code="low_confidence_after_review",
            message=f"{len(queue)} case(s) stayed below the review threshold ({settings.review_threshold}) even "
                    "after the deep AI review. They are counted with their best available labels, the methodology "
                    "states how many, and the per-case labels document flags each one.",
            detail={"count": len(queue)},
        ))
    if new_umbrellas:
        warnings.append(BundleWarning(
            code="umbrellas_pending_confirmation",
            message=f"{len(new_umbrellas)} umbrella(s) were proposed this run and await the Domain Admin's "
                    "confirmation; send the confirmed set back as reference_lists.umbrellas next period.",
            detail={"umbrellas": [u.name_ar for u in new_umbrellas]},
        ))
    if not refs.guidebook:
        warnings.append(BundleWarning(code="section_omitted", message="No service guidebook was provided, so the S5 digital-gap table is omitted.",
                                      detail={"section": "S5.1", "input": "reference_lists.guidebook"}))
    not_computable = [i for i in frameworks if i["status"] == "not_computable"]
    if not_computable:
        warnings.append(BundleWarning(
            code="metric_gap",
            message=f"{len(not_computable)} framework indicator(s) cannot be computed from this export; the report "
                    "recommends enabling the field rather than printing a value.",
            detail={"indicators": [f"{i['framework']}:{i['key']}" for i in not_computable]},
        ))

    classification = ClassificationSummary(
        taxonomy=tax.label, llm_threshold=settings.llm_threshold, review_threshold=settings.review_threshold,
        provenance={PROVENANCE.get(k, k): v for k, v in _count(c.provenance for c in cases).items() if k},
        mean_confidence=metrics["CLASSIFICATION_QUALITY"]["mean_confidence"],
        deep_review=DeepReview(
            reviewed=classified.deep_reviewed, low_confidence=len(queue),
            duplicates_reused=classified.duplicates_reused,
            low_confidence_case_ids=[c.case_id for c in queue[:_REVIEW_IDS_INLINE]],
            truncated=len(queue) > _REVIEW_IDS_INLINE,
        ),
        umbrella_set_version=refs.umbrellas.version if refs.umbrellas else None,
        umbrellas=[
            UmbrellaProposal(
                id=u.id, name_ar=u.name_ar, name_en=u.name_en or u.name_ar, meaning_ar=u.meaning_ar,
                meaning_en=u.meaning_en, cases=sum(1 for c in cases if c.bundle == u.id), new=u.new,
                member_root_causes=[rc for rc, _ in _count(c.root_cause for c in cases if c.bundle == u.id and c.root_cause).most_common(5)],
            )
            for u in umbrellas
        ] if metrics.get("BUNDLE") else [],
    )
    report(1.0, "اكتمل التحليل", "Stage 6: Analysis complete")
    return _RunOutput(metrics=metrics, narratives=narratives, reports=reports, classification=classification,
                      snapshot=snapshot, files=files, warnings=warnings, total_cases=len(cases))


def _staged(stage: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run ``fn`` on a worker thread, tagging any failure with its stage name."""
    with _named(stage):
        return fn(*args, **kwargs)


def _narrative_warnings(warnings: list[BundleWarning], lang: str, outcome) -> None:
    """What the narrative checks left standing, as caller-facing warnings."""
    if outcome.unverified:
        warnings.append(BundleWarning(
            code="narrative_unverified_figures",
            message=f"The {'Arabic' if lang == 'ar' else 'English'} narrative still carries figure(s) that are not in "
                    "the engine output after a corrective retry. Check them before publishing.",
            detail={"language": lang, "figures": outcome.unverified[:50]},
        ))
    if outcome.incomplete:
        warnings.append(BundleWarning(
            code="narrative_incomplete",
            message=f"The model left {len(outcome.incomplete)} {'Arabic' if lang == 'ar' else 'English'} narrative "
                    "field(s) unwritten even after a retry; they are empty in the report.",
            detail={"language": lang, "fields": outcome.incomplete},
        ))


def _glossary(metrics: dict[str, Any], tax, umbrellas, translations: dict[str, str], entity: EntityInfo,
              period: Period, ar_loc, en_loc) -> dict[str, str]:
    """Arabic term → the English the report already prints for it.

    The translation is told to use these exactly, so a service, umbrella, friction or
    table label reads the same in the English prose as in the English tables beside it.
    The translator receives only the entries its text contains.
    """
    from .engine.wording import CONTACT_TYPE_EN, PROVENANCE, PROVENANCE_EN, TIMELINESS_LABELS
    from .narratives.prompts import FIXED_TERMS_EN

    glossary: dict[str, str] = dict(FIXED_TERMS_EN)
    glossary.update(CONTACT_TYPE_EN)
    glossary.update({PROVENANCE[k]: PROVENANCE_EN[k] for k in PROVENANCE})
    glossary.update({v["ar"]: v["en"] for v in TIMELINESS_LABELS.values()})
    for name in list(tax.main_names) + list(tax.sub_names):
        if tax.en(name):
            glossary[name] = tax.en(name)
    for u in umbrellas:
        if u.name_en:
            glossary[u.name_ar] = u.name_en
    glossary.update({k: v for k, v in translations.items() if v})
    pairs = (
        ("JOURNEY_MAP", "name_ar", "name_en"),
        ("GAP_TABLE", "topic_ar", "topic_en"),
        ("NOTIFICATION_OPPORTUNITIES", "type_ar", "type_en"),
        ("VALIDATED_FAQS", "question_ar", "question_en"),
    )
    for key, ar_field, en_field in pairs:
        for row in metrics.get(key) or []:
            if row.get(ar_field) and row.get(en_field):
                glossary[row[ar_field]] = row[en_field]
    for key in ("CHANNEL", "DEPARTMENT", "SEVERITY"):
        for label in (metrics.get(key) or {}).get("labels", []):
            english = en_loc.name(label)
            if label and english and english != label:
                glossary[str(label)] = english
    if entity.name_ar and entity.name_en:
        glossary[entity.name_ar] = entity.name_en
    glossary[period.label_ar] = period.label_en
    return {k: v for k, v in glossary.items() if k and v and k != v}


def _count(values):
    from collections import Counter

    return Counter(values)


def _initiative_sources(metrics: dict[str, Any], umbrellas) -> list[dict[str, Any]]:
    """What an initiative or a use case may cite, each with its engine count."""
    sources: list[dict[str, Any]] = []
    if metrics.get("BUNDLE"):
        names = {u.id: u for u in umbrellas}
        for uid, count in zip(metrics["BUNDLE"]["ids"], metrics["BUNDLE"]["values"]):
            u = names.get(uid)
            sources.append({"id": uid, "kind": "bundle", "name_ar": u.name_ar if u else uid, "name_en": (u.name_en if u else "") or "", "cases": count})
    for f in metrics.get("JOURNEY_MAP", []):
        sources.append({"id": f["id"], "kind": "friction", "name_ar": f.get("name_ar", ""), "name_en": f.get("name_en", ""), "cases": f["case_count"]})
    for g in metrics.get("GAP_TABLE", []):
        sources.append({"id": g["id"], "kind": "gap", "name_ar": g.get("topic_ar", ""), "name_en": g.get("topic_en", ""), "cases": g["case_count"]})
    for n in metrics.get("NOTIFICATION_OPPORTUNITIES", []):
        sources.append({"id": n["id"], "kind": "notification", "name_ar": n.get("type_ar", ""), "name_en": n.get("type_en", ""), "cases": n["cases_eliminated"]})
    for q in metrics.get("VALIDATED_FAQS", [])[:10]:
        sources.append({"id": q["id"], "kind": "faq", "name_ar": q.get("question_ar", ""), "name_en": q.get("question_en", ""), "cases": q["frequency"]})
    rec = metrics.get("RECLASSIFICATION", {})
    if rec.get("count"):
        sources.append({"id": "RECLASSIFICATION", "kind": "reclassification", "name_ar": "الحالات القابلة لإعادة التصنيف الذكي",
                        "name_en": "Cases eligible for smart re-classification", "cases": rec["count"]})
    for i, event in enumerate(metrics.get("EVENTS", []), 1):
        sources.append({"id": f"E{i}", "kind": "event", "name_ar": f"{event['cluster']} — {event['month']}",
                        "name_en": f"{event['cluster']} — {event['month_en']}", "cases": event["to"]})
    return sources


def _labels_to_translate(metrics: dict[str, Any], umbrellas, tax) -> list[str]:
    labels: list[str] = []
    if metrics.get("ROOT_CAUSE_TOP"):
        labels += metrics["ROOT_CAUSE_TOP"]["labels"]
        for block in metrics["ROOT_CAUSE_TOP"]["per_bundle"].values():
            labels += block["labels"]
    labels += [u.name_ar for u in umbrellas if not u.name_en]
    for key in ("DEPARTMENT", "SEVERITY"):
        if metrics.get(key):
            labels += metrics[key]["labels"]
    for event in metrics.get("EVENTS", []):
        labels.append(event["cluster"])
    if metrics.get("RECORDED_VS_TRUE", {}).get("by_tag"):
        labels += [x["tag"] for x in metrics["RECORDED_VS_TRUE"]["by_tag"]]
    catalogue = set(tax.main_names) | set(tax.sub_names)
    return [x for x in labels if x and x not in catalogue and re.search(r"[؀-ۿ]", x)]


_ROOT_SECTIONS = (ReportSection.ROOT_CAUSES, ReportSection.SERVICE_FOCUS)

# What each section needs from the qualitative analysis — directly, or through the
# sections it is built from (Definition Sheet §6 relations: S1 ← S3, S4, S5;
# S5 → S6, S7, S8, S9; S6 → S8). The guidebook gaps are drawn from the journey's
# frictions, so a section needing gaps needs the journey too.
_SECTION_NEEDS: dict[ReportSection, set[str]] = {
    ReportSection.EXECUTIVE_SUMMARY: {"journey", "gaps"},
    ReportSection.CUSTOMER_JOURNEY: {"journey"},
    ReportSection.DIGITAL_GAPS: {"journey", "gaps", "faqs"},
    ReportSection.DIGITAL_TRANSFORMATION: {"journey", "gaps", "faqs"},
    ReportSection.AI_USE_CASES: {"journey", "gaps"},
    ReportSection.IMPROVEMENT_ROADMAP: {"journey", "gaps", "faqs"},
    ReportSection.CONCLUSION: {"journey", "gaps"},
}


def _resolve_sections(requested, settings, warnings: list[BundleWarning]) -> list[ReportSection]:
    """The tenant's section list, in report order; the cover always; S10–S11 only with X8."""
    wanted = set(requested) if requested else set(ReportSection)
    wanted.add(ReportSection.COVER)
    if not settings.root_cause_extraction:
        asked = [s for s in _ROOT_SECTIONS if requested and s in wanted]
        if asked:
            warnings.append(BundleWarning(
                code="section_omitted",
                message="Root-cause sections were requested but root-cause extraction (X8) is off, so they are left out.",
                detail={"sections": [SECTION_IDS[s] for s in asked], "input": "settings.root_cause_extraction"},
            ))
        wanted -= set(_ROOT_SECTIONS)
    return [s for s in ReportSection if s in wanted]


def _analysis_needed(shown: list[ReportSection]) -> dict[str, bool]:
    needed: set[str] = set()
    for section in shown:
        needed |= _SECTION_NEEDS.get(section, set())
    return {item: item in needed for item in ("journey", "faqs", "gaps")}


def _sections_present(metrics: dict[str, Any], settings) -> list[ReportSection]:
    present = [s for s in ReportSection if s not in (ReportSection.COVER, ReportSection.ROOT_CAUSES, ReportSection.SERVICE_FOCUS)]
    if metrics.get("BUNDLE"):
        present += [ReportSection.ROOT_CAUSES, ReportSection.SERVICE_FOCUS]
    return present


def _labels_document(run_id, cases, tax, settings, umbrellas, refs) -> dict[str, Any]:
    """Per-case labels — what the platform stores, and sends back frozen next period."""
    from .engine.wording import PROVENANCE

    names = {u.id: u for u in umbrellas}
    return {
        "run_id": run_id,
        "taxonomy": tax.label,
        "llm_threshold": settings.llm_threshold,
        "review_threshold": settings.review_threshold,
        "umbrella_set_version": refs.umbrellas.version if refs.umbrellas else None,
        "umbrellas": [{"id": u.id, "name_ar": u.name_ar, "name_en": u.name_en, "new": u.new} for u in umbrellas],
        "cases": [
            {
                "case_id": c.case_id,
                "label_contact_type": c.contact_type,
                "label_true_type": c.true_type,
                "label_main_service": c.main_service,
                "label_sub_classification": c.sub_classification,
                "label_reason": c.reason or c.evidence,
                "misclassified": c.misclassified,
                "label_confidence": c.confidence,
                "label_provenance": PROVENANCE.get(c.provenance or "", c.provenance),
                "label_root_cause": c.root_cause,
                "label_bundle": names[c.bundle].name_ar if c.bundle in names else c.bundle,
                "bundle_id": c.bundle,
                "deep_reviewed": c.deep_reviewed,
                "low_confidence": c.low_confidence,
                "duplicate_of": c.duplicate_of,
                "faq_id": c.faq_id,
                "corrections": c.corrections,
            }
            for c in cases
        ],
    }
