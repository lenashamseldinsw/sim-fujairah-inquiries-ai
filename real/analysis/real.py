"""Real implementation of the analyzer with agentic AI logic.

Integrates with the 6-stage pipeline for analyzing inquiries.
All required dependencies must be installed.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
from io import BytesIO

from .base import Analyzer

# Check all required dependencies at import time
_REQUIRED_PACKAGES = {
    'pandera': 'Schema validation',
    'chromadb': 'Vector embeddings/semantic search',
    'pdfplumber': 'PDF table extraction',
    'openpyxl': 'Excel file generation',
    'anthropic': 'Claude API client',
    'pydantic': 'Data validation',
}

_MISSING_PACKAGES = []
for pkg_name, pkg_purpose in _REQUIRED_PACKAGES.items():
    try:
        __import__(pkg_name)
    except ImportError:
        _MISSING_PACKAGES.append(f"{pkg_name} ({pkg_purpose})")

if _MISSING_PACKAGES:
    raise ImportError(
        f"RealAnalyzer requires the following missing packages:\n"
        + "\n".join(f"  - {pkg}" for pkg in _MISSING_PACKAGES)
        + "\n\nInstall with: pip install -r requirements.txt"
    )

# Import pipeline after verifying dependencies
try:
    from pipeline.orchestrator import PipelineOrchestrator
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pipeline.orchestrator import PipelineOrchestrator


class RealAnalyzer(Analyzer):
    """
    Real analyzer using the 6-stage agentic AI pipeline.

    Pipeline stages:
    1. Schema validation
    2. Rule-based classification
    3. LLM classification (low-confidence cases)
    4. Pattern analysis
    5. Gap analysis
    6. Artifact generation (Excel + Word)

    All required dependencies must be installed.
    """

    PROCESSING_STAGES = [
        {'stage': '1', 'label': 'التحقق من صيغة الملف', 'label_en': 'File Validation', 'percent_start': 0, 'percent_end': 10},
        {'stage': '2', 'label': 'تصنيف القواعد', 'label_en': 'Rule Classification', 'percent_start': 10, 'percent_end': 30},
        {'stage': '3', 'label': 'معالجة الذكاء الاصطناعي', 'label_en': 'AI Classification', 'percent_start': 30, 'percent_end': 50},
        {'stage': '4', 'label': 'تحليل الأنماط', 'label_en': 'Pattern Analysis', 'percent_start': 50, 'percent_end': 70},
        {'stage': '5', 'label': 'تحليل الفجوات', 'label_en': 'Gap Analysis', 'percent_start': 70, 'percent_end': 85},
        {'stage': '6', 'label': 'توليد التقرير', 'label_en': 'Report Generation', 'percent_start': 85, 'percent_end': 100},
    ]

    def __init__(self):
        """Initialize the real analyzer."""
        self.api_key = os.getenv('ANTHROPIC_API_KEY', '')
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Add it to real/.env or set it in your environment."
            )
        self.temp_dir = tempfile.mkdtemp(prefix='real_analyzer_')
        self.orchestrator = None


    def validate_file(self, uploaded_file) -> tuple[bool, str]:
        """Validate file type and size."""
        if uploaded_file is None:
            return False, "No file provided"

        filename = uploaded_file.name.lower()
        supported_formats = ['.xlsx', '.xls', '.pdf']
        has_valid_extension = any(filename.endswith(fmt) for fmt in supported_formats)

        if not has_valid_extension:
            return False, "Unsupported file type. Please upload Excel (.xlsx, .xls) or PDF"

        file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
        if file_size_mb > 200:
            return False, "File size exceeds 200 MB limit"

        return True, ""

    def get_processing_stages(self) -> list:
        """Return the processing stages for real analysis."""
        return self.PROCESSING_STAGES

    def analyze(self, uploaded_file) -> Dict[str, Any]:
        """
        Analyze an uploaded file using the 6-stage pipeline.

        Args:
            uploaded_file: Streamlit UploadedFile object

        Returns:
            Dictionary containing report structure with sections and tables
        """
        is_valid, error_msg = self.validate_file(uploaded_file)
        if not is_valid:
            raise ValueError(error_msg)

        try:
            df = self._parse_file(uploaded_file)
            return self._analyze_with_pipeline(df)
        except Exception as e:
            raise RuntimeError(f"Analysis failed: {str(e)}")

    def _parse_file(self, uploaded_file) -> pd.DataFrame:
        """Parse Excel or PDF file into DataFrame."""
        filename = uploaded_file.name.lower()

        try:
            if filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(uploaded_file)
            elif filename.endswith('.pdf'):
                df = self._parse_pdf(uploaded_file)
            else:
                raise ValueError(f"Unsupported format: {filename}")

            if df.empty:
                raise ValueError("File contains no data")

            return df
        except Exception as e:
            raise ValueError(f"Failed to parse file: {str(e)}")

    def _parse_pdf(self, uploaded_file) -> pd.DataFrame:
        """Parse PDF file into DataFrame."""
        try:
            import tabula
            pdf_bytes = BytesIO(uploaded_file.getvalue())
            tables = tabula.read_pdf(pdf_bytes, pages='all', multiple_tables=True)

            if not tables:
                raise ValueError("No tables found in PDF")

            df = pd.concat(tables, ignore_index=True)
            return df
        except ImportError:
            raise ValueError("PDF parsing requires tabula-py. Install with: pip install tabula-py")
        except Exception as e:
            raise ValueError(f"PDF parsing failed: {str(e)}")

    def _analyze_with_pipeline(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze using the full 6-stage pipeline, mapping outputs to UI sections."""
        try:
            import sys
            import streamlit as st
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))

            from pipeline.orchestrator import PipelineOrchestrator

            # Initialize report structure that maps directly to UI sections
            report = {
                "extraction_version": 1,
                "document_name": "Analysis Report - Real Pipeline",
                "document_path": f"{self.temp_dir}/analysis_report.docx",
                "metadata": {
                    "title": "Inquiry Analysis Report",
                    "author": "Real AI Pipeline",
                },
                "sections": {},
                "charts": []
            }

            session_id = Path(self.temp_dir).name
            self.orchestrator = PipelineOrchestrator(self.api_key, self.temp_dir)
            self.orchestrator.initialize_state(session_id)

            # Stage 1: Schema Validation
            success, msg = self.orchestrator.run_stage1_validator(df)
            if not success:
                raise ValueError(f"Stage 1: {msg}")
            report["sections"]["stage1_validation"] = {
                "title": "Schema Validation Results",
                "content": msg,
                "data": self.orchestrator.state.validated_schema if self.orchestrator.state else {}
            }
            self._store_report_progress(report, st)

            # Stage 2: Rule-based Classification
            success, msg = self.orchestrator.run_stage2_classifier()
            if not success:
                raise ValueError(f"Stage 2: {msg}")

            classified_count = len(self.orchestrator.state.rule_classified) if self.orchestrator.state else 0
            report["sections"]["stage2_classification"] = {
                "title": "Rule-Based Classification",
                "content": f"Classified {classified_count} cases with decision tree rules",
                "data": self.orchestrator.state.rule_classified[:10] if self.orchestrator.state else []
            }
            self._store_report_progress(report, st)

            # Stage 3: LLM Classification
            success, msg = self.orchestrator.run_stage3_llm_classifier()
            if not success:
                raise ValueError(f"Stage 3: {msg}")

            llm_classified_count = len(self.orchestrator.state.llm_classified) if self.orchestrator.state else 0
            report["sections"]["stage3_llm"] = {
                "title": "AI-Based Classification",
                "content": f"LLM classified {llm_classified_count} low-confidence cases",
                "data": self.orchestrator.state.llm_classified[:10] if self.orchestrator.state else []
            }
            self._store_report_progress(report, st)

            # Stage 4: Pattern Analysis
            success, msg = self.orchestrator.run_stage4_analysis()
            if not success:
                raise ValueError(f"Stage 4: {msg}")

            patterns = self.orchestrator.state.patterns if self.orchestrator.state else []
            faqs = self.orchestrator.state.faq_candidates if self.orchestrator.state else []

            report["sections"]["stage4_patterns"] = {
                "title": "Pattern Analysis",
                "content": f"Found {len(patterns)} inquiry patterns and {len(faqs)} FAQ candidates",
                "data": patterns[:5]
            }
            report["sections"]["stage4_faqs"] = {
                "title": "FAQ Candidates",
                "content": "Frequently asked questions extracted from inquiries",
                "data": faqs[:10]
            }
            self._store_report_progress(report, st)

            # Stage 5: Gap Analysis
            guidebook_text = self._load_guidebook()
            success, msg = self.orchestrator.run_stage5_gap_analysis(guidebook_text)
            if not success:
                raise ValueError(f"Stage 5: {msg}")

            gaps = self.orchestrator.state.gap_table if self.orchestrator.state else []
            validated_faqs = self.orchestrator.state.validated_faqs if self.orchestrator.state else []

            report["sections"]["stage5_gaps"] = {
                "title": "Service Gaps Identified",
                "content": f"Identified {len(gaps)} service gaps based on guidebook analysis",
                "data": gaps[:10]
            }
            report["sections"]["stage5_validated_faqs"] = {
                "title": "Validated FAQs",
                "content": f"Validated {len(validated_faqs)} FAQ candidates against guidelines",
                "data": validated_faqs[:10]
            }
            self._store_report_progress(report, st)

            # Stage 6: Artifact Generation
            excel_path = Path(self.temp_dir) / "analysis_results.xlsx"
            word_path = Path(self.temp_dir) / "analysis_report.docx"

            success, msg = self.orchestrator.run_stage6_artifacts(
                str(excel_path), str(word_path), language='ar'
            )
            if not success:
                raise ValueError(f"Stage 6: {msg}")

            report["sections"]["stage6_artifacts"] = {
                "title": "Generated Artifacts",
                "content": "Analysis report and detailed Excel workbook generated",
                "data": [
                    {"type": "Excel Workbook", "path": str(excel_path)},
                    {"type": "Word Report", "path": str(word_path)}
                ]
            }

            # Update metadata with final counts
            report["metadata"]["total_classified"] = len(self.orchestrator.state.all_classified) if self.orchestrator.state else 0
            report["metadata"]["patterns_found"] = len(patterns)
            report["metadata"]["faq_candidates"] = len(faqs)
            report["metadata"]["gaps_identified"] = len(gaps)

            # Store output file paths in session state for download functionality
            try:
                if 'output_files' not in st.session_state:
                    st.session_state.output_files = {}
                st.session_state.output_files['excel_path'] = str(excel_path)
                st.session_state.output_files['word_path'] = str(word_path)
            except Exception:
                pass  # Session state might not be available in all contexts

            return report

        except Exception as e:
            raise RuntimeError(f"Pipeline execution failed: {str(e)}")

    def _store_report_progress(self, report: Dict[str, Any], st) -> None:
        """Store intermediate report progress in session state for real-time display."""
        try:
            st.session_state.report_data = report
        except Exception:
            pass  # Session state might not be available in all contexts


    def _load_guidebook(self) -> str:
        """Load guidebook text for gap analysis."""
        try:
            guidebook_path = Path(__file__).parent.parent / '.guidebook_cache' / 'guidebook.txt'
            if guidebook_path.exists():
                return guidebook_path.read_text(encoding='utf-8')
        except:
            pass
        return ""

