"""
Rendering the report data as a Word document — one renderer, both languages.

Draws only what ``assemble`` placed: the cover from ``report["cover"]``, then each
section's paragraphs, bullet lists, tables, charts and data notes. Arabic renders
right-to-left in Dubai, English left-to-right in Calibri.

**Colours (Prerequisites §5).** The tenant's brand when the request sent one, and
NoveAI Navy / Magenta when it did not — the documented default. Status colours
(within / near / over deadline) are platform-locked and come with the chart, never
from the brand. Nothing on the cover or in a footer names an organisation the request
did not name.
"""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from ..models.entity import NOVEAI_MAGENTA, NOVEAI_NAVY
from ._docx import (
    ChartStyle,
    CoverPage,
    DocumentConfig,
    TableStyle,
    TextStyle,
    TocStyle,
    WordBuilder,
)
from .labels import t

__all__ = ["build_document", "theme_of", "Theme", "DEFAULT_THEME"]

DARK_GRAY = "404040"
MID_GRAY = "555555"
SOFT_GRAY = "6B6B6B"
_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")


@dataclasses.dataclass(frozen=True)
class Theme:
    primary: str
    secondary: str


DEFAULT_THEME = Theme(primary=NOVEAI_NAVY.lstrip("#").upper(), secondary=NOVEAI_MAGENTA.lstrip("#").upper())


def _hex(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().lstrip("#")
    if len(token) == 3:
        token = "".join(c * 2 for c in token)
    return token.upper() if _HEX_RE.match(token) else None


def theme_of(report: dict) -> Theme:
    """The brand colours in the report's branding pack, or the documented default."""
    brand = (report.get("branding") or {}).get("brand")
    if not isinstance(brand, dict):
        return DEFAULT_THEME
    primary = _hex(brand.get("primary"))
    if primary is None:
        return DEFAULT_THEME
    return Theme(primary=primary, secondary=_hex(brand.get("secondary")) or primary)


def _font(rtl: bool) -> str:
    return "Dubai" if rtl else "Calibri"


def _config(report: dict, theme: Theme) -> DocumentConfig:
    rtl = report["rtl"]
    lang = report["language"]
    return DocumentConfig(
        page_size="Letter",
        margin_top=2.54, margin_bottom=2.54, margin_left=2.54, margin_right=2.54,
        default_font=_font(rtl), default_font_size=12 if rtl else 11, default_rtl=rtl,
        accent_color=theme.primary, secondary_color=theme.secondary, heading_color=theme.primary,
        heading1_size=16, heading2_size=13, heading3_size=12, heading_bold=True,
        heading1_separator=False, heading2_separator=False, heading3_separator=False,
        header_type="text", header_text=f"{t('doc_title', lang)}  ·  {report['period']}",
        header_alignment="CENTER", header_text_color=theme.primary, header_font_size=10,
        header_bottom_border_color=theme.primary,
        footer_type="text_and_page_number", footer_text=t("footer", lang),
        footer_alignment="CENTER", footer_text_color=MID_GRAY, footer_font_size=9,
        footer_top_border_color=theme.primary, skip_first_page_header_footer=False,
    )


def _table_style(theme: Theme, rtl: bool) -> TableStyle:
    return TableStyle(
        header_bg_color=theme.primary, header_text_color="FFFFFF", header_bold=True,
        header_font_size=10, row_bg_color="FFFFFF", alt_row_bg_color="EEEEF3",
        border_color="CCCCCC", border_width_pt=0.5, font_size=9 if not rtl else 10,
        text_alignment="RIGHT" if rtl else "LEFT", rtl=rtl,
    )


def _chart_style(rtl: bool, pie: bool) -> ChartStyle:
    base = ChartStyle(
        width_cm=15, height_cm=9, show_legend=True, legend_position="b", show_data_labels=True,
        show_gridlines=True, font=_font(rtl), axis_font_size=9, legend_font_size=9, title_font_size=12,
    )
    if pie:
        base = dataclasses.replace(
            base, show_data_label_values=False, show_data_label_percentages=True, data_label_font_size=8
        )
    return base


def _cover(builder: WordBuilder, report: dict, theme: Theme, logo_path: str | None) -> None:
    rtl = report["rtl"]
    cover_data = report["cover"]
    cover = CoverPage()
    cover.add_spacer(10)
    if logo_path:
        cover.add_picture(logo_path, width_cm=4.2, height_cm=2.7, alignment="CENTER")
    cover.add_horizontal_separator(native=True, color=theme.primary)
    cover.add_heading(cover_data["title"], level=1, rtl=rtl,
                      style=TextStyle(size=24 if rtl else 20, alignment="CENTER", color=theme.primary, space_before=10, space_after=6))
    cover.add_paragraph(cover_data["entity"], rtl=rtl,
                        style=TextStyle(size=16, bold=True, alignment="CENTER", color=theme.secondary, space_after=2))
    if cover_data.get("center"):
        cover.add_paragraph(cover_data["center"], rtl=rtl, style=TextStyle(size=12, alignment="CENTER", color=SOFT_GRAY))
    if cover_data.get("name_short"):
        cover.add_paragraph(cover_data["name_short"], rtl=False, style=TextStyle(size=11, alignment="CENTER", color=SOFT_GRAY))
    cover.add_horizontal_separator(native=True, color=theme.primary)
    cover.add_paragraph(f"{cover_data['period']}  ·  {cover_data['date_range']}", rtl=rtl,
                        style=TextStyle(size=13, bold=True, alignment="CENTER", color=theme.primary, space_before=6, space_after=10))
    head = [t("indicator", report["language"]), t("value", report["language"])]
    if rtl:
        head.reverse()
    rows = []
    for tile in cover_data["tiles"]:
        row = {t("indicator", report["language"]): tile["label"], t("value", report["language"]): tile["value"]}
        rows.append({k: row[k] for k in head})
    cover.add_table(rows, style=_table_style(theme, rtl), rtl=rtl)
    if cover_data.get("source_system"):
        cover.add_paragraph(cover_data["source_system"], rtl=rtl, style=TextStyle(size=10, alignment="CENTER", color=SOFT_GRAY))
    cover.add_paragraph(f"{cover_data['entity']}  |  {t('prepared_by', report['language'])}", rtl=rtl,
                        style=TextStyle(size=9, alignment="CENTER", color=SOFT_GRAY, space_before=12))
    builder.add_cover_page(cover)


def _table(builder: WordBuilder, table: dict, theme: Theme, rtl: bool) -> None:
    columns, rows = table.get("columns", []), table.get("rows", [])
    if not columns or not rows:
        return
    ordered = list(reversed(columns)) if rtl else list(columns)
    builder.add_table([{c: row.get(c, "") for c in ordered} for row in rows], style=_table_style(theme, rtl), rtl=rtl)
    if table.get("note"):
        builder.add_paragraph(table["note"], rtl=rtl, italic=True, style=TextStyle(size=9, color=SOFT_GRAY))


def _chart(builder: WordBuilder, chart: dict, lang: str, rtl: bool) -> None:
    if chart.get("render_in_document") is False:
        return
    kind = chart.get("type", "column")
    word_kind = {"doughnut": "pie", "pie": "pie", "bar": "bar", "line": "line"}.get(kind, "column")
    colors = [c.lstrip("#") for c in chart.get("colors") or []]
    series = []
    for i, s in enumerate(chart.get("series", [])):
        entry = {"name": s.get(f"name_{lang}") or s.get("name_ar", ""), "values": s.get("data", [])}
        if word_kind != "pie" and i < len(colors):
            entry["color"] = colors[i]
        series.append(entry)
    style = _chart_style(rtl, word_kind == "pie")
    if word_kind == "pie" and colors:
        style = dataclasses.replace(style, series_colors=colors)
    builder.add_chart(
        {"title": chart.get(f"title_{lang}", ""), "categories": chart.get(f"categories_{lang}", []), "series": series},
        chart_type=word_kind, style=style, rtl=rtl,
    )


def _section(builder: WordBuilder, section: dict, depth: int, theme: Theme, lang: str, rtl: bool) -> None:
    if section.get("title"):
        builder.add_heading(section["title"], level=min(depth, 3), rtl=rtl)
    for para in (section.get("content") or "").split("\n"):
        if para.strip():
            builder.add_paragraph(para.strip(), rtl=rtl, style=TextStyle(alignment="JUSTIFY", color="000000"))
    for item in section.get("bullets") or []:
        builder.add_paragraph(f"•  {item}", rtl=rtl, style=TextStyle(alignment="JUSTIFY", color="000000"))
    for table in section.get("tables") or []:
        _table(builder, table, theme, rtl)
    for chart in section.get("charts") or []:
        _chart(builder, chart, lang, rtl)
    for note in section.get("notes") or []:
        builder.add_paragraph(f"{t('data_note', lang)}: {note}", rtl=rtl, italic=True, style=TextStyle(size=9, color=SOFT_GRAY))
    for sub in section.get("subsections") or []:
        _section(builder, sub, depth + 1, theme, lang, rtl)


def build_document(report: dict, output_path: str | Path) -> None:
    """Render one language's report data to a .docx."""
    theme = theme_of(report)
    rtl, lang = report["rtl"], report["language"]
    builder = WordBuilder(_config(report, theme))
    _cover(builder, report, theme, (report.get("branding") or {}).get("logo_path"))
    builder.add_toc(TocStyle(
        heading_text=t("toc", lang), heading_bg_color=theme.primary, heading_text_color="FFFFFF",
        heading_font=_font(rtl), entry_font=_font(rtl), rtl=rtl, exclude_cover_page=True,
    ))
    for section in report.get("sections", []):
        _section(builder, section, 1, theme, lang, rtl)
    builder.save(str(output_path))


def build_from_json(json_path: str | Path, output_path: str | Path) -> None:
    build_document(json.loads(Path(json_path).read_text(encoding="utf-8")), output_path)
