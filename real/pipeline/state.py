"""
Pydantic state model for the inquiries pipeline.

Shared state object passed through all 6 stages.
Serialized to JSON after each stage for recovery on browser refresh.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
import json
from datetime import datetime


class CaseRow(BaseModel):
    """Single case after classification."""
    case_number: str
    case_title: str
    date_opened: str
    case_channel: str
    description: str
    resolution_response: str
    sla_color: str
    case_type: str
    service_name: str
    actual_contact_type: str  # Set by rule or LLM classifier
    classification_reason: str  # Explanation of classification
    confidence: float  # Confidence score [0.0, 1.0]
    misclassification: str  # "OK" or "Over-classified: [orig] → [actual]"


class PatternCluster(BaseModel):
    """Identified pattern cluster from Stage 4."""
    cluster: str
    sub_theme: str
    case_count: int
    example_case_ids: List[str] = Field(default_factory=list)
    cluster_ar: Optional[str] = None
    sub_theme_ar: Optional[str] = None


class JourneyFriction(BaseModel):
    """Friction point in customer journey from Stage 4."""
    cluster: str
    friction_point: str
    root_cause_category: str  # missing_info | inaccessible_info | no_proactive_notification | platform_bug | policy_complexity
    case_count: int
    cluster_ar: Optional[str] = None
    friction_point_ar: Optional[str] = None


class FAQCandidate(BaseModel):
    """FAQ candidate from Stage 4, validated in Stage 5."""
    question: str
    answer: str
    frequency: int
    validation_status: str  # OK | CONFLICT
    question_ar: Optional[str] = None
    answer_ar: Optional[str] = None


class GapRow(BaseModel):
    """Gap analysis row from Stage 5."""
    topic: str
    case_count: int
    guidebook_status: str
    gap_type: str
    severity: str  # Critical | Medium | Adequate
    recommendation: str
    topic_ar: Optional[str] = None
    gap_type_ar: Optional[str] = None
    recommendation_ar: Optional[str] = None


class PipelineState(BaseModel):
    """
    Shared state object for all 6 pipeline stages.

    Stages:
      1. Schema validator — populates raw_df, validated_schema
      2. Rule-based classifier — populates rule_classified, llm_queue
      3. LLM classifier — populates llm_classified, human_review_queue
      4. Analysis — populates patterns, journey_map, faq_candidates, etc.
      5. Gap analysis — populates gap_table
      6. Artifact generator — uses all above to create Excel + Word
    """

    # --- INPUT ---
    raw_df: Optional[Any] = None  # pandas DataFrame from uploaded Excel
    validated_schema: Optional[Dict[str, Any]] = None  # Schema validation result

    # --- STAGE 2 (RULE CLASSIFIER) ---
    rule_classified: List[CaseRow] = Field(default_factory=list)  # Cases classified by rules
    llm_queue: List[Dict] = Field(default_factory=list)  # Low-confidence rule rejects for Stage 3

    # --- STAGE 3 (LLM CLASSIFIER) ---
    llm_classified: List[CaseRow] = Field(default_factory=list)  # Cases classified by LLM
    human_review_queue: List[Dict] = Field(default_factory=list)  # Low-confidence LLM results

    # --- MERGED ---
    all_classified: List[CaseRow] = Field(default_factory=list)  # Merged rule + LLM results

    # --- STAGE 4 (ANALYSIS) ---
    patterns: List[PatternCluster] = Field(default_factory=list)
    journey_map: List[JourneyFriction] = Field(default_factory=list)
    faq_candidates: List[FAQCandidate] = Field(default_factory=list)
    self_service_tags: List[Dict] = Field(default_factory=list)
    notification_opportunities: List[Dict] = Field(default_factory=list)

    # --- STAGE 4 (validated FAQs from Stage 5) ---
    validated_faqs: List[FAQCandidate] = Field(default_factory=list)

    # --- STAGE 5 (GAP ANALYSIS) ---
    gap_table: List[GapRow] = Field(default_factory=list)

    # --- STAGE 6 (REPORT SECTIONS) ---
    report_sections: Dict[str, Any] = Field(default_factory=dict)  # Keyed by section slug

    # --- PRIOR RUN (for monthly diff) ---
    prior_run_state: Optional[Dict[str, Any]] = None  # Loaded from uploaded JSON

    # --- METADATA ---
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    month_year: Optional[str] = None  # From data date range
    total_cases: int = 0

    class Config:
        arbitrary_types_allowed = True


def load_state_from_json(json_path: str) -> PipelineState:
    """Load state from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return PipelineState(**data)


def save_state_to_json(state: PipelineState, json_path: str) -> None:
    """Save state to JSON file."""
    data = state.model_dump(mode='json', exclude={'raw_df'})  # Exclude DataFrame
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
