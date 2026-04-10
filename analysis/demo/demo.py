"""Demo implementation of the analyzer with simulated data."""

import time
from typing import Dict, Any
from pathlib import Path
from analysis.shared.base import Analyzer
from analysis.demo.adaptive_extractor import AdaptiveReportExtractor


class DemoAnalyzer(Analyzer):
    """
    Demo analyzer that simulates the analysis process with pre-built report data.

    This implementation:
    - Simulates file processing with realistic stages
    - Returns a pre-built report from the outputs directory
    - Does NOT perform actual AI analysis
    - Provides a reference implementation for the Analyzer interface
    """

    # Simulated processing stages
    PROCESSING_STAGES = [
        {'stage': '1', 'label': 'جاري رفع الملفات', 'label_en': 'File Upload', 'percent_start': 0, 'percent_end': 25},
        {'stage': '2', 'label': 'تحليل البيانات', 'label_en': 'Data Analysis', 'percent_start': 25, 'percent_end': 50},
        {'stage': '3', 'label': 'معالجة الاستفسارات', 'label_en': 'Processing Inquiries', 'percent_start': 50, 'percent_end': 75},
        {'stage': '4', 'label': 'إنشاء التقرير النهائي', 'label_en': 'Report Generation', 'percent_start': 75, 'percent_end': 100},
    ]

    # Total processing time in seconds (simulated)
    TOTAL_PROCESSING_TIME = 3  # 3 seconds (for development - will be increased later)

    def validate_file(self, uploaded_file) -> tuple[bool, str]:
        """Validate file type and size."""
        if uploaded_file is None:
            return False, "No file provided"

        # Check file extension
        filename = uploaded_file.name.lower()
        supported_formats = ['.xlsx', '.xls', '.pdf']
        has_valid_extension = any(filename.endswith(fmt) for fmt in supported_formats)

        if not has_valid_extension:
            return False, "Unsupported file type. Please upload Excel (.xlsx, .xls) or PDF"

        # Check file size (200 MB limit)
        file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
        if file_size_mb > 200:
            return False, "File size exceeds 200 MB limit"

        return True, ""

    def get_processing_stages(self) -> list:
        """Return the processing stages for demo mode."""
        return self.PROCESSING_STAGES

    def analyze(self, uploaded_file) -> Dict[str, Any]:
        """
        Simulate analysis of an uploaded file.

        In demo mode, this:
        1. Validates the file
        2. Simulates processing stages with time delays
        3. Uses adaptive extraction with caching to load pre-built report

        Args:
            uploaded_file: Streamlit UploadedFile object

        Returns:
            Dictionary containing report structure with sections and tables
        """
        # Validate file
        is_valid, error_msg = self.validate_file(uploaded_file)
        if not is_valid:
            raise ValueError(error_msg)

        # Note: Progress simulation happens in process_with_analyzer() in app.py
        # We just extract and return the pre-built report here

        # Load pre-built report from outputs directory
        outputs_dir = Path("outputs").resolve()

        # Find the report file - look for any .docx with "تقرير" and "استفسارات"
        docx_files = [f for f in outputs_dir.glob("*.docx") if not f.name.startswith("~$")]

        report_path = None
        for f in docx_files:
            if 'تقرير' in f.name and 'استفسارات' in f.name:
                report_path = f
                break

        if report_path is None:
            raise FileNotFoundError(
                f"Report file not found in {outputs_dir}. "
                f"Found: {[f.name for f in docx_files]}"
            )

        # Extract and return the report using adaptive extractor (with caching)
        try:
            extractor = AdaptiveReportExtractor()
            report = extractor.extract_report(str(report_path))
            return report
        except Exception as e:
            raise RuntimeError(f"Error extracting report: {str(e)}")
