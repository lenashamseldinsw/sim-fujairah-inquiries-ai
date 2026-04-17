"""
Abstract Analyzer base class.

All analyzer implementations inherit from this.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List


class Analyzer(ABC):
    """Abstract base class for analyzers."""

    @abstractmethod
    def analyze(self, uploaded_file) -> Dict[str, Any]:
        """
        Analyze a file and return report structure.

        Args:
            uploaded_file: Streamlit UploadedFile object

        Returns:
            Dict with analysis results
        """
        pass

    @abstractmethod
    def validate_file(self, uploaded_file) -> Tuple[bool, str]:
        """
        Validate file format and size.

        Args:
            uploaded_file: Streamlit UploadedFile object

        Returns:
            (is_valid: bool, error_message: str)
        """
        pass

    @abstractmethod
    def get_processing_stages(self) -> List[Dict[str, Any]]:
        """
        Return processing stages for progress display.

        Returns:
            List of stage dicts with: {
                'label': str,
                'label_ar': str (optional),
                'label_en': str (optional),
                'percent_start': int,
                'percent_end': int
            }
        """
        pass
