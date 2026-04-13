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
def display_report_tabs(lang: str = 'ar', flow_type: str = 'inquiries'):
    """
    Display report tabs dynamically based on detected structure.

    This function now uses the new adaptive display system while maintaining
    backward compatibility with the old API.

    Args:
        lang: Language preference ('ar' or 'en')
        flow_type: 'inquiries' or 'complaints' - determines which output folder to use
    """
    try:
        import os
        from pathlib import Path

        # Determine output folder and search keywords based on flow type
        if flow_type == 'complaints':
            outputs_path = Path("complaints-output").resolve()
            search_keywords = ['تقرير', 'شكاوى']  # Report + Complaints
        else:  # default to inquiries
            outputs_path = Path("inquiries-output").resolve()
            search_keywords = ['تقرير', 'استفسارات']  # Report + Inquiries

        if not outputs_path.exists():
            st.error(f"❌ {outputs_path.name} folder not found at {outputs_path}")
            return

        # Find all .docx files (excluding temp files starting with ~$)
        docx_files = [f for f in outputs_path.glob("*.docx") if not f.name.startswith("~$")]

        if not docx_files:
            st.error(f"❌ No .docx files found in {outputs_path.name}/")
            return

        # Try to find the report file with the appropriate keywords
        report_path = None
        for docx_file in docx_files:
            if all(keyword in docx_file.name for keyword in search_keywords):
                report_path = docx_file
                break

        if report_path is None:
            st.error(f"❌ Report file not found. Files: {', '.join([f.name for f in docx_files])}")
            return

        # Set cache directory based on flow type
        if flow_type == 'complaints':
            cache_dir = "complaints-output/cache"
        else:
            cache_dir = "inquiries-output/cache"

        display = DynamicReportDisplay(lang=lang, cache_dir=cache_dir)
        display.display_report(str(report_path))
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
