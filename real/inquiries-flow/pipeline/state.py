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
    top_level: Optional[str] = None  # Two-level taxonomy: شكوى, استفسار, طلب, شكر وثناء
    sub_classification: Optional[str] = None  # Domain-specific sub-classification
    admin: Optional[str] = None  # General administration / department name (الإدارة_العامة)


class PatternCluster(BaseModel):
    """Identified pattern cluster from Stage 4."""
    cluster: str
    sub_theme: str
    case_count: int
    example_case_ids: List[str] = Field(default_factory=list)
    cluster_ar: Optional[str] = None
    sub_theme_ar: Optional[str] = None
    top_level: Optional[str] = None  # Associated top-level category
    sub_classification: Optional[str] = None  # Associated sub-classification


class JourneyFriction(BaseModel):
    """Friction point in customer journey from Stage 4."""
    cluster: str
    friction_point: str
    root_cause_category: str  # missing_info | inaccessible_info | no_proactive_notification | platform_bug | policy_complexity
    case_count: int
    cluster_ar: Optional[str] = None
    friction_point_ar: Optional[str] = None
    top_level: Optional[str] = None  # Associated top-level category
    sub_classification: Optional[str] = None  # Associated sub-classification


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
    guidebook_status: str  # "Covered" | "Partially Covered" | "Missing"
    gap_type: str
    severity: str  # Critical | Medium | Adequate
    recommendation: str
    topic_ar: Optional[str] = None
    gap_type_ar: Optional[str] = None
    recommendation_ar: Optional[str] = None
    sub_classification: Optional[str] = None  # sub_classification(s) this gap covers
    # Enhanced guidebook intelligence fields
    guidebook_excerpt: Optional[str] = None  # Actual text snippet from guidebook
    guidebook_excerpt_ar: Optional[str] = None
    coverage_percentage: Optional[float] = None  # % of issue addressed by guidebook
    clarity_assessment: Optional[str] = None  # plain_language | bureaucratic | unclear
    format_assessment: Optional[str] = None  # step_by_step | wall_of_text | mixed
    has_visual_guidance: Optional[bool] = None  # Has diagrams/screenshots
    guidebook_match_confidence: Optional[float] = None  # 0.0-1.0 confidence score
    proactive_notification_opportunity: Optional[bool] = None  # Could be solved by proactive SMS/email


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
    original_columns: List[str] = Field(default_factory=list)  # Original column names from input Excel

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
    proactive_notification_case_count: int = 0  # Authoritative count from LLM analysis

    # --- STAGE 4 (validated FAQs from Stage 5) ---
    validated_faqs: List[FAQCandidate] = Field(default_factory=list)

    # --- STAGE 5 (GAP ANALYSIS) ---
    gap_table: List[GapRow] = Field(default_factory=list)

    # --- STAGE 6 (REPORT SECTIONS) ---
    report_sections_ar: Dict[str, Any] = Field(default_factory=dict)  # Arabic sections, keyed by section slug
    report_sections_en: Dict[str, Any] = Field(default_factory=dict)  # English sections, keyed by section slug

    # --- STAGE 6 (REPORT DICTIONARY) ---
    report_json: Optional[Dict[str, Any]] = None  # Demo-compatible report dict (in-memory)

    # --- PRIOR RUN (for monthly diff) ---
    prior_run_state: Optional[Dict[str, Any]] = None  # Loaded from uploaded JSON

    # --- METADATA ---
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    month_year: Optional[str] = None  # From data date range
    total_cases: int = 0
    closed_cases_count: int = 0  # Cases where تاريخ_إغلاق_الطلب is not empty (for methodology section)
    reclassified_count: int = 0  # FIX 1: Centralized reclassification count
    reclassification_rate: float = 0.0  # Percentage of cases reclassified

    # --- PIPELINE ROUTING STATS (stored before queues cleared) ---
    llm_queue_count: int = 0  # Cases sent to LLM after stage 2
    human_review_count: int = 0  # Cases below LLM threshold, sent to human review
    rule_classified_count: int = 0  # Cases classified by rules in stage 2

    # --- ANALYSIS METADATA ---
    validated_faqs_count: int = 0  # Count of validated FAQs from stage 5
    guidebook_topics: List[str] = Field(default_factory=list)  # Friction cluster topics from gap_table

    # --- GUIDEBOOK METADATA (from Stage 5) ---
    guidebook_pages: Optional[int] = None  # Total pages in guidebook
    guidebook_faq_count: Optional[int] = None  # Total FAQs in guidebook
    guidebook_year: Optional[str] = None  # Publication year of guidebook

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


ARABIC_MONTHS = {
    'January': 'يناير',
    'February': 'فبراير',
    'March': 'مارس',
    'April': 'أبريل',
    'May': 'مايو',
    'June': 'يونيو',
    'July': 'يوليو',
    'August': 'أغسطس',
    'September': 'سبتمبر',
    'October': 'أكتوبر',
    'November': 'نوفمبر',
    'December': 'ديسمبر',
}

ENGLISH_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']


def convert_month_year_to_arabic(english_month_year: str) -> str:
    """
    Convert English month-year string to Arabic.

    Examples:
        "January 2025" → "يناير 2025"
        "January — February 2025" → "يناير — فبراير 2025"
        "January 2025 — February 2026" → "يناير 2025 — فبراير 2026"
    """
    if not english_month_year:
        return english_month_year

    result = english_month_year
    for eng_month, ar_month in ARABIC_MONTHS.items():
        result = result.replace(eng_month, ar_month)
    return result


def extract_month_year_range(cases: list, lang: str = 'en') -> str:
    """
    Extract month_year range from date_opened fields in cases.

    Handles formats: YYYY-MM-DD HH:MM:SS, DD/MM/YYYY, YYYY-MM-DD, etc.
    Args:
        cases: List of case dicts or CaseRow objects with date_opened field
        lang: 'en' for English, 'ar' for Arabic month names

    Returns:
        - English: "Month Year — Month Year" (e.g., "January 2025 — February 2025")
        - Arabic: "الشهر السنة — الشهر السنة" (e.g., "يناير 2025 — فبراير 2025")
    """
    if not cases:
        return None

    dates = []
    for case in cases:
        date_str = case.get('date_opened', '') if isinstance(case, dict) else case.date_opened
        if not date_str or str(date_str) in ('nan', 'NaT', 'None'):
            continue

        try:
            date_obj = None

            # Try ISO datetime format: YYYY-MM-DD HH:MM:SS
            if ' ' in str(date_str):
                date_part = str(date_str).split(' ')[0]  # Get YYYY-MM-DD part
                parts = date_part.split('-')
                if len(parts) == 3:
                    try:
                        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                        date_obj = datetime(year, month, day)
                    except (ValueError, IndexError):
                        pass

            # Try DD/MM/YYYY
            if date_obj is None and '/' in str(date_str):
                parts = str(date_str).split('/')
                if len(parts) == 3:
                    try:
                        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                        date_obj = datetime(year, month, day)
                    except (ValueError, IndexError):
                        pass

            # Try YYYY-MM-DD
            if date_obj is None and '-' in str(date_str):
                parts = str(date_str).split('-')
                if len(parts) == 3:
                    try:
                        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                        date_obj = datetime(year, month, day)
                    except (ValueError, IndexError):
                        pass

            if date_obj:
                dates.append(date_obj)
        except Exception:
            continue

    if not dates:
        return None

    dates.sort()
    min_date = dates[0]
    max_date = dates[-1]

    # Select month names based on language
    month_names = ARABIC_MONTHS if lang == 'ar' else ENGLISH_MONTHS

    min_month = month_names[ENGLISH_MONTHS[min_date.month - 1]] if lang == 'ar' else ENGLISH_MONTHS[min_date.month - 1]
    max_month = month_names[ENGLISH_MONTHS[max_date.month - 1]] if lang == 'ar' else ENGLISH_MONTHS[max_date.month - 1]

    if min_date.year == max_date.year and min_date.month == max_date.month:
        return f"{min_month} {min_date.year}"
    elif min_date.year == max_date.year:
        return f"{min_month} - {max_month} {max_date.year}"
    else:
        return f"{min_month} {min_date.year} - {max_month} {max_date.year}"
