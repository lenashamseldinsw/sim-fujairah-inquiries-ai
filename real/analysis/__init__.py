"""
Real Analysis Module - Unified entry point for both flows.

This module conditionally imports analyzers based on the flow type.
The actual implementations live in:
- /real/inquiries-flow/analysis/ (RealAnalyzer for inquiries)
- /real/complaints-flow/analysis/ (RealAnalyzer for complaints - TODO)

App.py imports from here and uses conditional logic to select the flow.
"""

import os
from pathlib import Path

# Get current app mode from environment
APP_MODE = os.getenv('APP_MODE', 'inquiries').lower()

# Import from the appropriate flow folder
if APP_MODE == 'inquiries' or True:  # Default to inquiries for now
    # Add inquiries flow to path
    _inquiries_path = Path(__file__).parent.parent / "inquiries-flow"
    import sys
    if str(_inquiries_path) not in sys.path:
        sys.path.insert(0, str(_inquiries_path))

    from analysis import (
        RealAnalyzer,
        DynamicReportDisplay,
        Analyzer
    )

__all__ = [
    'RealAnalyzer',
    'DynamicReportDisplay',
    'Analyzer',
]
