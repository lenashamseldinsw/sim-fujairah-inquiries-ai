"""
Real Analysis Module - Unified entry point for both flows.

This module conditionally imports analyzers based on the flow type.
The actual implementations live in:
- /real/inquiries-flow/analysis/ (RealAnalyzer for inquiries)
- /real/complaints-flow/analysis/ (RealAnalyzer for complaints - TODO)

App.py imports from here and uses conditional logic to select the flow.
"""

import os
import sys
import importlib.util
from pathlib import Path

# Get current flow from context (for unified app_inq_comp.py support)
# Usage: call set_flow_context('inquiries' or 'complaints') before creating analyzers
_FLOW_CONTEXT = os.getenv('FLOW_TYPE', '').lower()

def set_flow_context(flow_type: str):
    """Set the flow context for analyzer selection."""
    global _FLOW_CONTEXT
    _FLOW_CONTEXT = flow_type.lower()

def _load_analyzer_for_flow(flow_type: str):
    """Load analyzer from the appropriate flow folder."""
    flow_type = flow_type.lower()

    if flow_type == 'complaints':
        flow_path = Path(__file__).parent.parent / "complaints-flow" / "analysis" / "__init__.py"
    else:
        flow_path = Path(__file__).parent.parent / "inquiries-flow" / "analysis" / "__init__.py"

    spec = importlib.util.spec_from_file_location(f"_{flow_type}_analysis", flow_path)
    flow_analysis = importlib.util.module_from_spec(spec)
    sys.modules[f"_{flow_type}_analysis"] = flow_analysis
    spec.loader.exec_module(flow_analysis)

    return flow_analysis

# Load default flow (inquiries) for backward compatibility
_default_flow = _load_analyzer_for_flow('inquiries')
RealAnalyzer = _default_flow.RealAnalyzer
DynamicReportDisplay = _default_flow.DynamicReportDisplay
Analyzer = _default_flow.Analyzer

# For unified app: export factory functions
def get_analyzer_for_flow(flow_type: str):
    """Get analyzer instance for a specific flow."""
    flow_analysis = _load_analyzer_for_flow(flow_type)
    return flow_analysis.RealAnalyzer()

def get_display_for_flow(flow_type: str, lang: str = 'ar', cache_dir: str = None):
    """Get display instance for a specific flow."""
    flow_analysis = _load_analyzer_for_flow(flow_type)
    return flow_analysis.DynamicReportDisplay(lang=lang, cache_dir=cache_dir)

__all__ = [
    'RealAnalyzer',
    'DynamicReportDisplay',
    'Analyzer',
]
