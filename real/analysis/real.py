"""Real implementation of the analyzer with agentic AI logic.

Integrates with the 6-stage pipeline for analyzing inquiries.
Gracefully handles missing dependencies while providing a working analyzer.
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
from io import BytesIO
import json
import time

from .base import Analyzer


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
        self.temp_dir = tempfile.mkdtemp(prefix='real_analyzer_')
        self.orchestrator = None
        self._pipeline_available = self._check_pipeline_available()

    def _check_pipeline_available(self) -> bool:
        """Check if pipeline dependencies are available."""
        try:
            import sys
            pipeline_path = Path(__file__).parent.parent / 'pipeline'
            if pipeline_path.exists():
                sys.path.insert(0, str(pipeline_path.parent))
                from pipeline.orchestrator import PipelineOrchestrator
                return True
        except (ImportError, ModuleNotFoundError):
            return False

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
        Analyze an uploaded file using the pipeline or basic analysis.

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

            if self._pipeline_available and self.api_key:
                return self._analyze_with_pipeline(df)
            else:
                return self._analyze_with_basic_processing(df, uploaded_file.name)

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
        """Analyze using the full 6-stage pipeline."""
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))

            from pipeline.orchestrator import PipelineOrchestrator

            session_id = Path(self.temp_dir).name
            self.orchestrator = PipelineOrchestrator(self.api_key, self.temp_dir)
            self.orchestrator.initialize_state(session_id)

            success, msg = self.orchestrator.run_stage1_validator(df)
            if not success:
                raise ValueError(f"Stage 1: {msg}")

            success, msg = self.orchestrator.run_stage2_classifier()
            if not success:
                raise ValueError(f"Stage 2: {msg}")

            success, msg = self.orchestrator.run_stage3_llm_classifier()
            if not success:
                raise ValueError(f"Stage 3: {msg}")

            success, msg = self.orchestrator.run_stage4_analysis()
            if not success:
                raise ValueError(f"Stage 4: {msg}")

            guidebook_text = self._load_guidebook()
            success, msg = self.orchestrator.run_stage5_gap_analysis(guidebook_text)
            if not success:
                raise ValueError(f"Stage 5: {msg}")

            excel_path = Path(self.temp_dir) / "analysis_results.xlsx"
            word_path = Path(self.temp_dir) / "analysis_report.docx"

            success, msg = self.orchestrator.run_stage6_artifacts(
                str(excel_path), str(word_path), language='ar'
            )
            if not success:
                raise ValueError(f"Stage 6: {msg}")

            return self._generate_report_from_state()

        except Exception as e:
            raise RuntimeError(f"Pipeline execution failed: {str(e)}")

    def _analyze_with_basic_processing(self, df: pd.DataFrame, filename: str) -> Dict[str, Any]:
        """Basic analysis when pipeline is not available."""
        try:
            row_count = len(df)
            col_count = len(df.columns)
            columns = list(df.columns)

            categories = {}
            for col in df.select_dtypes(include=['object']).columns:
                try:
                    value_counts = df[col].value_counts().head(5)
                    categories[col] = dict(value_counts)
                except:
                    pass

            report = {
                "extraction_version": 1,
                "document_name": filename,
                "document_path": f"{self.temp_dir}/{filename}",
                "metadata": {
                    "title": "Inquiry Analysis Report (Basic)",
                    "author": "Real AI Pipeline",
                    "total_records": row_count,
                    "total_columns": col_count,
                    "columns": columns,
                },
                "charts": self._build_basic_charts(df, categories),
                "sections": self._build_basic_sections(df, categories),
            }

            return report

        except Exception as e:
            raise RuntimeError(f"Basic analysis failed: {str(e)}")

    def _build_basic_charts(self, df: pd.DataFrame, categories: Dict) -> list:
        """Build basic charts from DataFrame."""
        charts = []

        for col, value_counts in categories.items():
            if len(value_counts) <= 20:
                charts.append({
                    "type": "bar",
                    "title": f"Distribution: {col}",
                    "categories": list(value_counts.keys())[:10],
                    "series": [{"name": "Count", "data": list(value_counts.values())[:10]}],
                    "colors": ["#B68A35"]
                })

        if not charts and len(df) > 0:
            charts.append({
                "type": "pie",
                "title": "Data Overview",
                "categories": ["Records Analyzed"],
                "series": [{"name": "Count", "data": [len(df)]}],
                "colors": ["#B68A35"]
            })

        return charts

    def _build_basic_sections(self, df: pd.DataFrame, categories: Dict) -> Dict[str, Any]:
        """Build basic sections from DataFrame."""
        sections = {}

        sections["summary"] = {
            "title": "Data Summary",
            "content": f"Analyzed {len(df)} records across {len(df.columns)} columns",
            "data": [
                {"metric": "Total Records", "value": len(df)},
                {"metric": "Total Columns", "value": len(df.columns)},
            ]
        }

        if categories:
            cat_summary = []
            for col, counts in list(categories.items())[:3]:
                cat_summary.append({
                    "column": col,
                    "top_values": counts
                })
            sections["categories"] = {
                "title": "Category Distributions",
                "content": "Top values in categorical columns",
                "data": cat_summary
            }

        return sections

    def _load_guidebook(self) -> str:
        """Load guidebook text for gap analysis."""
        try:
            guidebook_path = Path(__file__).parent.parent / '.guidebook_cache' / 'guidebook.txt'
            if guidebook_path.exists():
                return guidebook_path.read_text(encoding='utf-8')
        except:
            pass
        return ""

    def _generate_report_from_state(self) -> Dict[str, Any]:
        """Generate report structure from pipeline state."""
        if not self.orchestrator or not self.orchestrator.state:
            raise ValueError("Pipeline state not available")

        state = self.orchestrator.state

        report = {
            "extraction_version": 1,
            "document_name": "Analysis Report - Real Pipeline",
            "document_path": f"{self.temp_dir}/analysis_report.docx",
            "metadata": {
                "title": "Inquiry Analysis Report",
                "author": "Real AI Pipeline",
                "total_classified": len(state.all_classified) if state.all_classified else 0,
                "patterns_found": len(state.patterns) if state.patterns else 0,
                "faq_candidates": len(state.faq_candidates) if state.faq_candidates else 0,
            },
            "charts": self._build_pipeline_charts(state),
            "sections": self._build_pipeline_sections(state),
        }

        return report

    def _build_pipeline_charts(self, state) -> list:
        """Build chart data from pipeline state."""
        charts = []

        try:
            if hasattr(state, 'patterns') and state.patterns:
                pattern_names = [
                    p.get('name', f'Pattern {i}')
                    for i, p in enumerate(state.patterns[:10])
                ]
                pattern_sizes = [
                    p.get('size', 0)
                    for p in state.patterns[:10]
                ]

                charts.append({
                    "type": "bar",
                    "title": "Inquiry Patterns",
                    "categories": pattern_names,
                    "series": [{"name": "Count", "data": pattern_sizes}],
                    "colors": ["#B68A35"]
                })

            if hasattr(state, 'all_classified') and state.all_classified:
                classifications = {}
                for item in state.all_classified:
                    category = item.get('category', 'Unknown') if isinstance(item, dict) else str(item)
                    classifications[category] = classifications.get(category, 0) + 1

                charts.append({
                    "type": "pie",
                    "title": "Classification Distribution",
                    "categories": list(classifications.keys())[:10],
                    "series": [{"name": "Count", "data": list(classifications.values())[:10]}],
                    "colors": ["#B68A35", "#2E86AB", "#1a6b3c", "#808080"]
                })
        except Exception:
            pass

        return charts

    def _build_pipeline_sections(self, state) -> Dict[str, Any]:
        """Build report sections from pipeline state."""
        sections = {}

        try:
            if hasattr(state, 'patterns') and state.patterns:
                sections["patterns"] = {
                    "title": "Identified Patterns",
                    "content": "Top patterns found in inquiries",
                    "data": state.patterns[:5]
                }

            if hasattr(state, 'faq_candidates') and state.faq_candidates:
                sections["faq"] = {
                    "title": "FAQ Candidates",
                    "content": "Frequently asked questions from inquiries",
                    "data": state.faq_candidates[:10]
                }

            if hasattr(state, 'gap_table') and state.gap_table:
                sections["gaps"] = {
                    "title": "Identified Gaps",
                    "content": "Service gaps identified through analysis",
                    "data": state.gap_table[:10]
                }
        except Exception:
            pass

        if not sections:
            sections["summary"] = {
                "title": "Analysis Summary",
                "content": "Pipeline analysis complete",
                "data": []
            }

        return sections
