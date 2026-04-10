"""
Configuration and style dataclasses for sword-word-builder.

All public — users import these alongside WordBuilder to customize documents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a 6-char hex color string (with or without '#') to an (R, G, B) tuple."""
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Expected a 6-character hex color, got: {hex_color!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------------------------------------------------------------------
# Page size constants  (width, height) in EMU (English Metric Units)
# 1 inch = 914400 EMU
# ---------------------------------------------------------------------------
_CM_TO_EMU = 360000  # 1 cm = 360000 EMU

PAGE_SIZES: dict[str, tuple[int, int]] = {
    "A4":     (21 * _CM_TO_EMU, 29.7 * _CM_TO_EMU),   # 21 × 29.7 cm portrait
    "Letter": (21.59 * _CM_TO_EMU, 27.94 * _CM_TO_EMU),
    "A3":     (29.7 * _CM_TO_EMU, 42 * _CM_TO_EMU),
}


# ---------------------------------------------------------------------------
# CellStyle — per-cell style override for individual table cells
# ---------------------------------------------------------------------------

@dataclass
class CellStyle:
    """Per-cell style override for use inside table data.

    Wrap any cell value with a ``CellStyle`` to override the table-level
    ``TableStyle`` defaults for that specific cell::

        {"التقييم": ("مطابق ✔", CellStyle(bg_color="1E7B4E", text_color="FFFFFF", bold=True))}

    Only non-``None`` fields are applied; everything else falls back to the
    enclosing ``TableStyle``.
    """

    bg_color: str | None = None       # 6-char hex; overrides row/header bg
    text_color: str | None = None     # 6-char hex; overrides cell_text_color
    bold: bool | None = None          # overrides cell bold
    font_size: int | None = None      # pt; overrides font_size


# ---------------------------------------------------------------------------
# CellLine — one styled paragraph inside a multi-paragraph table cell
# ---------------------------------------------------------------------------

@dataclass
class CellLine:
    """One paragraph (line) inside a multi-paragraph table cell.

    Wrap a list of ``CellLine`` objects as a cell value to produce multiple
    ``<w:p>`` elements inside a single ``<w:tc>``::

        [CellLine("59", font_size=20, bold=True, color="FFFFFF"),
         CellLine("إجمالي المعاملات", font_size=9, color="CCCCCC")]

    Only non-``None`` fields override the enclosing ``TableStyle`` defaults.
    """
    text: str
    font_size: int | None = None
    color: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] | None = None
    rtl: bool | None = None


# ---------------------------------------------------------------------------
# DocumentConfig
# ---------------------------------------------------------------------------

@dataclass
class DocumentConfig:
    """Document-level settings.  Pass to WordBuilder() to customize globally."""

    # Page geometry
    page_size: Literal["A4", "Letter", "A3"] = "A4"
    margin_top: float = 2.54      # cm
    margin_bottom: float = 2.54   # cm
    margin_left: float = 3.17     # cm
    margin_right: float = 3.17    # cm

    # Typography
    default_font: str = "Calibri"
    default_font_size: int = 11   # pt
    default_rtl: bool = False

    # Colors (6-char hex without '#' or with '#', both accepted)
    accent_color: str = "2E74B5"    # headings, table headers
    body_color: str = "000000"      # body text
    heading_color: str = "2E74B5"   # cover page / title color
    secondary_color: str = "003366" # heading 2 / subtitle

    # Heading typography
    heading_font: str | None = None  # None = inherit default_font
    heading_bold: bool = True
    heading1_size: int = 22    # pt
    heading2_size: int = 16
    heading3_size: int = 13

    # Heading separators  (bottom border drawn beneath the heading)
    heading1_separator: bool = True   # level-1 headings get a separator by default
    heading2_separator: bool = False
    heading3_separator: bool = False

    # Paragraph defaults
    default_paragraph_space_after: float = 6.0   # pt
    line_spacing: float | None = None             # None = single; float = exact pt

    # RTL / Arabic
    apply_arabic_reshaping: bool = False          # opt-in — most fonts don't need it
    arabic_auto_bold_phrases: list[str] = field(default_factory=lambda: [
        "الإطار الزمني:",
        "التأثير المتوقع:",
        "الموارد المطلوبة:",
        "الأولوية:",
        "النتيجة المتوقعة:",
    ])

    # Header (applies from page 2 when skip_first_page_header_footer=True)
    header_type: Literal["none", "page_number", "text", "image", "text_and_page_number"] = "none"
    header_text: str = ""
    header_image_path: str | None = None
    header_image_height_cm: float = 1.5
    header_alignment: Literal["LEFT", "CENTER", "RIGHT"] = "CENTER"

    # Footer
    footer_type: Literal["none", "page_number", "text", "image", "text_and_page_number"] = "page_number"
    footer_text: str = ""
    footer_image_path: str | None = None
    footer_image_height_cm: float = 1.0
    footer_alignment: Literal["LEFT", "CENTER", "RIGHT"] = "CENTER"

    # Skip cover/first page header & footer
    skip_first_page_header_footer: bool = True

    # Header styling overrides
    header_text_color: str | None = None        # None = body_color
    header_font_size: int | None = None         # None = default_font_size
    header_bottom_border_color: str | None = None  # None = no border
    header_spacing_after: float = 0.0           # pt

    # Footer styling overrides
    footer_text_color: str | None = None        # None = body_color
    footer_font_size: int | None = None         # None = default_font_size
    footer_top_border_color: str | None = None  # None = no border
    footer_spacing_before: float = 0.0          # pt


# ---------------------------------------------------------------------------
# TextStyle
# ---------------------------------------------------------------------------

@dataclass
class TextStyle:
    """Per-element text style override.

    None values mean "inherit from DocumentConfig / document default".
    """

    font: str | None = None            # None = inherit DocumentConfig.default_font
    size: int | None = None            # pt; None = inherit
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None           # 6-char hex (with or without '#'); None = inherit
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] = "LEFT"
    rtl: bool | None = None            # None = inherit DocumentConfig.default_rtl
    space_before: float | None = None  # pt; None = inherit
    space_after: float | None = None   # pt; None = inherit
    keep_with_next: bool = False


# ---------------------------------------------------------------------------
# TableStyle
# ---------------------------------------------------------------------------

@dataclass
class TableStyle:
    """Styling for a table created via WordBuilder.add_table()."""

    # Header row
    header_bg_color: str = "2E74B5"
    header_text_color: str = "FFFFFF"
    header_bold: bool = True
    header_font_size: int | None = None   # None = inherit document default

    # Per-column header background overrides.  If set, must have one entry per
    # column; header_bg_colors[i] takes precedence over header_bg_color for
    # column i.  Useful for KPI tile rows where each cell has a distinct colour.
    header_bg_colors: list[str] | None = None

    # Data rows
    row_bg_color: str = "FFFFFF"
    alt_row_bg_color: str | None = "D6E4F7"   # None disables alternating fills
    cell_text_color: str = "000000"

    # Borders
    border_color: str = "BFBFBF"
    border_width_pt: float = 0.5
    show_inner_borders: bool = True
    show_outer_border: bool = True

    # Cell padding (pt)
    cell_padding_top: float = 3.0
    cell_padding_bottom: float = 3.0
    cell_padding_left: float = 5.4
    cell_padding_right: float = 5.4

    # Column widths: None = auto-distribute equally.
    # Otherwise a list of fractions (must sum to ≤ 1.0).
    # Example: [0.2, 0.5, 0.3] for a 3-column table.
    column_widths: list[float] | None = None

    # Text defaults for cells
    font_size: int | None = None       # None = inherit
    text_alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] = "LEFT"
    auto_align_numbers: bool = True    # right-align int/float values automatically
    rtl: bool | None = None            # None = inherit DocumentConfig.default_rtl

    # Table horizontal alignment inside the page
    table_alignment: Literal["LEFT", "CENTER", "RIGHT"] = "LEFT"

    # metrics-table specific
    # When table_type="metrics", controls whether the label column is bolded.
    # Defaults to False so labels match the body text weight of real reports.
    metrics_label_bold: bool = False


# ---------------------------------------------------------------------------
# ChartStyle
# ---------------------------------------------------------------------------

@dataclass
class ChartStyle:
    """Styling for a native Word chart created via WordBuilder.add_chart()."""

    width_cm: float = 14.0
    height_cm: float = 9.0
    show_legend: bool = True
    legend_position: Literal["r", "l", "t", "b"] = "r"
    show_data_labels: bool = False
    show_gridlines: bool = True

    # Series fill colors (hex without '#').  Cycles if fewer than series count.
    series_colors: list[str] = field(default_factory=lambda: [
        "4472C4", "ED7D31", "A9D18E", "FFC000", "FF0000", "00B0F0",
    ])

    x_axis_title: str | None = None
    y_axis_title: str | None = None
    background_color: str = "FFFFFF"
    font: str | None = None              # None = inherit document default font
    title_font_size: int | None = None   # pt; chart title text
    axis_font_size: int | None = None    # pt; axis tick/category labels
    legend_font_size: int | None = None  # pt; legend entry labels
