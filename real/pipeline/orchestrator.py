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

from .state import PipelineState, save_state_to_json, load_state_from_json
from .stage1_validator import run_stage1
from .stage2_rules import run_stage2
from .stage3_llm import run_stage3
from .stage4_analysis import run_stage4
from .stage5_gap import run_stage5
from .stage6_artifacts import run_stage6
from .guidebook import GuidebookSearchIndex


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

    def run_stage1_validator(self, df: pd.DataFrame) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Run Stage 1: Schema validation.

        Returns:
            (success, message, result_dict)
        """
        try:
            self.state = run_stage1(self.state, df)
            self.save_state()
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
            self.save_state()

            msg = f"Classified {len(self.state.rule_classified)} cases, queued {len(self.state.llm_queue)} for LLM review"
            return True, msg
        except Exception as e:
            return False, f"Stage 2 error: {str(e)}"

    def run_stage3_llm_classifier(self) -> Tuple[bool, str]:
        """
        Run Stage 3: LLM classifier for low-confidence cases.

        Returns:
            (success, message)
        """
        if not self.state.llm_queue:
            # No low-confidence cases
            self.state.all_classified = self.state.rule_classified
            self.save_state()
            return True, "No low-confidence cases to review"

        try:
            self.state = run_stage3(self.state, self.api_key)

            # Merge classifications
            self.state.all_classified = self.state.rule_classified + self.state.llm_classified

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

            msg = f"Analyzed patterns: {len(self.state.patterns)} clusters, {len(self.state.faq_candidates)} FAQ candidates"
            return True, msg
        except anthropic.APIError as e:
            return False, f"API error: {str(e)}"
        except Exception as e:
            return False, f"Stage 4 error: {str(e)}"

    def run_stage5_gap_analysis(self, search_index: Optional[GuidebookSearchIndex] = None) -> Tuple[bool, str]:
        """
        Run Stage 5: Gap analysis and FAQ validation.

        Args:
            search_index: GuidebookSearchIndex for semantic search on guidebook

        Returns:
            (success, message)
        """
        try:
            self.state = run_stage5(self.state, self.api_key, search_index)
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
        Run Stage 6: Artifact generation (Excel + Word).

        Returns:
            (success, message)
        """
        try:
            self.state = run_stage6(self.state, excel_path, word_path, language, self.api_key)
            self.save_state()

            msg = f"Generated Excel ({excel_path}) and Word report ({word_path})"
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
        search_index: Optional[GuidebookSearchIndex] = None,
        language: str = 'ar'
    ) -> Dict[str, Any]:
        """
        Run all 6 stages in sequence.

        Args:
            df: Input DataFrame with case data
            excel_path: Path for Excel output
            word_path: Path for Word output
            search_index: GuidebookSearchIndex for Stage 5 semantic search
            language: Language for output ('ar' or 'en')

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
        success, msg, validation = self.run_stage1_validator(df)
        results['stages']['stage1'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)
            return results
        results['total_cases'] = self.state.total_cases

        # Stage 2
        success, msg = self.run_stage2_classifier()
        results['stages']['stage2'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)

        # Stage 3
        success, msg = self.run_stage3_llm_classifier()
        results['stages']['stage3'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)

        # Stage 4
        success, msg = self.run_stage4_analysis()
        results['stages']['stage4'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)

        # Stage 5
        success, msg = self.run_stage5_gap_analysis(search_index)
        results['stages']['stage5'] = {'success': success, 'message': msg}
        if not success:
            results['errors'].append(msg)

        # Stage 6
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
