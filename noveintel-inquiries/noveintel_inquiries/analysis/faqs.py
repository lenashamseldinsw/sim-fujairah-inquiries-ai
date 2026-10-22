"""
FAQ detection for Section 04 — the questions customers ask, never their answers.

What the BO's sample output and delivered Q2 report print as priority FAQs is the
largest root-cause clusters, phrased as customer questions, with their case counts;
FAQ coverage is the share of procedures-umbrella cases a catalogue entry answers; and
the report recommends tagging each catalogue question with its volume. All three come
from one pass over the cases, in four steps:

1. **Group** (embeddings). Each case's question is its root cause (X8), else its
   redacted description. Identical texts are one unit; units are embedded and grouped
   greedily — largest first, each unit joining the group whose leader it is most
   similar to, if at least ``faq_group_similarity``, else leading a new one. Exact-string counting would not do: the
   Q2 master writes 10,628 root causes in 5,766 ways, 4,827 of them once.
2. **Shortlist** (embeddings). Each group's nearest catalogue entries — the tenant's
   FAQ catalogue plus the guidebook's FAQs.
3. **Judge** (model). The model reads each group's phrasings beside its shortlisted
   entries, answers included, and says covered / partial / not covered — the nuance
   similarity cannot see (two entries can read alike and answer opposite cases). For
   the largest groups it also writes the customer's question. Every group behind the
   coverage figure is judged, not only the large ones: a small group inheriting its
   nearest large group's verdict was wrong more often than right in calibration.
4. **Merge** (model). One call over the largest groups marks those asking the same
   question in different words, which a single threshold cannot always tell apart.

The model never states a count. Its verdicts become per-case labels — ``faq_status``,
``faq_match``, and ``faq_id`` for the cases behind each priority FAQ (R5) — and the
engine sums them (``engine.compute.faq_coverage`` / ``faq_catalogue_volume``), so a
priority FAQ's frequency is the number of cases carrying its id.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..core42 import CHAT_MODEL, Core42Client, embeddings, tool_input
from ..core42.tokens import ScopedThreadPoolExecutor
from ..engine.compute import FaqPopulation, faq_population
from ..engine.parse import Case
from ..engine.text import clean_label, fold_text
from ..models.reference import FaqEntry, Guidebook
from ..models.settings import TenantSettings
from .prompts import FAQ_JUDGE_TOOL, FAQ_MERGE_TOOL, analysis_system_prompt

__all__ = ["FaqResult", "detect_faqs", "faq_entries", "group_units", "unit_text"]

logger = logging.getLogger(__name__)

_DESCRIPTION_CHARS = 240  # of a redacted description, when there is no root cause
_PHRASINGS = 3            # a group's most frequent phrasings shown to the model
_CANDIDATES = 4           # catalogue entries shortlisted per group
_ANSWER_CHARS = 220       # of each entry's answer: enough to judge by, too little to copy
_BATCH = 30               # groups per judging call
_MERGE_POOL = 3           # × priority_faqs: the largest groups the merge pass compares


@dataclass
class FaqResult:
    """What FAQ detection hands the pipeline. The labels are on the cases."""

    priority: list[dict[str, Any]] = field(default_factory=list)  # VALIDATED_FAQS
    population: FaqPopulation | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)   # indexed by Case.faq_match
    groups: int = 0
    judged: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Group:
    id: str
    units: list[int]
    cases: list[Case]
    vector: np.ndarray
    status: str | None = None
    faq_ids: list[int] = field(default_factory=list)
    question_ar: str = ""
    question_en: str = ""

    @property
    def size(self) -> int:
        return len(self.cases)


# ── Inputs ────────────────────────────────────────────────────────────────────


def unit_text(case: Case) -> str:
    """The text a case's question is grouped on: its root cause, else its description."""
    text = case.root_cause or (case.description or "")[:_DESCRIPTION_CHARS]
    return " ".join(text.replace("ـ", "").split())


def faq_entries(catalogue: list[FaqEntry] | None, guidebook: Guidebook | None) -> list[dict[str, Any]]:
    """The published FAQs a group is judged against: the catalogue, then the guidebook's."""
    from .analyse import guidebook_faqs

    entries = [
        {"question_ar": e.question_ar, "question_en": e.question_en or "", "answer": e.answer_ar or e.answer_en or "",
         "main_service": e.main_service, "source": "catalogue"}
        for e in catalogue or [] if e.question_ar
    ]
    if guidebook:
        entries += [{"question_ar": q, "question_en": "", "answer": a, "main_service": None, "source": "guidebook"}
                    for q, a in guidebook_faqs(guidebook) if q]
    return entries


# ── 1 · Grouping ──────────────────────────────────────────────────────────────


def group_units(vectors: np.ndarray, threshold: float) -> list[list[int]]:
    """Leader grouping, in the order given (largest unit first): a unit joins its most
    similar leader when that is at least ``threshold``, else leads a new group.
    Deterministic for a given order."""
    leaders = np.zeros_like(vectors)
    groups: list[list[int]] = []
    for i, vector in enumerate(vectors):
        if groups:
            sims = leaders[:len(groups)] @ vector
            best = int(np.argmax(sims))
            if sims[best] >= threshold:
                groups[best].append(i)
                continue
        leaders[len(groups)] = vector
        groups.append([i])
    return groups


def _groups(cases: list[Case], threshold: float) -> tuple[list[_Group], list[str]]:
    by_text: dict[str, list[Case]] = {}
    for case in cases:
        text = unit_text(case)
        if text:
            by_text.setdefault(text, []).append(case)
    texts = sorted(by_text, key=lambda t: (-len(by_text[t]), fold_text(t), t))
    if not texts:
        return [], []
    vectors = embeddings.embed_texts(texts, query=True)
    sizes = np.array([len(by_text[t]) for t in texts], dtype=np.float32)
    groups = []
    for n, members in enumerate(group_units(vectors, threshold), 1):
        centroid = (vectors[members] * sizes[members, None]).sum(axis=0)
        groups.append(_Group(
            id=f"g{n}", units=members, cases=[c for i in members for c in by_text[texts[i]]],
            vector=centroid / (np.linalg.norm(centroid) or 1.0),
        ))
    return groups, texts


# ── 3 · Judging ───────────────────────────────────────────────────────────────


def _phrasings(group: _Group, texts: list[str]) -> list[str]:
    return [texts[i] for i in group.units[:_PHRASINGS]]


def _dominant(values: list[Any]) -> Any:
    counted = Counter(v for v in values if v)
    return counted.most_common(1)[0][0] if counted else None


def _tool_call(client: Core42Client, system: str, payload: dict, tool: dict, max_tokens: int) -> dict:
    message = client.messages.create(
        model=CHAT_MODEL, max_tokens=max_tokens, system=system, tools=[tool], tool_choice={"type": "any"},
        stage="faqs", messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    return tool_input(message) or {}


def _judge_batch(client, system: str, batch: list[_Group], write: set[str], shortlist: dict[str, list[int]],
                 entries: list[dict], texts: list[str]) -> None:
    shown = sorted({i for g in batch for i in shortlist.get(g.id, [])})
    payload = {
        "catalogue": [
            {"faq_id": f"F{i}", "question": entries[i]["question_ar"],
             "answer": " ".join(entries[i]["answer"].split())[:_ANSWER_CHARS], "source": entries[i]["source"]}
            for i in shown
        ],
        "groups": [
            {"group_id": g.id, "phrasings": _phrasings(g, texts),
             "main_service": _dominant([c.main_service for c in g.cases]),
             "candidates": [f"F{i}" for i in shortlist.get(g.id, [])], "write_question": g.id in write}
            for g in batch
        ],
    }
    result = _tool_call(client, system, payload, FAQ_JUDGE_TOOL, 6000)
    by_id = {g.id: g for g in batch}
    for item in result.get("groups") or []:
        group = by_id.get(str(item.get("group_id", "")).strip())
        if group is None:
            continue
        allowed = shortlist.get(group.id, [])
        cited = []
        for ref in item.get("faq_ids") or []:
            ref = str(ref).strip().lstrip("Ff")
            if ref.isdigit() and int(ref) in allowed and int(ref) not in cited:
                cited.append(int(ref))
        status = item.get("status") if item.get("status") in ("covered", "partial", "not_covered") else "not_covered"
        if status != "not_covered" and not cited:
            status = "not_covered"  # a verdict must name the entry behind it
        group.status, group.faq_ids = status, cited if status != "not_covered" else []
        if group.id in write:
            group.question_ar = _question(item.get("question_ar"))
            group.question_en = _question(item.get("question_en"))


def _question(value: Any) -> str:
    """A model-written question, trimmed: no trailing full stop after its question mark."""
    text = clean_label(value)
    while text[-2:] in ("?.", "؟.", "?؟"):
        text = text[:-1]
    return text


def _judge(client, groups: list[_Group], write: set[str], entries: list[dict], texts: list[str],
           entity: str, vocabulary, warnings: list[str]) -> None:
    has_catalogue = bool(entries)
    shortlist: dict[str, list[int]] = {}
    if has_catalogue:
        entry_vectors = embeddings.embed_texts(
            [f"{e['question_ar']} {' '.join(e['answer'].split())[:300]}" for e in entries])
        for g in groups:
            sims = entry_vectors @ g.vector
            shortlist[g.id] = [int(i) for i in np.argsort(-sims)[:_CANDIDATES]]
    task = (
        "Task: each group gathers customer inquiries that ask one question, in the customers' own words "
        "(redacted). For each group, judge from its candidate catalogue entries only whether the entity's "
        "published FAQs already answer it: covered, partial or not_covered, citing the entries by faq_id. "
        "Read the answers. Judge the question, not the topic: an entry about the same service that answers a "
        "different question (eligibility instead of the steps, which periods qualify instead of how to apply), "
        "or that is written for another customer type (military instead of civil, employer instead of insured) "
        "or another condition, does not answer it — not_covered. Use partial only when an entry answers part "
        "of the very question asked; when in doubt, not_covered. Where write_question is true, write the question the group asks as a "
        "customer would ask it, one line — a question only, never its answer."
        if has_catalogue else
        "Task: each group gathers customer inquiries that ask one question, in the customers' own words "
        "(redacted). There is no FAQ catalogue: mark every group not_covered with no faq_ids. Where "
        "write_question is true, write the question the group asks as a customer would ask it, one line — "
        "a question only, never its answer."
    )
    system = analysis_system_prompt(entity, task, vocabulary)
    order = sorted(groups, key=lambda g: (str(_dominant([c.main_service for c in g.cases]) or ""), -g.size, g.id))
    batches = [order[i:i + _BATCH] for i in range(0, len(order), _BATCH)]
    with ScopedThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_judge_batch, client, system, b, write, shortlist, entries, texts): b for b in batches}
        failed = 0
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failed += len(futures[future])
                logger.warning("FAQ judging failed for a batch: %s", exc)
    if failed:
        warnings.append(f"FAQ judging failed for {failed} question group(s); their cases count as not covered.")


# ── 4 · Merging ───────────────────────────────────────────────────────────────


def _merge(client, pool: list[_Group], texts: list[str], entity: str, vocabulary) -> list[list[_Group]]:
    """The pool's groups, those asking the same question merged (union-find on the ids)."""
    parent = {g.id: g.id for g in pool}

    def root(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    if len(pool) > 1:
        system = analysis_system_prompt(
            entity,
            "Task: these question groups were formed by wording similarity. List the groups that ask the same "
            "customer question in different words, so they are counted once. Different services, steps, customer "
            "types or conditions are different questions; when in doubt, leave groups apart.",
            vocabulary,
        )
        payload = {"groups": [{"group_id": g.id, "question": g.question_ar, "phrasings": _phrasings(g, texts)} for g in pool]}
        result = _tool_call(client, system, payload, FAQ_MERGE_TOOL, 3000)
        for item in result.get("same_question") or []:
            ids = [str(x).strip() for x in (item.get("group_ids") if isinstance(item, dict) else item) or []]
            ids = [x for x in ids if x in parent]
            for other in ids[1:]:
                parent[root(other)] = root(ids[0])
    merged: dict[str, list[_Group]] = {}
    for g in pool:
        merged.setdefault(root(g.id), []).append(g)
    return list(merged.values())


# ── The priority list and the labels ──────────────────────────────────────────


def _status(group: _Group, entries: list[dict]) -> str:
    if not entries:
        return "not_checked"
    if group.status == "covered":
        return f"in_{entries[group.faq_ids[0]]['source']}"
    if group.status == "partial":
        return "partial"
    return "new" if group.status == "not_covered" else "not_checked"


def _priority(merged: list[list[_Group]], entries: list[dict], settings: TenantSettings) -> list[dict]:
    items = []
    for members in merged:
        members = sorted(members, key=lambda g: (-g.size, g.id))
        lead = members[0]
        cases = [c for g in members for c in g.cases]
        if len(cases) < settings.faq_min_cases:
            continue
        rc = Counter(unit_text(c) for c in cases)
        items.append({
            "members": members,
            "question_ar": lead.question_ar or next((g.question_ar for g in members if g.question_ar), "") or rc.most_common(1)[0][0],
            "question_en": lead.question_en or next((g.question_en for g in members if g.question_en), ""),
            "frequency": len(cases),
            "validation_status": _status(lead, entries),
            "matched_faqs": [entries[i]["question_ar"] for i in lead.faq_ids[:3]],
            "main_service": _dominant([c.main_service for c in cases]),
            "bundle": _dominant([c.bundle for c in cases]),
            "root_causes": [{"text": t, "cases": n} for t, n in rc.most_common(3)],
            "evidence_case_ids": sorted(c.case_id for c in cases),
        })
    items.sort(key=lambda q: (-q["frequency"], q["evidence_case_ids"][0]))
    items = items[:settings.priority_faqs]
    for n, item in enumerate(items, 1):
        item["id"] = f"Q{n}"
        for g in item.pop("members"):
            for case in g.cases:
                case.faq_id = item["id"]
    return items


def detect_faqs(
    cases: list[Case],
    *,
    umbrellas: list[Any],
    settings: TenantSettings,
    catalogue: list[FaqEntry] | None,
    guidebook: Guidebook | None,
    entity: str,
    vocabulary: dict[str, dict[str, str]],
    client: Core42Client | None = None,
    progress: Callable[[float, str, str], None] | None = None,
) -> FaqResult:
    result = FaqResult()
    for case in cases:
        case.faq_id = case.faq_status = case.faq_match = None
    population = faq_population(cases, umbrellas, settings)
    result.population = population
    result.entries = entries = faq_entries(catalogue, guidebook)
    if not population.cases:
        return result
    if progress:
        progress(0.6, "اكتشاف الأسئلة الشائعة وتغطيتها", "Stage 3: FAQ detection and coverage")
    client = client or Core42Client()

    groups, texts = _groups(population.cases, settings.faq_group_similarity)
    result.groups = len(groups)
    ranked = sorted(groups, key=lambda g: (-g.size, g.id))
    pool = [g for g in ranked if g.size >= settings.faq_min_cases][:_MERGE_POOL * settings.priority_faqs]
    write = {g.id for g in pool}
    if entries:
        coverage_ids = {id(c) for c in population.coverage}
        to_judge = [g for g in groups if g.id in write or any(id(c) in coverage_ids for c in g.cases)]
    else:
        to_judge = pool
    result.judged = len(to_judge)
    _judge(client, to_judge, write, entries, texts, entity, vocabulary, result.warnings)

    if entries:  # without published FAQs there is nothing a case could be covered by
        for g in to_judge:
            for case in g.cases:
                case.faq_status = g.status
                case.faq_match = g.faq_ids[0] if g.faq_ids else None

    try:
        merged = _merge(client, pool, texts, entity, vocabulary)
    except Exception as exc:
        result.warnings.append(f"FAQ question merging failed: {type(exc).__name__}; groups are listed unmerged.")
        logger.warning("FAQ merging failed: %s", exc)
        merged = [[g] for g in pool]
    result.priority = _priority(merged, entries, settings)
    return result
