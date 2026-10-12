"""
The qualitative analysis behind S4–S6: journey frictions, notification opportunities,
FAQ candidates and the guidebook gap table.

The model names and describes; the engine counts. Frictions and notification
opportunities are tied to whole case groups (a group to at most one item, enforced
here), so their counts are sums of frozen labels. FAQ frequency is its evidence count
(Data Mapping §4, ``frequency = len(valid_evidence)``): every case of the service is
matched against the FAQ's keywords, each case to at most one FAQ, and the match is
written on the case (``faq_id``) — the evidence link R5 asked for, carried into the
labels document and the workbook.

The gap table is conditional on the tenant's guidebook (a Module 03 reference list).
Without one it is omitted and the report says so; it is never filled from a default.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from ..api.models.reference import FaqEntry, Guidebook
from ..core42 import CHAT_MODEL, Core42Client
from ..core42.tokens import ScopedThreadPoolExecutor
from ..engine.compute import faq_keywords, pct
from ..engine.parse import Case
from ..engine.text import clean_label, count_hits, fold_text
from .groups import CaseGroup, build_groups, group_payload
from .prompts import FAQ_TOOL, GAP_TOOL, JOURNEY_TOOL, analysis_system_prompt

__all__ = ["AnalysisResult", "analyse", "guidebook_entries", "guidebook_meta"]

logger = logging.getLogger(__name__)

FAQ_SERVICES = 6
FAQ_SAMPLES = 25
MIN_FAQ_EVIDENCE = 3


@dataclass
class AnalysisResult:
    frictions: list[dict[str, Any]] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    faqs: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    guidebook: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


def _tool_call(client: Core42Client, system: str, user: str, tool: dict, max_tokens: int,
               stage: str, model: str = CHAT_MODEL) -> dict:
    message = client.messages.create(
        model=model, max_tokens=max_tokens, system=system, tools=[tool],
        tool_choice={"type": "any"}, stage=stage,
        messages=[{"role": "user", "content": user}],
    )
    for block in message.content:
        if getattr(block, "type", "") == "tool_use":
            return block.input or {}
    return {}


# ── Journey frictions and notification opportunities ─────────────────────────


def _assign(items: list[dict], groups: dict[str, CaseGroup], prefix: str) -> list[dict]:
    """Keep each group in at most one item; count each item from its groups."""
    taken: set[str] = set()
    out = []
    for item in items:
        ids = []
        for gid in item.get("group_ids") or []:
            gid = str(gid).strip()
            if gid in groups and gid not in taken:
                taken.add(gid)
                ids.append(gid)
        if not ids:
            continue
        members = [c for gid in ids for c in groups[gid].cases]
        out.append({
            **{k: clean_label(v) if isinstance(v, str) else v for k, v in item.items() if k != "group_ids"},
            "group_ids": ids,
            "case_count": len(members),
            "evidence_case_ids": [c.case_id for c in members[:10]],
            "sub_classifications": [groups[g].sub_classification for g in ids],
            "main_services": sorted({groups[g].main_service for g in ids}),
        })
    out.sort(key=lambda x: -x["case_count"])
    for i, item in enumerate(out, 1):
        item["id"] = f"{prefix}{i}"
    return out


def _journey(client, groups: list[CaseGroup], entity: str, vocabulary, total: int) -> tuple[list, list]:
    system = analysis_system_prompt(
        entity,
        "Task: map the customer journey. From the case groups, name the friction points that made customers "
        "contact the entity, each with its root-cause category and one improvement action, and the proactive "
        "notification opportunities that would make a contact unnecessary. Assign whole groups by group_id; "
        "a group goes to at most one friction and at most one notification opportunity. Leave out groups that "
        "show no friction (thanks, one-off requests).",
        vocabulary,
    )
    payload = {"total_cases": total, "groups": [group_payload(g) for g in groups]}
    result = _tool_call(client, system, json.dumps(payload, ensure_ascii=False), JOURNEY_TOOL, 12000, "journey")
    by_id = {g.id: g for g in groups}
    frictions = _assign(result.get("frictions") or [], by_id, "F")
    notifications = _assign(result.get("notification_opportunities") or [], by_id, "N")
    for n in notifications:
        n["cases_eliminated"] = n["case_count"]
    return frictions, notifications


# ── FAQ candidates ────────────────────────────────────────────────────────────


def _faqs_for_service(client, service: str, members: list[Case], entity: str, vocabulary) -> list[dict]:
    import random

    rng = random.Random(f"faq:{service}")
    pool = [c for c in members if c.contact_type == "استفسار" and c.description] or [c for c in members if c.description]
    picked = rng.sample(pool, min(FAQ_SAMPLES, len(pool)))
    system = analysis_system_prompt(
        entity,
        f"Task: propose the frequently asked questions the cases of the main service «{service}» show — "
        "questions a published FAQ could answer before the customer contacts the entity. Write each answer "
        "from what the agents' resolutions say. Give 3–6 distinctive Arabic keywords per question, the words "
        "a customer asking it actually writes. Propose 3 to 6 questions.",
        vocabulary,
    )
    payload = {
        "main_service": service,
        "samples": [
            {"description": " ".join(c.description.split())[:300], "resolution": " ".join(c.resolution_text.split())[:300]}
            for c in picked
        ],
    }
    result = _tool_call(client, system, json.dumps(payload, ensure_ascii=False), FAQ_TOOL, 5000, "faqs")
    out = []
    for item in result.get("faqs") or []:
        keywords = [fold_text(k) for k in item.get("keywords_ar") or [] if k and len(fold_text(k)) >= 3]
        if keywords:
            out.append({**{k: clean_label(v) for k, v in item.items() if isinstance(v, str)},
                        "keywords": keywords, "main_service": service})
    return out


def _match_faqs(cases: list[Case], candidates: list[dict]) -> list[dict]:
    """Each case to its best-matching FAQ of the same service; frequency = evidence."""
    by_service: dict[str, list[dict]] = {}
    for faq in candidates:
        by_service.setdefault(faq["main_service"], []).append(faq)
    evidence: dict[int, list[str]] = {id(f): [] for f in candidates}
    for case in cases:
        options = by_service.get(case.main_service)
        if not options:
            continue
        text = fold_text(f"{case.description} {case.root_cause or ''}")
        best, best_hits = None, 0
        for faq in options:
            need = min(2, len(faq["keywords"]))
            hits = count_hits(text, faq["keywords"])
            if hits >= need and hits > best_hits:
                best, best_hits = faq, hits
        if best is not None:
            evidence[id(best)].append(case.case_id)
            case.faq_id = id(best)  # replaced by the stable FAQ id below
    kept = []
    for faq in candidates:
        ids = evidence[id(faq)]
        if len(ids) >= MIN_FAQ_EVIDENCE:
            kept.append({**faq, "frequency": len(ids), "evidence_case_ids": ids, "_key": id(faq)})
    kept.sort(key=lambda f: -f["frequency"])
    stable = {}
    for i, faq in enumerate(kept, 1):
        faq["id"] = f"Q{i}"
        stable[faq.pop("_key")] = faq["id"]
    for case in cases:
        if isinstance(case.faq_id, int):
            case.faq_id = stable.get(case.faq_id)
    return kept


def _validate_faqs(faqs: list[dict], catalogue: list[FaqEntry] | None, guidebook_faq: list[tuple[str, str]]) -> None:
    """Mark each FAQ as already published (catalogue or guidebook) or new."""
    published = []
    for entry in catalogue or []:
        published.append(("catalogue", faq_keywords(entry.question_ar, entry.keywords)))
    for question, _ in guidebook_faq:
        published.append(("guidebook", faq_keywords(question, [])))
    for faq in faqs:
        text = fold_text(f"{faq.get('question_ar', '')}")
        status = "new"
        for source, kws in published:
            if kws and count_hits(text, kws) >= max(2, len(kws) // 2):
                status = f"in_{source}"
                break
        faq["validation_status"] = status


# ── Guidebook ─────────────────────────────────────────────────────────────────


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " · ".join(_flatten(v) for v in value if v)
    if isinstance(value, dict):
        return " · ".join(_flatten(v) for v in value.values() if v)
    return str(value)


def guidebook_entries(gb: Guidebook) -> list[tuple[str, str]]:
    entries = [(e.title, e.text) for e in gb.entries]
    for service in gb.services or []:
        title = service.get("service_name") or service.get("name") or service.get("title") or ""
        body = " · ".join(
            _flatten(service.get(k)) for k in (
                "description", "sub_service_name", "requirements", "delivery_channels",
                "service_center_steps", "processing_time", "fee_note", "working_hours",
            ) if service.get(k)
        )
        if title:
            entries.append((str(title), body))
    for item in gb.faq or []:
        question = item.get("question_ar") or item.get("question") or ""
        if question:
            entries.append((str(question), _flatten(item.get("answer_ar") or item.get("answer"))))
    return entries


def guidebook_faqs(gb: Guidebook) -> list[tuple[str, str]]:
    return [
        (str(i.get("question_ar") or i.get("question") or ""), _flatten(i.get("answer_ar") or i.get("answer")))
        for i in gb.faq or [] if i.get("question_ar") or i.get("question")
    ]


def guidebook_meta(gb: Guidebook) -> dict[str, Any]:
    doc = gb.document or {}
    topics = list(gb.topics) or [
        s.get("name_ar") or s.get("name") for s in (gb.sections or []) if s.get("name_ar") or s.get("name")
    ]
    return {
        "title": gb.title or doc.get("title_ar") or doc.get("title") or "",
        "title_en": doc.get("title_en") or gb.title or "",
        "pages": gb.pages or doc.get("total_pages") or doc.get("pages"),
        "year": gb.year or doc.get("year") or doc.get("source_date") or doc.get("edition"),
        "topics": [t for t in topics if t],
        "faq_count": len(gb.faq or []),
        "entries": len(guidebook_entries(gb)),
    }


def _retrieve(entries: list[tuple[str, str]], query: str, k: int = 3) -> list[dict]:
    words = [w for w in fold_text(query).split() if len(w) >= 4]
    scored = []
    for title, text in entries:
        hay = fold_text(f"{title} {text}")
        score = sum(1 for w in set(words) if w in hay) + 2 * sum(1 for w in set(words) if w in fold_text(title))
        if score:
            scored.append((score, title, text))
    scored.sort(key=lambda x: -x[0])
    return [{"title": t, "text": " ".join(x.split())[:500]} for _, t, x in scored[:k]]


def _gaps(client, frictions: list[dict], gb: Guidebook, entity: str, vocabulary, total: int) -> list[dict]:
    entries = guidebook_entries(gb)
    payload = []
    for f in frictions:
        query = " ".join([f.get("name_ar", ""), *f.get("sub_classifications", []), *f.get("main_services", [])])
        payload.append({
            "friction_id": f["id"],
            "friction": f.get("name_ar"),
            "remedy": f.get("remedy_ar"),
            "services": f.get("main_services"),
            "guidebook_text": _retrieve(entries, query),
        })
    system = analysis_system_prompt(
        entity,
        "Task: for each friction, judge from the guidebook text given with it whether the published guidebook "
        "already answers the customer's need — Covered, Partially Covered or Missing — quote the relevant line "
        "when there is one, name the gap type, and recommend one action. Judge only from the text given.",
        vocabulary,
    )
    result = _tool_call(client, system, json.dumps({"frictions": payload}, ensure_ascii=False), GAP_TOOL, 8000, "gaps")
    by_id = {f["id"]: f for f in frictions}
    gaps = []
    for item in result.get("gaps") or []:
        friction = by_id.get(str(item.get("friction_id", "")).strip())
        if not friction:
            continue
        status = item.get("guidebook_status") if item.get("guidebook_status") in ("Covered", "Partially Covered", "Missing") else "Missing"
        share = pct(friction["case_count"], total) or 0
        priority = "high" if status == "Missing" and share >= 5 else ("medium" if status != "Covered" else "low")
        gaps.append({
            "friction_id": friction["id"],
            "topic_ar": clean_label(item.get("topic_ar")) or friction.get("name_ar"),
            "topic_en": clean_label(item.get("topic_en")) or friction.get("name_en"),
            "case_count": friction["case_count"],
            "guidebook_status": status,
            "guidebook_excerpt": clean_label(item.get("guidebook_excerpt"))[:240],
            "gap_type": item.get("gap_type"),
            "priority": priority,
            "recommendation_ar": clean_label(item.get("recommendation_ar")),
            "recommendation_en": clean_label(item.get("recommendation_en")),
            "root_cause_category": friction.get("root_cause_category"),
            "evidence_case_ids": friction.get("evidence_case_ids", []),
        })
    gaps.sort(key=lambda g: ({"high": 0, "medium": 1, "low": 2}[g["priority"]], -g["case_count"]))
    for i, gap in enumerate(gaps, 1):
        gap["id"] = f"G{i}"
    return gaps


# ── Entry point ───────────────────────────────────────────────────────────────


def analyse(
    cases: list[Case],
    *,
    entity: str,
    vocabulary: dict[str, dict[str, str]],
    faq_catalogue: list[FaqEntry] | None,
    guidebook: Guidebook | None,
    client: Core42Client | None = None,
    progress: Callable[[float, str, str], None] | None = None,
    journey: bool = True,
    faqs: bool = True,
    gaps: bool = True,
) -> AnalysisResult:
    """The qualitative items. ``journey``/``faqs``/``gaps`` switch off the model work
    that no shown section needs (gaps need the journey's frictions)."""
    result = AnalysisResult()
    client = client or Core42Client()
    labelled = [c for c in cases if c.main_service and c.sub_classification]
    groups = build_groups(labelled)
    total = len(cases)

    result.patterns = [
        {
            "id": f"P{i + 1}",
            "main_service": g.main_service,
            "sub_classification": g.sub_classification,
            "case_count": g.size,
            "pct": pct(g.size, total),
            "dominant_contact_type": Counter(c.contact_type for c in g.cases).most_common(1)[0][0] if g.cases else None,
        }
        for i, g in enumerate(groups[:10])
    ]

    services = Counter(c.main_service for c in labelled if c.main_service)
    faq_services = [s for s, n in services.most_common(FAQ_SERVICES) if n >= 10] if faqs else []
    if progress:
        progress(0.5, "تحليل رحلة المتعامل والأسئلة الشائعة", "Stage 3: Journey and FAQ analysis")

    with ScopedThreadPoolExecutor(max_workers=5) as pool:
        journey_future = pool.submit(_journey, client, groups, entity, vocabulary, total) if groups and journey else None
        faq_futures = {
            pool.submit(_faqs_for_service, client, s, [c for c in labelled if c.main_service == s], entity, vocabulary): s
            for s in faq_services
        }
        candidates: list[dict] = []
        for future in as_completed(faq_futures):
            try:
                candidates.extend(future.result())
            except Exception as exc:
                result.warnings.append(f"FAQ analysis failed for «{faq_futures[future]}»: {type(exc).__name__}")
                logger.warning("FAQ analysis failed for %s: %s", faq_futures[future], exc)
        if journey_future:
            try:
                result.frictions, result.notifications = journey_future.result()
            except Exception as exc:
                result.warnings.append(f"Journey analysis failed: {type(exc).__name__}")
                logger.warning("Journey analysis failed: %s", exc)

    result.faqs = _match_faqs(labelled, candidates)
    gb_faqs = guidebook_faqs(guidebook) if guidebook else []
    _validate_faqs(result.faqs, faq_catalogue, gb_faqs)

    if guidebook:
        result.guidebook = guidebook_meta(guidebook)
        if result.frictions and gaps:
            if progress:
                progress(0.6, "تحليل الفجوات مقابل دليل الخدمات", "Stage 3: Guidebook gap analysis")
            try:
                result.gaps = _gaps(client, result.frictions, guidebook, entity, vocabulary, total)
            except Exception as exc:
                result.warnings.append(f"Gap analysis failed: {type(exc).__name__}")
                logger.warning("Gap analysis failed: %s", exc)
    return result
