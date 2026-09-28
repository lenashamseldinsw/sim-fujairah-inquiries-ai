"""
build_report_en.py
Reads complaint report JSON (e.g. complaints_report_*_data_en.json)
and writes a styled LTR .docx following the design palette in design-palette.md.
"""

import dataclasses
import json
import re
import sys
from pathlib import Path

# The Word builder is vendored into this package; no path insertion needed.

# Import utilities for label normalization
from .utils import normalize_friction_label
from ..reporting.sword_word_builder import (
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

# The tenant logo travels on the request (EntityInfo) and is injected into the
# report dict by pipeline.py before the document is built. There is deliberately
# no bundled default: a defaulted identity field is how one tenant's report ends
# up carrying another tenant's logo.
#
# It is read off the data rather than held in a module global because a worker
# can build two tenants' reports at once — a global would let one run's logo
# reach the other's cover.


def _branding(data: dict) -> dict:
    """The tenant identity pack for this run, or an empty mapping."""
    value = data.get("branding")
    return value if isinstance(value, dict) else {}


def _logo_path(data: dict):
    """Filesystem path to this run's logo, or None when the tenant sent none."""
    return _branding(data).get("logo_path") or None


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
# Theme
# ---------------------------------------------------------------------------
#
# The palette above is the *renderer's* default, not a tenant's. That distinction
# is load-bearing: ``EntityInfo`` carries no tenant colours — its ``brand`` defaults
# to the NoveAI platform palette, and putting a particular organisation's gold in
# the shared contract would be exactly the defaulted-identity mistake the contract
# exists to prevent.
#
# So the fallback lives here, where it belongs: a request that does not set
# ``brand`` is rendered in the design this report has always used, and one that does
# set it is rendered in the tenant's colours. ``pipeline.py`` only puts ``brand``
# into the branding pack when the caller actually supplied it, which is what makes
# the two cases distinguishable at all.


@dataclasses.dataclass(frozen=True)
class _Theme:
    """The two colours the document's chrome is drawn in."""

    primary: str    # headings, banners, table headers, rules
    secondary: str  # accents


DEFAULT_THEME = _Theme(primary=GOLD, secondary=GOLD)

_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")


def _hex(value: object) -> str | None:
    """A contract colour as the Word builder wants it: six hex digits, no '#'.

    Returns ``None`` for anything unusable, so a malformed colour falls back to the
    design palette rather than reaching python-docx, where a bad value produces a
    document that opens with a repair prompt.
    """
    if not isinstance(value, str):
        return None
    token = value.strip().lstrip("#")
    if len(token) == 3:  # #abc is shorthand for #aabbcc
        token = "".join(c * 2 for c in token)
    return token.upper() if _HEX_RE.match(token) else None


def _theme(data: dict) -> _Theme:
    """This run's palette: the tenant's brand where given, the design default where not."""
    brand = _branding(data).get("brand")
    if not isinstance(brand, dict):
        return DEFAULT_THEME
    primary = _hex(brand.get("primary"))
    if primary is None:
        return DEFAULT_THEME
    # A tenant that names one colour means it; the second falls back to the first
    # rather than to the design palette, which would mix two unrelated identities.
    return _Theme(primary=primary, secondary=_hex(brand.get("secondary")) or primary)


def _table_style(theme: _Theme) -> TableStyle:
    """The table style for this run. A function, not a constant: the header colour
    follows the tenant's brand, and a module-level constant is fixed at import."""
    return dataclasses.replace(TABLE_STYLE, header_bg_color=theme.primary)



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

    theme = _theme(data)

    return DocumentConfig(
        page_size="Letter",
        margin_top=2.54,
        margin_bottom=2.54,
        margin_left=2.54,
        margin_right=2.54,
        default_font="Calibri",
        default_font_size=12,
        default_rtl=False,
        accent_color=theme.primary,
        secondary_color=theme.secondary,
        heading_color=theme.primary,
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
        header_text_color=theme.primary,
        header_font_size=10,
        header_bottom_border_color=theme.primary,
        footer_type="text_and_page_number",
        footer_text="Confidential — Internal Use Only  |  Page ",
        footer_alignment="CENTER",
        footer_text_color=MID_GRAY,
        footer_font_size=9,
        footer_top_border_color=theme.primary,
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

    theme = _theme(data)
    cover = CoverPage()

    cover.add_spacer(12)
    logo_path = _logo_path(data)
    if logo_path:
        cover.add_picture(logo_path, width_cm=4.19, height_cm=2.74, alignment="CENTER")


    cover.add_horizontal_separator(native=True, color=theme.primary)

    cover.add_heading(
        doc_name,
        level=1,
        style=TextStyle(size=16, alignment="CENTER", color=theme.primary, space_before=12, space_after=12),
        rtl=False,
    )

    cover.add_horizontal_separator(native=True, color=theme.primary)

    cover.add_spacer(16)

    if period:
        cover.add_paragraph(
            period,
            style=TextStyle(size=14, bold=True, color=theme.primary, alignment="CENTER", space_before=0, space_after=8),
            rtl=False,
        )

    cover.add_spacer(16)

    stat_style = TextStyle(size=14, bold=True, color=theme.primary, alignment="CENTER", space_before=8, space_after=8)

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


def _render_table(builder: WordBuilder, table: dict, theme: _Theme = DEFAULT_THEME):
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    if not columns or not rows:
        return

    # Normalize friction-related labels (strip embedded counts, prepend reconciled count)
    # This applies to columns that may contain LLM-generated counts that don't match
    # the "Cases" or "الحالات" (case count) column
    # Note: normalize_friction_label works with Arabic patterns; English patterns would need
    # a separate handler, but the translation is done after reconciliation so this shouldn't occur
    friction_label_columns = {"نقطة الاحتكاك", "نوع الفجوة", "السبب الجذري",
                              "Friction Point", "Gap Type", "Root Cause"}  # Both Arabic and English
    has_case_count_col = "الحالات" in columns or "Cases" in columns

    processed_rows = []
    for row in rows:
        processed_row = dict(row)  # Make a copy

        if has_case_count_col:
            # Try to get case count from either Arabic or English column
            case_count_str = row.get("الحالات") or row.get("Cases", "0")
            try:
                case_count = int(case_count_str)
            except (ValueError, TypeError):
                case_count = 0

            # Apply normalization to any friction-related columns in this row
            for col in friction_label_columns:
                if col in processed_row and processed_row[col]:
                    processed_row[col] = normalize_friction_label(
                        processed_row[col],
                        case_count
                    )

        processed_rows.append(processed_row)

    # LTR: preserve natural column order
    ordered_rows = [{col: row.get(col, "") for col in columns} for row in processed_rows]

    builder.add_table(
        ordered_rows,
        style=_table_style(theme),
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


def _render_section(builder: WordBuilder, section: dict, depth: int = 1, theme: _Theme = DEFAULT_THEME):
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
        _render_table(builder, table, theme)

    for chart in section.get("charts", []):
        _render_chart(builder, chart)

    for subsection in section.get("subsections", []):
        _render_section(builder, subsection, depth=depth + 1, theme=theme)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_report(json_path: str | Path, output_path: str | Path):
    json_path = Path(json_path)
    output_path = Path(output_path)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    theme = _theme(data)
    config = _make_config(data)
    builder = WordBuilder(config)

    # Cover
    _build_cover(builder, data)

    # Native TOC
    builder.add_toc(
        TocStyle(
            heading_text="Table of Contents",
            heading_bg_color=theme.primary,
            heading_text_color="FFFFFF",
            heading_font="Calibri",
            entry_font="Calibri",
            rtl=False,
            exclude_cover_page=True,
        )
    )

    # Body sections
    for section in data.get("sections", []):
        _render_section(builder, section, depth=1, theme=theme)

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
