"""
DynamicReportDisplay - Display Word report dynamically.

For real flow, this is a stub that can be extended for report display.
"""

import streamlit as st
from pathlib import Path
from typing import Optional


class DynamicReportDisplay:
    """Display Word report content dynamically."""

    def __init__(self, lang: str = 'ar', cache_dir: Optional[str] = None):
        """
        Initialize display.

        Args:
            lang: Language ('ar' or 'en')
            cache_dir: Optional cache directory for extracted report structure
        """
        self.lang = lang
        self.cache_dir = cache_dir

    def display_report(self, report_path: str) -> None:
        """
        Display Word report.

        Args:
            report_path: Path to .docx file
        """
        path = Path(report_path)

        if not path.exists():
            st.error(f"Report file not found: {report_path}")
            return

        # For now, display basic file info
        st.info(f"📄 Report generated: {path.name}")

        # TODO: Extract and display report sections dynamically
        # This would require reading the .docx file and displaying its structure

        # Provide download link
        with open(report_path, "rb") as f:
            st.download_button(
                label="📥 Download Report",
                data=f,
                file_name=path.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
