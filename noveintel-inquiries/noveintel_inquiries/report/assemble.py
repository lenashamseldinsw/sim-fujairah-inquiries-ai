"""
Assembling the report — S0–S11 as data, in one language.

Every table and chart here is drawn from the engine output; every paragraph is a
narrative field; every heading and header is static text from ``labels``. Nothing is
computed and nothing is written here — this module only places.

A section whose optional input is absent is omitted with a one-line data note rather
than failing (Prerequisites §0, "graceful sections"); a present-but-empty column gets
a «لم يُزوَّد» note under the affected table.
"""
from __future__ import annotations

from typing import Any

from ..api.models.entity import TIMELINESS_COLORS
from ..api.models.enums import SECTION_IDS, ReportSection as RS
from ..api.models.narratives import ReportNarratives
from ..engine.localize import Localizer
from ..engine.wording import PROVENANCE, TIMELINESS_LABELS
from .labels import (
    CATEGORY, EFFORT, FAQ_STATUS, GAP_TYPE, GUIDEBOOK_STATUS, HORIZON, PRIORITY,
    SECTION_TITLES, t,
)

__all__ = ["assemble_report", "fmt_int", "fmt_pct", "categorical_palette"]


def fmt_int(value: Any) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{int(number):,}" if number.is_integer() else f"{number:,.1f}"


def fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{value}%"


def categorical_palette(primary: str, secondary: str) -> list[str]:
    return [primary, secondary, "#2F6F8F", "#C9A227", "#6B8E23", "#8C564B",
            "#5B6C8F", "#B07AA1", "#4E9A8A", "#9C755F"]


class _Builder:
    def __init__(self, lang: str, loc: Localizer, primary: str, secondary: str) -> None:
        self.lang = lang
        self.loc = loc
        self.ar_loc = Localizer("ar", loc.tax, [], loc.translations)
        self.primary = primary
        self.secondary = secondary
        self.palette = categorical_palette(primary, secondary)

    # ── primitives ──
    def t(self, key: str) -> str:
        return t(key, self.lang)

    def L(self, label: Any) -> str:
        return self.loc.name(label)

    def table(self, columns: list[str], rows: list[list[Any]], note: str | None = None) -> dict:
        heads = [self.t(c) if c in _T_KEYS else c for c in columns]
        return {
            "columns": heads,
            "rows": [dict(zip(heads, ["" if v is None else str(v) for v in row])) for row in rows],
            **({"note": note} if note else {}),
        }

    def chart(self, key: str, output_id: str | None, kind: str, title: tuple[str, str],
              categories_ar: list[str], categories_en: list[str],
              series: list[tuple[str, str, list[float]]], colors: list[str] | None = None) -> dict:
        return {
            "key": key,
            "output_id": output_id,
            "type": kind,
            "title_ar": title[0],
            "title_en": title[1],
            "categories_ar": [self.ar_loc.name(c) for c in categories_ar],
            "categories_en": [str(c) for c in categories_en],
            "series": [{"name_ar": a, "name_en": e, "data": [float(v or 0) for v in vals]} for a, e, vals in series],
            "colors": colors or [],
        }

    def section(self, key: str | None, sid: str, title: str, **parts: Any) -> dict:
        section = {"id": sid, "title": title}
        if key:
            section["key"] = key
        for name, value in parts.items():
            if value:
                section[name] = value
        return section

    def dist_rows(self, block: dict) -> list[list[Any]]:
        return [[self.L(lab), fmt_int(v), fmt_pct(p)] for lab, v, p in zip(block["labels"], block["values"], block["pct"])]



_T_KEYS = {
    "count", "cases", "share", "month", "change", "channel", "digital", "main_service", "sub_classification",
    "contact_type", "recorded", "actual", "case_id", "evidence", "recorded_tag", "match", "status", "target",
    "framework", "recommendation", "department", "dominant_type", "severity", "friction", "root_cause_category",
    "remedy", "topic", "guidebook_status", "excerpt", "gap_type", "priority", "question", "answer", "frequency",
    "faq_status", "notification", "trigger", "sample_message", "eliminable", "use_case", "function", "source_ref",
    "effort", "impact_cases", "initiative", "horizon", "description", "bundle", "root_cause", "near_over",
    "inquiries", "transactions", "per_100", "howto_cases", "coverage", "provenance", "previous", "current",
    "owner", "source", "nature", "size", "period", "field", "role", "indicator", "value", "item", "finding",
}


def assemble_report(
    *,
    lang: str,
    metrics: dict[str, Any],
    narratives: ReportNarratives,
    loc: Localizer,
    en_loc: Localizer,
    entity: Any,
    period: Any,
    settings: Any,
    method: dict[str, Any],
    sources_meta: dict[str, Any],
    initiative_sources: list[dict[str, Any]],
    umbrella_meta: list[dict[str, Any]],
    primary: str,
    secondary: str,
    branding: dict[str, Any],
    shown: list[Any] | None = None,
) -> dict[str, Any]:
    """The report as data — what the Word document is rendered from.

    ``shown`` is the tenant's section list; a section outside it is left out. The
    cover is always present.
    """
    b = _Builder(lang, loc, primary, secondary)
    m = metrics
    n = narratives.report
    s = narratives.sections
    ar = lang == "ar"
    E = lambda labels: [en_loc.name(x) for x in labels]  # noqa: E731
    title = lambda key: SECTION_TITLES[key][lang]  # noqa: E731
    sid = lambda key: SECTION_IDS[key]  # noqa: E731
    kpi = m["KPI"]
    sections: list[dict] = []

    # ── S0 cover ─────────────────────────────────────────────────────────────
    tiles = [
        (b.t("kpi_total"), fmt_int(kpi["total_cases"]), "O1"),
    ]
    if kpi.get("closed_cases") is not None:
        tiles.append((b.t("kpi_closed"), fmt_int(kpi["closed_cases"]), "O2"))
    if kpi.get("reclassification_rate") is not None:
        tiles.append((b.t("kpi_reclass"), fmt_pct(kpi["reclassification_rate"]), "O3"))
    if kpi.get("within_deadline_pct") is not None:
        tiles.append((b.t("kpi_within"), fmt_pct(kpi["within_deadline_pct"]), "O4"))
    if kpi.get("digital_share_pct") is not None:
        tiles.append((b.t("kpi_digital"), fmt_pct(kpi["digital_share_pct"]), "O5"))
    if kpi.get("top_service"):
        short = n.top_service_short or b.L(kpi["top_service"]["name"])
        tiles.append((b.t("kpi_top"), f"{short} ({fmt_pct(kpi['top_service']['pct'])})", "O6"))
    extras = [
        (b.t("kpi_classified"), f"{fmt_int(kpi['classified'])} ({fmt_pct(kpi['classified_pct'])})", None),
        (b.t("kpi_main"), fmt_int(kpi["main_services"]), None),
        (b.t("kpi_sub"), fmt_int(kpi["sub_classes"]), None),
    ]
    if kpi.get("inq_per_100_tx") is not None:
        extras.append((b.t("kpi_tx"), fmt_int(kpi["inq_per_100_tx"]), "O26"))
    if kpi.get("bundles"):
        extras.append((b.t("kpi_bundles"), fmt_int(kpi["bundles"]), None))
    cover = {
        "id": "S0",
        "key": RS.COVER.value,
        "title": b.t("doc_title"),
        "entity": entity.name(lang),
        "center": entity.center_name(lang),
        "name_short": entity.name_short or "",
        "period": period.label(lang),
        "date_range": kpi["period_date_range"],
        "source_system": settings.source_system or "",
        "tiles": [{"label": a, "value": v, "output_id": o} for a, v, o in tiles],
        "extra_tiles": [{"label": a, "value": v, "output_id": o} for a, v, o in extras],
    }

    # ── S1 executive summary ─────────────────────────────────────────────────
    kpi_rows = [[tile["label"], tile["value"]] for tile in cover["tiles"] + cover["extra_tiles"]]
    s1_subs = [b.section(None, "S1.1", b.t("s1_findings"), tables=[b.table(["indicator", "value"], kpi_rows)])]
    comp = m.get("COMPARISON")
    if comp and n.comparative_analysis:
        rows = [
            [b.t("kpi_total"), fmt_int(comp["total_cases"]["previous"]), fmt_int(comp["total_cases"]["current"])],
            [b.t("kpi_within"), fmt_pct(comp["within_deadline_pct"]["previous"]), fmt_pct(comp["within_deadline_pct"]["current"])],
            [b.t("kpi_digital"), fmt_pct(comp["digital_share_pct"]["previous"]), fmt_pct(comp["digital_share_pct"]["current"])],
        ]
        s1_subs.append(b.section(None, "S1.2", b.t("s1_comparison"), content=n.comparative_analysis,
                                 tables=[b.table(["indicator", "previous", "current"], rows)]))
    sections.append(b.section(RS.EXECUTIVE_SUMMARY.value, sid(RS.EXECUTIVE_SUMMARY), title(RS.EXECUTIVE_SUMMARY),
                              content="\n".join(x for x in (n.intro_statement, n.executive_summary) if x),
                              subsections=s1_subs))

    # ── S2 methodology (generated from run data — R1) ────────────────────────
    log = m["PARSE_LOG"]
    source_rows: list[list[str]] = []
    crm = settings.source_system or ("نظام إدارة علاقات المتعاملين" if ar else "CRM case export")
    source_rows.append([
        crm,
        "حالات المتعاملين بنصوص الوصف والرد" if ar else "Customer cases with description and resolution text",
        (f"{fmt_int(log['records_received'])} سجلاً مستلماً · {fmt_int(log['in_scope_total'])} حالة ضمن النطاق" if ar
         else f"{fmt_int(log['records_received'])} records received · {fmt_int(log['in_scope_total'])} cases in scope"),
        kpi["period_date_range"],
    ])
    tax = sources_meta["taxonomy"]
    source_rows.append([
        ("التصنيف المعتمد: " if ar else "Classification taxonomy: ") + tax["label"],
        "قائمة مرجعية للجهة" if ar else "Tenant reference list",
        (f"{tax['main_services']} خدمة رئيسية · {tax['sub_classifications']} تصنيفاً فرعياً" if ar
         else f"{tax['main_services']} main services · {tax['sub_classifications']} sub-classifications"),
        "—",
    ])
    gb = sources_meta.get("guidebook")
    if gb:
        topics = "، ".join(gb["topics"][:5]) if ar else ", ".join(gb["topics"][:5])
        source_rows.append([
            gb["title"] if ar else (gb.get("title_en") or gb["title"]),
            ("دليل الخدمات المعتمد" + (f" — يغطي {topics}" if topics else "")) if ar
            else ("Approved service guidebook" + (f" — covering {topics}" if topics else "")),
            (f"{fmt_int(gb['pages'])} صفحة · {fmt_int(gb['faq_count'])} سؤالاً شائعاً في الدليل" if ar
             else f"{fmt_int(gb['pages'])} pages · {fmt_int(gb['faq_count'])} FAQs in the guidebook"),
            str(gb.get("year") or "—"),
        ])
    if sources_meta.get("faq_catalogue"):
        source_rows.append([
            "قائمة الأسئلة الشائعة المعتمدة" if ar else "Approved FAQ catalogue",
            "قائمة مرجعية للجهة" if ar else "Tenant reference list",
            f"{fmt_int(sources_meta['faq_catalogue'])} " + ("سؤالاً" if ar else "questions"),
            "—",
        ])
    if sources_meta.get("transactions"):
        tx = sources_meta["transactions"]
        source_rows.append([
            "أحجام المعاملات" if ar else "Transaction volumes",
            "قائمة مرجعية مؤرخة بالفترة" if ar else "Period-stamped reference list",
            f"{fmt_int(tx['rows'])} " + ("صفاً" if ar else "rows") + f" · {fmt_int(tx['total'])} " + ("معاملة" if ar else "transactions"),
            kpi["period_date_range"],
        ])
    if sources_meta.get("umbrella_set"):
        us = sources_meta["umbrella_set"]
        source_rows.append([
            "الحزم الموضوعية المعتمدة" if ar else "Confirmed thematic bundles",
            "مجموعة الجهة المرحَّلة من الفترات السابقة" if ar else "The tenant's carried-forward set",
            f"{fmt_int(us['count'])} " + ("حزم" if ar else "bundles"),
            us.get("version") or "—",
        ])
    validated = len(m.get("VALIDATED_FAQS", []))
    parse_rows = [
        ["السجلات المستلمة" if ar else "Records received", fmt_int(log["records_received"])],
        ["صفوف بلا رقم طلب (مستبعدة)" if ar else "Rows without a case id (excluded)", fmt_int(log["artefact_rows_dropped"])],
        ["حالات مكررة (مستبعدة)" if ar else "Duplicate cases (excluded)", fmt_int(log["duplicates_removed"])],
    ]
    if log.get("entity_rows_excluded"):
        parse_rows.append(["حالات جهات أخرى (مستبعدة)" if ar else "Other entities' cases (excluded)", fmt_int(log["entity_rows_excluded"])])
    for kind, count in (log.get("scope_excluded") or {}).items():
        parse_rows.append([(f"خارج نطاق أنواع الحالات: {kind}" if ar else f"Outside the case-type scope: {kind}"), fmt_int(count)])
    parse_rows.append(["الحالات ضمن النطاق" if ar else "Cases in scope", fmt_int(log["in_scope_total"])])
    parse_rows.append(["أسئلة شائعة مقترحة من هذا التحليل" if ar else "FAQs proposed by this analysis", fmt_int(validated)])
    s21 = b.section(None, "S2.1", b.t("s2_sources"), tables=[
        b.table(["source", "nature", "size", "period"], source_rows),
        b.table(["item", "count"], parse_rows),
    ])
    s22 = b.section(None, "S2.2", b.t("s2_method"), content=_method_text(lang, method, settings))
    field_rows = []
    from ..api.models.columns import COLUMN_BY_NAME

    for name in log["columns_mapped"]:
        spec = COLUMN_BY_NAME[name]
        empty = name in log.get("columns_present_but_empty", [])
        field_rows.append([
            f"{spec.uid} · {spec.label_ar if ar else spec.label_en}",
            (("لم يُزوَّد — " if ar else "Not provided — ") if empty else "") + (_role(spec.name, lang)),
        ])
    for name in log.get("label_columns_supplied", []):
        spec = COLUMN_BY_NAME[name]
        field_rows.append([f"{spec.uid} · {spec.label_ar if ar else spec.label_en}",
                           "تصنيف معتمد سابقاً (مجمَّد)" if ar else "Previously confirmed label (frozen)"])
    excluded_note = []
    if log.get("sensitive_columns_excluded"):
        excluded_note.append(
            f"استُبعدت {len(log['sensitive_columns_excluded'])} حقول هوية عند الاستلام بعد استخدامها لإخفاء البيانات الشخصية من النص."
            if ar else
            f"{len(log['sensitive_columns_excluded'])} identity column(s) were excluded at ingest after being used to redact the free text."
        )
    if log.get("columns_unmapped"):
        excluded_note.append(
            f"{len(log['columns_unmapped'])} حقول غير مطابقة للحقول الموحدة لم تُستخدم في أي قسم." if ar else
            f"{len(log['columns_unmapped'])} column(s) not mapped to a universal column were not read by any section."
        )
    if log.get("system_columns_dropped"):
        excluded_note.append(
            f"حُذفت {len(log['system_columns_dropped'])} حقول نظام." if ar else
            f"{len(log['system_columns_dropped'])} system column(s) were dropped."
        )
    s23 = b.section(None, "S2.3", b.t("s2_fields"), tables=[b.table(["field", "role"], field_rows)],
                    notes=excluded_note + [x[lang] for x in m.get("DATA_NOTES", [])])
    cq = m["CLASSIFICATION_QUALITY"]
    prov_labels = list(cq["provenance"].keys())
    prov_en = E(prov_labels)
    s24 = b.section(
        None, "S2.4", b.t("s2_quality"),
        content=_quality_line(lang, cq),
        tables=[b.table(["provenance", "cases", "share"], [
            [b.L(k), fmt_int(v), fmt_pct(p)] for (k, v), p in zip(cq["provenance"].items(), cq["provenance_pct"])
        ])],
        charts=[b.chart("classification_quality", "O21", "doughnut",
                        ("مصدر التصنيف", "Classification source"), prov_labels, prov_en,
                        [("الحالات", "Cases", list(cq["provenance"].values()))], b.palette[: len(prov_labels)])],
    )
    s25 = b.section(None, "S2.5", b.t("s2_note"), content=n.methodology_note)
    sections.append(b.section(RS.METHODOLOGY.value, sid(RS.METHODOLOGY), title(RS.METHODOLOGY),
                              subsections=[s21, s22, s23, s24, s25]))

    # ── S3 classification map ────────────────────────────────────────────────
    s3: list[dict] = []
    mon = m["MONTHLY"]
    month_labels = mon["labels"] if ar else mon["labels_en"]
    s3.append(b.section(
        None, "S3.1", b.t("s3_overview"),
        content="\n".join(x for x in (n.statistics_intro, n.monthly_narrative) if x),
        bullets=n.event_narratives,
        tables=[b.table(["month", "cases", "share", "change"], [
            [lab, fmt_int(v), fmt_pct(p), fmt_pct(d)] for lab, v, p, d in zip(month_labels, mon["values"], mon["pct"], mon["delta_pct"])
        ])] if mon["values"] else [],
        charts=[b.chart("monthly_bar", "O19", "column", ("التوزيع الشهري للحالات", "Monthly distribution of cases"),
                        mon["labels"], mon["labels_en"], [("الحالات", "Cases", mon["values"])], [primary])] if mon["values"] else [],
    ))
    at = m["ACTUAL_TYPE"]
    rva = m["RECORDED_VS_ACTUAL"]
    rec = m["RECLASSIFICATION"]
    sample_rows = [[x["case_id"], b.L(x["recorded"]), b.L(x["actual"]), x["evidence"]] for x in rec["sample"]]
    s3.append(b.section(
        None, "S3.2", b.t("s3_types"),
        content="\n".join(x for x in (s.contact_type_narrative, s.reclassification_narrative) if x),
        tables=[b.table(["contact_type", "count", "share"], b.dist_rows(at))]
        + ([b.table(["case_id", "recorded", "actual", "evidence"], sample_rows)] if sample_rows else []),
        charts=[
            b.chart("actual_type_mix", "O8", "doughnut", ("التوزيع الفعلي لأنواع التواصل", "Actual contact-type distribution"),
                    at["labels"], E(at["labels"]), [("الحالات", "Cases", at["values"])], b.palette[: len(at["labels"])]),
            b.chart("classification_mix", "O7", "column", ("التصنيف الأصلي مقابل الصحيح", "Recorded vs actual classification"),
                    rva["categories"], E(rva["categories"]),
                    [("التصنيف الأصلي", "Recorded", rva["recorded"]), ("التصنيف الصحيح", "Actual", rva["actual"])],
                    [secondary, primary]),
        ],
    ))
    ms, sc = m["MAIN_SERVICE"], m["SUB_CLASS"]
    svc_charts = [
        b.chart("main_service_bar", None, "bar", ("التوزيع حسب الخدمة الرئيسية", "Distribution by main service"),
                ms["labels"], E(ms["labels"]), [("الحالات", "Cases", ms["values"])], [primary]),
        b.chart("sub_service_bar", None, "bar", ("التوزيع حسب التصنيف الفرعي", "Distribution by sub-classification"),
                sc["labels"][:15], E(sc["labels"][:15]), [("الحالات", "Cases", sc["values"][:15])], [secondary]),
    ]
    if m.get("SERVICE"):
        sv = m["SERVICE"]
        svc_charts.append(b.chart("service_distribution", "O9", "bar", ("توزيع الطلبات على الخدمات (الوسم المسجَّل)", "Cases by recorded service tag"),
                                  sv["labels"][:15], sv["labels_en"][:15], [("الحالات", "Cases", sv["values"][:15])], [primary]))
    s3.append(b.section(
        None, "S3.3", b.t("s3_services"),
        content="\n".join(x for x in (n.main_service_narrative, n.sub_service_narrative) if x),
        tables=[b.table(["main_service", "cases", "share"], b.dist_rows(ms)),
                b.table(["sub_classification", "cases", "share"], b.dist_rows(sc))],
        charts=svc_charts,
    ))
    by_type = m.get("SUB_CLASS_BY_TYPE", {})
    if by_type:
        type_subs: list[dict] = []
        top_subs: list[str] = []
        for block in by_type.values():
            for lab in block["labels"][:5]:
                if lab not in top_subs:
                    top_subs.append(lab)
        top_subs = top_subs[:10]
        series = [
            (ctype, E([ctype])[0], [dict(zip(block["labels"], block["values"])).get(x, 0) for x in top_subs])
            for ctype, block in by_type.items()
        ]
        for i, (ctype, block) in enumerate(by_type.items()):
            type_subs.append(b.section(None, f"S3.4.{i + 1}", b.L(ctype),
                                       tables=[b.table(["sub_classification", "cases", "share"], b.dist_rows(block)[:12])]))
        s3.append(b.section(
            None, "S3.4", b.t("s3_by_type"), subsections=type_subs,
            charts=[b.chart("sub_class_by_type", "O13", "stacked_bar", ("التصنيفات الفرعية حسب نوع التواصل", "Sub-classifications by contact type"),
                            top_subs, E(top_subs), series, b.palette[: len(series)])],
        ))
    rvt = m.get("RECORDED_VS_TRUE", {})
    if rvt.get("available"):
        tags = [x["tag"] for x in rvt["by_tag"]]
        s3.append(b.section(
            None, "S3.5", b.t("s3_recorded_true"), content=n.recorded_vs_true_narrative,
            tables=[b.table(["recorded_tag", "cases", "match"], [[b.L(x["tag"]), fmt_int(x["cases"]), fmt_pct(x["match_pct"])] for x in rvt["least_matching"]])],
            charts=[b.chart("recorded_vs_true_stacked", "O7", "stacked_bar",
                            ("التصنيف المسجَّل في النظام مقابل الموضوع الحقيقي", "Recorded classification vs true subject"),
                            tags, E(tags),
                            [("مطابق", "Matches", [x["matches"] for x in rvt["by_tag"]]),
                             ("قابل لإعادة التصنيف الذكي", "Eligible for smart re-classification", [x["cases"] - x["matches"] for x in rvt["by_tag"]])],
                            [primary, TIMELINESS_COLORS["near"]])],
        ))
    elif n.recorded_vs_true_narrative:
        s3.append(b.section(None, "S3.5", b.t("s3_recorded_true"), content=n.recorded_vs_true_narrative))
    ch = m.get("CHANNEL", {})
    if ch.get("labels"):
        ch_rows = [[b.L(lab), fmt_int(v), fmt_pct(p), b.t("yes") if d else b.t("no")]
                   for lab, v, p, d in zip(ch["labels"], ch["values"], ch["pct"], ch["digital"])]
        ch_charts = [b.chart("channel_donut", "O12", "doughnut", ("توزيع القنوات", "Channel mix"),
                             ch["labels"], E(ch["labels"]), [("الحالات", "Cases", ch["values"])], b.palette[: len(ch["labels"])])]
        if comp and comp.get("channels"):
            labels = [c["label"] for c in comp["channels"]]
            ch_charts.append(b.chart("channel_comparison_bar", "O20", "column", ("القنوات مقارنة بالفترة السابقة", "Channels vs the previous period"),
                                     labels, E(labels),
                                     [("الفترة السابقة", "Previous period", [c["previous_pct"] or 0 for c in comp["channels"]]),
                                      ("الفترة الحالية", "This period", [c["current_pct"] or 0 for c in comp["channels"]])],
                                     [secondary, primary]))
        s3.append(b.section(None, "S3.6", b.t("s3_channels"), content=n.channel_narrative,
                            tables=[b.table(["channel", "cases", "share", "digital"], ch_rows)], charts=ch_charts))
    tl = m["TIMELINESS"]
    if tl.get("available"):
        keys = ["within", "near", "over", "unspecified"]
        keys = [k for k in keys if tl[k] or k != "unspecified"]
        tl_rows = [[TIMELINESS_LABELS[k][lang], fmt_int(tl[k]), fmt_pct(tl[f"{k}_pct"])] for k in keys]
        fw_rows = [
            [i[f"name_{lang}"], _fw_name(i["framework"], lang),
             fmt_pct(i["value_pct"]) if i["value_pct"] is not None else _fw_status(i["status"], lang),
             i[f"target_{lang}"] or "—", i[f"recommendation_{lang}"] or "—"]
            for i in m.get("FRAMEWORKS", [])
        ]
        tables = [b.table(["status", "cases", "share"], tl_rows)]
        if fw_rows:
            tables.append(b.table(["indicator", "framework", "value", "target", "recommendation"], fw_rows))
        if m.get("NEAR_OVER_BY_SERVICE"):
            no = m["NEAR_OVER_BY_SERVICE"]
            tables.append(b.table(["main_service", "near_over", "cases"], [[b.L(x), fmt_pct(p), fmt_int(c)] for x, p, c in zip(no["labels"], no["pct"], no["counts"])][:10]))
        s3.append(b.section(
            None, "S3.7", b.t("s3_timeliness"), content=n.timeliness_narrative, tables=tables,
            charts=[b.chart("timeliness_donut", "O10", "pie", ("الالتزام بزمن الاستجابة", "Response-time compliance"),
                            [TIMELINESS_LABELS[k]["ar"] for k in keys], [TIMELINESS_LABELS[k]["en"] for k in keys],
                            [("الحالات", "Cases", [tl[k] for k in keys])], [TIMELINESS_COLORS[k] for k in keys])],
        ))
    else:
        s3.append(b.section(None, "S3.7", b.t("s3_timeliness"), notes=[_omitted(lang, "sla_status")],
                            tables=[_fw_table(b, m, lang)] if m.get("FRAMEWORKS") else []))
    if m.get("INQ_PER_100_TX"):
        tx = m["INQ_PER_100_TX"]
        blocks = []
        for key in ("by_main_service", "by_sub_service"):
            blk = tx[key]
            if blk["labels"]:
                blocks.append(b.table(["main_service" if key == "by_main_service" else "sub_classification", "inquiries", "transactions", "per_100"],
                                      [[b.L(x), fmt_int(i), fmt_int(tr), fmt_int(p)] for x, i, tr, p in zip(blk["labels"], blk["inquiries"], blk["transactions"], blk["per_100"])]))
        sub = tx["by_sub_service"] if tx["by_sub_service"]["labels"] else tx["by_main_service"]
        s3.append(b.section(
            None, "S3.8", b.t("s3_tx"), content=n.transactions_ratio_narrative, tables=blocks,
            charts=[b.chart("inq_per_100_bar", "O26", "bar", ("الاستفسارات لكل 100 معاملة", "Inquiries per 100 transactions"),
                            sub["labels"][:12], E(sub["labels"][:12]), [("لكل 100 معاملة", "Per 100 transactions", sub["per_100"][:12])], [primary])],
        ))
    oos = m["OUT_OF_SCOPE_DETECTED"]
    if oos["total"]:
        oos_rows = [[b.L(lbl), fmt_int(oos[k])] for k, lbl in (("complaint", "شكوى"), ("incident", "بلاغ"), ("compliment", "شكر وثناء")) if oos[k]]
        s3.append(b.section(None, "S3.9", b.t("s3_oos"), content=s.out_of_scope_narrative,
                            tables=[b.table(["contact_type", "cases"], oos_rows)]))
    if m.get("SEVERITY"):
        sv = m["SEVERITY"]
        s3.append(b.section(None, "S3.10", b.t("s3_severity"),
                            tables=[b.table(["severity", "cases", "share"], b.dist_rows(sv))],
                            charts=[b.chart("severity_mix", "O11", "pie", ("شدة الطلب", "Severity"), sv["labels"], E(sv["labels"]),
                                            [("الحالات", "Cases", sv["values"])], b.palette[: len(sv["labels"])])]))
    if m.get("DEPARTMENT"):
        dp = m["DEPARTMENT"]
        s3.append(b.section(None, "S3.11", b.t("s3_departments"), content=s.department_narrative,
                            tables=[b.table(["department", "cases", "share", "dominant_type"],
                                            [[b.L(x), fmt_int(v), fmt_pct(p), b.L(dp["dominant_type"].get(x, ""))] for x, v, p in zip(dp["labels"], dp["values"], dp["pct"])][:15])],
                            charts=[b.chart("department_distribution", "O14", "bar", ("التوزيع حسب الإدارات", "Distribution by department"),
                                            dp["labels"][:12], E(dp["labels"][:12]), [("الحالات", "Cases", dp["values"][:12])], [primary])]))
    if m.get("AGENT"):
        s3.append(b.section(None, "S3.12", b.t("s3_agents"),
                            notes=["عرض محايد غير تقييمي؛ تُستبعد قوائم الانتظار ولا يُرتَّب الأفراد." if ar else
                                   "A neutral, non-evaluative view; queues are excluded and people are not ranked."],
                            tables=[b.table(["owner", "cases", "share", "kpi_within"],
                                            [[a["owner"], fmt_int(a["count"]), fmt_pct(a["pct"]), fmt_pct(a["within_deadline_pct"])] for a in m["AGENT"]])]))
    sections.append(b.section(RS.CLASSIFICATION_MAP.value, sid(RS.CLASSIFICATION_MAP), title(RS.CLASSIFICATION_MAP), subsections=s3))

    # ── S4 journey ───────────────────────────────────────────────────────────
    jm = m.get("JOURNEY_MAP", [])
    pick = lambda item, field: item.get(f"{field}_{lang}") or item.get(f"{field}_ar") or ""  # noqa: E731
    if jm:
        rows = [[pick(f, "name"), fmt_int(f["case_count"]), CATEGORY.get(f["root_cause_category"], {}).get(lang, ""), pick(f, "remedy")] for f in jm]
        sections.append(b.section(RS.CUSTOMER_JOURNEY.value, sid(RS.CUSTOMER_JOURNEY), title(RS.CUSTOMER_JOURNEY),
                                  content=s.journey_narrative,
                                  subsections=[b.section(None, "S4.1", b.t("s4_frictions"),
                                                         tables=[b.table(["friction", "cases", "root_cause_category", "remedy"], rows)],
                                                         bullets=n.friction_points)]))
    else:
        sections.append(b.section(RS.CUSTOMER_JOURNEY.value, sid(RS.CUSTOMER_JOURNEY), title(RS.CUSTOMER_JOURNEY),
                                  notes=["لم تُرصد نقاط احتكاك قابلة للتجميع في بيانات هذه الفترة." if ar else
                                         "No groupable friction points were found in this period's data."]))

    # ── S5 digital gaps ──────────────────────────────────────────────────────
    s5: list[dict] = []
    gaps = m.get("GAP_TABLE", [])
    if gaps:
        rows = [[pick(g, "topic"), fmt_int(g["case_count"]), GUIDEBOOK_STATUS[g["guidebook_status"]][lang],
                 g["guidebook_excerpt"] or "—", GAP_TYPE.get(g["gap_type"], {}).get(lang, ""), PRIORITY[g["priority"]][lang],
                 pick(g, "recommendation")] for g in gaps]
        s5.append(b.section(None, "S5.1", b.t("s5_gaps"),
                            tables=[b.table(["topic", "cases", "guidebook_status", "excerpt", "gap_type", "priority", "recommendation"], rows)]))
        by_cat: dict[str, int] = {}
        for f in jm:
            by_cat[f["root_cause_category"]] = by_cat.get(f["root_cause_category"], 0) + f["case_count"]
        s5.append(b.section(None, "S5.2", b.t("s5_roots"), content=s.gap_root_causes_narrative,
                            tables=[b.table(["root_cause_category", "cases"], [[CATEGORY.get(k, {}).get(lang, k), fmt_int(v)] for k, v in sorted(by_cat.items(), key=lambda x: -x[1])])]))
    if m.get("FAQ_COVERAGE") or m.get("DEFLECTABLE_PCT") or n.digital_opportunity_narrative:
        tables, charts = [], []
        fc = m.get("FAQ_COVERAGE")
        if fc:
            tables.append(b.table(["main_service", "howto_cases", "coverage"],
                                  [[b.L(x), fmt_int(h), fmt_pct(c)] for x, h, c in zip(fc["labels"], fc["howto_cases"], fc["coverage_pct"])]))
            charts += [
                b.chart("faq_coverage_bar", None, "bar", ("تغطية الأسئلة الشائعة حسب الخدمة", "FAQ coverage by service"),
                        fc["labels"][:12], E(fc["labels"][:12]), [("التغطية", "Coverage", fc["coverage_pct"][:12])], [primary]),
                b.chart("howto_by_service_bar", None, "bar", ("أسئلة «الكيفية» حسب الخدمة", "How-to questions by service"),
                        fc["labels"][:12], E(fc["labels"][:12]), [("الحالات", "Cases", fc["howto_cases"][:12])], [secondary]),
            ]
        if m.get("DEFLECTABLE_PCT"):
            d = m["DEFLECTABLE_PCT"]
            tables.append(b.table(["indicator", "value"], [[
                "نسبة الحالات في حزم قابلة للخدمة الذاتية" if ar else "Share of cases in self-serviceable bundles",
                f"{fmt_pct(d['pct'])} ({fmt_int(d['count'])})"]]))
        s5.append(b.section(None, "S5.3", b.t("s5_opportunity"), content=n.digital_opportunity_narrative,
                            bullets=n.priority_faqs, tables=tables, charts=charts))
    if kpi.get("digital_share_pct") is not None and s5:
        s5[0].setdefault("notes", []).append(
            f"نسبة التواصل عبر القنوات الرقمية: {fmt_pct(kpi['digital_share_pct'])}." if ar else
            f"Share of contact through digital channels: {fmt_pct(kpi['digital_share_pct'])}."
        )
    s5_notes = [] if gaps else [_omitted(lang, "guidebook")]
    sections.append(b.section(RS.DIGITAL_GAPS.value, sid(RS.DIGITAL_GAPS), title(RS.DIGITAL_GAPS),
                              content=s.digital_gaps_narrative, notes=s5_notes, subsections=s5))

    # ── S6 digital transformation (deterministic tables — R6) ────────────────
    s6: list[dict] = []
    faqs = m.get("VALIDATED_FAQS", [])
    if faqs:
        s6.append(b.section(None, "S6.1", b.t("s6_faqs"), tables=[b.table(
            ["question", "answer", "frequency", "faq_status"],
            [[pick(q, "question"), pick(q, "answer"), fmt_int(q["frequency"]), FAQ_STATUS[q["validation_status"]][lang]] for q in faqs],
        )]))
    notes = m.get("NOTIFICATION_OPPORTUNITIES", [])
    if notes:
        s6.append(b.section(None, "S6.2", b.t("s6_notifications"), tables=[b.table(
            ["notification", "trigger", "sample_message", "eliminable"],
            [[pick(x, "type"), pick(x, "trigger"), pick(x, "message"), fmt_int(x["cases_eliminated"])] for x in notes],
        )]))
    sections.append(b.section(RS.DIGITAL_TRANSFORMATION.value, sid(RS.DIGITAL_TRANSFORMATION), title(RS.DIGITAL_TRANSFORMATION),
                              content=s.digital_transformation_narrative, subsections=s6,
                              notes=[] if s6 else ["لم تُستخرج أسئلة شائعة أو فرص إشعارات بأدلة كافية في هذه الفترة." if ar else
                                                   "No FAQs or notification opportunities with enough evidence were found this period."]))

    # ── S7 AI use cases + period comparison (R9) ─────────────────────────────
    src_names = {x["id"]: x[f"name_{lang}"] or x["name_ar"] for x in initiative_sources}
    uc_rows = [[u.title, u.function, src_names.get(u.source_ref, u.source_ref), fmt_int(u.impact_cases), EFFORT[u.effort.value][lang]] for u in s.ai_use_cases]
    s7_subs = []
    if comp:
        rows = [[b.t("kpi_total"), fmt_int(comp["total_cases"]["previous"]), fmt_int(comp["total_cases"]["current"])],
                [b.t("kpi_within"), fmt_pct(comp["within_deadline_pct"]["previous"]), fmt_pct(comp["within_deadline_pct"]["current"])],
                [b.t("kpi_digital"), fmt_pct(comp["digital_share_pct"]["previous"]), fmt_pct(comp["digital_share_pct"]["current"])],
                [b.t("kpi_reclass"), fmt_pct(comp["reclassification_rate"]["previous"]), fmt_pct(comp["reclassification_rate"]["current"])]]
        s7_subs.append(b.section(None, "S7.1", b.t("s7_comparison"), tables=[b.table(["indicator", "previous", "current"], rows)],
                                 charts=[b.chart("period_comparison", "O20", "column", ("المقارنة مع الفترة السابقة", "Period comparison"),
                                                 ["إجمالي الحالات"], ["Total cases"],
                                                 [(comp["label"], comp["label_en"], [comp["total_cases"]["previous"]]),
                                                  (period.label_ar, period.label_en, [comp["total_cases"]["current"]])],
                                                 [secondary, primary])]))
    sections.append(b.section(RS.AI_USE_CASES.value, sid(RS.AI_USE_CASES), title(RS.AI_USE_CASES),
                              content=s.ai_use_cases_intro,
                              tables=[b.table(["use_case", "function", "source_ref", "impact_cases", "effort"], uc_rows)] if uc_rows else [],
                              subsections=s7_subs))

    # ── S8 roadmap ───────────────────────────────────────────────────────────
    ini_rows = [[i.title, HORIZON[i.horizon.value][lang], src_names.get(i.bundle_ref, i.bundle_ref), fmt_int(i.addresses_cases), i.description]
                for i in sorted(n.initiatives, key=lambda x: ["immediate", "short", "medium"].index(x.horizon.value))]
    sections.append(b.section(RS.IMPROVEMENT_ROADMAP.value, sid(RS.IMPROVEMENT_ROADMAP), title(RS.IMPROVEMENT_ROADMAP),
                              content=n.roadmap_intro,
                              tables=[b.table(["initiative", "horizon", "source_ref", "cases", "description"], ini_rows)] if ini_rows else []))

    # ── S9 conclusion ────────────────────────────────────────────────────────
    closing = [n.closing_statement] if n.closing_statement else []
    if entity.closing_statement:
        closing.append(entity.closing_statement)
    closing.append(f"{b.t('end_of_report')} | {entity.name(lang)} | {period.label(lang)}")
    sections.append(b.section(RS.CONCLUSION.value, sid(RS.CONCLUSION), title(RS.CONCLUSION), subsections=[
        b.section(None, "S9.1", b.t("s9_findings"), bullets=n.key_findings),
        b.section(None, "S9.2", b.t("s9_recommendations"), bullets=n.recommendations),
        b.section(None, "S9.3", b.t("s9_kpis"), tables=[b.table(["indicator", "value"], kpi_rows)], content="\n".join(closing)),
    ]))

    # ── S10–S11 (X8) ─────────────────────────────────────────────────────────
    if m.get("BUNDLE"):
        bd = m["BUNDLE"]
        meta = {u["id"]: u for u in umbrella_meta}
        colours = {uid: b.palette[i % len(b.palette)] for i, uid in enumerate(sorted(bd["ids"], key=lambda x: (meta.get(x, {}).get("order", 99), x)))}
        s10 = [b.section(None, "S10.1", b.t("s10_bundles"), content=n.bundle_distribution_narrative,
                         tables=[b.table(["bundle", "cases", "share"], b.dist_rows(bd))],
                         charts=[b.chart("bundle_bar", "O22", "bar", ("توزيع دوافع التواصل (الحزم الموضوعية)", "Contact motives (thematic bundles)"),
                                         bd["labels"], E(bd["labels"]), [("الحالات", "Cases", bd["values"])],
                                         [colours[x] for x in bd["ids"]])])]
        matrix = m["BUNDLE_BY_SERVICE"]["counts"]
        services = list(matrix)[:10]
        heat = b.chart("bundle_service_heatmap", "O23", "heatmap", ("الحزم حسب الخدمة الرئيسية", "Bundles by main service"),
                       services, E(services), [(lab, E([lab])[0], [matrix[sv].get(lab, 0) for sv in services]) for lab in bd["labels"]])
        heat["render_in_document"] = False
        s10.append(b.section(None, "S10.2", b.t("s10_matrix"), content=n.bundle_by_service_narrative,
                             tables=[b.table(["main_service", *[b.L(x) for x in bd["labels"]]],
                                             [[b.L(sv), *[fmt_int(matrix[sv].get(lab, 0)) for lab in bd["labels"]]] for sv in services])],
                             charts=[heat]))
        per = m["ROOT_CAUSE_TOP"]["per_bundle"]
        narr = {x.bundle: x.narrative for x in n.bundle_narratives}
        bundle_subs = []
        for i, (uid, lab) in enumerate(zip(bd["ids"], bd["labels"])):
            u = meta.get(uid, {})
            meaning = u.get(f"meaning_{lang}") or u.get("meaning_ar") or ""
            inner = per.get(lab, {"labels": [], "values": []})
            bundle_subs.append(b.section(None, f"S10.3.{i + 1}", b.L(lab),
                                         content="\n".join(x for x in (meaning, narr.get(b.L(lab)) or narr.get(lab, "")) if x),
                                         tables=[b.table(["root_cause", "cases"], [[b.L(r), fmt_int(v)] for r, v in zip(inner["labels"], inner["values"])])] if inner["labels"] else []))
        s10.append(b.section(None, "S10.3", b.t("s10_per_bundle"), subsections=bundle_subs))
        top = m["ROOT_CAUSE_TOP"]
        s10.append(b.section(None, "S10.4", b.t("s10_top"), content=n.top_root_causes_narrative,
                             tables=[b.table(["root_cause", "cases"], [[b.L(r), fmt_int(v)] for r, v in zip(top["labels"], top["values"])])],
                             charts=[b.chart("top_root_causes_bar", "O24", "bar", ("الأسباب الجذرية الأكثر تكراراً", "Most frequent root causes"),
                                             top["labels"], E(top["labels"]), [("الحالات", "Cases", top["values"])], [primary])]))
        if m.get("NEAR_OVER_BY_BUNDLE"):
            no = m["NEAR_OVER_BY_BUNDLE"]
            s10.append(b.section(None, "S10.5", b.t("s10_timeliness"), content=n.timeliness_by_bundle_narrative,
                                 tables=[b.table(["bundle", "near_over", "cases"], [[b.L(x), fmt_pct(p), fmt_int(c)] for x, p, c in zip(no["labels"], no["pct"], no["counts"])])],
                                 charts=[b.chart("near_over_by_bundle_bar", "O25", "bar", ("قرب انتهاء المهلة أو تجاوزها حسب الحزمة", "Near or over deadline by bundle"),
                                                 no["labels"], E(no["labels"]), [("النسبة", "Share", no["pct"])], [TIMELINESS_COLORS["near"]])]))
        sections.append(b.section(RS.ROOT_CAUSES.value, sid(RS.ROOT_CAUSES), title(RS.ROOT_CAUSES), content=n.root_causes_intro, subsections=s10))

        focus_narr = {f.service: f for f in n.service_focus_narratives}
        s11 = []
        for i, f in enumerate(m.get("SERVICE_FOCUS", []), 1):
            fn = focus_narr.get(b.L(f["service"])) or focus_narr.get(f["service"])
            months_ar, months_en = list(f["months"]), list(f["months_en"])
            charts = [
                b.chart(f"focus_{i}_monthly_bar", None, "column", (f"{f['service']} — التوزيع الشهري", f"{E([f['service']])[0]} — monthly"),
                        months_ar, months_en, [("الحالات", "Cases", list(f["months"].values()))], [primary]),
                b.chart(f"focus_{i}_subclass_donut", None, "doughnut", (f"{f['service']} — التصنيفات الفرعية", f"{E([f['service']])[0]} — sub-classifications"),
                        f["sub_classes"]["labels"], E(f["sub_classes"]["labels"]), [("الحالات", "Cases", f["sub_classes"]["values"])], b.palette[: len(f["sub_classes"]["labels"])]),
                b.chart(f"focus_{i}_bundle_bar", None, "bar", (f"{f['service']} — الحزم", f"{E([f['service']])[0]} — bundles"),
                        f["bundles"]["labels"], E(f["bundles"]["labels"]), [("الحالات", "Cases", f["bundles"]["values"])], [secondary]),
            ]
            facts = [[b.t("cases"), fmt_int(f["count"])], [b.t("share"), fmt_pct(f["share_pct"])],
                     [b.t("kpi_within"), fmt_pct(f["within_deadline_pct"])],
                     ["الهاتف" if ar else "Phone", fmt_pct(f["phone_pct"])], ["الدردشة الحية" if ar else "Live chat", fmt_pct(f["livechat_pct"])]]
            body = [fn.overview, fn.why_this_service, fn.sub_class_narrative, fn.bundle_narrative] if fn else []
            s11.append(b.section(None, f"S11.{i}", b.L(f["service"]), content="\n".join(x for x in body if x),
                                 tables=[b.table(["indicator", "value"], facts)], charts=charts))
        if s11:
            sections.append(b.section(RS.SERVICE_FOCUS.value, sid(RS.SERVICE_FOCUS), title(RS.SERVICE_FOCUS), subsections=s11))

    if shown is not None:
        keep = {str(getattr(x, "value", x)) for x in shown}
        sections = [x for x in sections if x.get("key") in keep]

    return {
        "document_name": f"{b.t('doc_title')} — {period.label(lang)}",
        "language": lang,
        "rtl": ar,
        "entity": entity.name(lang),
        "period": period.label(lang),
        "cover": cover,
        "metadata": {
            "total_cases": kpi["total_cases"],
            "closed_cases": kpi.get("closed_cases"),
            "within_deadline_pct": kpi.get("within_deadline_pct"),
            "period_date_range": kpi["period_date_range"],
        },
        "branding": branding,
        "sections": sections,
    }


# ── Static paragraphs ─────────────────────────────────────────────────────────


def _role(column: str, lang: str) -> str:
    from ..api.models.columns import COLUMN_BY_NAME

    roles_ar = {
        "case_id": "مفتاح إزالة التكرار ورقم الدليل", "description": "مدخل التصنيف (ما طلبه المتعامل)",
        "resolution_text": "مدخل التصنيف الأقوى (ما نفّذه الموظف)", "case_type": "نطاق التحليل والتصنيف المسجَّل",
        "crm_service": "الوسم المسجَّل — للمقارنة فقط", "crm_service_group": "سياق فقط", "channel": "مزيج القنوات والحصة الرقمية",
        "opened_datetime": "الفترة والتوزيع الشهري", "closed_datetime": "الحالات المغلقة", "sla_status": "الالتزام بزمن الاستجابة",
        "status": "الحالات المفتوحة والمغلقة", "department": "التوزيع حسب الإدارات", "owner": "التقارير على مستوى الموظف (عند التفعيل)",
        "severity": "شدة الطلب", "escalation_datetime": "نافذة مستوى الخدمة", "entity": "تحديد نطاق الجهة",
        "crm_title": "سياق فقط — لا يُعتمد", "updated_datetime": "لا يُستخدم",
    }
    if lang == "ar":
        return roles_ar.get(column, "حقل إضافي")
    return COLUMN_BY_NAME[column].role.split(".")[0]


def _method_text(lang: str, method: dict[str, Any], settings: Any) -> str:
    x5, x6 = settings.llm_threshold, settings.review_threshold
    if lang == "ar":
        lines = [
            "يعتمد التصنيف على قراءة حقلين فقط: وصف الحالة وردّ المعالجة؛ وعند التعارض يحسم الرد. لا يُعتمد عنوان الحالة أو وسم الخدمة المسجَّل إلا سياقاً.",
            f"تُصنَّف الحالة المكرَّرة (الوصف نفسه) مرة واحدة وتُنسخ تسمياتها إلى نظيراتها. المستوى الأول سلسلة قواعد مبنية على الكلمات الدالّة في التصنيف المعتمد؛ وما تقل ثقته عن {x5} يُحال إلى نموذج الذكاء الاصطناعي، وما تقل ثقته بعد ذلك عن {x6} أو يخالف قاعدة من قواعد الدليل يُعاد تحليله في مراجعة معمّقة: تمريرة ثانية بنموذج أعلى قدرة وأمثلة أكثر، تُقرأ فيها الحالة من جديد.",
            f"في هذا التشغيل: {method['frozen']} حالة بتصنيف معتمد سابقاً، و{method['duplicates']} حالة مكرَّرة نُسخت تسمياتها، و{method['routed']} حالة أُحيلت إلى النموذج، و{method['corrected']} تصحيحاً آلياً وفق القواعد، و{method['deep_reviewed']} حالة خضعت للمراجعة المعمّقة، بقيت منها {method['low_confidence']} حالة بثقة منخفضة وحُسبت بأفضل تسمياتها المتاحة.",
        ]
        if method.get("root_causes"):
            lines.append(
                f"كُتب سبب جذري لكل حالة وفق دليل الأسباب الجذرية (القواعد R1–R7)، ثم جُمعت الأسباب في حزم موضوعية: {method['umbrellas']} حزمة، منها {method['new_umbrellas']} مقترحة جديدة بانتظار اعتماد مسؤول المجال."
            )
        return "\n".join(lines)
    lines = [
        "Classification reads two fields only — the case description and the resolution response — and the resolution decides when they disagree. The CRM case title and recorded service tag are context, never truth.",
        f"A case whose description repeats another's is classified once and its labels are copied to the duplicates. Tier one is a rule chain built on the approved taxonomy's keyword signals; a case below {x5} confidence goes to the artificial-intelligence model, and one still below {x6}, or still breaking a codebook rule, is re-analysed in a deep review: a second pass by a more capable model with more worked examples, reading the case afresh.",
        f"In this run: {method['frozen']} cases carried previously confirmed labels, {method['duplicates']} duplicates had their labels copied, {method['routed']} went to the model, {method['corrected']} rule-based corrections were applied, and {method['deep_reviewed']} cases were deep-reviewed, of which {method['low_confidence']} remain low-confidence and are counted with their best available labels.",
    ]
    if method.get("root_causes"):
        lines.append(
            f"A root cause was written for every case to the root-cause codebook (rules R1–R7), and the causes were grouped into thematic bundles: {method['umbrellas']} bundles, {method['new_umbrellas']} of them newly proposed and awaiting the Domain Admin's confirmation."
        )
    return "\n".join(lines)


def _quality_line(lang: str, cq: dict[str, Any]) -> str:
    parts = ", ".join(f"{k} {p}%" for k, p in zip(cq["provenance"], cq["provenance_pct"]))
    if lang == "ar":
        return (f"مصدر التصنيف: {parts}. متوسط الثقة {cq['mean_confidence']}، و{cq['pct_ge_threshold']}% من الحالات بثقة "
                f"{cq['threshold']} فأعلى، و{cq['queue_size_at_compute']} حالة بثقة منخفضة بعد المراجعة المعمّقة"
                + (f"، و{cq['unclassified']} حالة غير مصنَّفة." if cq.get("unclassified") else "."))
    parts_en = ", ".join(f"{_prov_en(k)} {p}%" for k, p in zip(cq["provenance"], cq["provenance_pct"]))
    return (f"Classification source: {parts_en}. Mean confidence {cq['mean_confidence']}; {cq['pct_ge_threshold']}% of cases at "
            f"{cq['threshold']} or above; {cq['queue_size_at_compute']} cases low-confidence after the deep review"
            + (f"; {cq['unclassified']} unclassified." if cq.get("unclassified") else "."))


def _prov_en(label: str) -> str:
    from ..engine.wording import PROVENANCE_EN

    for key, ar in PROVENANCE.items():
        if ar == label:
            return PROVENANCE_EN[key]
    return label


def _fw_name(fid: str, lang: str) -> str:
    from ..engine.frameworks import FRAMEWORK_NAMES

    return FRAMEWORK_NAMES.get(fid, {}).get(lang, fid)


def _fw_status(status: str, lang: str) -> str:
    return {
        "not_computable": {"ar": "غير قابل للاحتساب من التصدير", "en": "Not computable from this export"},
        "reference": {"ar": "مرجعي", "en": "Reference only"},
        "partial": {"ar": "جزئي", "en": "Partial"},
    }.get(status, {}).get(lang, status)


def _fw_table(b: _Builder, m: dict, lang: str) -> dict:
    rows = [[i[f"name_{lang}"], _fw_name(i["framework"], lang),
             fmt_pct(i["value_pct"]) if i["value_pct"] is not None else _fw_status(i["status"], lang),
             i[f"target_{lang}"] or "—", i[f"recommendation_{lang}"] or "—"] for i in m.get("FRAMEWORKS", [])]
    return b.table(["indicator", "framework", "value", "target", "recommendation"], rows)


def _omitted(lang: str, what: str) -> str:
    texts = {
        "guidebook": ("لم يُدرج جدول الفجوات الرقمية لعدم تزويد دليل الخدمات المعتمد ضمن القوائم المرجعية.",
                      "The digital gap table is omitted because no approved service guidebook was provided."),
        "sla_status": ("لم يُحتسب الالتزام بزمن الاستجابة لعدم تزويد حقل حالة مستوى الخدمة أو الطوابع الزمنية.",
                       "Response-time compliance is not computed: neither the SLA status nor timestamps were provided."),
    }
    return texts[what][0 if lang == "ar" else 1]
