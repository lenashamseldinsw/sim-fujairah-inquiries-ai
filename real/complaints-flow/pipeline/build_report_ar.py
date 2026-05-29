"""
build_report_ar.py
Reads complaint report JSON and writes a styled .docx
following the design palette in design-palette.md.
"""

import dataclasses
import json
import sys
from pathlib import Path

# Add root directory to path to find sword_word_builder
root_dir = Path(__file__).resolve().parent.parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

LOGO_PATH = root_dir / "assets" / "fujairah-short-logo.png"

from sword_word_builder import (
    WordBuilder,
    DocumentConfig,
    TextStyle,
    TableStyle,
    ChartStyle,
    TocStyle,
    CoverPage,
)

# ---------------------------------------------------------------------------
# Design constants
# ---------------------------------------------------------------------------

GOLD = "B68A35"
DARK_GRAY = "404040"
MID_GRAY = "555555"
SOFT_GRAY = "606060"

TABLE_STYLE = TableStyle(
    header_bg_color=GOLD,
    header_text_color="FFFFFF",
    header_bold=True,
    header_font_size=10,
    row_bg_color="FFFFFF",
    alt_row_bg_color="D9D9D9",
    border_color="CCCCCC",
    border_width_pt=0.5,
    font_size=10,
    text_alignment="RIGHT",
    rtl=True,
)

CHART_STYLE = ChartStyle(
    width_cm=14,
    height_cm=9,
    show_legend=True,
    legend_position="b",
    show_data_labels=True,
    show_gridlines=True,
    font="Dubai",
    axis_font_size=9,
    legend_font_size=9,
    title_font_size=12,
)

PIE_CHART_STYLE = ChartStyle(
    width_cm=14,
    height_cm=9,
    show_legend=True,
    legend_position="b",
    show_data_labels=True,
    show_gridlines=False,
    font="Dubai",
    axis_font_size=9,
    legend_font_size=9,
    title_font_size=12,
    show_data_label_values=False,
    show_data_label_percentages=True,
    data_label_font_size=8,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_subsection(sections, id_fragment: str):
    """Recursively find the first subsection whose id contains id_fragment."""
    for sec in sections:
        if id_fragment in sec.get("id", ""):
            return sec
        found = _find_subsection(sec.get("subsections", []), id_fragment)
        if found:
            return found
    return None


def _extract_cover_stats(data: dict):
    """Derive headline KPIs for the cover page from JSON content (complaints version)."""
    traffic_pct = ""
    digital_channel_rate = "0"
    rejection_rate = 0.0
    true_digital_gaps = 0

    # Total complaints count from metadata
    total_complaints = data.get("metadata", {}).get("total_complaints", 0)

    # Fallback: if metadata doesn't have total_complaints, sum section 3.1 distribution table
    if not total_complaints:
        sec_31 = _find_subsection(data["sections"], "التوزيع_الفعلي")
        if sec_31:
            for table in sec_31.get("tables", []):
                for row in table.get("rows", []):
                    try:
                        total_complaints += int(row.get("العدد", 0))
                    except (ValueError, TypeError):
                        pass

    # Section 3.1: extract traffic complaint percentage
    sec_31 = _find_subsection(data["sections"], "التوزيع_الفعلي")
    if sec_31:
        for table in sec_31.get("tables", []):
            for row in table.get("rows", []):
                if row.get("نوع الشكوى") == "شكوى مرورية":
                    traffic_pct = row.get("النسبة", "")

    # Digital channel rate from metadata
    digital_channel_rate = data.get("metadata", {}).get("digital_channel_rate", "0")

    # Rejection rate (formal rejection) from metadata
    rejection_rate = data.get("metadata", {}).get("rejection_rate", 0.0)

    # Count only 🔴 true digital gaps (services with NO digital channel)
    # Excludes 🟡 awareness gaps per report_structure.md spec
    sec_51 = _find_subsection(data["sections"], "جدول_الفجوات")
    if sec_51:
        for table in sec_51.get("tables", []):
            for row in table.get("rows", []):
                gap_type = row.get("نوع الفجوة", "")
                if gap_type.startswith("🔴") or "حقيقية" in gap_type:
                    true_digital_gaps += 1

    return total_complaints, traffic_pct, digital_channel_rate, rejection_rate, true_digital_gaps


def _make_config(data: dict) -> DocumentConfig:
    doc_name = data.get("document_name", "تقرير تحليل شكاوى المتعاملين")
    # Extract period from document name (format: "تقرير تحليل شكاوى المتعاملين — يناير 2025")
    parts = doc_name.split('—')
    period = parts[1].strip() if len(parts) > 1 else "Q1 2026"

    header_text = f"{parts[0].strip()}  ·  {period}"

    return DocumentConfig(
        page_size="Letter",
        margin_top=2.54,
        margin_bottom=2.54,
        margin_left=2.54,
        margin_right=2.54,
        default_font="Dubai",
        default_font_size=12,
        default_rtl=True,
        accent_color=GOLD,
        secondary_color=GOLD,
        heading_color=GOLD,
        heading1_size=16,
        heading2_size=13,
        heading3_size=12,
        heading_bold=True,
        heading1_separator=False,
        heading2_separator=False,
        heading3_separator=False,
        header_type="text",
        header_text=header_text,
        header_alignment="CENTER",
        header_text_color=GOLD,
        header_font_size=10,
        header_bottom_border_color=GOLD,
        footer_type="text_and_page_number",
        footer_text="سري — للاستخدام الداخلي  |  صفحة ",
        footer_alignment="CENTER",
        footer_text_color=MID_GRAY,
        footer_font_size=9,
        footer_top_border_color=GOLD,
        skip_first_page_header_footer=False,
    )


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------


def _build_cover(builder: WordBuilder, data: dict):
    total_complaints, traffic_pct, digital_channel_rate, rejection_rate, true_digital_gaps = _extract_cover_stats(data)
    doc_name = data.get("document_name", "تقرير تحليل شكاوى المتعاملين")
    parts = doc_name.split("—")
    period = parts[1].strip() if len(parts) > 1 else ""

    cover = CoverPage()

    cover.add_spacer(12)
    cover.add_picture(LOGO_PATH, width_cm=4.19, height_cm=2.74, alignment="CENTER")


    cover.add_horizontal_separator(native=True, color=GOLD)

    cover.add_heading(
        doc_name,
        level=1,
        style=TextStyle(size=26, alignment="CENTER", color=GOLD, space_before=12, space_after=12),
        rtl=True,
    )

    cover.add_horizontal_separator(native=True, color=GOLD)

    cover.add_spacer(16)

    if period:
        cover.add_paragraph(
            period,
            style=TextStyle(size=14, bold=True, color=GOLD, alignment="CENTER", space_before=0, space_after=8),
            rtl=True,
        )

    cover.add_spacer(16)

    stat_style = TextStyle(size=14, bold=True, color=GOLD, alignment="CENTER", space_before=8, space_after=8)

    if total_complaints:
        cover.add_paragraph(f"إجمالي الشكاوى: {total_complaints} شكوى", style=stat_style, rtl=True)
    if traffic_pct:
        cover.add_paragraph(f"الشكاوى المرورية: {traffic_pct} من الإجمالي", style=stat_style, rtl=True)
    cover.add_paragraph(f"القنوات الرقمية: {digital_channel_rate} من التقديمات", style=stat_style, rtl=True)
    if rejection_rate > 0:
        cover.add_paragraph(f"معدل الرفض الرسمي: {rejection_rate:.1f}%", style=stat_style, rtl=True)
    if true_digital_gaps:
        cover.add_paragraph(f"رصد {true_digital_gaps} فجوات رقمية محددة", style=stat_style, rtl=True)

    cover.add_spacer(32)

    meta = data.get("metadata", {})
    created = meta.get("created", "2026-04-30")[:10]
    cover.add_paragraph(
        f"شرطة الفجيرة  |  {created}  |  تحليل ذكاء الأعمال المتكامل",
        style=TextStyle(color=SOFT_GRAY, alignment="CENTER", space_before=0, space_after=0),
        rtl=True,
    )

    builder.add_cover_page(cover)


# ---------------------------------------------------------------------------
# Table & chart renderers
# ---------------------------------------------------------------------------


def _render_table(builder: WordBuilder, table: dict):
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    if not columns or not rows:
        return

    # Reverse column order for RTL visual layout (rightmost = first logical column)
    rtl_columns = list(reversed(columns))
    ordered_rows = [{col: row.get(col, "") for col in rtl_columns} for row in rows]

    builder.add_table(
        ordered_rows,
        style=TABLE_STYLE,
        rtl=True,
    )


def _render_chart(builder: WordBuilder, chart: dict):
    colors = chart.get("colors", [])
    chart_type = chart.get("type", "column")
    series = []
    for i, s in enumerate(chart.get("series", [])):
        entry = {
            "name": s.get("name", ""),
            "values": s.get("data", []),
        }
        # For pie charts slice colors come from ChartStyle.series_colors, not per-series color
        if chart_type != "pie" and i < len(colors):
            entry["color"] = colors[i].lstrip("#")
        series.append(entry)

    chart_data = {
        "title": chart.get("title", ""),
        "categories": chart.get("categories", []),
        "series": series,
    }

    style = CHART_STYLE
    if chart_type == "pie":
        style = PIE_CHART_STYLE
        if colors:
            style = dataclasses.replace(
                PIE_CHART_STYLE,
                series_colors=[c.lstrip("#") for c in colors],
            )

    if chart_type == "bar":
        chart_type = "column"

    builder.add_chart(
        chart_data,
        chart_type=chart_type,
        style=style,
        rtl=True,
    )


# ---------------------------------------------------------------------------
# Section renderer
# ---------------------------------------------------------------------------


def _render_section(builder: WordBuilder, section: dict, depth: int = 1):
    level = min(depth, 3)
    title = section.get("title", "")
    if title:
        builder.add_heading(title, level=level, rtl=True)

    content = section.get("content", "").strip()
    if content:
        for para in content.split("\n"):
            para = para.strip()
            if para:
                builder.add_paragraph(
                    para,
                    rtl=True,
                    style=TextStyle(alignment="JUSTIFY", color="000000"),
                )

    for table in section.get("tables", []):
        _render_table(builder, table)

    for chart in section.get("charts", []):
        _render_chart(builder, chart)

    for subsection in section.get("subsections", []):
        _render_section(builder, subsection, depth=depth + 1)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_report(json_path: str | Path, output_path: str | Path):
    json_path = Path(json_path)
    output_path = Path(output_path)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    config = _make_config(data)
    builder = WordBuilder(config)

    # Cover
    _build_cover(builder, data)

    # Native TOC
    builder.add_toc(
        TocStyle(
            heading_text="المحتويات",
            heading_bg_color=GOLD,
            heading_text_color="FFFFFF",
            heading_font="Dubai",
            entry_font="Dubai",
            rtl=True,
            exclude_cover_page=True,
        )
    )

    # Body sections
    for section in data.get("sections", []):
        _render_section(builder, section, depth=1)

    builder.save(str(output_path))
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    base = Path(__file__).parent
    json_path = base / "report_final_ar.json"
    out_path = json_path.with_suffix(".docx")
    build_report(json_path, out_path)
