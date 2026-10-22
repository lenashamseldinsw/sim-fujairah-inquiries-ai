"""
NoveIntelligence document ingestion — Excel workbooks into a pgvector store.

Self-contained: usable on its own, and by the analytics services through what it
exports (``faq_catalogue`` writes the inquiries service's reference list). It
imports nothing from either service.
"""
from .excel import Workbook, read_workbook
from .faq import faq_catalogue
from .ingest import IngestReport, ingest_workbook, search
from .serialize import Chunk, chunk_workbook

__all__ = [
    "Chunk",
    "IngestReport",
    "Workbook",
    "chunk_workbook",
    "faq_catalogue",
    "ingest_workbook",
    "read_workbook",
    "search",
]
