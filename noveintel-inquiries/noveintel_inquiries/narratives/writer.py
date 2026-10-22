"""
Layer 3 — the narrative writer, and the pre-flight checklist enforced in code.

Two structured calls (the ADPF ``InquiriesReportNarratives`` and the nine-section
``SectionNarratives``), in Arabic, under one system prompt, in parallel; each part runs
its own retry rounds and is handed on the moment it is final, so its English
translation can start while the other part is still being written. Then
the Full Report Prompt §6 checklist, applied rather than hoped for:

* every number in the prose is checked against the context — a figure that is not
  there is sent back once with the list of offenders; one that survives the retry is
  reported as ``narrative_unverified_figures``;
* banned words are replaced; the tenant vocabulary is applied; list items lose any
  leading number or bullet;
* conditional fields are emptied when their input is absent, whatever the model wrote;
* an initiative's ``addresses_cases`` and a use case's ``impact_cases`` are set from the
  reference they name — the model's own number is never kept;
* the KPI tile's short name is cut to 14 Arabic / 16 English characters.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from ..models.narratives import (
    InquiriesReportNarratives,
    ReportNarratives,
    SectionNarratives,
)
from ..core42 import CHAT_MODEL, Core42Client, tool_input
from ..core42.tokens import ScopedThreadPoolExecutor
from ..engine.text import to_western_digits
from ..engine.wording import apply_vocabulary, clean_list_item, replace_banned
from .prompts import narrative_system_prompt, translation_system_prompt

__all__ = [
    "NarrativeOutcome", "PartOutcome", "write_narratives", "translate_part", "translate_narratives",
    "combine", "check_figures", "postprocess", "postprocess_part",
]

logger = logging.getLogger(__name__)

_LIST_FIELDS = ("key_findings", "recommendations", "priority_faqs", "friction_points", "event_narratives")
_ROOT_FIELDS = (
    "root_causes_intro", "bundle_distribution_narrative", "bundle_by_service_narrative",
    "top_root_causes_narrative", "timeliness_by_bundle_narrative",
)


class NarrativeOutcome(BaseModel):
    narratives: ReportNarratives | None = None
    units: list["PartOutcome"] = []
    unverified: list[str] = []
    incomplete: list[str] = []
    banned_hits: list[str] = []
    dropped_initiatives: int = 0
    error: str | None = None


def _inline_refs(schema: dict) -> dict:
    """Pydantic's $defs/$ref inlined — some gateways reject references in tools."""
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def _tool(name: str, model: type[BaseModel], must_write: list[str] | None = None,
          only: list[str] | None = None) -> dict:
    """The structured-output tool. Fields whose input is present may not be empty.

    Without this an all-empty answer is schema-valid, and a reasoning model sometimes
    returns exactly that in a few seconds instead of writing the report. ``only``
    limits the tool to the fields being asked for: a field of a hidden section is not
    in the schema at all, so the model spends no tokens on it.
    """
    schema = _inline_refs(model.model_json_schema())
    if only is not None:
        schema["properties"] = {k: v for k, v in schema["properties"].items() if k in only}
    schema["required"] = list(schema["properties"])
    for field in must_write or []:
        prop = schema["properties"].get(field, {})
        if prop.get("type") == "string":
            prop["minLength"] = 1
        elif prop.get("type") == "array":
            prop["minItems"] = 1
    return {
        "name": name,
        "description": "Return every field. Fields listed as required text must be written; a conditional "
                       "field without input is an empty string or list.",
        "input_schema": schema,
    }


def must_write(context: dict, model: type[BaseModel]) -> list[str]:
    """Fields that must carry text for this context — the inverse of the conditional rules."""
    absent: set[str] = set()
    if model is InquiriesReportNarratives:
        if "previous_period" not in context:
            absent.add("comparative_analysis")
        if "INQ_PER_100_TX" not in context:
            absent.add("transactions_ratio_narrative")
        if "FAQ_COVERAGE" not in context and "DEFLECTABLE_PCT" not in context:
            absent.add("digital_opportunity_narrative")
        if "VALIDATED_FAQS" not in context:
            absent.add("priority_faqs")
        if "EVENTS" not in context:
            absent.add("event_narratives")
        if "JOURNEY_MAP" not in context:
            absent.add("friction_points")
        if "INITIATIVE_SOURCES" not in context:
            absent.add("initiatives")
        if "BUNDLE" not in context:
            absent |= set(_ROOT_FIELDS) | {"bundle_narratives", "service_focus_narratives"}
    else:
        if "DEPARTMENT" not in context:
            absent.add("department_narrative")
        if "GAP_TABLE" not in context:
            absent |= {"digital_gaps_narrative", "gap_root_causes_narrative"}
        if not context.get("OUT_OF_SCOPE_DETECTED", {}).get("total"):
            absent.add("out_of_scope_narrative")
        if "INITIATIVE_SOURCES" not in context:
            absent.add("ai_use_cases")
    return [name for name in model.model_fields if name not in absent]


def _write_these(lang: str, fields: list[str]) -> str:
    if lang == "ar":
        return "اكتب نصاً فعلياً في كل حقل من الحقول التالية، ولا يُقبل فيها نص فارغ: " + "، ".join(fields)
    return "Write real text in every one of these fields; an empty value is not accepted: " + ", ".join(fields)


def _empty_note(lang: str, fields: list[str]) -> str:
    if lang == "ar":
        return "تركت إجابتك السابقة هذه الحقول فارغة، وهي مطلوبة: " + "، ".join(fields) + ". اكتبها كاملة."
    return "Your previous answer left these required fields empty: " + ", ".join(fields) + ". Write them in full."


# ── Figures ──────────────────────────────────────────────────────────────────

_NUMBER = re.compile(r"\d[\d,٬]*(?:[.٫]\d+)?")
_ALWAYS_OK = {str(n) for n in range(0, 13)} | {"30", "100"}


def _norm(token: str) -> str:
    token = to_western_digits(token).replace("٬", "").replace(",", "").replace("٫", ".")
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token


def _allowed_numbers(context: dict) -> set[str]:
    allowed = set(_ALWAYS_OK)

    def walk(node: Any) -> None:
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, (int, float)):
            allowed.add(_norm(str(node)))
            if isinstance(node, float):
                allowed.add(_norm(f"{node:.1f}"))
                allowed.add(_norm(f"{node:.2f}"))
            return
        if isinstance(node, str):
            for token in _NUMBER.findall(to_western_digits(node)):
                allowed.add(_norm(token))
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(k)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(context)
    return allowed


def _texts(narr: dict) -> list[str]:
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for k, v in node.items():
                if k not in ("addresses_cases", "impact_cases", "bundle_ref", "source_ref", "horizon", "effort"):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(narr)
    return out


def check_figures(narr: dict, context: dict) -> list[str]:
    """Numbers in the prose that do not occur anywhere in the context."""
    allowed = _allowed_numbers(context)
    offenders = []
    for text in _texts(narr):
        for token in _NUMBER.findall(to_western_digits(text)):
            if _norm(token) not in allowed:
                offenders.append(token)
    return sorted(set(offenders))


# ── Post-processing ──────────────────────────────────────────────────────────


def _clean_text(text: str, lang: str, vocabulary: dict[str, str], hits: list[str]) -> str:
    text, found = replace_banned(text, lang)
    hits.extend(found)
    return apply_vocabulary(text, vocabulary, lang)


def _shorten(name: str, limit: int) -> str:
    name = " ".join(name.split())
    if len(name) <= limit:
        return name
    cut = name[:limit]
    return cut[: cut.rfind(" ")].strip() if " " in cut else cut


_EMPTY = {"report": InquiriesReportNarratives, "sections": SectionNarratives}


def postprocess_part(part: str, data: dict, context: dict, lang: str, vocabulary: dict[str, str],
                     sources: dict[str, dict], hidden: set[str] | None = None) -> tuple[dict, list[str], int]:
    """The checklist for one part. Returns the cleaned part, banned-word hits and dropped refs."""
    hits: list[str] = []

    def clean(node: Any) -> Any:
        if isinstance(node, str):
            return _clean_text(node, lang, vocabulary, hits)
        if isinstance(node, list):
            return [clean(x) for x in node]
        if isinstance(node, dict):
            return {k: (clean(v) if k not in ("bundle_ref", "source_ref", "horizon", "effort") else v) for k, v in node.items()}
        return node

    data = clean(data)
    dropped = 0
    if part == "report":
        report = data
        for field in _LIST_FIELDS:
            report[field] = [x for x in (clean_list_item(i) for i in report.get(field) or []) if x]
        # Conditional fields: empty exactly when the input is absent (hard rule 6).
        if "previous_period" not in context:
            report["comparative_analysis"] = ""
        if "INQ_PER_100_TX" not in context:
            report["transactions_ratio_narrative"] = ""
        if "FAQ_COVERAGE" not in context and "DEFLECTABLE_PCT" not in context:
            report["digital_opportunity_narrative"] = ""
        if "VALIDATED_FAQS" not in context:
            report["priority_faqs"] = []
        if "EVENTS" not in context:
            report["event_narratives"] = []
        if "JOURNEY_MAP" not in context:
            report["friction_points"] = []
        if "BUNDLE" not in context:
            for field in _ROOT_FIELDS:
                report[field] = ""
            report["bundle_narratives"] = []
            report["service_focus_narratives"] = []
        else:
            bundles = set(context["BUNDLE"]["labels"])
            report["bundle_narratives"] = [b for b in report.get("bundle_narratives") or [] if b.get("bundle") in bundles]
            focus = {f["service"] for f in context.get("SERVICE_FOCUS", [])}
            report["service_focus_narratives"] = [
                f for f in report.get("service_focus_narratives") or [] if f.get("service") in focus
            ]
        # Counts come from the reference, never from the model.
        initiatives = []
        for item in report.get("initiatives") or []:
            source = sources.get(str(item.get("bundle_ref", "")).strip())
            if not source:
                dropped += 1
                continue
            item["addresses_cases"] = source["cases"]
            item["title"] = clean_list_item(item.get("title", "")) or (
                f"معالجة: {source.get('name', '')}" if lang == "ar" else f"Address: {source.get('name', '')}"
            ).strip(": ")
            initiatives.append(item)
        report["initiatives"] = initiatives
        report["top_service_short"] = _shorten(report.get("top_service_short") or "", 14 if lang == "ar" else 16)
    else:
        sections = data
        if "DEPARTMENT" not in context:
            sections["department_narrative"] = ""
        if "GAP_TABLE" not in context:
            sections["digital_gaps_narrative"] = ""
            sections["gap_root_causes_narrative"] = ""
        if not context.get("OUT_OF_SCOPE_DETECTED", {}).get("total"):
            sections["out_of_scope_narrative"] = ""
        use_cases = []
        for item in sections.get("ai_use_cases") or []:
            source = sources.get(str(item.get("source_ref", "")).strip())
            if not source:
                dropped += 1
                continue
            item["impact_cases"] = source["cases"]
            use_cases.append(item)
        sections["ai_use_cases"] = use_cases
    # A section the tenant hid prints nothing, whatever the model wrote.
    model = _EMPTY[part]
    for field in hidden or ():
        annotation = str(model.model_fields[field].annotation)
        data[field] = [] if annotation.startswith("list") else ""
    return data, sorted(set(hits)), dropped


def postprocess(report: dict, sections: dict, context: dict, lang: str,
                vocabulary: dict[str, str], sources: dict[str, dict]) -> tuple[dict, dict, list[str], int]:
    """Both parts through the checklist."""
    report, hits_r, dropped_r = postprocess_part("report", report, context, lang, vocabulary, sources)
    sections, hits_s, dropped_s = postprocess_part("sections", sections, context, lang, vocabulary, sources)
    return report, sections, sorted(set(hits_r + hits_s)), dropped_r + dropped_s


# ── Calls ────────────────────────────────────────────────────────────────────


def _call(client: Core42Client, system: str, context: dict, tool: dict, note: str | None = None,
          stage: str = "narratives", retry: bool | None = None) -> dict:
    content = json.dumps(context, ensure_ascii=False, default=str)
    if note:
        content = f"{note}\n\n{content}"
    message = client.messages.create(
        model=CHAT_MODEL, max_tokens=14000, system=system, tools=[tool],
        tool_choice={"type": "any"}, stage=stage,
        messages=[{"role": "user", "content": content}],
    )
    data = tool_input(message)  # fields split across several tool calls are merged
    if data is None:
        raise ValueError("The narrative model returned no structured output.")
    logger.info(
        "Narrative %s: %d/%d fields filled, stop=%s%s.", tool["name"], _filled(data), len(data),
        getattr(message, "stop_reason", "?"), " (retry)" if (note if retry is None else retry) else "",
    )
    return data


def _filled(data: dict) -> int:
    return sum(1 for v in data.values() if v not in ("", [], None))


def _retry_note(lang: str, offenders: list[str], draft: dict) -> str:
    """An edit request: the previous draft, the figures to fix, everything else kept."""
    listed = ", ".join(offenders)
    previous = json.dumps(draft, ensure_ascii=False)
    if lang == "ar":
        return (
            f"وردت في مسودتك السابقة أرقام غير موجودة في السياق: {listed}. "
            "أعد المسودة نفسها كاملة بجميع حقولها ونصوصها كما هي، مع استبدال كل رقم من هذه الأرقام بالقيمة "
            "المطابقة في السياق حرفياً أو حذف العبارة التي تتضمنه. لا تترك حقلاً فارغاً كان مكتوباً.\n"
            f"المسودة السابقة:\n{previous}\n\nالسياق:"
        )
    return (
        f"Your previous draft contained figures not in the context: {listed}. "
        "Return the same draft in full — every field and its text as written — replacing each of these "
        "figures with the matching context value verbatim, or removing the phrase that carries it. Do not "
        "empty a field that had text.\n"
        f"Previous draft:\n{previous}\n\nContext:"
    )


def _missing(data: dict, model: type[BaseModel]) -> list[str]:
    return [name for name in model.model_fields if name not in data]


def _complete(data: dict, model: type[BaseModel]) -> list[str]:
    """Fill fields the model left out with their empty value; return their names."""
    missing = _missing(data, model)
    for name in missing:
        annotation = str(model.model_fields[name].annotation)
        data[name] = [] if annotation.startswith("list") else ""
    return missing


def _empty_part(part: str) -> dict:
    data: dict = {}
    _complete(data, _EMPTY[part])
    return data


class PartOutcome(BaseModel):
    """One unit of the narrative — a part, or a group of a part's fields — final and
    cleaned, or why not. ``fields`` are the fields this unit wrote; ``None`` means all
    of the part's fields (the unit is the whole part)."""

    part: str
    unit: str = ""
    fields: list[str] | None = None
    data: dict | None = None
    unverified: list[str] = []
    incomplete: list[str] = []
    banned_hits: list[str] = []
    dropped: int = 0
    error: str | None = None


NarrativeOutcome.model_rebuild()


def _rounds(call: Callable[[str | None], dict], *, lang: str, model: type[BaseModel], required: list[str],
            asked: list[str], context: dict, label: str) -> tuple[dict | None, list[str], str | None]:
    """First draft, a retry if it came back empty, a corrective retry for figures.

    A retry replaces a draft only when it is at least as complete — a correction must
    never cost the report its prose.
    """
    def attempt(note: str | None) -> dict | None:
        try:
            return call(note)
        except Exception as exc:
            logger.warning("Narrative %s failed: %s", label, exc)
            attempt.error = type(exc).__name__  # type: ignore[attr-defined]
            return None

    attempt.error = None  # type: ignore[attr-defined]

    # Only the fields asked for count: a hidden section's field is not in the tool.
    def missing(answer: dict) -> list[str]:
        return [f for f in asked if f not in answer]

    def quality(answer: dict | None) -> tuple[int, int]:
        return (-len(missing(answer)), _filled(answer)) if answer else (-999, 0)

    def unwritten(answer: dict | None) -> list[str]:
        return [f for f in required if (answer or {}).get(f) in (None, "", [])]

    draft = attempt(None)
    gaps = unwritten(draft)
    if draft is None or missing(draft) or len(gaps) > len(required) // 3:
        retry = attempt(_empty_note(lang, gaps or required))
        if retry and quality(retry) > quality(draft):
            draft = retry
    if draft is None:
        return None, [], attempt.error or "empty narrative"  # type: ignore[attr-defined]
    if _filled(draft) < max(1, len(required) // 3):
        return None, [], "empty narrative"

    offenders = check_figures(draft, context)
    if offenders:
        logger.info("Narrative %s: figures not in the context: %s", label, offenders)
        answer = attempt(_retry_note(lang, offenders, draft))
        if answer and quality(answer) >= quality(draft):
            found = check_figures(answer, context)
            if len(found) <= len(offenders):
                draft, offenders = answer, found
    return draft, offenders, None


def write_narratives(
    context: dict,
    *,
    root_causes: bool,
    vocabulary: dict[str, str],
    sources: list[dict],
    hidden: dict[str, set[str]] | None = None,
    groups: list[set[str]] | None = None,
    on_part: Callable[[PartOutcome], None] | None = None,
    client: Core42Client | None = None,
) -> NarrativeOutcome:
    """Write the Arabic narrative: every unit in parallel, each with its own rounds.

    A unit is a part, or — with ``groups`` — a group of the report part's fields
    written by its own call. The fields share one context and one system prompt and
    none reads another's text, so splitting them changes no dependency; it only lets
    the calls run side by side. Each unit is cleaned and handed to ``on_part`` the
    moment it is final, so its translation can start while the others are still
    being written. Fields of hidden sections are not asked for and come back empty.
    Never raises.
    """
    client = client or Core42Client()
    hidden = hidden or {"report": set(), "sections": set()}
    names = {"report": "write_report_narratives", "sections": "write_section_narratives"}
    source_map = {s["id"]: s for s in sources}

    # Asked for: the fields of shown sections whose input is present. A hidden
    # section's field, or a conditional field without input (a department narrative
    # with no department column), is left out of the tool: it is neither written nor
    # paid for, and its absence from the answer is not a reason to retry.
    required = {part: [f for f in must_write(context, model) if f not in hidden[part]] for part, model in _EMPTY.items()}
    system = narrative_system_prompt("ar", root_causes=root_causes, vocabulary=vocabulary,
                                     section_fields=bool(required["sections"]))
    units: list[tuple[str, str, list[str]]] = []
    for part in _EMPTY:
        if part == "report" and groups:
            covered: set[str] = set()
            for i, group in enumerate(groups, 1):
                fields = [f for f in required[part] if f in group]
                covered |= set(fields)
                if fields:
                    units.append((part, f"{part}.{i}", fields))
            rest = [f for f in required[part] if f not in covered]
            if rest:
                units.append((part, f"{part}.rest", rest))
        else:
            units.append((part, part, required[part]))

    def one(part: str, unit: str, fields: list[str]) -> PartOutcome:
        model = _EMPTY[part]
        not_asked = set(model.model_fields) - set(fields)
        if not fields:
            outcome = PartOutcome(part=part, unit=unit, fields=[], data=_empty_part(part))
        else:
            tool = _tool(names[part], model, fields, only=fields)
            preface = _write_these("ar", fields)

            def call(note: str | None) -> dict:
                return _call(client, system, context, tool, "\n\n".join(x for x in (preface, note) if x),
                             retry=note is not None)

            draft, offenders, error = _rounds(call, lang="ar", model=model, required=fields, asked=fields,
                                              context=context, label=f"ar/{unit}")
            if draft is None:
                outcome = PartOutcome(part=part, unit=unit, fields=fields, error=error)
            else:
                outcome = _finish(part, draft, offenders, context, "ar", vocabulary, source_map, not_asked)
                outcome.unit, outcome.fields = unit, fields
        if outcome.data is not None and on_part:
            try:
                on_part(outcome)
            except Exception as exc:  # the caller's hook must not cost the Arabic report
                logger.warning("on_part hook failed for %s: %s", unit, exc)
        return outcome

    with ScopedThreadPoolExecutor(max_workers=max(2, len(units))) as pool:
        futures = [pool.submit(one, *u) for u in units]
        outcomes = [future.result() for future in futures]
    return combine(outcomes)


def _finish(part: str, draft: dict, offenders: list[str], context: dict, lang: str,
            vocabulary: dict[str, str], sources: dict[str, dict], hidden: set[str]) -> PartOutcome:
    try:
        # A field left out counts as incomplete only if it was asked for.
        incomplete = [f for f in _complete(draft, _EMPTY[part]) if f not in hidden]
        data, hits, dropped = postprocess_part(part, draft, context, lang, vocabulary, sources, hidden)
        _EMPTY[part].model_validate(data)
        return PartOutcome(part=part, data=data, unverified=offenders, incomplete=incomplete,
                           banned_hits=hits, dropped=dropped)
    except (ValidationError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Narrative %s/%s unusable: %s", lang, part, exc)
        return PartOutcome(part=part, error=f"{type(exc).__name__}: {str(exc)[:300]}")


def combine(units: list[PartOutcome] | dict[str, PartOutcome]) -> NarrativeOutcome:
    """Finished units into one narrative outcome.

    Each part starts empty and takes, from every unit of that part, the fields that unit
    wrote — so units of one part, even from separate calls, never overwrite each other.
    """
    units = list(units.values()) if isinstance(units, dict) else list(units)
    failed = [u for u in units if u.data is None]
    if failed:
        return NarrativeOutcome(error="; ".join(f"{u.unit or u.part}: {u.error}" for u in failed), units=units)
    merged = {part: _empty_part(part) for part in _EMPTY}
    for u in units:
        fields = u.fields if u.fields is not None else list(_EMPTY[u.part].model_fields)
        for field in fields:
            merged[u.part][field] = u.data[field]
    return NarrativeOutcome(
        narratives=ReportNarratives(
            report=InquiriesReportNarratives.model_validate(merged["report"]),
            sections=SectionNarratives.model_validate(merged["sections"]),
        ),
        units=units,
        unverified=sorted({f for u in units for f in u.unverified}),
        incomplete=[f for u in units for f in u.incomplete],
        banned_hits=sorted({h for u in units for h in u.banned_hits}),
        dropped_initiatives=sum(u.dropped for u in units),
    )


# ── Translation: the English report from the Arabic narrative ────────────────


def translate_part(
    part: str,
    arabic: dict,
    *,
    context: dict,
    glossary: dict[str, str],
    vocabulary: dict[str, str],
    sources: list[dict],
    unit: str = "",
    client: Core42Client | None = None,
) -> PartOutcome:
    """Translate one finished Arabic unit into English. Never raises.

    Only the fields the Arabic carries are asked for. A field left untranslated is
    asked for again; a figure the English carries that the engine output does not is
    sent back once as an edit. Then the English wording rules apply, as for any
    narrative: banned words, the tenant's English vocabulary, plain lists, the
    16-character tile name, counts from their references.
    """
    client = client or Core42Client()
    model = _EMPTY[part]
    written = [f for f in model.model_fields if arabic.get(f) not in (None, "", [])]
    if not written:
        return PartOutcome(part=part, unit=unit or part, fields=[], data=_empty_part(part))
    system = translation_system_prompt(vocabulary)
    names = {"report": "write_report_narratives", "sections": "write_section_narratives"}
    # Only the fields the Arabic carries are sent and asked for.
    tool = _tool(names[part], model, written, only=written)
    source = {f: arabic[f] for f in written}
    payload = {"glossary": _glossary_for(source, glossary), "arabic": source}

    def call(note: str | None) -> dict:
        return _call(client, system, payload, tool, note, "translation")

    draft, offenders, error = _rounds(call, lang="en", model=model, required=written, asked=written,
                                      context=context, label=f"en/{unit or part}")
    if draft is None:
        return PartOutcome(part=part, unit=unit or part, fields=written, error=error or "translation failed")
    hidden = {f for f in model.model_fields if f not in written}
    outcome = _finish(part, draft, offenders, context, "en", vocabulary, {s["id"]: s for s in sources}, hidden)
    outcome.unit, outcome.fields = unit or part, written
    return outcome


def translate_narratives(
    arabic: ReportNarratives,
    *,
    context: dict,
    glossary: dict[str, str],
    vocabulary: dict[str, str],
    sources: list[dict],
    client: Core42Client | None = None,
) -> NarrativeOutcome:
    """Translate both finished Arabic parts in parallel. Never raises."""
    source_ar = {"report": arabic.report.model_dump(mode="json"), "sections": arabic.sections.model_dump(mode="json")}
    with ScopedThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            part: pool.submit(translate_part, part, source_ar[part], context=context, glossary=glossary,
                              vocabulary=vocabulary, sources=sources, client=client)
            for part in _EMPTY
        }
        parts = {part: future.result() for part, future in futures.items()}
    outcome = combine(parts)
    if outcome.error:
        outcome.error = "translation failed: " + outcome.error
    return outcome


def _glossary_for(arabic: dict, glossary: dict[str, str]) -> dict[str, str]:
    """The glossary entries that occur in this text — short prompts translate better."""
    text = json.dumps(arabic, ensure_ascii=False)
    return {ar: en for ar, en in glossary.items() if ar and en and ar in text}
