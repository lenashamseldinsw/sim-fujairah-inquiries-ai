"""
Layer 1, second half — ``compute()``: every number the report prints.

Pure: the run's case set ``S`` (frozen labels on every case) in, a dict of the Data
Mapping §4 keys out. No model call. The narrative writer receives this and nothing
else, and every figure in its prose must equal a value here (Prerequisites §8,
"numeric fidelity — hard gate").

**One denominator (R2).** ``S`` is the in-scope case set after artefact rows,
duplicates and the case-type scope — the parse log accounts for everything outside
it. Every key reads ``S``; distributions over the labelled subset ``L`` say so.
Nothing is dropped between here and the report, so the cover total equals the sum of
the S3.1 distribution equals the sum of the per-type sheets.

Labels are the canonical Arabic names (taxonomy, contact types, umbrella names).
``engine.localize`` renders them in English for the English report.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

from ..api.models.period import Period
from ..api.models.reference import History, PeriodSnapshot, ReferenceLists
from ..api.models.settings import ComparisonBasis, DigitalChannelDefinition, TenantSettings
from .parse import Case, ParseLog
from .taxonomy import TaxonomyIndex
from .text import clean_label, count_hits, fold_text
from .wording import (
    CONTACT_TYPES,
    PROVENANCE,
    TYPE_TO_CONTACT,
    UNCLASSIFIED,
    channel_key,
    is_live_chat_or_self_service,
    is_phone_channel,
    is_walk_in_channel,
    month_name,
)

__all__ = ["Umbrella", "compute", "pct", "snapshot_of", "IN_SCOPE_TYPES"]

IN_SCOPE_TYPES = {"inquiry", "service_request"}

_SEVERITY_RELABEL = {
    "طلب عادي": "طلب روتيني",
    "عادي": "روتيني",
    "طلب عاجل": "طلب حرج",
    "عاجل": "حرج",
}


def pct(numerator: float, denominator: float) -> float | None:
    """A percentage to one decimal, rounded half-up — the way the reports print it."""
    if not denominator:
        return None
    value = Decimal(str(numerator * 100 / denominator))
    rounded = float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    if rounded == 100.0 and numerator < denominator:
        # 10,628 of 10,630 is not "100%": keep the second decimal (99.98) so a
        # short-fall the parse log accounts for is not rounded out of sight.
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return rounded


@dataclass
class Umbrella:
    """One umbrella as the run uses it."""

    id: str
    name_ar: str
    name_en: str = ""
    meaning_ar: str = ""
    meaning_en: str = ""
    new: bool = False
    carried: bool = False


@dataclass
class ComputeInputs:
    cases: list[Case]
    settings: TenantSettings
    taxonomy: TaxonomyIndex
    period: Period
    parse_log: ParseLog
    reference: ReferenceLists
    history: History | None = None
    umbrellas: list[Umbrella] = field(default_factory=list)
    umbrella_set_version: str | None = None
    frameworks: list[dict[str, Any]] = field(default_factory=list)
    entity_name_ar: str = ""
    entity_name_en: str = ""


def _dist(counter: Counter, denominator: int, order: Iterable[str] | None = None) -> dict[str, Any]:
    items = (
        [(k, counter.get(k, 0)) for k in order]
        if order is not None
        else counter.most_common()
    )
    return {
        "labels": [k for k, _ in items],
        "values": [v for _, v in items],
        "pct": [pct(v, denominator) for _, v in items],
    }


def _in_scope_type(case: Case) -> str | None:
    if case.true_type:
        return case.true_type
    if case.contact_type:
        from .wording import CONTACT_TO_TYPE

        return CONTACT_TO_TYPE.get(case.contact_type)
    return None


def _is_classified(case: Case) -> bool:
    """``L``: frozen labels, and a true type inside the inquiries scope."""
    return case.labelled and (_in_scope_type(case) in IN_SCOPE_TYPES)


def _digital(channel: str, settings: TenantSettings) -> bool:
    if settings.digital_channels is not None:
        wanted = {fold_text(c) for c in settings.digital_channels}
        return fold_text(channel) in wanted
    if settings.digital_channel_definition is DigitalChannelDefinition.LIVE_CHAT_AND_SELF_SERVICE:
        return is_live_chat_or_self_service(channel)
    return not (is_phone_channel(channel) or is_walk_in_channel(channel))


def compute(inputs: ComputeInputs) -> dict[str, Any]:
    """The engine output — every key the report, the dashboard and the prose read."""
    cases = inputs.cases
    settings = inputs.settings
    tax = inputs.taxonomy
    S = len(cases)
    L_cases = [c for c in cases if _is_classified(c)]
    L = len(L_cases)
    supplied = set(inputs.parse_log.columns_mapped)
    has = lambda col: col in supplied and col not in inputs.parse_log.columns_present_but_empty  # noqa: E731
    out: dict[str, Any] = {}
    umbrella_by_id = {u.id: u for u in inputs.umbrellas}
    x8 = settings.root_cause_extraction or any(c.bundle for c in cases)

    # ── Out of scope detected (mis-tagged complaints / incidents / compliments) ──
    oos = Counter(_in_scope_type(c) for c in cases if _in_scope_type(c) in ("complaint", "incident", "compliment"))
    oos_ids = [c.case_id for c in cases if _in_scope_type(c) in ("complaint", "incident", "compliment")]
    out["OUT_OF_SCOPE_DETECTED"] = {
        "complaint": oos.get("complaint", 0),
        "incident": oos.get("incident", 0),
        "compliment": oos.get("compliment", 0),
        "total": len(oos_ids),
        "case_ids": oos_ids[:200],
    }

    # ── Main service / sub-classification over L ───────────────────────────────
    main_counter = Counter(c.main_service for c in L_cases)
    sub_counter = Counter(c.sub_classification for c in L_cases)
    unclassified = S - L - len(oos_ids)
    main = _dist(main_counter, L)
    sub = _dist(sub_counter, L)
    if unclassified > 0:
        for block in (main, sub):
            block["labels"].append(UNCLASSIFIED["ar"])
            block["values"].append(unclassified)
            block["pct"].append(pct(unclassified, S))
    out["MAIN_SERVICE"] = main
    out["SUB_CLASS"] = sub

    # ── Timeliness ─────────────────────────────────────────────────────────────
    sla = Counter(c.sla for c in cases)
    has_sla = any(c.sla != "unspecified" for c in cases)
    within_deadline = sla.get("within", 0) + sla.get("near", 0)
    framework_name = {
        "entity_process_kpi": "مؤشر الالتزام الزمني — عملية الرد على الاستفسارات",
        "tamm": "مؤشرات مركز اتصال حكومة أبوظبي «تم»",
        "gsr": "النظام العالمي لتصنيف الخدمات",
        "other": "إطار الجهة",
    }.get((settings.timeliness_framework.value if settings.timeliness_framework else "other"))
    days = settings.timeliness_target_working_days or 0
    out["TIMELINESS"] = {
        "available": has_sla,
        "within": sla.get("within", 0),
        "near": sla.get("near", 0),
        "over": sla.get("over", 0),
        "unspecified": sla.get("unspecified", 0),
        "within_pct": pct(sla.get("within", 0), S),
        "near_pct": pct(sla.get("near", 0), S),
        "over_pct": pct(sla.get("over", 0), S),
        "unspecified_pct": pct(sla.get("unspecified", 0), S),
        "within_deadline": within_deadline,
        "within_deadline_pct": pct(within_deadline, S) if has_sla else None,
        "breached_pct": pct(sla.get("over", 0), S) if has_sla else None,
        "target": _days_label(days, "ar"),
        "target_en": _days_label(days, "en"),
        "framework": framework_name,
        "framework_id": settings.timeliness_framework.value if settings.timeliness_framework else None,
    }
    out["SLA"] = {
        "on_time": sla.get("within", 0),
        "near_deadline": sla.get("near", 0),
        "late": sla.get("over", 0),
        "unspecified": sla.get("unspecified", 0),
        "within_deadline_pct": out["TIMELINESS"]["within_deadline_pct"],
    }

    # ── Channels ───────────────────────────────────────────────────────────────
    has_channel = has("channel")
    channel_counter = Counter(c.channel or "—" for c in cases) if has_channel else Counter()
    channel = _dist(channel_counter, S)
    channel["digital"] = [_digital(label, settings) for label in channel["labels"]]
    channel["keys"] = [channel_key(label) for label in channel["labels"]]
    digital = sum(v for v, d in zip(channel["values"], channel["digital"]) if d)
    out["CHANNEL"] = channel

    # ── Monthly ────────────────────────────────────────────────────────────────
    month_counter = Counter(
        (c.opened.year, c.opened.month) for c in cases if c.opened
    )
    months = sorted(month_counter)
    monthly_values = [month_counter[m] for m in months]
    out["MONTHLY"] = {
        "months": [f"{y}-{m:02d}" for y, m in months],
        "labels": [month_name(m, "ar") for _, m in months],
        "labels_en": [month_name(m, "en") for _, m in months],
        "values": monthly_values,
        "pct": [pct(v, S) for v in monthly_values],
        "delta_pct": [None] + [
            pct(monthly_values[i] - monthly_values[i - 1], monthly_values[i - 1])
            for i in range(1, len(monthly_values))
        ],
        "undated": S - sum(monthly_values),
    }

    # ── Recorded types and recorded vs actual ──────────────────────────────────
    recorded_counter = Counter(c.case_type_raw or "—" for c in cases)
    out["CASE_TYPE_RECORDED"] = _dist(recorded_counter, S)

    actual_counter = Counter(c.contact_type or UNCLASSIFIED["ar"] for c in cases)
    order = [t for t in CONTACT_TYPES if actual_counter.get(t)] + [
        k for k in actual_counter if k not in CONTACT_TYPES
    ]
    out["ACTUAL_TYPE"] = _dist(actual_counter, S, order)

    recorded_as_contact = Counter(
        TYPE_TO_CONTACT.get(c.recorded_type) if c.recorded_type else "غير محدد" for c in cases
    )
    cats = list(CONTACT_TYPES)
    out["RECORDED_VS_ACTUAL"] = {
        "categories": cats,
        "recorded": [recorded_as_contact.get(t, 0) for t in cats],
        "actual": [actual_counter.get(t, 0) for t in cats],
        "recorded_unspecified": recorded_as_contact.get("غير محدد", 0),
        "matrix": {
            r: {a: sum(1 for c in cases if c.recorded_type and TYPE_TO_CONTACT.get(c.recorded_type) == r and c.contact_type == a) for a in cats}
            for r in cats
        },
    }
    compared = [c for c in cases if c.misclassified is not None]
    reclassified = [c for c in compared if c.misclassified]
    sample = sorted(reclassified, key=lambda c: -(c.confidence or 0))[:10]
    out["RECLASSIFICATION"] = {
        "count": len(reclassified),
        "compared": len(compared),
        "rate": pct(len(reclassified), S) if compared else None,
        "sample": [
            {
                "case_id": c.case_id,
                "recorded": TYPE_TO_CONTACT.get(c.recorded_type, c.case_type_raw),
                "actual": c.contact_type,
                "evidence": (c.evidence or c.reason or c.description)[:240],
            }
            for c in sample
        ],
    }

    sub_by_type: dict[str, Any] = {}
    for contact in CONTACT_TYPES:
        group = [c for c in cases if c.contact_type == contact and c.sub_classification]
        if group:
            sub_by_type[contact] = _dist(Counter(c.sub_classification for c in group), len(group))
    out["SUB_CLASS_BY_TYPE"] = sub_by_type

    # ── Recorded service tag (O9) and RECORDED_VS_TRUE ─────────────────────────
    if has("crm_service"):
        out["SERVICE"] = _dist(
            Counter((c.crm_service_ar or c.crm_service or "—") for c in cases), S
        )
        out["SERVICE"]["labels_en"] = [
            next((c.crm_service_en for c in cases if (c.crm_service_ar or c.crm_service) == label and c.crm_service_en), label)
            for label in out["SERVICE"]["labels"]
        ]
        pairs = [(c, tax.crosswalk_main(c.crm_service)) for c in L_cases if c.crm_service]
        mapped = [(c, m) for c, m in pairs if m]
        matches = sum(1 for c, m in mapped if m == c.main_service)
        per_tag: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for c, m in mapped:
            tag = c.crm_service_ar or c.crm_service
            per_tag[tag][0] += 1
            per_tag[tag][1] += int(m == c.main_service)
        least = sorted(
            ((t, n, pct(k, n)) for t, (n, k) in per_tag.items() if n >= 10),
            key=lambda x: (x[2] or 0, -x[1]),
        )[:5]
        out["RECORDED_VS_TRUE"] = {
            "available": bool(mapped),
            "compared": len(mapped),
            "unmapped_tags": len(pairs) - len(mapped),
            "match_count": matches,
            "mismatch_count": len(mapped) - matches,
            "match_pct": pct(matches, len(mapped)),
            "mismatch_pct": pct(len(mapped) - matches, len(mapped)),
            "least_matching": [{"tag": t, "cases": n, "match_pct": p} for t, n, p in least],
            "by_tag": [
                {"tag": t, "cases": n, "matches": k, "match_pct": pct(k, n)}
                for t, (n, k) in sorted(per_tag.items(), key=lambda x: -x[1][0])[:10]
            ],
            "basis": "catalogue crosswalk (crm_service → main service)",
        }
    else:
        out["RECORDED_VS_TRUE"] = {"available": False}

    # ── Severity, closure, departments ─────────────────────────────────────────
    if has("severity"):
        sev = Counter(_SEVERITY_RELABEL.get(c.severity, c.severity) or "—" for c in cases)
        out["SEVERITY"] = _dist(sev, S)
    closed = sum(1 for c in cases if c.is_closed)
    out["CLOSED"] = {
        "available": has("closed_datetime"),
        "closed_cases": closed,
        "closure_rate": pct(closed, S) if has("closed_datetime") else None,
    }
    if has("department"):
        dept_counter = Counter(c.department or "—" for c in cases)
        dept = _dist(dept_counter, S)
        dept["dominant_type"] = {}
        dept["dominant_sub"] = {}
        for name in dept["labels"]:
            members = [c for c in cases if (c.department or "—") == name]
            types = Counter(c.contact_type for c in members if c.contact_type)
            subs = Counter(c.sub_classification for c in members if c.sub_classification)
            dept["dominant_type"][name] = types.most_common(1)[0][0] if types else ""
            dept["dominant_sub"][name] = subs.most_common(1)[0][0] if subs else ""
        out["DEPARTMENT"] = dept

    # ── Bundles and root causes (X8) ──────────────────────────────────────────
    if x8:
        bundle_counter = Counter(c.bundle for c in L_cases if c.bundle)
        ordered = sorted(inputs.umbrellas, key=lambda u: -bundle_counter.get(u.id, 0))
        out["BUNDLE"] = {
            "ids": [u.id for u in ordered],
            "labels": [u.name_ar for u in ordered],
            "values": [bundle_counter.get(u.id, 0) for u in ordered],
            "pct": [pct(bundle_counter.get(u.id, 0), L) for u in ordered],
            "new": [u.new for u in ordered],
            "set_version": inputs.umbrella_set_version,
        }
        rc_counter = Counter(_norm_rc(c.root_cause) for c in L_cases if c.root_cause)
        top = rc_counter.most_common(settings.top_root_causes)
        per_bundle = {}
        for u in ordered:
            inner = Counter(_norm_rc(c.root_cause) for c in L_cases if c.bundle == u.id and c.root_cause)
            per_bundle[u.name_ar] = {
                "labels": [k for k, _ in inner.most_common(settings.root_causes_per_bundle)],
                "values": [v for _, v in inner.most_common(settings.root_causes_per_bundle)],
            }
        out["ROOT_CAUSE_TOP"] = {
            "labels": [k for k, _ in top],
            "values": [v for _, v in top],
            "distinct": len(rc_counter),
            "per_bundle": per_bundle,
        }
        matrix: dict[str, dict[str, int]] = {}
        row_pct: dict[str, dict[str, float | None]] = {}
        for service in main["labels"]:
            if service == UNCLASSIFIED["ar"]:
                continue
            members = [c for c in L_cases if c.main_service == service]
            counts = Counter(c.bundle for c in members if c.bundle)
            matrix[service] = {u.name_ar: counts.get(u.id, 0) for u in ordered}
            row_pct[service] = {u.name_ar: pct(counts.get(u.id, 0), len(members)) for u in ordered}
        out["BUNDLE_BY_SERVICE"] = {"counts": matrix, "row_pct": row_pct}
        if has_sla:
            ranked = []
            for u in ordered:
                members = [c for c in L_cases if c.bundle == u.id]
                if members:
                    near_over = sum(1 for c in members if c.sla in ("near", "over"))
                    ranked.append((u.name_ar, pct(near_over, len(members)), near_over))
            ranked.sort(key=lambda x: -(x[1] or 0))
            out["NEAR_OVER_BY_BUNDLE"] = {
                "labels": [r[0] for r in ranked],
                "pct": [r[1] for r in ranked],
                "counts": [r[2] for r in ranked],
            }
        deflectable_names = {fold_text(n) for n in settings.deflectable()}
        deflectable = [u for u in ordered if fold_text(u.name_ar) in deflectable_names or fold_text(u.name_en) in deflectable_names]
        deflect_count = sum(bundle_counter.get(u.id, 0) for u in deflectable)
        out["DEFLECTABLE_PCT"] = {
            "pct": pct(deflect_count, L),
            "count": deflect_count,
            "bundles": [u.name_ar for u in deflectable],
        }
        out["SERVICE_FOCUS"] = _service_focus(L_cases, main, ordered, settings, has_sla, has_channel)

    if has_sla:
        ranked = []
        for service in main["labels"]:
            members = [c for c in L_cases if c.main_service == service]
            if len(members) >= 10:
                near_over = sum(1 for c in members if c.sla in ("near", "over"))
                ranked.append((service, pct(near_over, len(members)), near_over))
        ranked.sort(key=lambda x: -(x[1] or 0))
        out["NEAR_OVER_BY_SERVICE"] = {
            "labels": [r[0] for r in ranked],
            "pct": [r[1] for r in ranked],
            "counts": [r[2] for r in ranked],
        }

    # ── Transactions ratio (conditional) ───────────────────────────────────────
    if inputs.reference.transactions:
        out["INQ_PER_100_TX"] = _transactions(inputs.reference.transactions, L_cases, L, tax)

    # ── FAQ coverage (conditional) ─────────────────────────────────────────────
    if inputs.reference.faq_catalogue:
        out["FAQ_COVERAGE"] = _faq_coverage(
            inputs.reference.faq_catalogue, L_cases, tax, out.get("BUNDLE"), umbrella_by_id
        )

    # ── Events ─────────────────────────────────────────────────────────────────
    out["EVENTS"] = _events(L_cases, umbrella_by_id, settings, x8)

    # ── Classification quality ─────────────────────────────────────────────────
    prov = Counter(c.provenance for c in cases if c.provenance)
    prov_items = [(k, v) for k, v in prov.most_common()]
    confidences = [c.confidence for c in cases if c.confidence is not None]
    queue = [c for c in cases if c.low_confidence]
    out["CLASSIFICATION_QUALITY"] = {
        "provenance": {PROVENANCE.get(k, k): v for k, v in prov_items},
        "provenance_keys": [k for k, _ in prov_items],
        "provenance_pct": [pct(v, S) for _, v in prov_items],
        "mean_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "pct_ge_threshold": pct(sum(1 for x in confidences if x >= settings.llm_threshold), len(confidences)) if confidences else None,
        "threshold": settings.llm_threshold,
        "llm_threshold": settings.llm_threshold,
        "review_threshold": settings.review_threshold,
        "deep_reviewed": sum(1 for c in cases if c.deep_reviewed),
        "duplicates_reused": sum(1 for c in cases if c.duplicate_of),
        # The ADPF key, kept: the cases still below X6 after the deep review.
        "queue_size_at_compute": len(queue),
        "queue_cleared": not queue,
        "taxonomy": tax.label,
        "umbrella_set_version": inputs.umbrella_set_version,
        "unclassified": unclassified,
    }

    # ── Agents (X9) ────────────────────────────────────────────────────────────
    if settings.agent_level_reporting and has("owner"):
        import re

        queue_re = re.compile(settings.queue_owner_pattern, re.IGNORECASE)
        people = defaultdict(list)
        for c in cases:
            if c.owner and not queue_re.search(c.owner):
                people[c.owner].append(c)
        out["AGENT"] = [
            {
                "owner": owner,
                "count": len(members),
                "pct": pct(len(members), S),
                "within_deadline_pct": pct(sum(1 for c in members if c.sla in ("within", "near")), len(members)) if has_sla else None,
            }
            for owner, members in sorted(people.items())
        ]

    # ── KPI ────────────────────────────────────────────────────────────────────
    top_service = None
    labelled_mains = [(k, v) for k, v in main_counter.most_common() if k]
    if labelled_mains:
        name, count = labelled_mains[0]
        top_service = {"name": name, "pct": pct(count, L), "count": count}
    out["KPI"] = {
        "total_cases": S,
        "classified": L,
        "classified_pct": pct(L, S),
        "closed_cases": closed if has("closed_datetime") else None,
        "reclassification_rate": out["RECLASSIFICATION"]["rate"],
        "reclassified": len(reclassified),
        "main_services": len([k for k in main_counter if k]),
        "sub_classes": len([k for k in sub_counter if k]),
        "bundles": len(inputs.umbrellas) if x8 else None,
        "within_deadline_pct": out["TIMELINESS"]["within_deadline_pct"],
        "digital_share_pct": pct(digital, S) if has_channel else None,
        "top_service": top_service,
        "inq_per_100_tx": out.get("INQ_PER_100_TX", {}).get("overall"),
        "report_period": inputs.period.label_ar,
        "report_period_en": inputs.period.label_en,
        "period_date_range": f"{inputs.period.start:%d/%m/%Y} – {inputs.period.end:%d/%m/%Y}",
        "granularity": inputs.period.granularity.value,
        "source_system": settings.source_system,
        "deep_reviewed": sum(1 for c in cases if c.deep_reviewed),
        "low_confidence_after_review": len(queue),
        "entity": inputs.entity_name_ar,
        "entity_en": inputs.entity_name_en,
    }

    # ── Comparison (R9) ────────────────────────────────────────────────────────
    snap = snapshot_of(out, inputs.period)
    previous = _previous(inputs.history, settings)
    if previous:
        out["COMPARISON"] = _comparison(previous, snap, settings)

    out["FRAMEWORKS"] = inputs.frameworks
    out["PARSE_LOG"] = inputs.parse_log.as_dict()
    out["METRIC_GAPS"], out["DATA_NOTES"] = _gaps(inputs, out, has)
    out["_SNAPSHOT"] = snap.model_dump()
    return out


# ── Helpers ──────────────────────────────────────────────────────────────────


def _days_label(days: float, lang: str) -> str:
    if not days:
        return ""
    whole = int(days) if float(days).is_integer() else days
    if lang == "en":
        return f"{whole} working day{'s' if whole != 1 else ''}"
    if whole == 1:
        return "يوم عمل واحد"
    if whole == 2:
        return "يومان عمل"
    return f"{whole} أيام عمل" if isinstance(whole, int) and whole <= 10 else f"{whole} يوم عمل"


def _norm_rc(text: str | None) -> str:
    return clean_label(text)


def _service_focus(L_cases, main, ordered_umbrellas, settings, has_sla, has_channel):
    focus = []
    services = [s for s in main["labels"] if s != UNCLASSIFIED["ar"]][: settings.focus_services_count]
    L = len(L_cases)
    for service in services:
        members = [c for c in L_cases if c.main_service == service]
        n = len(members)
        months = Counter((c.opened.year, c.opened.month) for c in members if c.opened)
        ordered_months = sorted(months)
        peak = max(ordered_months, key=lambda m: months[m]) if ordered_months else None
        subs = Counter(c.sub_classification for c in members)
        bundles = Counter(c.bundle for c in members if c.bundle)
        names = {u.id: u.name_ar for u in ordered_umbrellas}
        top_bundles = bundles.most_common(5)
        channels = Counter(c.channel for c in members if c.channel)
        phone = sum(v for k, v in channels.items() if is_phone_channel(k))
        chat = sum(v for k, v in channels.items() if channel_key(k) == "live_chat")
        focus.append({
            "service": service,
            "count": n,
            "share_pct": pct(n, L),
            "months": {month_name(m, "ar"): months[(y, m)] for y, m in ordered_months},
            "months_en": {month_name(m, "en"): months[(y, m)] for y, m in ordered_months},
            "peak_month": month_name(peak[1], "ar") if peak else None,
            "peak_month_en": month_name(peak[1], "en") if peak else None,
            "within_deadline_pct": pct(n - sum(1 for c in members if c.sla == "over"), n) if has_sla else None,
            "sub_classes": {
                "labels": [k for k, _ in subs.most_common()],
                "values": [v for _, v in subs.most_common()],
                "pct": [pct(v, n) for _, v in subs.most_common()],
            },
            "bundles": {
                "labels": [names.get(k, k) for k, _ in top_bundles],
                "values": [v for _, v in top_bundles],
                "pct": [pct(v, n) for _, v in top_bundles],
            },
            "phone_pct": pct(phone, n) if has_channel else None,
            "livechat_pct": pct(chat, n) if has_channel else None,
        })
    return focus


def _transactions(rows, L_cases, L, tax: TaxonomyIndex) -> dict[str, Any]:
    denominator = sum(r.total_requests for r in rows if r.counts_in_denominator)
    by_main: dict[str, float] = defaultdict(float)
    by_sub: dict[str, float] = defaultdict(float)
    unjoined = []
    for r in rows:
        main_name = tax.main(r.taxonomy_main_service or r.main_service)
        sub_name = tax.sub(r.taxonomy_sub_classification or r.sub_service) if (r.taxonomy_sub_classification or r.sub_service) else None
        if sub_name and not main_name:
            mains = tax.mains_for_sub(sub_name)
            main_name = mains[0] if len(mains) == 1 else None
        if main_name:
            by_main[main_name] += r.total_requests
        if sub_name:
            by_sub[sub_name] += r.total_requests
        if not main_name and not sub_name:
            unjoined.append(r.sub_service or r.main_service)
    main_counts = Counter(c.main_service for c in L_cases)
    sub_counts = Counter(c.sub_classification for c in L_cases)

    def block(counts: Counter, totals: dict[str, float]) -> dict[str, Any]:
        rows_ = [(k, counts.get(k, 0), totals[k]) for k in totals if totals[k] > 0 and counts.get(k, 0)]
        rows_.sort(key=lambda x: -(x[1] / x[2]))
        return {
            "labels": [k for k, _, _ in rows_],
            "inquiries": [i for _, i, _ in rows_],
            "transactions": [int(t) if float(t).is_integer() else t for _, _, t in rows_],
            "per_100": [pct(i, t) for _, i, t in rows_],
        }

    return {
        "overall": pct(L, denominator),
        "inquiries": L,
        "transactions_total": int(denominator) if float(denominator).is_integer() else denominator,
        "by_main_service": block(main_counts, by_main),
        "by_sub_service": block(sub_counts, by_sub),
        "unjoined_rows": unjoined,
        "denominator_rule": "rows with counts_in_denominator = true",
    }


_STOP = {fold_text(w) for w in (
    "كيف", "كيفية", "هل", "ما", "ماذا", "متى", "أين", "اين", "يمكن", "يمكنني", "عن", "في",
    "من", "على", "إلى", "الى", "مع", "the", "how", "what", "when", "can", "for", "and",
    "do", "does", "is", "are", "my", "to", "of", "a", "an", "الاستفسار", "استفسار",
)}


def faq_keywords(question: str, keywords: list[str]) -> list[str]:
    if keywords:
        return [fold_text(k) for k in keywords if k]
    words = [fold_text(w) for w in question.replace("؟", " ").replace("?", " ").split()]
    return [w for w in words if len(w) >= 4 and w not in _STOP]


def _faq_coverage(catalogue, L_cases, tax: TaxonomyIndex, bundle_block, umbrellas) -> dict[str, Any]:
    entries = []
    for faq in catalogue:
        entries.append((tax.main(faq.main_service) if faq.main_service else None,
                        faq_keywords(faq.question_ar, faq.keywords)))
    if bundle_block and bundle_block.get("ids"):
        howto_id = _howto_bundle(bundle_block, umbrellas)
        population = [c for c in L_cases if c.bundle == howto_id]
        basis = "root causes in the procedures umbrella"
    else:
        population = [c for c in L_cases if c.contact_type == "استفسار"]
        basis = "inquiry-type cases"
    by_service: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for c in population:
        text = fold_text(f"{c.root_cause or ''} {c.description}")
        covered = any(
            (svc is None or svc == c.main_service) and count_hits(text, kws) >= min(2, len(kws))
            for svc, kws in entries if kws
        )
        by_service[c.main_service][0] += 1
        by_service[c.main_service][1] += int(covered)
    ranked = sorted(by_service.items(), key=lambda x: -x[1][0])
    total = sum(n for n, _ in by_service.values())
    covered_total = sum(k for _, k in by_service.values())
    return {
        "basis": basis,
        "catalogue_size": len(catalogue),
        "overall_pct": pct(covered_total, total),
        "labels": [k for k, _ in ranked],
        "howto_cases": [n for _, (n, _) in ranked],
        "covered_cases": [k for _, (_, k) in ranked],
        "coverage_pct": [pct(k, n) for _, (n, k) in ranked],
    }


def _howto_bundle(bundle_block, umbrellas) -> str | None:
    for uid, label in zip(bundle_block["ids"], bundle_block["labels"]):
        folded = fold_text(label)
        if any(t in folded for t in (fold_text("إجراءات"), fold_text("متطلبات"), fold_text("كيفية"))):
            return uid
    return bundle_block["ids"][0] if bundle_block["ids"] else None


def _events(L_cases, umbrellas, settings: TenantSettings, x8: bool) -> list[dict[str, Any]]:
    clusters: dict[str, Counter] = defaultdict(Counter)
    for c in L_cases:
        if not c.opened:
            continue
        key = (umbrellas[c.bundle].name_ar if c.bundle in umbrellas else c.bundle) if x8 and c.bundle else c.sub_classification
        if key:
            clusters[key][(c.opened.year, c.opened.month)] += 1
    theta = settings.event_threshold_pct / 100
    events = []
    for cluster, counts in clusters.items():
        months = sorted(counts)
        for prev, cur in zip(months, months[1:]):
            before, after = counts[prev], counts[cur]
            if after >= (1 + theta) * before and after >= settings.event_min_cases:
                events.append({
                    "cluster": cluster,
                    "month": month_name(cur[1], "ar"),
                    "month_en": month_name(cur[1], "en"),
                    "from": before,
                    "to": after,
                    "delta_pct": pct(after - before, before) if before else None,
                })
    events.sort(key=lambda e: -(e["to"] - e["from"]))
    return events[:8]


def snapshot_of(out: dict[str, Any], period: Period) -> PeriodSnapshot:
    kpi_like = out.get("TIMELINESS", {})
    channel = out.get("CHANNEL", {})
    bundle = out.get("BUNDLE", {})
    total = sum(channel.get("values", [])) or 0
    return PeriodSnapshot(
        label_ar=period.label_ar,
        label_en=period.label_en,
        total_cases=sum(out.get("ACTUAL_TYPE", {}).get("values", [])),
        classified=sum(v for k, v in zip(out["MAIN_SERVICE"]["labels"], out["MAIN_SERVICE"]["values"]) if k != UNCLASSIFIED["ar"]),
        within_deadline_pct=kpi_like.get("within_deadline_pct"),
        digital_share_pct=pct(
            sum(v for v, d in zip(channel.get("values", []), channel.get("digital", [])) if d), total
        ) if total else None,
        reclassification_rate=out.get("RECLASSIFICATION", {}).get("rate"),
        channel_pct=dict(zip(channel.get("labels", []), channel.get("pct", []))),
        bundle_counts=dict(zip(bundle.get("labels", []), bundle.get("values", []))),
        contact_type_counts=dict(zip(out["ACTUAL_TYPE"]["labels"], out["ACTUAL_TYPE"]["values"])),
        main_service_counts=dict(zip(out["MAIN_SERVICE"]["labels"], out["MAIN_SERVICE"]["values"])),
    )


def _previous(history: History | None, settings: TenantSettings) -> tuple[str, PeriodSnapshot] | None:
    if not history:
        return None
    if settings.comparison_basis is ComparisonBasis.SAME_PERIOD_LAST_YEAR:
        return ("same_period_last_year", history.same_period_last_year) if history.same_period_last_year else None
    return ("previous_period", history.previous_period) if history.previous_period else None


def _delta(previous: float | None, current: float | None) -> dict[str, Any]:
    return {
        "previous": previous,
        "current": current,
        "change": round(current - previous, 1) if previous is not None and current is not None else None,
    }


def _comparison(previous: tuple[str, PeriodSnapshot], current: PeriodSnapshot, settings) -> dict[str, Any]:
    basis, prev = previous
    channels = [
        {"label": label, "previous_pct": prev.channel_pct.get(label), "current_pct": current.channel_pct.get(label)}
        for label in dict.fromkeys([*current.channel_pct, *prev.channel_pct])
    ]
    bundles = [
        {"label": label, "previous": prev.bundle_counts.get(label, 0), "current": current.bundle_counts.get(label, 0)}
        for label in dict.fromkeys([*current.bundle_counts, *prev.bundle_counts])
    ]
    return {
        "basis": basis,
        "label": prev.label_ar,
        "label_en": prev.label_en or prev.label_ar,
        "total_cases": {
            **_delta(prev.total_cases, current.total_cases),
            "change_pct": pct(current.total_cases - prev.total_cases, prev.total_cases),
        },
        "within_deadline_pct": _delta(prev.within_deadline_pct, current.within_deadline_pct),
        "digital_share_pct": _delta(prev.digital_share_pct, current.digital_share_pct),
        "reclassification_rate": _delta(prev.reclassification_rate, current.reclassification_rate),
        "channels": channels,
        "bundles": bundles,
    }


_GAP_TEXT = {
    "transactions": (
        "تفعيل ربط بيانات حجم المعاملات لكل خدمة لاحتساب عدد الاستفسارات لكل 100 معاملة.",
        "Enable the per-service transaction volumes to compute inquiries per 100 transactions.",
    ),
    "faq_catalogue": (
        "تفعيل قائمة الأسئلة الشائعة المعتمدة للجهة لقياس تغطية المحتوى الرقمي.",
        "Enable the entity's approved FAQ catalogue to measure digital-content coverage.",
    ),
    "sla_status": (
        "تفعيل حقل حالة الالتزام بمستوى الخدمة في التصدير لقياس الالتزام بزمن الاستجابة.",
        "Enable the SLA-status field in the export to measure response-time compliance.",
    ),
    "channel": (
        "تفعيل حقل قناة تقديم الخدمة في التصدير لقياس حصة القنوات الرقمية.",
        "Enable the channel field in the export to measure the digital-channel share.",
    ),
    "satisfaction_score": (
        "تفعيل حقل رضا المتعامل في التصدير لربط التحليل بتجربة المتعامل.",
        "Enable the customer-satisfaction field in the export to tie the analysis to customer experience.",
    ),
    "guidebook": (
        "تفعيل ربط دليل الخدمات المعتمد لتحليل الفجوات الرقمية.",
        "Enable the approved service guidebook to analyse digital gaps.",
    ),
}


def _gaps(inputs: ComputeInputs, out: dict[str, Any], has) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    metric: list[dict[str, str]] = []
    if not inputs.reference.transactions:
        metric.append({"key": "transactions", "ar": _GAP_TEXT["transactions"][0], "en": _GAP_TEXT["transactions"][1]})
    if not inputs.reference.faq_catalogue:
        metric.append({"key": "faq_catalogue", "ar": _GAP_TEXT["faq_catalogue"][0], "en": _GAP_TEXT["faq_catalogue"][1]})
    if not inputs.reference.guidebook:
        metric.append({"key": "guidebook", "ar": _GAP_TEXT["guidebook"][0], "en": _GAP_TEXT["guidebook"][1]})
    if not out["TIMELINESS"]["available"]:
        metric.append({"key": "sla_status", "ar": _GAP_TEXT["sla_status"][0], "en": _GAP_TEXT["sla_status"][1]})
    if not has("channel"):
        metric.append({"key": "channel", "ar": _GAP_TEXT["channel"][0], "en": _GAP_TEXT["channel"][1]})
    if not has("satisfaction_score"):
        metric.append({"key": "satisfaction_score", "ar": _GAP_TEXT["satisfaction_score"][0], "en": _GAP_TEXT["satisfaction_score"][1]})
    for ind in inputs.frameworks:
        if ind.get("status") == "not_computable" and ind.get("recommendation_ar"):
            metric.append({"key": f"framework:{ind['key']}", "ar": ind["recommendation_ar"], "en": ind["recommendation_en"]})
    notes: list[dict[str, str]] = []
    from ..api.models.columns import COLUMN_BY_NAME

    for column in inputs.parse_log.columns_present_but_empty:
        spec = COLUMN_BY_NAME[column]
        notes.append({
            "column": column,
            "ar": f"حقل «{spec.label_ar}» موجود في التصدير لكنه فارغ في جميع الحالات (لم يُزوَّد).",
            "en": f"The '{spec.label_en}' column is present in the export but empty on every case (not provided).",
        })
    return metric, notes
