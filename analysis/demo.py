"""Demo implementation of the analyzer with simulated data."""

import time
from typing import Dict, Any
from pathlib import Path
from analysis.base import Analyzer
from report_extractor import extract_full_report


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
    TOTAL_PROCESSING_TIME = 120  # 2 minutes

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
        3. Loads and returns a pre-built report from outputs directory

        Args:
            uploaded_file: Streamlit UploadedFile object

        Returns:
            Dictionary containing report structure with sections and tables
        """
        # Validate file
        is_valid, error_msg = self.validate_file(uploaded_file)
        if not is_valid:
            raise ValueError(error_msg)

        # Simulate processing with realistic timing
        stages = self.PROCESSING_STAGES
        time_per_stage = self.TOTAL_PROCESSING_TIME / len(stages)

        for stage in stages:
            time.sleep(time_per_stage)
            # In real implementation, update progress bar here
            # For now, just simulate the processing time

        # Load pre-built report from outputs directory
        report_path = Path("outputs/تقرير تحليل استفسارات المتعاملين.docx")

        if not report_path.exists():
            raise FileNotFoundError(
                f"Demo report not found at {report_path}. "
                "Please ensure the pre-built report exists in the outputs directory."
            )

        # Extract and return the report
        try:
            report = extract_full_report(str(report_path))
            return report
        except Exception as e:
            raise RuntimeError(f"Error extracting report: {str(e)}")
