"""
build_report_ar.py
Reads complaint report JSON and writes a styled .docx
following the design palette in design-palette.md.
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
    rejection_rate = 0.0
    closure_rate = 0.0

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

    # Closure rate (on-time closure) from metadata
    closure_rate = data.get("metadata", {}).get("closure_rate", 0.0)

    return total_complaints, traffic_pct, digital_channel_rate, rejection_rate, closure_rate


def _make_config(data: dict) -> DocumentConfig:
    doc_name = data.get("document_name", "تقرير تحليل شكاوى المتعاملين")
    # Extract period from document name (format: "تقرير تحليل شكاوى المتعاملين — يناير 2025")
    parts = doc_name.split('—')
    period = parts[1].strip() if len(parts) > 1 else "Q1 2026"

    header_text = f"{parts[0].strip()}  ·  {period}"

    theme = _theme(data)

    return DocumentConfig(
        page_size="Letter",
        margin_top=2.54,
        margin_bottom=2.54,
        margin_left=2.54,
        margin_right=2.54,
        default_font="Dubai",
        default_font_size=12,
        default_rtl=True,
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
        footer_text="سري — للاستخدام الداخلي  |  صفحة ",
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
    total_complaints, traffic_pct, digital_channel_rate, rejection_rate, closure_rate = _extract_cover_stats(data)
    doc_name = data.get("document_name", "تقرير تحليل شكاوى المتعاملين")
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
        style=TextStyle(size=26, alignment="CENTER", color=theme.primary, space_before=12, space_after=12),
        rtl=True,
    )

    cover.add_horizontal_separator(native=True, color=theme.primary)

    cover.add_spacer(16)

    if period:
        cover.add_paragraph(
            period,
            style=TextStyle(size=14, bold=True, color=theme.primary, alignment="CENTER", space_before=0, space_after=8),
            rtl=True,
        )

    cover.add_spacer(16)

    stat_style = TextStyle(size=14, bold=True, color=theme.primary, alignment="CENTER", space_before=8, space_after=8)

    if total_complaints:
        cover.add_paragraph(f"إجمالي الشكاوى: {total_complaints} شكوى", style=stat_style, rtl=True)
    if traffic_pct:
        cover.add_paragraph(f"الشكاوى المرورية: {traffic_pct} من الإجمالي", style=stat_style, rtl=True)
    cover.add_paragraph(f"القنوات الرقمية: {digital_channel_rate} من التقديمات", style=stat_style, rtl=True)
    if rejection_rate > 0:
        cover.add_paragraph(f"معدل الرفض الرسمي: {rejection_rate:.1f}%", style=stat_style, rtl=True)
    if closure_rate > 0:
        cover.add_paragraph(f"معدل الإغلاق في الوقت المحدد: {closure_rate:.1f}%", style=stat_style, rtl=True)

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


def _render_table(builder: WordBuilder, table: dict, theme: _Theme = DEFAULT_THEME):
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    if not columns or not rows:
        return

    # Normalize friction-related labels (strip embedded counts, prepend reconciled count)
    # This applies to columns that may contain LLM-generated counts that don't match
    # the "الحالات" (case count) column
    friction_label_columns = {"نقطة الاحتكاك", "نوع الفجوة", "السبب الجذري"}
    has_case_count_col = "الحالات" in columns

    processed_rows = []
    for row in rows:
        processed_row = dict(row)  # Make a copy

        if has_case_count_col:
            try:
                case_count = int(row.get("الحالات", 0))
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

    # Reverse column order for RTL visual layout (rightmost = first logical column)
    rtl_columns = list(reversed(columns))
    ordered_rows = [{col: row.get(col, "") for col in rtl_columns} for row in processed_rows]

    builder.add_table(
        ordered_rows,
        style=_table_style(theme),
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


def _render_section(builder: WordBuilder, section: dict, depth: int = 1, theme: _Theme = DEFAULT_THEME):
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
            heading_text="المحتويات",
            heading_bg_color=theme.primary,
            heading_text_color="FFFFFF",
            heading_font="Dubai",
            entry_font="Dubai",
            rtl=True,
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
    json_path = base / "report_final_ar.json"
    out_path = json_path.with_suffix(".docx")
    build_report(json_path, out_path)
