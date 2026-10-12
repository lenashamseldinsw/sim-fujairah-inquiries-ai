"""
The data context — the narrative writer's only input (Full Report Prompt §3).

The engine output is serialised into the user message so the model has every number
it may cite, under the keys the prompt names (``KPI``, ``MONTHLY``, ``CHANNEL``, …,
``previous_period``) plus the nine-section keys (``ACTUAL_TYPE``, ``JOURNEY_MAP``, …,
``INITIATIVE_SOURCES``). Labels are rendered in the run's language.

What is deliberately left out: case ids, sample texts and evidence excerpts (the
narrative writer never sees a case — hard rule 10), and owner names (no individual
callouts — hard rule 9).
"""
from __future__ import annotations

from typing import Any

from ..engine.localize import Localizer
from ..engine.wording import TIMELINESS_LABELS
from ..report.labels import CATEGORY, FAQ_STATUS, GAP_TYPE, GUIDEBOOK_STATUS, PRIORITY

__all__ = ["build_context"]


def _dist(block: dict | None, loc: Localizer, cap: int | None = None) -> dict | None:
    if not block:
        return None
    labels = loc.names(block.get("labels", []))
    out = {"labels": labels, "values": block.get("values", []), "pct": block.get("pct", [])}
    if cap:
        out = {k: v[:cap] for k, v in out.items()}
    return out


def build_context(
    metrics: dict[str, Any],
    lang: str,
    loc: Localizer,
    *,
    entity_name: str,
    vision: str | None,
    sections: list[str],
    vocabulary: dict[str, str],
    initiative_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    m = metrics
    L = lambda x: loc.name(x)  # noqa: E731
    pick = lambda item, field: item.get(f"{field}_{lang}") or item.get(f"{field}_ar") or ""  # noqa: E731

    kpi = dict(m["KPI"])
    if kpi.get("top_service"):
        kpi["top_service"] = {**kpi["top_service"], "name": L(kpi["top_service"]["name"])}
    kpi["report_period"] = kpi.pop("report_period_en") if lang == "en" else kpi["report_period"]
    kpi.pop("report_period_en", None)
    kpi.pop("entity", None)
    kpi.pop("entity_en", None)

    ctx: dict[str, Any] = {
        "ENTITY": {"name": entity_name, "vision": vision or ""},
        "REPORT_SECTIONS": sections,
        "KPI": kpi,
        "MONTHLY": {
            "labels": m["MONTHLY"]["labels_en" if lang == "en" else "labels"],
            "values": m["MONTHLY"]["values"],
            "pct": m["MONTHLY"]["pct"],
            "delta_pct": m["MONTHLY"]["delta_pct"],
        },
        "CASE_TYPE_RECORDED": _dist(m.get("CASE_TYPE_RECORDED"), loc),
        "ACTUAL_TYPE": _dist(m.get("ACTUAL_TYPE"), loc),
        "MAIN_SERVICE": _dist(m.get("MAIN_SERVICE"), loc),
        "SUB_CLASS": _dist(m.get("SUB_CLASS"), loc, cap=15),
        "RECORDED_VS_ACTUAL": {
            "categories": loc.names(m["RECORDED_VS_ACTUAL"]["categories"]),
            "recorded": m["RECORDED_VS_ACTUAL"]["recorded"],
            "actual": m["RECORDED_VS_ACTUAL"]["actual"],
        },
        "RECLASSIFICATION": {k: m["RECLASSIFICATION"][k] for k in ("count", "compared", "rate")},
        "SUB_CLASS_BY_TYPE": {L(k): _dist(v, loc, cap=6) for k, v in m.get("SUB_CLASS_BY_TYPE", {}).items()},
        "OUT_OF_SCOPE_DETECTED": {k: v for k, v in m["OUT_OF_SCOPE_DETECTED"].items() if k != "case_ids"},
        "CLASSIFICATION_QUALITY": {
            **{k: v for k, v in m["CLASSIFICATION_QUALITY"].items() if k not in ("provenance", "provenance_keys")},
            "provenance": {L(k): v for k, v in m["CLASSIFICATION_QUALITY"]["provenance"].items()},
        },
        "PARSE_SUMMARY": {
            k: m["PARSE_LOG"].get(k) for k in (
                "records_received", "artefact_rows_dropped", "duplicates_removed",
                "entity_rows_excluded", "in_scope_total",
            )
        } | {"scope_excluded": sum(m["PARSE_LOG"].get("scope_excluded", {}).values())},
        "vocabulary": vocabulary,
        "METRIC_GAPS": [g[lang] for g in m.get("METRIC_GAPS", [])],
        "DATA_NOTES": [n[lang] for n in m.get("DATA_NOTES", [])],
        "INITIATIVE_SOURCES": [
            {"id": s["id"], "kind": s["kind"], "name": s[f"name_{lang}"] or s["name_ar"], "cases": s["cases"]}
            for s in initiative_sources
        ],
        "EVENTS": [
            {k: v for k, v in {**e, "cluster": L(e["cluster"]), "month": e["month_en"] if lang == "en" else e["month"]}.items() if k != "month_en"}
            for e in m.get("EVENTS", [])
        ],
    }

    if m.get("CHANNEL", {}).get("labels"):
        ctx["CHANNEL"] = {
            **_dist(m["CHANNEL"], loc),
            "digital": m["CHANNEL"]["digital"],
        }
        if m.get("COMPARISON"):
            ctx["CHANNEL"]["previous"] = {
                "labels": [L(c["label"]) for c in m["COMPARISON"]["channels"] if c["previous_pct"] is not None],
                "pct": [c["previous_pct"] for c in m["COMPARISON"]["channels"] if c["previous_pct"] is not None],
            }

    timeliness = {k: v for k, v in m["TIMELINESS"].items() if k not in ("framework_id", "available")}
    if lang == "en":
        timeliness["target"] = timeliness.pop("target_en")
        timeliness["labels"] = {k: v["en"] for k, v in TIMELINESS_LABELS.items()}
    else:
        timeliness.pop("target_en", None)
        timeliness["labels"] = {k: v["ar"] for k, v in TIMELINESS_LABELS.items()}
    if m["TIMELINESS"].get("available"):
        if lang == "en":
            from ..engine.frameworks import FRAMEWORK_NAMES

            fid = {"entity_process_kpi": "entity_process_kpi", "tamm": "tamm_contact_centre", "gsr": "gsr"}.get(
                m["TIMELINESS"].get("framework_id") or "", "")
            timeliness["framework"] = FRAMEWORK_NAMES.get(fid, {}).get("en", "the entity's framework")
        ctx["TIMELINESS"] = timeliness
    for key in ("NEAR_OVER_BY_BUNDLE", "NEAR_OVER_BY_SERVICE"):
        if m.get(key):
            ctx[key] = {"labels": loc.names(m[key]["labels"]), "pct": m[key]["pct"]}

    if m.get("RECORDED_VS_TRUE", {}).get("available"):
        rvt = m["RECORDED_VS_TRUE"]
        ctx["RECORDED_VS_TRUE"] = {
            "match_pct": rvt["match_pct"], "mismatch_pct": rvt["mismatch_pct"],
            "mismatch_count": rvt["mismatch_count"], "compared": rvt["compared"],
            "least_matching": [{**x, "tag": L(x["tag"])} for x in rvt["least_matching"]],
        }
    if m.get("SEVERITY"):
        ctx["SEVERITY"] = _dist(m["SEVERITY"], loc)
    if m["CLOSED"].get("available"):
        ctx["CLOSED"] = {k: v for k, v in m["CLOSED"].items() if k != "available"}
    if m.get("DEPARTMENT"):
        ctx["DEPARTMENT"] = {
            **_dist(m["DEPARTMENT"], loc, cap=12),
            "dominant_type": {L(k): L(v) for k, v in list(m["DEPARTMENT"]["dominant_type"].items())[:12]},
        }

    if m.get("BUNDLE"):
        ctx["BUNDLE"] = {**_dist(m["BUNDLE"], loc), "new": m["BUNDLE"]["new"], "ids": m["BUNDLE"]["ids"]}
        rct = m["ROOT_CAUSE_TOP"]
        ctx["ROOT_CAUSE_TOP"] = {
            "labels": loc.names(rct["labels"]), "values": rct["values"],
            "per_bundle": {L(k): {"labels": loc.names(v["labels"]), "values": v["values"]} for k, v in rct["per_bundle"].items()},
        }
        ctx["BUNDLE_BY_SERVICE"] = {
            L(service): {L(b): n for b, n in row.items() if n}
            for service, row in m["BUNDLE_BY_SERVICE"]["counts"].items()
        }
        ctx["SERVICE_FOCUS"] = [
            {
                "service": L(f["service"]), "count": f["count"], "share_pct": f["share_pct"],
                "months": f["months_en"] if lang == "en" else f["months"],
                "peak_month": f["peak_month_en"] if lang == "en" else f["peak_month"],
                "within_deadline_pct": f["within_deadline_pct"],
                "sub_classes": _dist(f["sub_classes"], loc),
                "bundles": {"labels": loc.names(f["bundles"]["labels"]), "pct": f["bundles"]["pct"]},
                "phone_pct": f["phone_pct"], "livechat_pct": f["livechat_pct"],
            }
            for f in m.get("SERVICE_FOCUS", [])
        ]
        if m.get("DEFLECTABLE_PCT"):
            ctx["DEFLECTABLE_PCT"] = {**m["DEFLECTABLE_PCT"], "bundles": loc.names(m["DEFLECTABLE_PCT"]["bundles"])}

    if m.get("INQ_PER_100_TX"):
        tx = m["INQ_PER_100_TX"]
        ctx["INQ_PER_100_TX"] = {
            "overall": tx["overall"], "transactions_total": tx["transactions_total"],
            "by_main_service": {**tx["by_main_service"], "labels": loc.names(tx["by_main_service"]["labels"])},
            "by_sub_service": {**tx["by_sub_service"], "labels": loc.names(tx["by_sub_service"]["labels"])},
        }
    if m.get("FAQ_COVERAGE"):
        fc = m["FAQ_COVERAGE"]
        ctx["FAQ_COVERAGE"] = {**fc, "labels": loc.names(fc["labels"])}
    if m.get("COMPARISON"):
        comp = m["COMPARISON"]
        ctx["previous_period"] = {
            "label": comp["label_en"] if lang == "en" else comp["label"],
            "total_cases": comp["total_cases"]["previous"],
            "within_deadline_pct": comp["within_deadline_pct"]["previous"],
            "digital_share_pct": comp["digital_share_pct"]["previous"],
            "reclassification_rate": comp["reclassification_rate"]["previous"],
            "total_cases_change_pct": comp["total_cases"].get("change_pct"),
            "bundles": {L(b["label"]): b["previous"] for b in comp["bundles"]},
        }

    if m.get("JOURNEY_MAP"):
        ctx["JOURNEY_MAP"] = [
            {"id": f["id"], "name": pick(f, "name"), "category": CATEGORY.get(f["root_cause_category"], {}).get(lang, f["root_cause_category"]),
             "cases": f["case_count"], "remedy": pick(f, "remedy")}
            for f in m["JOURNEY_MAP"]
        ]
    if m.get("GAP_TABLE"):
        ctx["GAP_TABLE"] = [
            {"id": g["id"], "topic": pick(g, "topic"), "cases": g["case_count"],
             "status": GUIDEBOOK_STATUS[g["guidebook_status"]][lang],
             "gap_type": GAP_TYPE.get(g["gap_type"], {}).get(lang, g["gap_type"]),
             "priority": PRIORITY[g["priority"]][lang], "recommendation": pick(g, "recommendation")}
            for g in m["GAP_TABLE"]
        ]
    if m.get("VALIDATED_FAQS"):
        ctx["VALIDATED_FAQS"] = [
            {"id": q["id"], "question": pick(q, "question"), "main_service": L(q["main_service"]),
             "frequency": q["frequency"], "status": FAQ_STATUS[q["validation_status"]][lang]}
            for q in m["VALIDATED_FAQS"]
        ]
    if m.get("NOTIFICATION_OPPORTUNITIES"):
        ctx["NOTIFICATION_OPPORTUNITIES"] = [
            {"id": n["id"], "type": pick(n, "type"), "trigger": pick(n, "trigger"), "cases": n["cases_eliminated"]}
            for n in m["NOTIFICATION_OPPORTUNITIES"]
        ]
    if m.get("PATTERNS"):
        ctx["PATTERNS"] = [
            {"main_service": L(p["main_service"]), "sub_classification": L(p["sub_classification"]),
             "cases": p["case_count"], "pct": p["pct"]}
            for p in m["PATTERNS"]
        ]
    if m.get("FRAMEWORKS"):
        from ..engine.frameworks import FRAMEWORK_NAMES

        status_words = {
            "computed": {"ar": "محتسب", "en": "computed"},
            "partial": {"ar": "محتسب جزئياً", "en": "partially computed"},
            "not_computable": {"ar": "غير قابل للاحتساب من التصدير", "en": "not computable from this export"},
            "reference": {"ar": "مرجعي", "en": "reference only"},
        }
        ctx["FRAMEWORKS"] = [
            {"framework": FRAMEWORK_NAMES.get(i["framework"], {}).get(lang, ""), "indicator": i[f"name_{lang}"],
             "status": status_words.get(i["status"], {}).get(lang, i["status"]), "value_pct": i["value_pct"],
             "target": i[f"target_{lang}"], "recommendation": i[f"recommendation_{lang}"]}
            for i in m["FRAMEWORKS"]
        ]
    return {k: v for k, v in ctx.items() if v not in (None, {}, [])}
