"""Abstract base class for analysis implementations (demo and real)."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class Analyzer(ABC):
    """
    Abstract base class that defines the interface for all analyzer implementations.

    Implementations (DemoAnalyzer, RealAnalyzer) must implement all abstract methods.
    This allows UI (app.py) to work with either demo or real analyzers seamlessly.
    """

    @abstractmethod
    def analyze(self, uploaded_file) -> Dict[str, Any]:
        """
        Analyze an uploaded file and return structured report data.

        Args:
            uploaded_file: Streamlit UploadedFile object containing the data to analyze

        Returns:
            Dict with the report structure containing:
            - title: str - Report title
            - charts: List[Dict] - Chart data for visualization
            - sections: Dict - Report sections with tables and content
        """
        pass

    @abstractmethod
    def get_processing_stages(self) -> list:
        """
        Get the processing stages to display in UI progress tracking.

        Returns:
            List of dicts with 'stage', 'description', 'percent_start', 'percent_end'
        """
        pass

    @abstractmethod
    def validate_file(self, uploaded_file) -> tuple[bool, str]:
        """
        Validate that an uploaded file is in a supported format.

        Args:
            uploaded_file: Streamlit UploadedFile object

        Returns:
            Tuple of (is_valid: bool, error_message: str or empty string)
        """
        pass
