"""Real analysis module with agentic AI implementation."""

from .base import Analyzer
from .dynamic_display import DynamicReportDisplay
from .real import RealAnalyzer
from .adaptive_extractor import AdaptiveReportExtractor
from .report_structure_detector import ReportStructureDetector

__all__ = [
    'Analyzer',
    'DynamicReportDisplay',
    'RealAnalyzer',
    'AdaptiveReportExtractor',
    'ReportStructureDetector'
]
