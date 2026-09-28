"""
Real Complaints Pipeline
========================

6-stage server-side pipeline for analyzing complaints:
1. Schema Validator — validates input Excel against contract
2. Rule-based Classifier — applies priority decision tree
3. LLM Classifier — processes low-confidence rule-engine rejects
4. Analysis — pattern mining, FAQ extraction, friction mapping
5. Gap Analysis — guidebook-based gap identification
6. Artifact Generator — Excel workbook + Word report

Each stage receives the shared Pydantic state object, enriches it, returns it.
State is serialized to JSON after each stage for recovery on browser refresh.
"""

from .state import PipelineState
from .orchestrator import PipelineOrchestrator

__all__ = ["PipelineState", "PipelineOrchestrator"]
