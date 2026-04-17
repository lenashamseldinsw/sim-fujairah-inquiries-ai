"""
sword-word-builder
==================
A general-purpose Python library for building Word (.docx) documents with
native charts, tables, RTL/LTR text support, and full styling customization.

Quickstart::

    from sword_word_builder import WordBuilder, DocumentConfig

    builder = WordBuilder(DocumentConfig(default_font="Calibri"))
    builder.add_heading("My Report", level=1)
    builder.add_paragraph("Some introductory text.")
    builder.add_table([{"Name": "Alice", "Score": 95}])
    builder.add_chart(
        {"title": "Revenue", "categories": ["Q1","Q2"], "series": [{"name":"Rev","values":[100,150]}]},
        chart_type="column",
    )
    builder.save("report.docx")
"""

from .builder import WordBuilder
from .config import DocumentConfig, TextStyle, TableStyle, ChartStyle, CellStyle, CellLine, TocStyle
from ._cover_page import CoverPage

__version__ = "0.1.0"

__all__ = [
    "WordBuilder",
    "DocumentConfig",
    "TextStyle",
    "TableStyle",
    "ChartStyle",
    "CellStyle",
    "CellLine",
    "TocStyle",
    "CoverPage",
]
