"""
RealAnalyzer - AI-based inquiries analysis using the 6-stage pipeline.

Implements the Analyzer interface and integrates with the pipeline orchestrator.
"""

import pandas as pd
import streamlit as st
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple, List
import os

from .base import Analyzer

# Import pipeline (located in parent inquiries-flow folder)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.orchestrator import PipelineOrchestrator


class RealAnalyzer(Analyzer):
    """Real analyzer using 6-stage pipeline."""

    def __init__(self):
        """Initialize analyzer with API key from Streamlit secrets."""
        self.api_key = st.secrets.get("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in secrets or environment")

        # Create temp directory for outputs
        self.output_dir = Path(tempfile.gettempdir()) / "inquiries_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def validate_file(self, uploaded_file) -> Tuple[bool, str]:
        """
        Validate uploaded file.

        Args:
            uploaded_file: Streamlit UploadedFile object

        Returns:
            (is_valid, error_message)
        """
        # Check file type
        if uploaded_file.type not in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                       'application/vnd.ms-excel',
                                       'application/pdf']:
            return False, "Only Excel (.xlsx, .xls) and PDF files are supported"

        # Check file size (max 200 MB)
        max_size = 200 * 1024 * 1024
        if uploaded_file.size > max_size:
            return False, f"File size exceeds {max_size / 1024 / 1024:.0f} MB limit"

        return True, ""

    def analyze(self, uploaded_file) -> Dict[str, Any]:
        """
        Analyze uploaded file using the 6-stage pipeline.

        Args:
            uploaded_file: Streamlit UploadedFile object

        Returns:
            Dict with analysis results and file paths
        """
        try:
            # Read Excel file
            if uploaded_file.type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                       'application/vnd.ms-excel']:
                # Try to read with various headers
                for header_row in [None, 0, 4]:  # Try no header, row 0, row 4
                    try:
                        df = pd.read_excel(uploaded_file, header=header_row)
                        if len(df) > 0:
                            break
                    except Exception:
                        continue
            else:
                raise ValueError("PDF processing not yet implemented")

            if len(df) == 0:
                raise ValueError("No data found in file")

            # Create session ID for state tracking
            session_id = uploaded_file.name.replace('.', '_').replace(' ', '_')

            # Initialize orchestrator
            orchestrator = PipelineOrchestrator(self.api_key, temp_dir=str(self.output_dir))
            orchestrator.initialize_state(session_id)

            # Run full pipeline
            excel_path = str(self.output_dir / f"{session_id}_inquiries.xlsx")
            word_path = str(self.output_dir / f"{session_id}_inquiries.docx")

            # Load guidebook if available
            guidebook_text = self._load_guidebook()

            results = orchestrator.run_full_pipeline(
                df=df,
                excel_path=excel_path,
                word_path=word_path,
                guidebook_text=guidebook_text,
                language='ar'
            )

            if not results['success']:
                raise ValueError(f"Pipeline failed: {results['errors']}")

            # Return result with file paths
            return {
                'success': True,
                'message': 'Analysis completed successfully',
                'excel_path': excel_path,
                'word_path': word_path,
                'summary': orchestrator.get_state_summary(),
                'results': results
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Analysis failed: {str(e)}',
                'error': str(e)
            }

    def _load_guidebook(self) -> str:
        """Load guidebook PDF text."""
        # TODO: Implement PDF loading and chunking
        # For now, return empty string
        return ""

    def get_processing_stages(self) -> List[Dict[str, Any]]:
        """
        Return processing stages for progress display.

        Returns:
            List of stage dicts
        """
        return [
            {
                'label': 'تحقق من الملف',
                'label_ar': 'تحقق من الملف',
                'label_en': 'Validating file',
                'percent_start': 0,
                'percent_end': 10,
            },
            {
                'label': 'تصنيف الحالات',
                'label_ar': 'تصنيف الحالات',
                'label_en': 'Classifying cases',
                'percent_start': 10,
                'percent_end': 35,
            },
            {
                'label': 'تحليل الأنماط',
                'label_ar': 'تحليل الأنماط',
                'label_en': 'Analyzing patterns',
                'percent_start': 35,
                'percent_end': 65,
            },
            {
                'label': 'إنشاء التقارير',
                'label_ar': 'إنشاء التقارير',
                'label_en': 'Generating reports',
                'percent_start': 65,
                'percent_end': 100,
            },
        ]
