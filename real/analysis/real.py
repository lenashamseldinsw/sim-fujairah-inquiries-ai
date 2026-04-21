"""Real implementation of the analyzer with agentic AI logic.

Integrates with the 6-stage pipeline for analyzing inquiries.
All required dependencies must be installed.
"""

import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
from io import BytesIO

from .base import Analyzer
from pipeline.guidebook import GuidebookSearchIndex

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
        try:
            import streamlit as st
            self.api_key = st.secrets.get('ANTHROPIC_API_KEY', '')
        except (ImportError, AttributeError, KeyError):
            # Fallback to environment variable if not in Streamlit context
            self.api_key = os.getenv('ANTHROPIC_API_KEY', '')

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. "
                "Add it to ~/.streamlit/secrets.toml (local) or "
                "configure it in your deployment platform's secrets."
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
            print(f"[RealAnalyzer] Parsing file: {uploaded_file.name}")
            df = self._parse_file(uploaded_file)
            print(f"[RealAnalyzer] Parsed {len(df)} rows")

            print(f"[RealAnalyzer] Starting pipeline analysis...")
            result = self._analyze_with_pipeline(df)
            print(f"[RealAnalyzer] Pipeline complete, returning report")
            return result
        except Exception as e:
            import traceback
            error_msg = f"Analysis failed: {str(e)}\n{traceback.format_exc()}"
            print(f"[RealAnalyzer] ERROR: {error_msg}")
            raise RuntimeError(error_msg)

    def _parse_file(self, uploaded_file) -> pd.DataFrame:
        """Parse Excel or PDF file into DataFrame."""
        filename = uploaded_file.name.lower()

        try:
            if filename.endswith(('.xlsx', '.xls')):
                # Convert uploaded file bytes to BytesIO for pandas
                file_bytes = BytesIO(uploaded_file.getvalue())

                # Read entire file with no headers to find the header row
                print(f"[Parser] Reading entire file to detect header row...")
                df_raw = pd.read_excel(file_bytes, header=None)
                print(f"[Parser] Raw file has {len(df_raw)} rows")

                # Find the row with the most non-NaN values (likely headers)
                header_row_idx = 0
                max_non_null = 0
                for idx, row in df_raw.iterrows():
                    non_null = row.dropna()
                    if len(non_null) > max_non_null:
                        max_non_null = len(non_null)
                        header_row_idx = idx
                        print(f"[Parser] Row {idx} has {len(non_null)} non-null values")

                print(f"[Parser] Best header row is {header_row_idx} with {max_non_null} values")
                print(f"[Parser] Headers: {list(df_raw.iloc[header_row_idx].values)}")

                if header_row_idx is None:
                    raise ValueError("Could not find header row in file")

                # Read with the detected header row
                file_bytes.seek(0)
                df = pd.read_excel(file_bytes, header=header_row_idx)
                print(f"[Parser] Using row {header_row_idx} as headers")

                # Remove any rows before the header row
                if header_row_idx > 0:
                    df = df.iloc[header_row_idx:].reset_index(drop=True)

            elif filename.endswith('.pdf'):
                df = self._parse_pdf(uploaded_file)
            else:
                raise ValueError(f"Unsupported format: {filename}")

            if df.empty:
                raise ValueError("File contains no data")

            print(f"[Parser] File columns: {list(df.columns)}")
            print(f"[Parser] Detected {len(df)} data rows")
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
        """
        Analyze using 6-stage pipeline with parallel artifact generation.

        Returns immediately after stage 5 with analysis results.
        Stage 6 (artifact generation) runs in background thread.
        """
        try:
            import sys
            import streamlit as st
            from pathlib import Path
            # Add both real folder and root folder to path for imports
            real_dir = Path(__file__).parent.parent
            root_dir = real_dir.parent
            sys.path.insert(0, str(real_dir))
            sys.path.insert(0, str(root_dir))

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
                "charts": [],
                "artifacts_status": {
                    "excel_ready": False,
                    "word_ready": False,
                    "excel_path": None,
                    "word_path": None,
                    "error": None
                }
            }

            session_id = Path(self.temp_dir).name
            print(f"[Pipeline] Session ID: {session_id}")
            self.orchestrator = PipelineOrchestrator(self.api_key, self.temp_dir)
            self.orchestrator.initialize_state(session_id)
            print(f"[Pipeline] Orchestrator initialized")

            # Stage 1: Schema Validation
            print(f"[Pipeline] Running Stage 1: Schema Validation")
            success, msg, schema_data = self.orchestrator.run_stage1_validator(df)
            if not success:
                raise ValueError(f"Stage 1: {msg}")
            report["sections"]["stage1_validation"] = {
                "title": "Schema Validation Results",
                "content": msg,
                "data": schema_data or {}
            }

            # Stage 2: Rule-based Classification
            print(f"[Pipeline] Running Stage 2: Rule-based Classification")
            success, msg = self.orchestrator.run_stage2_classifier()
            if not success:
                raise ValueError(f"Stage 2: {msg}")
            print(f"[Pipeline] Stage 2 complete: {msg}")

            classified_count = len(self.orchestrator.state.rule_classified) if self.orchestrator.state else 0
            report["sections"]["stage2_classification"] = {
                "title": "Rule-Based Classification",
                "content": f"Classified {classified_count} cases with decision tree rules",
                "data": self.orchestrator.state.rule_classified[:10] if self.orchestrator.state else []
            }

            # Stage 3: LLM Classification
            print(f"[Pipeline] Running Stage 3: LLM Classification")
            success, msg = self.orchestrator.run_stage3_llm_classifier()
            if not success:
                raise ValueError(f"Stage 3: {msg}")
            print(f"[Pipeline] Stage 3 complete: {msg}")

            llm_classified_count = len(self.orchestrator.state.llm_classified) if self.orchestrator.state else 0
            report["sections"]["stage3_llm"] = {
                "title": "AI-Based Classification",
                "content": f"LLM classified {llm_classified_count} low-confidence cases",
                "data": self.orchestrator.state.llm_classified[:10] if self.orchestrator.state else []
            }

            # Stage 4: Pattern Analysis
            print(f"[Pipeline] Running Stage 4: Pattern Analysis")
            success, msg = self.orchestrator.run_stage4_analysis()
            if not success:
                raise ValueError(f"Stage 4: {msg}")
            print(f"[Pipeline] Stage 4 complete: {msg}")

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

            # Stage 5: Gap Analysis
            print(f"[Pipeline] Running Stage 5: Gap Analysis")
            search_index = self._load_guidebook_search()
            success, msg = self.orchestrator.run_stage5_gap_analysis(search_index)
            if not success:
                raise ValueError(f"Stage 5: {msg}")
            print(f"[Pipeline] Stage 5 complete: {msg}")

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

            # Update metadata with analysis results (before artifacts are ready)
            report["metadata"]["total_classified"] = len(self.orchestrator.state.all_classified) if self.orchestrator.state else 0
            report["metadata"]["patterns_found"] = len(patterns)
            report["metadata"]["faq_candidates"] = len(faqs)
            report["metadata"]["gaps_identified"] = len(gaps)

            # ============================================================================
            # Stage 6: Queue artifact generation in background thread
            # This allows UI to display results immediately while artifacts are generated
            # ============================================================================
            print(f"[Pipeline] Stage 6: Queuing artifact generation in background")
            excel_path = Path(self.temp_dir) / "analysis_results.xlsx"
            word_path = Path(self.temp_dir) / "analysis_report.docx"

            # Update report with artifact paths (will be marked ready when generation completes)
            report["artifacts_status"]["excel_path"] = str(excel_path)
            report["artifacts_status"]["word_path"] = str(word_path)

            # Start artifact generation in background thread
            # Store reference to orchestrator state so background thread can access it
            artifact_thread = threading.Thread(
                target=self._generate_artifacts_background,
                args=(report, excel_path, word_path, self.orchestrator.state, self.api_key),
                daemon=True
            )
            artifact_thread.start()
            print(f"[Pipeline] Background artifact generation started")

            # Return report immediately (UI can display while artifacts generate)
            print(f"[Pipeline] Analysis complete! Report returned with {len(report.get('sections', {}))} sections")
            return report

        except Exception as e:
            raise RuntimeError(f"Pipeline execution failed: {str(e)}")

    def _generate_artifacts_background(self, report: Dict[str, Any], excel_path: Path, word_path: Path, state, api_key: str) -> None:
        """
        Generate Excel and Word artifacts in background thread.
        Updates report dict when complete so UI can display download buttons.

        Args:
            report: Report dict to update with artifact status
            excel_path: Path to save Excel file
            word_path: Path to save Word file
            state: Pipeline state with analysis results
            api_key: API key for sword-word-builder
        """
        try:
            # Set up sys.path in background thread (required for imports)
            import sys
            from pathlib import Path
            real_dir = Path(__file__).parent.parent
            root_dir = real_dir.parent
            if str(real_dir) not in sys.path:
                sys.path.insert(0, str(real_dir))
            if str(root_dir) not in sys.path:
                sys.path.insert(0, str(root_dir))

            from pipeline.stage6_artifacts import generate_excel, generate_word_report

            # Generate Excel
            generate_excel(state, str(excel_path))
            report["artifacts_status"]["excel_ready"] = True

            # Generate Word report
            generate_word_report(
                state,
                str(word_path),
                language='ar',
                api_key=api_key
            )
            report["artifacts_status"]["word_ready"] = True

            # Add artifacts section once both are ready
            report["sections"]["stage6_artifacts"] = {
                "title": "Generated Artifacts",
                "content": "Analysis report and detailed Excel workbook ready for download",
                "data": [
                    {"type": "Excel Workbook", "path": str(excel_path), "ready": True},
                    {"type": "Word Report", "path": str(word_path), "ready": True}
                ]
            }

        except Exception as e:
            import traceback
            error_details = f"{str(e)}\n{traceback.format_exc()}"
            report["artifacts_status"]["error"] = error_details
            report["sections"]["stage6_artifacts"] = {
                "title": "Artifact Generation Error",
                "content": f"Failed to generate artifacts: {str(e)}",
                "data": []
            }
            print(f"[Background] Artifact generation error: {error_details}")



    def _load_guidebook_search(self) -> GuidebookSearchIndex:
        """Load pre-computed guidebook search index from .guidebook_cache."""
        try:
            guidebook_path = Path(__file__).parent.parent / 'inquiries-flow' / 'inquiries-supporting-files' / 'customer_services_guidebook.pdf'
            persist_dir = Path(__file__).parent.parent / '.guidebook_cache'

            if not persist_dir.exists():
                print(f"[GuidebookLoader] ⚠️ Cache not found. Run: python real/precompute_guidebook.py")
                return None

            print(f"[GuidebookLoader] Loading pre-computed search index from {persist_dir}")
            search_index = GuidebookSearchIndex(str(guidebook_path), persist_dir=str(persist_dir))
            # Load from cache without recomputing
            search_index.collection = search_index.client.get_collection(name="guidebook")
            return search_index
        except Exception as e:
            print(f"[GuidebookLoader] Error loading search index: {e}")
            import traceback
            traceback.print_exc()
            return None

