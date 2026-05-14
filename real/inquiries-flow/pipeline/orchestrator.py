"""
Pipeline Orchestrator

Chains all 6 stages together with error handling and state persistence.
Each stage receives the shared state object and returns it enriched.
State is saved to JSON after each stage for recovery on browser refresh.
"""

import json
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import pandas as pd
import anthropic

from .state import PipelineState, CaseRow, save_state_to_json, load_state_from_json, extract_month_year_range
from .stage1_validator import run_stage1
from .stage2_rules import run_stage2
from .stage3_llm import run_stage3
from .stage4_analysis import run_stage4
from .stage5_gap import run_stage5, load_guidebook_for_stage5, extract_guidebook_topics, extract_guidebook_metadata
from .stage6_artifacts import run_stage6


class PipelineOrchestrator:
    """Orchestrates the 6-stage pipeline."""

    def __init__(self, api_key: str, temp_dir: Optional[str] = None):
        """
        Initialize orchestrator.

        Args:
            api_key: Anthropic API key
            temp_dir: Temp directory for state files (default: system temp)
        """
        self.api_key = api_key
        self.temp_dir = Path(temp_dir or tempfile.gettempdir()) / 'pipeline_state'
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.state: Optional[PipelineState] = None
        self.state_file: Optional[Path] = None
        self.guidebook_path: Optional[str] = None

    def initialize_state(self, session_id: str) -> None:
        """Initialize or load state for a session."""
        self.state_file = self.temp_dir / f"{session_id}_state.json"

        if self.state_file.exists():
            try:
                self.state = load_state_from_json(str(self.state_file))
            except Exception as e:
                print(f"Failed to load state: {e}. Starting fresh.")
                self.state = PipelineState()
        else:
            self.state = PipelineState()

    def save_state(self) -> None:
        """Save current state to JSON."""
        if self.state and self.state_file:
            save_state_to_json(self.state, str(self.state_file))

    def find_guidebook_json(self) -> bool:
        """
        Find and set the guidebook JSON path.

        Returns:
            True if guidebook found, False otherwise
        """
        if self.guidebook_path:
            return True  # Already found

        try:
            # Try relative paths to guidebook (works in any deployment)
            locations = [
                Path(__file__).parent.parent / 'inquiries-supporting-files' / 'guidebook_final.json',
                Path(__file__).parent.parent / 'inquiries-supporting-files' / 'guidebook.json',
                Path(__file__).parent.parent.parent / 'real' / 'inquiries-flow' / 'inquiries-supporting-files' / 'guidebook_final.json',
            ]

            for loc in locations:
                if loc.exists():
                    self.guidebook_path = str(loc)
                    print(f"[Guidebook] Found at {loc.name}")
                    return True

            print(f"[Guidebook] JSON not found in inquiries-flow/inquiries-supporting-files/")
            return False

        except Exception as e:
            print(f"[Guidebook] Error: {e}")
            return False

    def run_stage1_validator(self, df: pd.DataFrame) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Run Stage 1: Schema validation.

        Returns:
            (success, message, result_dict)
        """
        try:
            self.state = run_stage1(self.state, df)
            self.save_state()
            print(f"[Stage1] Case count audit: total_cases={self.state.total_cases}, raw_df_rows={len(self.state.raw_df) if self.state.raw_df is not None else 0}")
            return True, "Schema validation passed", self.state.validated_schema
        except ValueError as e:
            return False, str(e), {}
        except Exception as e:
            return False, f"Stage 1 error: {str(e)}", {}

    def run_stage2_classifier(self) -> Tuple[bool, str]:
        """
        Run Stage 2: Rule-based classifier.

        Returns:
            (success, message)
        """
        try:
            self.state = run_stage2(self.state)

            # Preserve queue counts before they're cleared
            self.state.rule_classified_count = len(self.state.rule_classified)
            self.state.llm_queue_count = len(self.state.llm_queue)

            self.save_state()

            # Log case counts
            print(f"[Stage2] Case count audit:")
            print(f"  total_cases: {self.state.total_cases}")
            print(f"  rule_classified: {len(self.state.rule_classified)}")
            print(f"  llm_queue: {len(self.state.llm_queue)}")
            print(f"  Sum: {len(self.state.rule_classified) + len(self.state.llm_queue)}")

            msg = f"Classified {len(self.state.rule_classified)} cases, queued {len(self.state.llm_queue)} for LLM review"
            return True, msg
        except Exception as e:
            return False, f"Stage 2 error: {str(e)}"

    def run_stage3_llm_classifier(self, progress_callback=None) -> Tuple[bool, str]:
        """
        Run Stage 3: LLM classifier for low-confidence cases.

        Args:
            progress_callback: Optional function(progress_pct, msg_ar, msg_en) for UI updates

        Returns:
            (success, message)
        """
        if not self.state.llm_queue:
            # No low-confidence cases
            self.state.all_classified = self.state.rule_classified
            self.state.human_review_count = 0  # Preserve count: no cases sent to human review
            self.state.human_review_queue = []  # No human review cases
            self.state.month_year = extract_month_year_range(
                [c.model_dump() for c in self.state.all_classified]
            )
            self.save_state()
            return True, "No low-confidence cases to review"

        try:
            self.state = run_stage3(self.state, self.api_key, progress_callback=progress_callback)

            # Merge classifications (include human_review_queue so all input cases appear in Excel output)
            human_review_cases = [CaseRow(**item) for item in self.state.human_review_queue]
            self.state.all_classified = self.state.rule_classified + self.state.llm_classified + human_review_cases

            # Preserve human review count
            self.state.human_review_count = len(self.state.human_review_queue)

            # Log case counts for debugging
            print(f"[Stage3] Case count audit:")
            print(f"  total_cases (from Stage 1): {self.state.total_cases}")
            print(f"  rule_classified: {len(self.state.rule_classified)}")
            print(f"  llm_classified: {len(self.state.llm_classified)}")
            print(f"  human_review_queue: {len(self.state.human_review_queue)}")
            print(f"  all_classified: {len(self.state.all_classified)}")
            print(f"  Sum: {len(self.state.rule_classified) + len(self.state.llm_classified) + len(self.state.human_review_queue)}")

            # Extract month_year range from date_opened fields
            self.state.month_year = extract_month_year_range(
                [c.model_dump() for c in self.state.all_classified]
            )

            self.save_state()

            msg = f"LLM classified {len(self.state.llm_classified)} cases, {len(self.state.human_review_queue)} sent to human review"
            return True, msg
        except anthropic.APIError as e:
            return False, f"API error: {str(e)}"
        except Exception as e:
            return False, f"Stage 3 error: {str(e)}"

    def run_stage4_analysis(self) -> Tuple[bool, str]:
        """
        Run Stage 4: Analysis (patterns, FAQs, friction mapping).

        Returns:
            (success, message)
        """
        try:
            self.state = run_stage4(self.state, self.api_key)

            self.save_state()

            if not self.state.journey_map:
                print("[Stage4] WARNING: journey_map is empty — customer_journey section will be skipped in Stage 6")

            msg = (
                f"Analyzed patterns: {len(self.state.patterns)} clusters, "
                f"{len(self.state.faq_candidates)} FAQ candidates, "
                f"{len(self.state.journey_map)} friction points"
            )
            return True, msg
        except anthropic.APIError as e:
            return False, f"API error: {str(e)}"
        except Exception as e:
            return False, f"Stage 4 error: {str(e)}"

    def run_stage5_gap_analysis(self) -> Tuple[bool, str]:
        """
        Run Stage 5: Gap analysis and FAQ validation.

        Returns:
            (success, message)
        """
        try:
            # journey_map is required for Stage 5 — if empty, Stage 4 did not complete correctly
            if not self.state.journey_map:
                return False, (
                    "Stage 5 skipped: state.journey_map is empty — "
                    "Stage 4 (stage4_analysis) must complete successfully before gap analysis can run."
                )

            # Find and load guidebook
            if not self.find_guidebook_json():
                return False, "Could not find guidebook JSON"

            # Extract friction clusters from journey map for filtering
            friction_clusters = [j.cluster for j in self.state.journey_map]

            # Load filtered guidebook data
            guidebook_data = load_guidebook_for_stage5(self.guidebook_path, friction_clusters)

            self.state = run_stage5(self.state, self.api_key, guidebook_data)

            # gap_table must be populated — if empty after retries, the LLM failed all attempts
            if not self.state.gap_table:
                return False, (
                    "Stage 5 gap analysis produced no gaps after 3 LLM attempts — "
                    "check [Stage5] logs for details. The guidebook may have insufficient "
                    "coverage for the detected friction clusters, or the tool call failed repeatedly."
                )

            # Preserve metadata for methodology section
            self.state.validated_faqs_count = len(self.state.validated_faqs)

            # Extract guidebook metadata (pages, FAQ count, year, topics)
            guidebook_meta = extract_guidebook_metadata(self.guidebook_path)
            self.state.guidebook_pages = guidebook_meta['pages']
            self.state.guidebook_faq_count = guidebook_meta['faq_count']
            self.state.guidebook_year = guidebook_meta['year']
            self.state.guidebook_topics = guidebook_meta['topics']

            self.save_state()

            msg = f"Gap analysis complete: {len(self.state.gap_table)} gaps identified, {len(self.state.validated_faqs)} FAQs validated"
            return True, msg
        except anthropic.APIError as e:
            return False, f"API error: {str(e)}"
        except Exception as e:
            return False, f"Stage 5 error: {str(e)}"

    def run_stage6_artifacts(
        self,
        excel_path: str,
        word_path: str,
        language: str = 'ar'
    ) -> Tuple[bool, str]:
        """
        Run Stage 6: Artifact generation (Excel + Word + in-memory report dict).

        Args:
            excel_path: Path to save Excel workbook
            word_path: Path to save Word document
            language: 'ar' or 'en'

        Returns:
            (success, message)
        """
        try:
            self.state = run_stage6(
                self.state,
                excel_path,
                word_path,
                language=language,
                api_key=self.api_key
            )
            self.save_state()

            msg = f"Generated Excel ({excel_path}) and Word ({word_path}); report dict in state.report_json"
            return True, msg
        except AssertionError as e:
            return False, f"Validation failed: {str(e)}"
        except Exception as e:
            return False, f"Stage 6 error: {str(e)}"

    def run_full_pipeline(
        self,
        df: pd.DataFrame,
        excel_path: str,
        word_path: str,
        language: str = 'ar',
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Run all 6 stages in sequence.

        Args:
            df: Input DataFrame with case data
            excel_path: Path for Excel output
            word_path: Path for Word output
            language: Language for output ('ar' or 'en')
            progress_callback: Optional function(pct, msg_ar, msg_en) for UI updates

        Returns:
            Results dict with stage outcomes
        """
        results = {
            'success': False,
            'stages': {},
            'total_cases': 0,
            'errors': []
        }

        # Stage 1
        if progress_callback:
            progress_callback(0.10, "التحقق من صيغة البيانات", "Stage 1: File Validation")
        success, msg, validation = self.run_stage1_validator(df)
        results['stages']['stage1'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)
            return results
        results['total_cases'] = self.state.total_cases

        # Stage 2
        if progress_callback:
            progress_callback(0.25, "تصنيف الحالات حسب القواعس", "Stage 2: Rule Classification")
        success, msg = self.run_stage2_classifier()
        results['stages']['stage2'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)
            return results

        # Stage 3
        if progress_callback:
            progress_callback(0.40, "تصنيف الحالات باستخدام الذكاء الاصطناعي", "Stage 3: AI Classification")
        success, msg = self.run_stage3_llm_classifier(progress_callback=progress_callback)
        results['stages']['stage3'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)
            return results

        # Stage 4 — populates journey_map required by Stage 6 report generation
        if progress_callback:
            progress_callback(0.55, "تحليل الأنماط والفجوات", "Stage 4: Pattern Analysis")
        success, msg = self.run_stage4_analysis()
        results['stages']['stage4'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)
            return results

        # Stage 5
        if progress_callback:
            progress_callback(0.70, "تحليل الفجوات في الخدمات", "Stage 5: Gap Analysis")
        success, msg = self.run_stage5_gap_analysis()
        results['stages']['stage5'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)
            return results

        # Stage 6
        if progress_callback:
            progress_callback(0.85, "توليد التقارير والقوائم", "Stage 6: Report Generation")
        success, msg = self.run_stage6_artifacts(excel_path, word_path, language)
        results['stages']['stage6'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)
            return results

        results['success'] = True
        return results

    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current state."""
        if not self.state:
            return {}

        return {
            'total_cases': self.state.total_cases,
            'classified_cases': len(self.state.all_classified),
            'human_review_queue': len(self.state.human_review_queue),
            'patterns': len(self.state.patterns),
            'faq_candidates': len(self.state.faq_candidates),
            'validated_faqs': len(self.state.validated_faqs),
            'gaps': len(self.state.gap_table),
        }
