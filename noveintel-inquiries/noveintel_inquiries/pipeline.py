"""
The entry points: a request in, a bundle out.

``validate_records`` parses only — no model call, no cost — and answers "will this be
accepted, and what will the run see?" before a caller commits to minutes of work.

``generate_report`` runs the three layers (Prerequisites §0):

    parse ─► classify (rules → model → review; X8: root causes → umbrellas)
          ─► analyse (frictions, notifications, guidebook gaps)
             + detect FAQs, after the umbrellas (questions and catalogue coverage, as labels)
          ─► compute (every number, on frozen labels)
          ─► narrate (AR and EN, prose only, checked against the numbers)
          ─► assemble the shown sections ─► Word ×2, report JSON ×2, workbook, per-case labels

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

from .models import (
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
from .models.enums import ReportSection
from . import sections
from .config import get_pricing_settings
from .engine.period import period_from_datetimes
from .exceptions import MissingInputs, RunAbandoned, StageFailure, UpstreamFailure
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
    from .models import PeriodSnapshot

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
    """The stages in order. The analysis runs beside umbrella discovery, the figures and
    the early narrative; the English translation runs beside the Arabic documents."""
    from .core42.tokens import ScopedThreadPoolExecutor

    run = _Run(request, run_id, period, workdir, branding, progress)
    run.parse()
    run.classify()
    run.choose_sections()

    # Two workers: the journey analysis from stage 3, FAQ detection once the umbrellas exist.
    analysis_pool = ScopedThreadPoolExecutor(max_workers=2)
    translation_pool = ScopedThreadPoolExecutor(max_workers=4)
    try:
        analysis_job = run.start_analysis(analysis_pool)
        run.discover_umbrellas()
        faq_job = run.start_faqs(analysis_pool)
        run.compute()
        run.settle_sections()
        outcome_ar = run.narrate(analysis_job, faq_job, translation_pool)
    except BaseException:
        analysis_pool.shutdown(wait=False, cancel_futures=True)
        translation_pool.shutdown(wait=False, cancel_futures=True)
        raise
    analysis_pool.shutdown(wait=False)

    if outcome_ar.narratives is None:
        translation_pool.shutdown(wait=False, cancel_futures=True)
        if int(_read_ledger().get("gateway_failures") or 0):
            raise UpstreamFailure("narratives")
        raise StageFailure("narratives", "The Arabic narrative could not be written. The detail is in the service log under run id " + run_id + ".")
    try:
        run.render(outcome_ar)
    finally:
        translation_pool.shutdown(wait=True, cancel_futures=True)
    return run.output()


class _Run:
    """One run's state, handed from stage to stage.

    Each method is a stage of ``_run`` and sets what the later ones read. Two stages
    report at once from stage 3 on (umbrellas beside the analysis, the translation
    beside the documents), so progress only ever moves forward.
    """

    def __init__(self, request: GenerateInquiriesReportRequest, run_id: str, period: Period, workdir: Path,
                 branding: dict[str, Any], progress: Callable[..., None] | None) -> None:
        self.request, self.run_id, self.period, self.workdir, self.branding = request, run_id, period, workdir, branding
        self.settings = request.settings
        self.refs = request.reference_lists
        self.entity = request.entity
        self.vocab = _vocabulary(request)
        self.warnings: list[BundleWarning] = []
        self._progress = progress
        self._progress_lock = threading.Lock()
        self._reached = 0.0

    def report(self, fraction: float, ar: str, en: str) -> None:
        if not self._progress:
            return
        with self._progress_lock:
            if fraction < self._reached:
                return
            self._reached = fraction
        self._progress(fraction, ar, en)

    # ── Layer 1a: parse ───────────────────────────────────────────────────────

    def parse(self) -> None:
        from .engine.parse import parse_records
        from .engine.taxonomy import load_taxonomy

        entity = self.entity
        self.report(0.05, "التحقق من البيانات وتنقيتها", "Stage 1: Parsing and cleansing the cases")
        with _step(self.run_id, "Parsing"), _named("parsing"):
            self.parsed = parse_records(self.request.records, self.settings, (entity.name_ar, entity.name_en, entity.name_short or ""))
            self.cases = self.parsed.cases
            if not self.cases:
                raise ValueError(
                    "No case remained after removing rows without a case id, duplicates and cases outside the "
                    f"case-type scope ({self.parsed.log.scope}). The parse log: {json.dumps(self.parsed.log.as_dict(), ensure_ascii=False)[:600]}"
                )
            self.tax = load_taxonomy(self.refs.taxonomy)

    # ── Layer 2: classify ─────────────────────────────────────────────────────

    def classify(self) -> None:
        from .classification.classify import classify_cases
        from .engine.compute import Umbrella

        carried = [
            Umbrella(id=u.id, name_ar=u.name_ar, name_en=u.name_en or "", meaning_ar=u.meaning_ar or "",
                     meaning_en=u.meaning_en or "", carried=True)
            for u in (self.refs.umbrellas.umbrellas if self.refs.umbrellas else [])
        ]
        self.report(0.1, "تصنيف الحالات", "Stage 2: Classifying the cases")
        with _step(self.run_id, "Classification"), _named("classification"):
            classified = classify_cases(self.cases, self.tax, self.settings, entity_name=self.entity.name_en,
                                        carried_umbrellas=carried, progress=self.report)
            if classified.routed_to_model and classified.model_unavailable == classified.routed_to_model:
                if int(_read_ledger().get("gateway_failures") or 0):
                    raise UpstreamFailure("classification")
                raise StageFailure("classification", "The model returned no usable classification for any routed case.")
        self.classified = classified

    def choose_sections(self) -> None:
        """Which sections the tenant asked for, and what they need from the analysis."""
        self.shown = sections.resolve(self.request.options.sections, self.settings, self.warnings)
        self.needs = sections.analysis_needed(self.shown)

    # ── Stage 3: the qualitative analysis, in the background ──────────────────
    # Only the sections in ``sections.SECTIONS`` that declare an analysis item use it.
    # Everything else — umbrella grouping, the figures, and the narrative of the sections
    # that do not need it — goes ahead without waiting.

    def start_analysis(self, pool) -> Any:
        from .analysis.analyse import analyse

        self.report(0.44, "تحليل رحلة المتعامل وتجميع الحزم", "Stage 3: Analysis and umbrella discovery")
        return pool.submit(
            _staged, "analysis", analyse, self.cases, entity=self.entity.name_en, vocabulary=self.vocab,
            guidebook=self.refs.guidebook, progress=self.report,
            journey=self.needs["journey"], gaps=self.needs["gaps"],
        )

    # ── Stage 3b: FAQ detection — needs the umbrellas, so it starts after them ─

    def start_faqs(self, pool) -> Any:
        """Section 04's questions and coverage, beside compute and the early narrative.

        Only when a shown section prints FAQs (Section 04, the roadmap). Its labels are
        written on the cases; ``narrate`` sums them once the job is in.
        """
        from .analysis.faqs import detect_faqs

        if not self.needs["faqs"]:
            return None
        return pool.submit(
            _staged, "analysis", detect_faqs, self.cases, umbrellas=self.umbrellas, settings=self.settings,
            catalogue=self.refs.faq_catalogue, guidebook=self.refs.guidebook, entity=self.entity.name_en,
            vocabulary=self.vocab, progress=self.report,
        )

    def discover_umbrellas(self) -> None:
        from .classification.classify import group_umbrellas

        with _step(self.run_id, "Umbrella discovery"):
            _staged("classification", group_umbrellas, self.cases, self.classified, self.tax, self.settings,
                    progress=self.report)
        self.umbrellas = self.classified.umbrellas

    # ── Layer 1b: compute — needs the umbrellas, never the analysis ───────────

    def compute(self) -> None:
        from .analysis.analyse import recurring_patterns
        from .engine.compute import ComputeInputs, compute
        from .engine.frameworks import evaluate_frameworks

        refs, log = self.refs, self.parsed.log
        self.report(0.62, "احتساب المؤشرات", "Stage 4: Computing the figures")
        with _step(self.run_id, "Computing"), _named("computing"):
            self.frameworks = evaluate_frameworks(self.cases, self.settings, set(log.columns_mapped) - set(log.columns_present_but_empty))
            metrics = compute(ComputeInputs(
                cases=self.cases, settings=self.settings, taxonomy=self.tax, period=self.period, parse_log=log,
                reference=refs, history=self.request.history, umbrellas=self.umbrellas,
                umbrella_set_version=(refs.umbrellas.version if refs.umbrellas else None),
                frameworks=self.frameworks, entity_name_ar=self.entity.name_ar, entity_name_en=self.entity.name_en,
            ))
            metrics["PATTERNS"] = recurring_patterns(self.cases)
            metrics["CLASSIFICATION_QUALITY"]["routed_to_model"] = self.classified.routed_to_model
            metrics["CLASSIFICATION_QUALITY"]["model_unavailable"] = self.classified.model_unavailable
            self.snapshot = metrics.pop("_SNAPSHOT")
        # The figures without the analysis: frozen from here on, so the early narrative
        # and its translation read a dict nothing else writes to.
        self.metrics_early = metrics
        self.metrics = metrics

    def settle_sections(self) -> None:
        """English availability, and the sections this run can actually produce."""
        from .engine.localize import Localizer, missing_catalogue_english

        metrics = self.metrics_early
        # English availability (Domain 01 ruling).
        printed = list(metrics["MAIN_SERVICE"]["labels"]) + list(metrics["SUB_CLASS"]["labels"])
        missing_en = missing_catalogue_english(self.tax, printed)
        self.english_on = False
        if self.request.options.include_english:
            if missing_en:
                self.warnings.append(BundleWarning(
                    code="english_export_unavailable",
                    message="The taxonomy has no English name for some services the report prints, so the "
                            "English report is unavailable (Domain 01 ruling). Add name_en to the catalogue.",
                    detail={"missing_english_names": missing_en[:50]},
                ))
            else:
                self.english_on = True

        self.shown = sections.present(self.shown, metrics)
        body = [k for k in self.shown if k != ReportSection.COVER]
        self.titles = {lang: [sections.section(k).title[lang] for k in body] for lang in ("ar", "en")}
        self.root_causes = bool(metrics.get("BUNDLE")) and any(sections.section(k).needs_bundles for k in self.shown)
        self.ar_loc = Localizer("ar", self.tax, self.umbrellas, {})

    # ── Layer 3: the Arabic narrative ─────────────────────────────────────────

    def narrate(self, analysis_job, faq_job, translation_pool) -> Any:
        """The Arabic narrative in three calls, each translated the moment it is final.

        Groups A and B need no analysis and start at once; group C (``sections.LATE_GROUP``)
        waits for it. ``self.metrics`` becomes the full figures once the analysis is in.
        """
        from .core42.tokens import ScopedThreadPoolExecutor
        from .narratives.translate import translate_labels
        from .narratives.writer import combine, write_narratives

        vocab = self.vocab
        calls = sections.narrative_calls(self.shown)
        english = _English(self, translation_pool)
        english.add_stage("early", self.metrics_early, [])

        self.report(0.68, "كتابة التحليلات السردية", "Stage 5: Writing the narrative")
        with _step(self.run_id, "Arabic narrative"), ScopedThreadPoolExecutor(max_workers=3) as pool:
            to_translate = _labels_to_translate(self.metrics_early, self.umbrellas, self.tax, self.shown)
            if self.english_on and to_translate:
                english.labels_job = pool.submit(_staged, "narratives", translate_labels, to_translate)
            early_job = pool.submit(
                _staged, "narratives", write_narratives, self.arabic_context(self.metrics_early, []),
                root_causes=self.root_causes, vocabulary=vocab["ar"], sources=[], hidden=calls["early_hidden"],
                groups=calls["early_groups"], on_part=english.translator("early"),
            )

            with _step(self.run_id, "Waiting for the analysis"):
                analysis = analysis_job.result()
                faqs = self._faq_result(faq_job)
            self.analysis, self.faqs = analysis, faqs
            for message in analysis.warnings + faqs.warnings + self.classified.warnings:
                self.warnings.append(BundleWarning(code="partial_analysis", message=message))
            # The full figures: a new dict, so the early narrative's never changes under it.
            self.metrics = {
                **self.metrics_early,
                "JOURNEY_MAP": analysis.frictions,
                "NOTIFICATION_OPPORTUNITIES": analysis.notifications,
                "VALIDATED_FAQS": [q | {"evidence_case_ids": q["evidence_case_ids"][:20]} for q in faqs.priority],
                **_faq_figures(faqs),
                "GAP_TABLE": analysis.gaps,
                "PATTERNS": analysis.patterns,
                **({"GUIDEBOOK": analysis.guidebook} if analysis.guidebook else {}),
            }
            self.sources = _initiative_sources(self.metrics, self.umbrellas)
            english.add_stage("late", self.metrics, self.sources)
            late_job = pool.submit(
                _staged, "narratives", write_narratives, self.arabic_context(self.metrics, self.sources),
                root_causes=self.root_causes, vocabulary=vocab["ar"],
                sources=[{**x, "name": x["name_ar"]} for x in self.sources], hidden=calls["late_hidden"],
                on_part=english.translator("late"),
            )
            early, late = early_job.result(), late_job.result()
        self.english = english
        self.en_loc = english.side("late")["loc"]
        return combine(early.units + late.units)

    def _faq_result(self, faq_job) -> Any:
        """The FAQ job's result; a failure leaves Section 04 without FAQs, with a warning."""
        from .analysis.faqs import FaqResult

        if faq_job is None:
            return FaqResult()
        try:
            return faq_job.result()
        except RunAbandoned:
            raise
        except Exception as exc:
            logger.warning("[%s] FAQ detection failed: %s", self.run_id, exc)
            for case in self.cases:
                case.faq_id = case.faq_status = case.faq_match = None
            return FaqResult(warnings=[f"FAQ detection failed ({type(exc).__name__}); Section 04 has no FAQ figures."])

    def arabic_context(self, metrics: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
        from .narratives.context import build_context

        return sections.prune_context(build_context(
            metrics, "ar", self.ar_loc, entity_name=self.entity.name_ar, vision=self.entity.closing_statement,
            sections=self.titles["ar"], vocabulary=self.vocab["ar"], initiative_sources=sources,
        ), self.shown)

    # ── Assemble and render — the Arabic side while the translation runs ──────

    def render(self, outcome_ar) -> None:
        from .analysis.analyse import guidebook_meta
        from .narratives.writer import combine
        from .report.workbook import write_workbook

        _narrative_warnings(self.warnings, "ar", outcome_ar)
        self.narratives: dict[Language, ReportNarratives] = {Language.AR: outcome_ar.narratives}
        self.reports: dict[Language, dict[str, Any]] = {}
        self.files: dict[str, Path] = {}
        refs, tax, umbrellas, classified = self.refs, self.tax, self.umbrellas, self.classified

        self.report(0.82, "إعداد التقارير والملفات", "Stage 6: Building the documents")
        with _step(self.run_id, "Assembling the documents"), _named("documents"):
            gb_meta = guidebook_meta(refs.guidebook) if refs.guidebook else None
            self.sources_meta = {
                "taxonomy": {"label": tax.label, "main_services": len(tax.main_names), "sub_classifications": len(tax.sub_names)},
                "guidebook": gb_meta,
                "faq_catalogue": len(refs.faq_catalogue or []),
                "transactions": {"rows": len(refs.transactions), "total": sum(r.total_requests for r in refs.transactions if r.counts_in_denominator)} if refs.transactions else None,
                "umbrella_set": {"count": len(refs.umbrellas.umbrellas), "version": refs.umbrellas.version} if refs.umbrellas and refs.umbrellas.umbrellas else None,
            }
            self.new_umbrellas = [u for u in umbrellas if u.new]
            self.method = {
                "frozen": classified.frozen.cases_with_frozen_labels, "routed": classified.routed_to_model,
                "corrected": classified.corrected + classified.root_cause_fixes,
                "duplicates": classified.duplicates_reused, "deep_reviewed": classified.deep_reviewed,
                "low_confidence": classified.low_confidence,
                "root_causes": bool(self.metrics.get("BUNDLE")), "umbrellas": len(umbrellas), "new_umbrellas": len(self.new_umbrellas),
            }
            self.umbrella_meta = [
                {"id": u.id, "order": i, "meaning_ar": u.meaning_ar, "meaning_en": u.meaning_en}
                for i, u in enumerate(umbrellas)
            ]

            self._render(Language.AR, outcome_ar.narratives, self.ar_loc)
            names = {u.id: u.name_ar for u in umbrellas}
            workbook_path = self.workdir / "cases.xlsx"
            # Owner names are staff names: carried only when agent-level reporting (X9) is on.
            workbook_columns = [
                c for c in self.parsed.log.columns_mapped
                if c not in ("owner", "resolved_by") or self.settings.agent_level_reporting
            ]
            write_workbook(workbook_path, self.cases, workbook_columns, self.metrics, names, self.entity.brand.primary)
            self.files["workbook"] = workbook_path
            labels_path = self.workdir / "labels.json"
            labels_path.write_text(json.dumps(_labels_document(self.run_id, self.cases, tax, self.settings, umbrellas, refs),
                                              ensure_ascii=False, default=str), encoding="utf-8")
            self.files["labels"] = labels_path

            if self.english_on:
                with _step(self.run_id, "Waiting for the English translation"):
                    translated = [job.result() for job in self.english.jobs]
                # Complete only when every Arabic unit came back translated.
                outcome_en = combine(translated) if len(translated) == len(outcome_ar.units) else None
                if outcome_en is None or outcome_en.narratives is None:
                    self.warnings.append(BundleWarning(
                        code="english_export_unavailable",
                        message="The English translation did not complete, so no English report was produced. "
                                "The Arabic report is unaffected; retrying the run is safe.",
                    ))
                else:
                    self.narratives[Language.EN] = outcome_en.narratives
                    _narrative_warnings(self.warnings, "en", outcome_en)
                    self._render(Language.EN, outcome_en.narratives, self.en_loc)

    def _render(self, lang: Language, narr: ReportNarratives, loc) -> None:
        from .report.assemble import assemble_report
        from .report.word import build_document

        data = assemble_report(
            lang=lang.value, metrics=self.metrics, narratives=narr, loc=loc, en_loc=self.en_loc,
            entity=self.entity, period=self.period, settings=self.settings, method=self.method,
            sources_meta=self.sources_meta, initiative_sources=self.sources, umbrella_meta=self.umbrella_meta,
            primary=self.entity.brand.primary, secondary=self.entity.brand.secondary,
            branding=self.branding, shown=self.shown,
        )
        self.reports[lang] = data
        json_path = self.workdir / f"report_{lang.value}_data.json"
        json_path.write_text(json.dumps({k: v for k, v in data.items() if k != "branding"}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        docx_path = self.workdir / f"report_{lang.value}.docx"
        build_document(data, docx_path)
        self.files[f"report_{lang.value}"] = docx_path
        self.files[f"report_data_{lang.value}"] = json_path

    # ── The result ────────────────────────────────────────────────────────────

    def output(self) -> _RunOutput:
        from .engine.wording import PROVENANCE

        cases, settings, refs, warnings = self.cases, self.settings, self.refs, self.warnings
        classified, umbrellas, metrics = self.classified, self.umbrellas, self.metrics
        queue = [c for c in cases if c.low_confidence]

        # Warnings worth surfacing.
        if queue:
            warnings.append(BundleWarning(
                code="low_confidence_after_review",
                message=f"{len(queue)} case(s) stayed below the review threshold ({settings.review_threshold}) even "
                        "after the deep AI review. They are counted with their best available labels, the methodology "
                        "states how many, and the per-case labels document flags each one.",
                detail={"count": len(queue)},
            ))
        if self.new_umbrellas:
            warnings.append(BundleWarning(
                code="umbrellas_pending_confirmation",
                message=f"{len(self.new_umbrellas)} umbrella(s) were proposed this run and await the Domain Admin's "
                        "confirmation; send the confirmed set back as reference_lists.umbrellas next period.",
                detail={"umbrellas": [u.name_ar for u in self.new_umbrellas]},
            ))
        if "digital_gaps" in self.shown and not refs.guidebook:
            warnings.append(BundleWarning(
                code="section_omitted",
                message="No service guidebook was provided, so the S5 digital-gap table is omitted.",
                detail={"section": "S5.1", "input": "reference_lists.guidebook"},
            ))
        not_computable = [i for i in self.frameworks if i["status"] == "not_computable"]
        if not_computable:
            warnings.append(BundleWarning(
                code="metric_gap",
                message=f"{len(not_computable)} framework indicator(s) cannot be computed from this export; the report "
                        "recommends enabling the field rather than printing a value.",
                detail={"indicators": [f"{i['framework']}:{i['key']}" for i in not_computable]},
            ))

        classification = ClassificationSummary(
            taxonomy=self.tax.label, llm_threshold=settings.llm_threshold, review_threshold=settings.review_threshold,
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
        self.report(1.0, "اكتمل التحليل", "Stage 6: Analysis complete")
        return _RunOutput(metrics=metrics, narratives=self.narratives, reports=self.reports, classification=classification,
                          snapshot=self.snapshot, files=self.files, warnings=warnings, total_cases=len(cases))


class _English:
    """The English side of the narrative: each finished Arabic unit is translated at once.

    Built lazily and once — the localizer when the first unit needs it (it waits for
    the label translations), and per stage ("early", "late") its context and glossary.
    Units finish on the writer's threads, hence the lock.
    """

    def __init__(self, run: _Run, pool) -> None:
        self.run = run
        self.pool = pool
        self.labels_job: Any = None
        self.jobs: list[Any] = []
        self._stages: dict[str, dict[str, Any]] = {}
        self._side: dict[str, Any] = {}
        self._lock = threading.Lock()

    def add_stage(self, stage: str, metrics: dict[str, Any], sources: list[dict[str, Any]]) -> None:
        self._stages[stage] = {"metrics": metrics, "sources": sources}

    def side(self, stage: str) -> dict[str, Any]:
        """The English localizer, and per stage its context and glossary — built once."""
        from .engine.localize import Localizer
        from .narratives.context import build_context

        run = self.run
        with self._lock:
            if "loc" not in self._side:
                translations = self.labels_job.result() if self.labels_job else {}
                for u in run.umbrellas:
                    if not u.name_en and u.name_ar in translations:
                        u.name_en = translations[u.name_ar]
                self._side.update(translations=translations, loc=Localizer("en", run.tax, run.umbrellas, translations))
            if run.english_on and stage not in self._side:
                m, src, en_loc = self._stages[stage]["metrics"], self._stages[stage]["sources"], self._side["loc"]
                self._side[stage] = {
                    "context": sections.prune_context(build_context(
                        m, "en", en_loc, entity_name=run.entity.name_en, vision=run.entity.closing_statement,
                        sections=run.titles["en"], vocabulary=run.vocab["en"], initiative_sources=src,
                    ), run.shown),
                    "glossary": _glossary(m, run.tax, run.umbrellas, self._side["translations"], run.entity, run.period,
                                          run.ar_loc, en_loc),
                    "sources": [{**x, "name": x["name_en"] or x["name_ar"]} for x in src],
                }
            return self._side

    def translator(self, stage: str) -> Callable[[Any], None] | None:
        """The writer's ``on_part`` hook for this stage: queue the unit's translation."""
        if not self.run.english_on:
            return None
        from .narratives.writer import translate_part

        def start(unit) -> None:
            side = self.side(stage)[stage]
            self.run.report(0.78, "ترجمة التقرير إلى الإنجليزية", "Stage 5: Writing the narrative; translating the finished parts")
            self.jobs.append(self.pool.submit(
                _staged, "translation", translate_part, unit.part, unit.data, context=side["context"],
                glossary=side["glossary"], vocabulary=self.run.vocab["en"], sources=side["sources"], unit=unit.unit,
            ))
        return start


def _staged(stage: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run ``fn`` on a worker thread, tagging any failure with its stage name."""
    with _named(stage):
        return fn(*args, **kwargs)


def _faq_figures(faqs) -> dict[str, Any]:
    """FAQ_COVERAGE and FAQ_CATALOGUE_VOLUME — sums of the labels FAQ detection wrote.

    Conditional on the tenant's FAQ catalogue (Data Mapping §1): without one there is
    nothing to be covered by, and Section 04 carries the metric-gap recommendation.
    """
    from .engine.compute import faq_catalogue_volume, faq_coverage

    catalogue = sum(1 for e in faqs.entries if e["source"] == "catalogue")
    if faqs.population is None or not catalogue:
        return {}
    figures: dict[str, Any] = {"FAQ_CATALOGUE_VOLUME": faq_catalogue_volume(faqs.population, faqs.entries)}
    if faqs.population.coverage:
        figures["FAQ_COVERAGE"] = faq_coverage(faqs.population, catalogue)
    return figures


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


def _labels_to_translate(metrics: dict[str, Any], umbrellas, tax, shown=None) -> list[str]:
    """AI-generated or recorded labels the English report prints — only for shown sections."""
    shown = set(shown) if shown is not None else {k for k, s in sections.SECTIONS.items() if s.enabled}
    labels: list[str] = []
    if metrics.get("ROOT_CAUSE_TOP") and ReportSection.ROOT_CAUSES in shown:
        labels += metrics["ROOT_CAUSE_TOP"]["labels"]
        for block in metrics["ROOT_CAUSE_TOP"]["per_bundle"].values():
            labels += block["labels"]
    # Umbrella names appear wherever bundles do: Sections 02 and 03, the Section 04
    # self-service share, the roadmap's sources and the executive summary's motives.
    if shown & {ReportSection.ROOT_CAUSES, ReportSection.SERVICE_FOCUS, ReportSection.EXECUTIVE_SUMMARY,
                ReportSection.DIGITAL_CONTENT_OPPORTUNITIES, ReportSection.IMPROVEMENT_ROADMAP}:
        labels += [u.name_ar for u in umbrellas if not u.name_en]
    # Event clusters name the appendix's observations and the roadmap's event sources.
    if shown & {ReportSection.APPENDICES, ReportSection.IMPROVEMENT_ROADMAP}:
        for event in metrics.get("EVENTS", []):
            labels.append(event["cluster"])
    if ReportSection.STATISTICS in shown and metrics.get("RECORDED_VS_TRUE", {}).get("by_tag"):
        labels += [x["tag"] for x in metrics["RECORDED_VS_TRUE"]["by_tag"]]
    # Departments and severities name the classification map's subsections (disabled).
    if "classification_map" in shown:
        for key in ("DEPARTMENT", "SEVERITY"):
            if metrics.get(key):
                labels += metrics[key]["labels"]
    catalogue = set(tax.main_names) | set(tax.sub_names)
    return [x for x in labels if x and x not in catalogue and re.search(r"[؀-ۿ]", x)]


def _labels_document(run_id, cases, tax, settings, umbrellas, refs) -> dict[str, Any]:
    """Per-case labels — what the platform stores, and sends back frozen next period."""
    from .analysis.faqs import faq_entries
    from .engine.wording import PROVENANCE

    names = {u.id: u for u in umbrellas}
    # ``faq_match`` indexes the entries FAQ detection judged against, in this order.
    faq_questions = [e["question_ar"] for e in faq_entries(refs.faq_catalogue, refs.guidebook)]
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
                "faq_status": c.faq_status,
                "faq_catalogue_question": faq_questions[c.faq_match] if c.faq_match is not None else None,
                "corrections": c.corrections,
            }
            for c in cases
        ],
    }
