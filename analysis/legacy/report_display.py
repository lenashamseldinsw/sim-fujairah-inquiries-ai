"""Display report with exact Arabic headings and Chart.js visualizations.

LEGACY MODULE: This module is maintained for backward compatibility.
New code should use analysis.dynamic_display module instead.
"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from typing import Dict, Any
from analysis.shared import DynamicReportDisplay


# Re-export the dynamic display function for backward compatibility
def display_report_tabs(lang: str = 'ar'):
    """
    Display report tabs dynamically based on detected structure.

    This function now uses the new adaptive display system while maintaining
    backward compatibility with the old API.

    Args:
        lang: Language preference ('ar' or 'en')
    """
    try:
        import os
        from pathlib import Path

        # Find outputs folder - try current dir first, then relative to script
        outputs_path = Path("outputs").resolve()
        if not outputs_path.exists():
            st.error(f"❌ outputs folder not found at {outputs_path}")
            return

        # Find all .docx files (excluding temp files starting with ~$)
        docx_files = [f for f in outputs_path.glob("*.docx") if not f.name.startswith("~$")]

        if not docx_files:
            st.error("❌ No .docx files found in outputs/")
            return

        # Try to find the report file with "تقرير" and "استفسارات"
        report_path = None
        for docx_file in docx_files:
            if 'تقرير' in docx_file.name and 'استفسارات' in docx_file.name:
                report_path = docx_file
                break

        if report_path is None:
            st.error(f"❌ Report file not found. Files: {', '.join([f.name for f in docx_files])}")
            return

        display = DynamicReportDisplay(lang=lang)
        display.display_report(str(report_path))
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
