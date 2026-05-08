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

# Get current app mode from environment
APP_MODE = os.getenv('APP_MODE', 'inquiries').lower()

# Import from the appropriate flow folder
if APP_MODE == 'inquiries' or True:  # Default to inquiries for now
    # Load inquiries-flow analysis module
    _inquiries_path = Path(__file__).parent.parent / "inquiries-flow" / "analysis" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_inquiries_analysis", _inquiries_path)
    _inquiries_analysis = importlib.util.module_from_spec(spec)
    sys.modules["_inquiries_analysis"] = _inquiries_analysis
    spec.loader.exec_module(_inquiries_analysis)

    RealAnalyzer = _inquiries_analysis.RealAnalyzer
    DynamicReportDisplay = _inquiries_analysis.DynamicReportDisplay
    Analyzer = _inquiries_analysis.Analyzer

__all__ = [
    'RealAnalyzer',
    'DynamicReportDisplay',
    'Analyzer',
]
