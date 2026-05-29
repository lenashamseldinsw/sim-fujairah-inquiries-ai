"""
build_report_en.py
Reads complaint report JSON (e.g. complaints_report_*_data_en.json)
and writes a styled LTR .docx following the design palette in design-palette.md.
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
    text_alignment="LEFT",
    rtl=False,
)

CHART_STYLE = ChartStyle(
    width_cm=14,
    height_cm=9,
    show_legend=True,
    legend_position="b",
    show_data_labels=True,
    show_gridlines=True,
    font="Calibri",
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
    font="Calibri",
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
    zero_rejection = False

    # Total complaints count from metadata
    total_complaints = data.get("metadata", {}).get("total_complaints", 0)

    # Fallback: if metadata doesn't have total_complaints, sum section 3.1 distribution table
    if not total_complaints:
        sec_31 = _find_subsection(data["sections"], "التوزيع_الفعلي")
        if sec_31:
            for table in sec_31.get("tables", []):
                for row in table.get("rows", []):
                    try:
                        total_complaints += int(row.get("Count", 0))
                    except (ValueError, TypeError):
                        pass

    # Section 3.1: extract traffic complaint percentage
    sec_31 = _find_subsection(data["sections"], "التوزيع_الفعلي")
    if sec_31:
        for table in sec_31.get("tables", []):
            for row in table.get("rows", []):
                if row.get("Complaint Type") == "Traffic Complaint":
                    traffic_pct = row.get("Percentage", "")

    # Digital channel rate from metadata
    digital_channel_rate = data.get("metadata", {}).get("digital_channel_rate", "0")

    # Zero rejection flag from metadata
    zero_rejection = data.get("metadata", {}).get("zero_rejection_rate", False)

    return total_complaints, traffic_pct, digital_channel_rate, zero_rejection


def _make_config(data: dict) -> DocumentConfig:
    doc_name = data.get("document_name", "Customer Complaint Analysis Report")
    # Extract period from document name (format: "Report Name — Period")
    parts = doc_name.split("—")
    period = parts[1].strip() if len(parts) > 1 else ""

    header_text = f"{parts[0].strip()}  ·  {period}" if period else parts[0].strip()

    return DocumentConfig(
        page_size="Letter",
        margin_top=2.54,
        margin_bottom=2.54,
        margin_left=2.54,
        margin_right=2.54,
        default_font="Calibri",
        default_font_size=12,
        default_rtl=False,
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
        footer_text="Confidential — Internal Use Only  |  Page ",
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
    total_complaints, traffic_pct, digital_channel_rate, zero_rejection = _extract_cover_stats(data)
    doc_name = data.get("document_name", "Customer Complaint Analysis Report")
    parts = doc_name.split("—")
    period = parts[1].strip() if len(parts) > 1 else ""

    cover = CoverPage()

    cover.add_spacer(12)
    cover.add_picture(LOGO_PATH, width_cm=4.19, height_cm=2.74, alignment="CENTER")


    cover.add_horizontal_separator(native=True, color=GOLD)

    cover.add_heading(
        doc_name,
        level=1,
        style=TextStyle(size=16, alignment="CENTER", color=GOLD, space_before=12, space_after=12),
        rtl=False,
    )

    cover.add_horizontal_separator(native=True, color=GOLD)

    cover.add_spacer(16)

    if period:
        cover.add_paragraph(
            period,
            style=TextStyle(size=14, bold=True, color=GOLD, alignment="CENTER", space_before=0, space_after=8),
            rtl=False,
        )

    cover.add_spacer(16)

    stat_style = TextStyle(size=14, bold=True, color=GOLD, alignment="CENTER", space_before=8, space_after=8)

    if total_complaints:
        cover.add_paragraph(f"Total Complaints: {total_complaints}", style=stat_style, rtl=False)
    if traffic_pct:
        cover.add_paragraph(f"Traffic Complaints: {traffic_pct} of Total", style=stat_style, rtl=False)
    cover.add_paragraph(f"Digital Submission Rate: {digital_channel_rate}%", style=stat_style, rtl=False)
    if zero_rejection:
        cover.add_paragraph("0% Formal Rejection Rate", style=stat_style, rtl=False)

    cover.add_spacer(32)

    meta = data.get("metadata", {})
    created = meta.get("created", "2026-04-30")[:10]
    cover.add_paragraph(
        f"Fujairah Police  |  {created}  |  Integrated Business Intelligence Analysis",
        style=TextStyle(color=SOFT_GRAY, alignment="CENTER", space_before=0, space_after=0),
        rtl=False,
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

    # LTR: preserve natural column order
    ordered_rows = [{col: row.get(col, "") for col in columns} for row in rows]

    builder.add_table(
        ordered_rows,
        style=TABLE_STYLE,
        rtl=False,
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
        rtl=False,
    )


# ---------------------------------------------------------------------------
# Section renderer
# ---------------------------------------------------------------------------


def _render_section(builder: WordBuilder, section: dict, depth: int = 1):
    level = min(depth, 3)
    title = section.get("title", "")
    if title:
        builder.add_heading(title, level=level, rtl=False)

    content = section.get("content", "").strip()
    if content:
        for para in content.split("\n"):
            para = para.strip()
            if para:
                builder.add_paragraph(
                    para,
                    rtl=False,
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
            heading_text="Table of Contents",
            heading_bg_color=GOLD,
            heading_text_color="FFFFFF",
            heading_font="Calibri",
            entry_font="Calibri",
            rtl=False,
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

    # Try to find the most recent English JSON in the same directory,
    # falling back to a fixed name if none is found.
    en_files = sorted(base.glob("*_en.json"), reverse=True)
    if en_files:
        json_path = en_files[0]
    else:
        json_path = base / "report_final_en.json"

    out_path = json_path.with_suffix(".docx")
    build_report(json_path, out_path)
