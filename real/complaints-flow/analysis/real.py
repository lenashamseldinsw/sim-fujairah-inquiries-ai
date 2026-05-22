"""
RealAnalyzer - AI-based complaints analysis using the 6-stage pipeline.

Implements the Analyzer interface and integrates with the pipeline orchestrator.
"""

import pandas as pd
import streamlit as st
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple, List
import os
from datetime import datetime
import anthropic
from .base import Analyzer

# Import pipeline (located in parent complaints-flow folder)
# Use importlib with unique module name to prevent cache collision with inquiries flow
import sys
import importlib.util
sys.path.insert(0, str(Path(__file__).parent.parent))
spec = importlib.util.spec_from_file_location(
    "complaints_pipeline_orchestrator",
    str(Path(__file__).parent.parent / "pipeline" / "orchestrator.py")
)
complaints_orch_module = importlib.util.module_from_spec(spec)
sys.modules["complaints_pipeline_orchestrator"] = complaints_orch_module
spec.loader.exec_module(complaints_orch_module)
PipelineOrchestrator = complaints_orch_module.PipelineOrchestrator

class RealAnalyzer:
    def __init__(self, api_key=None):
        # Try to get API key from parameter, then st.secrets, then environment
        if api_key is None:
            try:
                api_key = st.secrets.get("ANTHROPIC_API_KEY")
            except:
                api_key = None

        if api_key is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in secrets or environment")
        self.api_key = api_key
        self.client = anthropic.Anthropic(api_key=api_key)

        # Create temp directory for outputs
        self.output_dir = Path(tempfile.gettempdir()) / "complaints_output"
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

    def analyze(self, uploaded_file, progress_callback=None) -> Dict[str, Any]:
        """
        Analyze uploaded file using the 6-stage pipeline.

        Args:
            uploaded_file: Streamlit UploadedFile object
            progress_callback: Optional function(progress_pct, message_ar, message_en) for UI updates

        Returns:
            Dict with analysis results and file paths
        """
        try:
            # Notify start
            if progress_callback:
                progress_callback(0.05, "جاري تحليل الملف...", f"Parsing file: {uploaded_file.name}")

            # Read Excel file
            if uploaded_file.type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                       'application/vnd.ms-excel']:
                # Try to read with various headers and find one with required columns
                required_cols = ['رقم الطلب', 'تفاصيل الطلب', 'الحل', 'الخدمة']
                df = None

                for header_row in [None, 0, 1, 2, 3, 4]:  # Try multiple header rows
                    try:
                        test_df = pd.read_excel(uploaded_file, header=header_row)

                        # Check if this has the required columns
                        if all(col in test_df.columns for col in required_cols):
                            df = test_df
                            print(f"[RealAnalyzer] Successfully read Excel with header={header_row}")
                            break
                    except Exception as e:
                        print(f"[RealAnalyzer] Failed to read with header={header_row}: {e}")
                        continue

                if df is None or len(df) == 0:
                    raise ValueError("Could not read Excel file with required columns: رقم الطلب, تفاصيل الطلب, الحل, الخدمة")
            else:
                raise ValueError("PDF processing not yet implemented")

            # Use a unique session ID per run so stale state from a previous (possibly
            # failed) run is never loaded.  A fixed filename-based ID would cause
            # initialize_state() to reload the old state.json — including an empty
            # journey_map from a prior Stage 4 failure — and then carry it into Stage 6.
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base = uploaded_file.name.replace('.', '_').replace(' ', '_')
            session_id = f"{base}_{timestamp}"

            # Initialize orchestrator
            orchestrator = PipelineOrchestrator(self.api_key, temp_dir=str(self.output_dir))
            orchestrator.initialize_state(session_id)

            # Run full pipeline
            excel_path = str(self.output_dir / f"{session_id}_complaints.xlsx")
            word_path = str(self.output_dir / f"{session_id}_complaints.docx")
            # English Word is saved alongside Arabic with _en suffix by generate_word_report
            word_path_en = str(Path(word_path).with_stem(Path(word_path).stem + "_en"))

            results = orchestrator.run_full_pipeline(
                df=df,
                excel_path=excel_path,
                word_path=word_path,
                language='ar',
                progress_callback=progress_callback
            )

            if not results['success']:
                raise ValueError(f"Pipeline failed: {results['errors']}")

            # Mark as complete
            if progress_callback:
                progress_callback(1.0, "✅ اكتمل التحليل", "✅ Analysis Complete")

            # Return result with file paths and report JSON for display
            report_json    = orchestrator.state.report_json    if orchestrator.state else {}
            report_json_en = orchestrator.state.report_json_en if orchestrator.state else {}

            # Build response - merge report structure with metadata
            response = {
                'success': True,
                'message': 'Analysis completed successfully',
                'excel_path': excel_path,
                'word_path': word_path,
                'word_path_en': word_path_en,
                'summary': orchestrator.get_state_summary(),
                'results': results,
            }
            # Merge Arabic report structure (sections, metadata, charts, etc.) at top level
            if report_json:
                response.update(report_json)
            # Store English report separately so display_report_tabs() can use it when lang='en'
            if report_json_en:
                response['report_json_en'] = report_json_en

            return response

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
