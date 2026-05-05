"""
STAGE 5: Gap Analysis (LLM, guidebook-based)

Evaluates guidance gaps using the guidebook JSON.

Rubric:
1. Content existence: is info present in guidebook?
2. Language clarity: plain language or bureaucratic?
3. Format: step-by-step or wall of text?
4. Visual guidance: diagrams/screenshots?
5. Notification gap: would proactive notification help?

Output: gap_table with topic, case_count, severity, recommendation.
Also validates FAQ candidates from Stage 4 against guidebook.
"""

import json
import anthropic
from typing import Dict, Any, List, Optional
from .state import PipelineState, GapRow, FAQCandidate


GAP_ANALYSIS_TOOL = {
    "name": "analyze_gaps",
    "description": "Analyze information gaps and guidebook coverage based on customer interactions",
    "input_schema": {
        "type": "object",
        "properties": {
            "gap_table": {
                "type": "array",
                "description": "List of identified gaps with detailed guidebook intelligence",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "topic_ar": {"type": "string"},
                        "case_count": {"type": "integer"},
                        "guidebook_status": {"type": "string", "enum": ["Covered", "Partially Covered", "Missing"]},
                        "guidebook_excerpt": {"type": "string", "description": "Relevant text snippet from guidebook"},
                        "coverage_percentage": {"type": "number", "description": "0-100: what % of the issue is addressed by guidebook"},
                        "guidebook_match_confidence": {"type": "number", "description": "0.0-1.0: confidence that guidebook content matches the issue"},
                        "proactive_notification_opportunity": {"type": "boolean", "description": "Could proactive SMS/email resolve this?"},
                        "gap_type": {"type": "string"},
                        "gap_type_ar": {"type": "string"},
                        "severity": {"type": "string", "enum": ["Critical", "Medium", "Adequate"]},
                        "recommendation": {"type": "string"},
                        "recommendation_ar": {"type": "string"}
                    }
                }
            },
            "faq_validations": {
                "type": "array",
                "description": "Validation status for FAQ candidates from Stage 4",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "validation_status": {"type": "string", "enum": ["OK", "CONFLICT"]},
                        "conflict_reason": {"type": "string"}
                    }
                }
            }
        },
        "required": ["gap_table"]
    }
}


def extract_guidebook_topics(guidebook_path: str) -> List[str]:
    """
    Extract actual service category names from guidebook JSON.

    Returns the section names (service categories) that the guidebook covers.
    These are the REAL topics the guidebook addresses, not friction points.

    Args:
        guidebook_path: Path to guidebook JSON

    Returns:
        List of service category names in Arabic

    Raises:
        FileNotFoundError: If guidebook file doesn't exist
        KeyError: If guidebook structure doesn't have 'sections'
    """
    with open(guidebook_path) as f:
        g = json.load(f)

    sections = g.get('sections', [])
    if not sections:
        raise KeyError("Guidebook JSON missing 'sections' field")

    # Extract section names - these are the service categories
    topics = [s.get('name_ar') or s.get('name_en') for s in sections if 'name_ar' in s or 'name_en' in s]

    if not topics:
        raise ValueError("No service categories found in guidebook sections")

    return topics


def extract_guidebook_metadata(guidebook_path: str) -> Dict[str, Any]:
    """
    Extract guidebook metadata (pages, FAQ count, publication year, topics).

    Args:
        guidebook_path: Path to guidebook JSON

    Returns:
        Dict with keys: pages, faq_count, year, topics

    Raises:
        FileNotFoundError: If guidebook file doesn't exist
        KeyError: If guidebook structure doesn't have required fields
    """
    with open(guidebook_path) as f:
        g = json.load(f)

    # Extract pages from document metadata
    document = g.get('document', {})
    pages = document.get('total_pages', 160)

    # Extract FAQ count
    faqs = g.get('faq', [])
    faq_count = len(faqs)

    # Extract year from source_date (e.g., "October 2025" -> "2025")
    source_date = document.get('source_date', '2025')
    year = source_date.split()[-1] if source_date else '2025'

    # Extract topics (service categories)
    topics = extract_guidebook_topics(guidebook_path)

    return {
        'pages': pages,
        'faq_count': faq_count,
        'year': year,
        'topics': topics
    }


def load_guidebook_for_stage5(guidebook_path: str, friction_clusters: List[str]) -> dict:
    """
    Load and filter guidebook JSON for Stage 5 gap analysis.

    Uses simple string matching to filter services by friction cluster keywords.
    Always includes faq and fees_schedules.

    Args:
        guidebook_path: Path to guidebook JSON
        friction_clusters: List of friction cluster names from journey_map

    Returns:
        Dict with filtered services, faq, and fees_schedules
    """
    with open(guidebook_path) as f:
        g = json.load(f)

    # Fields Stage 5 needs per service
    needed_fields = [
        'service_name', 'section', 'description', 'requirements',
        'delivery_channels', 'service_center_steps',
        'working_hours', 'processing_time', 'fee_aed', 'fee_note'
    ]

    # Filter services by friction cluster keyword match (case-insensitive)
    all_services = g.get('services', [])
    matched = []
    seen_ids = set()

    for service in all_services:
        # Build searchable text from service name, section, and description
        name_section = (service.get('service_name', '') + ' ' +
                        service.get('section', '') + ' ' +
                        service.get('description', '')).lower()

        for cluster in friction_clusters:
            cluster_lower = cluster.lower()
            # Check if cluster matches by full phrase or any substantial word (>3 chars)
            if cluster_lower in name_section or any(
                word in name_section
                for word in cluster_lower.split()
                if len(word) > 3
            ):
                service_number = service.get('service_number')
                if service_number not in seen_ids:
                    # Include only fields that exist
                    filtered = {k: service[k] for k in needed_fields if k in service}
                    matched.append(filtered)
                    seen_ids.add(service_number)
                break

    # If no matches, fall back to all services with needed fields
    if not matched:
        matched = [{k: s[k] for k in needed_fields if k in s}
                   for s in all_services]

    return {
        'services': matched,
        'faq': g.get('faq', []),
        'fees_schedules': g.get('fees_schedules', [])
    }


def build_gap_analysis_prompt(
    patterns: List[Dict],
    journey_map: List[Dict],
    guidebook_data: Optional[Dict] = None,
    locked_case_counts: Optional[Dict[str, int]] = None
) -> str:
    """Build prompt for gap analysis with guidebook context from JSON."""
    patterns_text = json.dumps(patterns, ensure_ascii=False, indent=2)
    journey_text = json.dumps(journey_map, ensure_ascii=False, indent=2)

    # Format guidebook data for prompt
    guidebook_context = ""
    if guidebook_data:
        guidebook_context = json.dumps(guidebook_data, ensure_ascii=False, indent=2)
    else:
        guidebook_context = "(Guidebook data not available)"

    # Format locked case counts for LLM reference
    locked_counts_text = ""
    if locked_case_counts:
        locked_counts_text = json.dumps(locked_case_counts, ensure_ascii=False, indent=2)

    return f"""You are evaluating information gaps in government customer service.

Given:
1. Identified friction points and patterns from customer interactions
2. Relevant sections from the customer services guidebook (services, FAQs, fee schedules)

Evaluate each friction topic on:
1. Content Existence — is relevant information in the guidebook?
2. Language Clarity — is it in plain language or bureaucratic?
3. Format — is it step-by-step or a wall of text?
4. Visual Guidance — are there diagrams or screenshots?
5. Notification Gap — would proactive SMS/email notifications eliminate this inquiry?

Friction Points from Analysis:
{journey_text}

Patterns Identified:
{patterns_text}

Guidebook Content (filtered services, FAQs, fee schedules):
{guidebook_context}

LOCKED CASE COUNTS — DO NOT MODIFY:
These case counts are pre-computed from the friction points above and MUST be used as-is.
Match each gap to its corresponding friction cluster and use the locked count.
{locked_counts_text}

CRITICAL INSTRUCTION — case_count propagation:
For EVERY gap you identify, you MUST use the case_count from the LOCKED CASE COUNTS above.
Find the corresponding gap topic in the locked table and copy the case_count exactly.
DO NOT invent case_count values. DO NOT default to 1.
ALWAYS check the locked counts first — they are the source of truth.

For each major friction topic, provide:
- topic: Name of the gap topic (must match a friction point cluster if possible)
- topic_ar: Arabic name of the gap topic
- case_count: FROM LOCKED CASE COUNTS TABLE ABOVE (copy verbatim, do NOT alter)
- guidebook_status: "Covered" (full coverage), "Partially Covered", or "Missing"
- guidebook_excerpt: The actual relevant text from the guidebook (if applicable)
- coverage_percentage: 0-100 score of how much the guidebook addresses this issue
- clarity_assessment: "plain_language", "bureaucratic", or "unclear"
- format_assessment: "step_by_step", "wall_of_text", or "mixed"
- has_visual_guidance: true/false (diagrams, screenshots, etc.)
- guidebook_match_confidence: 0.0-1.0 confidence that the guidebook content matches the actual customer need
- proactive_notification_opportunity: true/false (would SMS/email proactive notifications prevent this inquiry?)
- severity: "Critical", "Medium", or "Adequate"
- gap_type: Type of gap (e.g., "missing_content", "unclear_process", "no_automation")
- gap_type_ar: Arabic type of gap
- recommendation: Specific, actionable recommendation for improvement
- recommendation_ar: Arabic recommendation

Return bilingual output (English and Arabic) for all content.
"""


def run_stage5(
    state: PipelineState,
    api_key: str,
    guidebook_data: Optional[Dict] = None
) -> PipelineState:
    """
    Stage 5: Gap analysis.

    Input: state with patterns, journey_map, faq_candidates from Stage 4
    Output: state with gap_table and validated_faqs

    Args:
        state: Pipeline state
        api_key: Anthropic API key
        guidebook_data: Filtered guidebook dict with services, faq, fees_schedules
    """
    if not state.journey_map:
        return state

    client = anthropic.Anthropic(api_key=api_key)

    # Build locked case counts from journey_map before API call
    # This maps friction clusters to their case counts for injection into results
    locked_case_counts = {}
    for friction in state.journey_map:
        cluster_key = friction.cluster or friction.cluster_ar or "unknown"
        friction_point = friction.friction_point or friction.friction_point_ar or ""
        locked_case_counts[f"{cluster_key} — {friction_point}"] = friction.case_count

    # Build analysis prompt with guidebook context and locked case counts
    prompt = build_gap_analysis_prompt(
        [p.model_dump() for p in state.patterns],
        [j.model_dump() for j in state.journey_map],
        guidebook_data,
        locked_case_counts
    )

    # Call Claude with tool-use
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,  # Increased to accommodate full gap_table analysis
        system="You are an expert analyst of government customer service. Provide gap analysis based on the guidebook and customer interaction patterns. Return detailed, bilingual recommendations.",
        tools=[GAP_ANALYSIS_TOOL],
        tool_choice={"type": "any"},  # Force tool use to prevent silent fallback to text
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    # Extract tool use result
    print(f"[Stage5] Message has {len(message.content)} blocks")
    for i, block in enumerate(message.content):
        print(f"[Stage5] Block {i}: type={block.type}")
        if block.type == "text":
            print(f"[Stage5]   Text: {block.text[:200]}")
        if block.type == "tool_use":
            print(f"[Stage5] Tool call received: {block.name}")
            print(f"[Stage5] Input type: {type(block.input)}")
            print(f"[Stage5] Input value: {block.input}")
            print(f"[Stage5] Keys in response: {list(block.input.keys()) if isinstance(block.input, dict) else 'N/A'}")
            print(f"[Stage5] gap_table length: {len(block.input.get('gap_table', []))}")
            print(f"[Stage5] faq_validations length: {len(block.input.get('faq_validations', []))}")
            # Print first gap_table item if any exist
            if block.input.get('gap_table'):
                print(f"[Stage5] First gap: {block.input['gap_table'][0]}")
            else:
                print(f"[Stage5] gap_table raw value: {block.input.get('gap_table')}")

            analysis = block.input

            # Parse gap table with enhanced guidebook intelligence
            if 'gap_table' in analysis:
                # Build journey_map lookup by topic and cluster for case_count matching
                journey_map_by_topic = {}
                cluster_to_case_count = {}
                for friction in (state.journey_map or []):
                    friction_topic = friction.friction_point or friction.friction_point_ar or ""
                    cluster_topic = friction.cluster or friction.cluster_ar or ""
                    if friction_topic:
                        journey_map_by_topic[friction_topic.lower()[:50]] = friction.case_count
                    if cluster_topic:
                        cluster_key = cluster_topic.lower()[:50]
                        journey_map_by_topic[cluster_key] = friction.case_count
                        cluster_to_case_count[cluster_topic] = friction.case_count  # Exact match for reinject

                gap_rows = []
                for g in analysis.get('gap_table', []):
                    case_count = g.get('case_count', 0)
                    gap_topic = g.get('topic_ar') or g.get('topic') or ""

                    # PRIMARY: Reinject from locked case counts (journey_map source of truth)
                    # Try exact match on gap topic against journey_map
                    gap_topic_lower = gap_topic.lower()[:50]
                    matched_count = journey_map_by_topic.get(gap_topic_lower)

                    # Try partial match if exact fails
                    if not matched_count:
                        for jm_key, count in journey_map_by_topic.items():
                            if jm_key in gap_topic_lower or gap_topic_lower in jm_key:
                                matched_count = count
                                break

                    # If matched, reinject locked count (overrides LLM output)
                    if matched_count and matched_count > 0:
                        case_count = matched_count
                        if case_count != g.get('case_count', 0):
                            print(f"[Stage5] REINJECT: case_count={case_count} for gap '{gap_topic[:50]}' (was {g.get('case_count', '?')})")

                    gap_rows.append(GapRow(
                        topic=g.get('topic', ''),
                        topic_ar=g.get('topic_ar', ''),
                        case_count=case_count,
                        guidebook_status=g.get('guidebook_status', ''),
                        gap_type=g.get('gap_type', ''),
                        gap_type_ar=g.get('gap_type_ar', ''),
                        severity=g.get('severity', 'Medium'),
                        recommendation=g.get('recommendation', ''),
                        recommendation_ar=g.get('recommendation_ar', ''),
                        # Enhanced guidebook intelligence
                        guidebook_excerpt=g.get('guidebook_excerpt', None),
                        guidebook_excerpt_ar=g.get('guidebook_excerpt_ar', None),
                        coverage_percentage=float(g.get('coverage_percentage', 0)) if g.get('coverage_percentage') else None,
                        clarity_assessment=g.get('clarity_assessment', None),
                        format_assessment=g.get('format_assessment', None),
                        has_visual_guidance=g.get('has_visual_guidance', None),
                        guidebook_match_confidence=float(g.get('guidebook_match_confidence', 0)) if g.get('guidebook_match_confidence') else None,
                        proactive_notification_opportunity=g.get('proactive_notification_opportunity', None)
                    ))

                state.gap_table = gap_rows

            # Validate FAQ candidates
            if 'faq_validations' in analysis:
                faq_validations = {
                    v['question']: v['validation_status']
                    for v in analysis.get('faq_validations', [])
                }

                validated = []
                for faq in state.faq_candidates:
                    status = faq_validations.get(faq.question, 'OK')
                    faq.validation_status = status
                    if status == 'OK':
                        validated.append(faq)

                state.validated_faqs = validated
            else:
                # If no validations provided, assume all OK
                for faq in state.faq_candidates:
                    faq.validation_status = 'OK'
                state.validated_faqs = state.faq_candidates

            break
    else:
        # No tool call found — log warning
        print("[Stage5] WARNING: No tool call in LLM response — gap_table may be empty")

    if not state.gap_table:
        print("[Stage5] WARNING: gap_table is empty after LLM call — tool call may have failed or guidebook content unavailable")

    return state
