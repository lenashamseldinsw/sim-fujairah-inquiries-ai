"""
Layer 2 — the classifier, end to end (Prerequisites §1.B, Data Mapping §3).

    frozen labels ─► duplicates (identical, then near-identical) share one classification
        ─► keyword rules («آلي - موثوق»)
            └─ confidence < X5 ─► model, first pass («نموذج»)
                  └─ codebook corrections ─► «آلي - مُصحّح»
                        └─ confidence < X6, or a rule still broken
                              ─► deep review, a second AI pass («يدوي - مُراجع»)
    X8 on: a root cause per case (root-cause codebook); umbrellas are grouped by
    ``group_umbrellas``, which the pipeline runs alongside the analysis.

What it guarantees:

* a frozen label is never overwritten — only missing fields are filled;
* identical cases (same description and resolution, folded) are classified once and
  the labels copied, with provenance «آلي - موثوق» — fast, and consistent by design. So
  are near-identical ones (embeddings at least ``near_duplicate_similarity`` apart): on
  the ADPF Q2 file one case in ten had one, and reviewers had labelled the pair the same
  95% of the time — against 68% agreement between the classifier and the reviewers;
* every case leaves with a contact type, a main service and a sub-classification, a
  confidence and a provenance, so ``S`` never shrinks here;
* the "review" tier is an AI pass, not a person: the cases the first pass was unsure
  of are re-classified by the reasoning model with more evidence. A case still below
  X6 afterwards is marked ``low_confidence`` and reported, never dropped;
* provenance is set here, never by the model; thresholds come from the settings (R11).
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from ..models.settings import TenantSettings
from ..core42 import Core42Client, embeddings
from ..engine.compute import Umbrella
from ..engine.parse import Case
from ..engine.taxonomy import TaxonomyIndex
from ..engine.text import clean_label, fold_text
from ..engine.wording import CONTACT_TO_TYPE
from .labels import FrozenReport, UmbrellaRegistry, apply_frozen
from .model import ModelClassifier
from .prompts import RECURRING_SITUATIONS_ADPF
from .rootcause import check_root_cause
from .rules import classify_by_rules
from .umbrellas import discover_umbrellas

__all__ = ["ClassificationResult", "classify_cases", "group_umbrellas"]

logger = logging.getLogger(__name__)

_CONTACT_TYPES = ("استفسار", "طلب خدمة", "شكوى", "شكر وثناء")
_TRUE_TYPES = ("inquiry", "service_request", "complaint", "incident", "compliment", "out_of_scope")
_MIN_DUPLICATE_KEY = 12


@dataclass
class ClassificationResult:
    umbrellas: list[Umbrella]
    frozen: FrozenReport
    registry: UmbrellaRegistry | None = None
    routed_to_model: int = 0
    model_unavailable: int = 0
    corrected: int = 0
    root_cause_fixes: int = 0
    duplicates_reused: int = 0
    near_duplicates_reused: int = 0
    deep_reviewed: int = 0
    low_confidence: int = 0
    warnings: list[str] = field(default_factory=list)


def _duplicate_key(case: Case) -> str | None:
    key = fold_text(f"{case.description} || {case.resolution_text}")
    return key if len(fold_text(case.description)) >= _MIN_DUPLICATE_KEY else None


def _near_duplicates(candidates: list[Case], threshold: float) -> dict[str, Case]:
    """Case id → the earlier case whose labels it copies (near-identical text).

    Each case is compared with the cases before it only, and a match is followed to the
    case that is actually classified, so labels flow one way and never in a circle. If
    the embedding call fails, nothing is copied and every case is classified.
    """
    if threshold >= 1.0 or len(candidates) < 2:
        return {}
    texts = [f"{' '.join(c.description.split())[:700]} || {' '.join(c.resolution_text.split())[:700]}" for c in candidates]
    try:
        vectors = embeddings.embed_texts(texts, stage="near_duplicates")
    except Exception as exc:  # never a reason to fail classification
        logger.warning("Near-duplicate detection skipped: %s", exc)
        return {}
    source = list(range(len(candidates)))
    for start in range(0, len(candidates), 1000):
        block = vectors[start:start + 1000] @ vectors[:start + 1000].T
        for k in range(block.shape[0]):
            i = start + k
            if i == 0:
                continue
            earlier = block[k, :i]
            j = int(earlier.argmax())
            if earlier[j] >= threshold:
                source[i] = source[j]
    return {candidates[i].case_id: candidates[source[i]] for i in range(len(candidates)) if source[i] != i}


def _apply_answer(case: Case, answer: dict, tax: TaxonomyIndex, *, labels: bool, x8: bool) -> None:
    """Write a model answer onto a case, leaving frozen fields alone."""
    if "contact_type" not in case.frozen:
        contact = answer.get("actual_contact_type")
        if contact in _CONTACT_TYPES:
            case.contact_type = contact
    true_type = answer.get("true_type")
    if true_type in _TRUE_TYPES and "true_type" not in case.frozen:
        case.true_type = true_type
    if labels and "main_service" not in case.frozen and "sub_classification" not in case.frozen:
        main = tax.main(answer.get("main_service"))
        sub = tax.sub(answer.get("sub_classification"))
        if main or sub:
            case.main_service = main or case.main_service
            case.sub_classification = sub or case.sub_classification
        case.reason = clean_label(answer.get("classification_reason")) or case.reason
        try:
            case.confidence = max(0.0, min(1.0, float(answer.get("confidence"))))
        except (TypeError, ValueError):
            pass
    if x8 and "root_cause" not in case.frozen and answer.get("root_cause"):
        case.root_cause = clean_label(answer.get("root_cause")) or case.root_cause


def classify_cases(
    cases: list[Case],
    tax: TaxonomyIndex,
    settings: TenantSettings,
    *,
    entity_name: str,
    carried_umbrellas: list[Umbrella],
    client: Core42Client | None = None,
    progress: Callable[[float, str, str], None] | None = None,
) -> ClassificationResult:
    """Label every case in place. Umbrellas are grouped separately (``group_umbrellas``)."""
    registry = UmbrellaRegistry([Umbrella(**u.__dict__) for u in carried_umbrellas])
    frozen = apply_frozen(cases, tax, registry)
    result = ClassificationResult(umbrellas=registry.umbrellas, frozen=frozen, registry=registry)
    x8 = settings.root_cause_extraction
    x5, x6 = settings.llm_threshold, settings.review_threshold

    # ── Duplicates: classify one case per identical text ─────────────────────
    first_of: dict[str, Case] = {}
    copies: list[Case] = []
    for case in cases:
        key = _duplicate_key(case)
        if key is None or case.frozen:
            continue
        if key in first_of:
            case.duplicate_of = first_of[key].case_id
            copies.append(case)
        else:
            first_of[key] = case
    near = _near_duplicates(list(first_of.values()), settings.near_duplicate_similarity)
    for case in copies:  # an exact copy of a near-copy reads from the case actually classified
        if case.duplicate_of in near:
            case.duplicate_of = near[case.duplicate_of].case_id
    for case in first_of.values():
        if case.case_id in near:
            case.duplicate_of = near[case.case_id].case_id
            copies.append(case)
    result.near_duplicates_reused = len(near)
    work = [c for c in cases if c.duplicate_of is None]

    # ── Tier 1: keyword rules, for every field not frozen ─────────────────────
    route: list[tuple[Case, dict, dict, str | None]] = []
    labels_from_rules: set[str] = set()
    for case in work:
        fixed = {}
        if case.main_service and case.sub_classification:
            fixed["main_service"] = case.main_service
            fixed["sub_classification"] = case.sub_classification
        if case.contact_type:
            fixed["actual_contact_type"] = case.contact_type
        if case.root_cause:
            fixed["root_cause"] = case.root_cause

        needs_service = "main_service" not in fixed
        needs_type = "actual_contact_type" not in fixed
        needs_root = x8 and not case.root_cause
        if not (needs_service or needs_type or needs_root):
            continue

        rule = classify_by_rules(case, tax)
        if needs_type:
            case.contact_type, case.true_type = rule.contact_type, rule.true_type
        if needs_service:
            case.main_service, case.sub_classification = rule.main_service, rule.sub_classification
            case.reason = case.reason or rule.reason
            case.confidence = rule.confidence
            case.provenance = "auto"
            labels_from_rules.add(case.case_id)
        elif needs_type and case.confidence is None:
            case.confidence = rule.type_confidence

        uncertain = (needs_service and rule.confidence < x5) or (needs_type and rule.type_confidence < x5)
        if uncertain or needs_root:
            suggestion = {
                "actual_contact_type": rule.contact_type,
                "main_service": rule.main_service,
                "sub_classification": rule.sub_classification,
            }
            if not uncertain:
                # The rules settled the labels; the model is asked for the root cause only.
                fixed = {
                    **fixed,
                    "actual_contact_type": case.contact_type,
                    "main_service": case.main_service,
                    "sub_classification": case.sub_classification,
                }
                suggestion = None
            route.append((case, suggestion, fixed, None))

    # ── Tier 2: the model's first pass ───────────────────────────────────────
    recurring = RECURRING_SITUATIONS_ADPF if (tax.taxonomy.id or "").startswith("adpf") else None
    model: ModelClassifier | None = None
    flagged: dict[str, str] = {}
    if route:
        model = ModelClassifier(tax, root_causes=x8, entity=entity_name, recurring=recurring, client=client)
        result.routed_to_model = len(route)

        def report(done: int, total: int) -> None:
            if progress:
                progress(0.12 + 0.24 * done / total,
                         f"تصنيف الحالات بالنموذج {done}/{total}", f"Stage 2: Model classification {done}/{total}")

        answers = model.classify(route, report)
        for case, suggestion, fixed, _ in route:
            answer = answers.get(case.case_id)
            if not answer:
                result.model_unavailable += 1
                flagged[case.case_id] = "the first pass returned no labels for this case"
                continue
            settled_by_model = suggestion is not None and case.case_id in labels_from_rules
            _apply_answer(case, answer, tax, labels=settled_by_model, x8=x8)
            if settled_by_model:
                case.provenance = "llm"

    # ── Corrections: taxonomy pairs and the root-cause codebook ───────────────
    for case in work:
        if case.provenance == "deep_review" and case.frozen:
            continue
        if case.sub_classification and not tax.is_valid_pair(case.main_service, case.sub_classification):
            mains = tax.mains_for_sub(case.sub_classification)
            if len(mains) == 1:
                case.main_service = mains[0]
                case.corrections.append("main service aligned to the sub-classification")
                if case.provenance in ("llm", "auto"):
                    case.provenance = "auto_corrected"
                result.corrected += 1
            elif case.main_service in tax.main_to_subs:
                case.sub_classification = tax.main_to_subs[case.main_service][0]
                case.corrections.append("sub-classification reset under the main service")
                flagged[case.case_id] = "the sub-classification did not belong to the main service"
                result.corrected += 1

    if x8 and model is not None:
        result.root_cause_fixes = _enforce_root_causes(work, tax, model, flagged)

    # ── Tier 3: the deep review — a second, higher-effort AI pass ─────────────
    for case in work:
        if case.frozen and case.provenance == "deep_review":
            continue
        if case.confidence is None or case.confidence < x6:
            flagged.setdefault(case.case_id, f"first-pass confidence {case.confidence} is below {x6}")
    review = [c for c in work if c.case_id in flagged and not ("main_service" in c.frozen and "contact_type" in c.frozen)]
    if review:
        deep = ModelClassifier(tax, root_causes=x8, entity=entity_name, recurring=recurring,
                               client=client or (model.client if model else None), deep=True)

        def report_review(done: int, total: int) -> None:
            if progress:
                progress(0.36 + 0.08 * done / total,
                         f"المراجعة المعمّقة {done}/{total}", f"Stage 2: Deep review {done}/{total}")

        items = [
            (c, {"actual_contact_type": c.contact_type, "main_service": c.main_service,
                 "sub_classification": c.sub_classification, "confidence": c.confidence,
                 "reason": c.reason, **({"root_cause": c.root_cause} if x8 else {})},
             {k: v for k, v in (("main_service", c.main_service), ("sub_classification", c.sub_classification))
              if k in c.frozen}, flagged[c.case_id])
            for c in review
        ]
        answers = deep.classify(items, report_review)
        for case in review:
            answer = answers.get(case.case_id)
            if not answer:
                case.corrections.append("deep review returned no labels; first-pass labels kept")
                continue
            _apply_answer(case, answer, tax, labels=True, x8=x8)
            if case.sub_classification and not tax.is_valid_pair(case.main_service, case.sub_classification):
                mains = tax.mains_for_sub(case.sub_classification)
                if len(mains) == 1:
                    case.main_service = mains[0]
            if x8 and case.root_cause:
                check = check_root_cause(case.root_cause, main_service=case.main_service,
                                         sub=case.sub_classification, tax=tax)
                case.root_cause = check.text or case.root_cause
            case.provenance = "deep_review"
            case.deep_reviewed = True
            result.deep_reviewed += 1

    for case in work:
        if case.contact_type and not case.true_type:
            case.true_type = CONTACT_TO_TYPE.get(case.contact_type)
        if not (case.frozen and case.provenance == "deep_review"):
            case.low_confidence = case.confidence is None or case.confidence < x6
    result.low_confidence = sum(1 for c in cases if c.low_confidence)

    # ── Copy labels onto the duplicates ───────────────────────────────────────
    by_id = {c.case_id: c for c in work}
    for case in copies:
        source = by_id[case.duplicate_of]
        for attr in ("contact_type", "true_type", "main_service", "sub_classification", "reason",
                     "confidence", "root_cause", "evidence", "low_confidence"):
            setattr(case, attr, getattr(source, attr))
        case.provenance = "auto"
        kind = "near-identical" if case.case_id in near else "identical"
        case.corrections.append(f"labels copied from the {kind} case {source.case_id}")
    result.duplicates_reused = len(copies)
    result.low_confidence = sum(1 for c in cases if c.low_confidence)

    logger.info(
        "Classification: %d frozen, %d duplicates reused (%d near-identical), %d to the model, %d unavailable, "
        "%d corrected, %d root-cause fixes, %d deep-reviewed, %d still low-confidence, provenance %s.",
        frozen.cases_with_frozen_labels, result.duplicates_reused, result.near_duplicates_reused, result.routed_to_model,
        result.model_unavailable, result.corrected, result.root_cause_fixes, result.deep_reviewed,
        result.low_confidence, dict(Counter(c.provenance for c in cases)),
    )
    return result


def group_umbrellas(
    cases: list[Case],
    result: ClassificationResult,
    tax: TaxonomyIndex,
    settings: TenantSettings,
    *,
    client: Core42Client | None = None,
    progress: Callable[[float, str, str], None] | None = None,
) -> None:
    """Umbrella discovery (X8). Needs root causes only — runs alongside the analysis."""
    if not settings.root_cause_extraction:
        return

    def report(done: int, total: int) -> None:
        if progress:
            progress(0.44 + 0.06 * done / total,
                     f"تجميع الأسباب الجذرية في حزم {done}/{total}", f"Stage 3: Umbrella discovery {done}/{total}")

    result.warnings += discover_umbrellas(
        cases, result.registry, settings.umbrella_range(), client=client, progress=report,
        service_names=tax.main_names + tax.sub_names,
    )
    result.umbrellas = result.registry.umbrellas


def _enforce_root_causes(cases: list[Case], tax: TaxonomyIndex, model: ModelClassifier,
                         flagged: dict[str, str]) -> int:
    """Check model-written root causes; fix in code or re-ask once. Returns fixes."""
    fixes = 0
    reask: list[tuple[Case, None, dict, str]] = []
    for case in cases:
        if not case.root_cause or "root_cause" in case.frozen:
            continue
        check = check_root_cause(
            case.root_cause, main_service=case.main_service, sub=case.sub_classification, tax=tax
        )
        if check.fixed:
            case.root_cause = check.text
            case.corrections.append("root cause: case specifics removed (R1)")
            fixes += 1
            if case.provenance in ("llm", "auto"):
                case.provenance = "auto_corrected"
        if check.violation:
            fixed = {
                "actual_contact_type": case.contact_type,
                "main_service": case.main_service,
                "sub_classification": case.sub_classification,
            }
            reask.append((case, None, fixed, f"{check.violation} Current root_cause: «{case.root_cause}»"))
    if not reask:
        return fixes
    answers = model.classify(reask, fixing=True)
    for case, _, _, note in reask:
        answer = answers.get(case.case_id) or {}
        rewritten = clean_label(answer.get("root_cause"))
        if not rewritten:
            flagged.setdefault(case.case_id, f"the root cause breaks the codebook: {note.split(':')[0]}")
            continue
        check = check_root_cause(rewritten, main_service=case.main_service, sub=case.sub_classification, tax=tax)
        if check.violation:
            # Still breaking the codebook after one rewrite: the deep review takes it.
            case.root_cause = check.text or case.root_cause
            flagged.setdefault(case.case_id, f"the root cause still breaks the codebook: {check.violation}")
            continue
        case.root_cause = check.text
        case.corrections.append(f"root cause rewritten: {note.split(':')[0]}")
        fixes += 1
        if case.provenance in ("llm", "auto"):
            case.provenance = "auto_corrected"
    return fixes
