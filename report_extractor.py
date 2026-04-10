"""LEGACY: Root-level wrapper for backward compatibility.

This module maintains backward compatibility for code that imports from the root level.
New code should import directly from analysis.legacy or analysis.real.adaptive_extractor.
"""

from analysis.legacy.report_extractor import extract_full_report

__all__ = ['extract_full_report']
