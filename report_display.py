"""LEGACY: Root-level wrapper for backward compatibility.

This module maintains backward compatibility for code that imports from the root level.
New code should import directly from analysis.legacy or analysis.shared.dynamic_display.
"""

from analysis.legacy.report_display import display_report_tabs

__all__ = ['display_report_tabs']
