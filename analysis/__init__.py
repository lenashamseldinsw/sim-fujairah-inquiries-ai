"""Analysis module for handling both demo and real implementations.

New structure:
- analysis/shared/ - Common components (base, display)
- analysis/demo/ - Demo analyzer implementation (with extraction utilities)
- analysis/real/ - Real analyzer implementation
- analysis/legacy/ - Legacy modules for backward compatibility
"""

# Import from shared components
from analysis.shared import Analyzer, DynamicReportDisplay

# Import from demo (extraction utilities + analyzer)
from analysis.demo import (
    DemoAnalyzer,
    AdaptiveReportExtractor,
    ReportStructureDetector
)

# Import from real
from analysis.real import RealAnalyzer

__all__ = [
    'Analyzer',
    'DemoAnalyzer',
    'RealAnalyzer',
    'AdaptiveReportExtractor',
    'ReportStructureDetector',
    'DynamicReportDisplay'
]
