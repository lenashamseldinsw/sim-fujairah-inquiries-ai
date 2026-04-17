"""
Real Inquiries Analysis Module

Exports:
- RealAnalyzer: AI-based analyzer using 6-stage pipeline
- DynamicReportDisplay: Report display component
- Analyzer: Base interface
"""

from .base import Analyzer
from .real import RealAnalyzer
from .dynamic_display import DynamicReportDisplay

__all__ = [
    'Analyzer',
    'RealAnalyzer',
    'DynamicReportDisplay',
]
