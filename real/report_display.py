"""Unified report display handler for both inquiries and complaints flows."""

import streamlit as st
import sys
import importlib.util
from pathlib import Path
from typing import Optional


def display_report_tabs(
    lang: str = 'ar',
    flow_type: str = 'inquiries',
    period: str = None
):
    """
    Display report from JSON data in session state.

    Args:
        lang: Language preference ('ar' or 'en')
        flow_type: 'inquiries' or 'complaints' - determines which output folder to use
        period: The period folder name (e.g. '2025', 'Q1_2026'). If None, uses root folder.
    """
    try:
        # Use flow-specific session state keys
        state_key = f'{flow_type}_report_data'
        report_data = st.session_state.get(state_key)

        if report_data:
            # Determine cache dir and flow path based on flow_type
            real_dir = Path(__file__).parent
            if flow_type == 'complaints':
                cache_dir = str(real_dir / "complaints-flow" / "output" / "cache")
                flow_path = real_dir / "complaints-flow" / "analysis" / "__init__.py"
            else:
                cache_dir = str(real_dir / "inquiries-flow" / "output" / "cache")
                flow_path = real_dir / "inquiries-flow" / "analysis" / "__init__.py"

            # Load the appropriate flow's analysis module
            spec = importlib.util.spec_from_file_location(f"_{flow_type}_analysis", flow_path)
            flow_analysis = importlib.util.module_from_spec(spec)
            sys.modules[f"_{flow_type}_analysis"] = flow_analysis
            spec.loader.exec_module(flow_analysis)

            # Get the DynamicReportDisplay from the flow module
            display = flow_analysis.DynamicReportDisplay(lang=lang, cache_dir=cache_dir)

            # Use English JSON if available and requested
            if lang == 'en' and report_data.get('report_json_en'):
                display.display_from_json(report_data['report_json_en'])
            else:
                display.display_from_json(report_data)

        return True

    except Exception as e:
        st.error(f"Error displaying report: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
