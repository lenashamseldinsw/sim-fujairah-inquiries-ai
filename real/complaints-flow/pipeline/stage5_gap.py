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
from collections import defaultdict
from pathlib import Path
from .state import PipelineState, GapRow, FAQCandidate
from .json_utils import extract_methodology_context


GAP_ANALYSIS_TOOL = {
    "name": "analyze_gaps",
    "description": "Analyze information gaps and guidebook coverage based on customer complaints",
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
                        "guidebook_excerpt": {"type": "string", "description": "Relevant text snippet from guidebook (English)"},
                        "guidebook_excerpt_ar": {"type": "string", "description": "Relevant text snippet from guidebook (Arabic)"},
                        "coverage_percentage": {"type": "number", "description": "0-100: what % of the issue is addressed by guidebook"},
                        "guidebook_match_confidence": {"type": "number", "description": "0.0-1.0: confidence that guidebook content matches the issue"},
                        "proactive_notification_opportunity": {
                            "type": "boolean",
                            "description": (
                                "Could a proactive SMS/notification have prevented this complaint? "
                                "Examples: complaint receipt confirmation, complaint resolution status update, "
                                "escalation notification, redirect to correct channel at submission time."
                            )
                        },
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


def reconcile_faq_frequencies(
    faq_list: List[FAQCandidate],
    journey_map: List[Any],
    all_classified: List[Any]
) -> List[FAQCandidate]:
    """
    Reconcile FAQ frequencies using sub_classification as the ONLY signal.

    STRICT VALIDATION: sub_classification direct lookup only
    - LLM assigns sub_classification to each FAQ from the patterns list
    - Look up actual case count for that sub_classification
    - Cap at the friction's reconciled case_count (not full category total)
    - This avoids register mismatch entirely — uses authoritative ground truth
    - If sub_classification is missing or unmatched, FAQ is REJECTED (frequency=0)

    NO FALLBACK: Keyword matching is disabled to prevent false positives that
    inflated FAQ frequencies (e.g., "complaint" keyword matching unrelated cases).
    """
    if not faq_list or not all_classified:
        return faq_list

    # Build ground truth: sub_classification → actual case count
    actual_sub_counts: Dict[str, int] = defaultdict(int)
    for case in all_classified:
        sub = case.sub_classification or ''
        if sub:
            actual_sub_counts[sub] += 1

    # Build journey_map cap: sub_classification → friction case_count
    # (the reconciled per-friction count, always <= sub total)
    friction_cap: Dict[str, int] = {}
    for jf in (journey_map or []):
        sub = getattr(jf, 'sub_classification', None)
        cc = getattr(jf, 'case_count', 0)
        if sub and cc > 0:
            # Take the MAX friction case_count per sub (most relevant friction wins)
            if sub not in friction_cap or cc > friction_cap[sub]:
                friction_cap[sub] = cc

    reconciled_faqs = []

    # Build case number lookup for fast validation
    case_numbers = {case.case_number for case in all_classified}

    for faq in faq_list:
        q_text = (faq.question_ar or faq.question or '').strip()
        a_text = (faq.answer_ar or faq.answer or '').strip()

        # ── EVIDENCE VALIDATION ───────────────────────────────────────────────
        # Validate evidence_case_ids against actual cases in all_classified.
        # Frequency = count of valid (existing) evidence cases.
        # Sub_classification is for categorization only, not for filtering count.
        reconciled_frequency = 0
        signal_used = "rejected (no evidence)"

        evidence_ids = getattr(faq, 'evidence_case_ids', []) or []

        if evidence_ids:
            # Count how many evidence case IDs actually exist in all_classified
            valid_evidence = [cid for cid in evidence_ids if cid in case_numbers]
            reconciled_frequency = len(valid_evidence)

            if len(valid_evidence) < len(evidence_ids):
                # Some evidence cases don't exist (hallucinated or typo)
                signal_used = f"evidence: {len(valid_evidence)}/{len(evidence_ids)} valid cases"
            else:
                signal_used = f"evidence: {len(valid_evidence)} cases verified"
        else:
            # No evidence provided — reject the FAQ
            signal_used = "rejected (no evidence_case_ids)"

        print(
            f"[Stage5] FAQ '{q_text[:50]}': "
            f"{getattr(faq, 'frequency', 0)} → {reconciled_frequency} [{signal_used}]"
        )
        reconciled_faqs.append(faq.model_copy(update={"frequency": reconciled_frequency}))

    return reconciled_faqs


def find_guidebook_json() -> Optional[str]:
    """
    Find the complaints guidebook JSON file from multiple possible locations.

    Returns the path to guidebook_final.json if found, None otherwise.
    """
    locations = [
        Path(__file__).parent.parent / 'complaints-supporting-files' / 'guidebook_final.json',
        Path(__file__).parent.parent / 'complaints-supporting-files' / 'guidebook.json',
        Path(__file__).parent.parent.parent / 'real' / 'complaints-flow' / 'complaints-supporting-files' / 'guidebook_final.json',
    ]

    for loc in locations:
        if loc.exists():
            return str(loc)

    return None


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
    with open(guidebook_path, encoding="utf-8") as f:
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
    with open(guidebook_path, encoding="utf-8") as f:
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
    with open(guidebook_path, encoding="utf-8") as f:
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

    return f"""You are evaluating information gaps in government customer service complaints.

Given:
1. Identified friction points and complaint patterns from customer interactions
2. Relevant sections from the customer services guidebook (services, FAQs, fee schedules)

Evaluate each friction topic on:
1. Content Existence — is relevant information in the guidebook?
2. Language Clarity — is it in plain language or bureaucratic?
3. Format — is it step-by-step or a wall of text?
4. Visual Guidance — are there diagrams or screenshots?
5. Notification Gap — would proactive SMS/email notifications eliminate this complaint?

Complaint Patterns and Friction Points from Analysis:
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
- guidebook_excerpt: The actual relevant text from the guidebook (if applicable) — English text
- guidebook_excerpt_ar: The actual relevant text from the guidebook (if applicable) — Arabic text (translate excerpt into Arabic if needed)
- coverage_percentage: 0-100 score of how much the guidebook addresses this issue
- clarity_assessment: "plain_language", "bureaucratic", or "unclear"
- format_assessment: "step_by_step", "wall_of_text", or "mixed"
- has_visual_guidance: true/false (diagrams, screenshots, etc.)
- guidebook_match_confidence: 0.0-1.0 confidence that the guidebook content matches the actual customer need
- proactive_notification_opportunity: true/false (would proactive SMS/email notifications prevent this complaint? Examples: complaint receipt confirmation, complaint resolution status update, escalation notification, redirect to correct channel at submission time.)
- severity: "Critical", "Medium", or "Adequate"
- gap_type: Type of gap (e.g., "missing_content", "unclear_process", "no_automation", "channel_confusion")
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
    # When journey_map is empty, gap analysis cannot run — but we can still validate
    # faq_candidates so that Stage 6 has FAQ data for the digital_transformation section.
    if not state.journey_map:
        if state.faq_candidates:
            print(
                "[Stage5] journey_map is empty — skipping gap analysis. "
                "Promoting faq_candidates to validated_faqs without guidebook cross-check."
            )
            for faq in state.faq_candidates:
                faq.validation_status = 'OK'

            # Reconcile FAQ frequencies against actual case counts
            print("[Stage5] Reconciling FAQ frequencies against all_classified...")
            reconciled = reconcile_faq_frequencies(state.faq_candidates, [], state.all_classified)
            state.validated_faqs = reconciled
        else:
            print("[Stage5] journey_map and faq_candidates are both empty — nothing to process.")
        return state

    client = anthropic.Anthropic(api_key=api_key)

    # Extract methodology context if present
    methodology_context = None
    if state.complaints_methodology:
        methodology_context = extract_methodology_context(
            state.complaints_methodology,
            [
                "6_performance_indicators",
                "5_procedures.5_6_satisfaction_measurement",
                "5_procedures.5_7_reporting"
            ]
        )

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

    # Call Claude with tool-use — retry up to 3 times if gap_table comes back empty
    MAX_ATTEMPTS = 3
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            print(f"[Stage5] Retrying LLM call (attempt {attempt}/{MAX_ATTEMPTS}) — gap_table was empty on previous attempt")

        # Build system prompt with optional methodology context
        system_prompt = "You are an expert analyst of government customer service complaints. Provide gap analysis based on the guidebook and complaint patterns. Return detailed, bilingual recommendations."

        if methodology_context:
            methodology_text = "\n\n### السياق: معايير الأداء من المنهجية (الإصدار 4.0)\n\n"
            if methodology_context.get("6_performance_indicators"):
                indicators = methodology_context["6_performance_indicators"].get("indicators", [])
                methodology_text += "**مؤشرات الأداء الرسمية:**\n"
                for ind in indicators:
                    methodology_text += f"- {ind.get('indicator', '')}: الهدف {ind.get('target', '')} (مسؤول: {ind.get('responsible', '')})\n"
                methodology_text += "\n"

            if methodology_context.get("5_6_satisfaction_measurement"):
                methodology_text += "**قياس الرضا:** يتعين قياس رضا المتعامل عن حل الشكوى بعد الانتهاء من معالجتها.\n\n"

            if methodology_context.get("5_7_reporting"):
                methodology_text += "**التقارير:** يجب حصر جميع الشكاوى وتحليلها لتحديد الأسباب الجذرية والحلول المناسبة.\n"

            system_prompt += methodology_text

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,  # Large datasets need room for full gap_table + faq_validations
            system=system_prompt,
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
        print(f"[Stage5] Attempt {attempt}: message has {len(message.content)} blocks")
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

                # ── FIX 3: Parse gap table and inject journey_map case counts ──
                # Build authoritative journey_map lookup (friction-level case counts)
                if 'gap_table' in analysis:
                    # STEP 1: Build journey_map lookup for friction-level case counts
                    friction_case_count_lookup = {}
                    for friction in (state.journey_map or []):
                        # Index by multiple fields for flexible matching
                        for text_field in [
                            friction.cluster_ar,
                            friction.cluster,
                            friction.friction_point_ar,
                            friction.friction_point,
                        ]:
                            if text_field:
                                norm_key = text_field.lower().strip()[:50]
                                # Keep the minimum (most specific) matching count
                                if norm_key not in friction_case_count_lookup:
                                    friction_case_count_lookup[norm_key] = friction.case_count
                                else:
                                    friction_case_count_lookup[norm_key] = min(
                                        friction_case_count_lookup[norm_key],
                                        friction.case_count
                                    )

                    if friction_case_count_lookup:
                        print(f"[Stage5] Built friction_case_count_lookup: {len(friction_case_count_lookup)} entries")

                    # STEP 2: Reinject journey_map case counts into gap_table
                    gap_rows = []
                    for g in analysis.get('gap_table', []):
                        gap_topic = (g.get('topic_ar') or g.get('topic') or "").strip()
                        gap_topic_norm = gap_topic.lower()[:50]

                        # Try exact match first
                        injected_count = friction_case_count_lookup.get(gap_topic_norm)

                        # Try partial match if exact fails
                        if not injected_count:
                            for fkey, fcount in friction_case_count_lookup.items():
                                if fkey in gap_topic_norm or gap_topic_norm in fkey:
                                    injected_count = fcount
                                    break

                        # Use injected count if found; otherwise use LLM count (with step 3 cap)
                        case_count = injected_count if injected_count else g.get('case_count', 0)

                        if injected_count and injected_count != g.get('case_count', 0):
                            print(f"[Stage5] FIX 3 INJECT: gap '{gap_topic[:40]}' case_count: {g.get('case_count')} → {case_count} (from journey_map)")

                        gap_rows.append(GapRow(
                            topic=g.get('topic', ''),
                            topic_ar=g.get('topic_ar', ''),
                            case_count=case_count,
                            case_ids=g.get('case_ids', []),
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

                # ── FIX 3 (continued): Hard cap gap case_counts at max friction level ──
                # Prevents LLM hallucination for gaps with no journey_map match
                max_friction_count = max(
                    (f.case_count for f in (state.journey_map or [])),
                    default=0
                )

                if max_friction_count > 0:
                    for gap in state.gap_table:
                        if gap.case_count > max_friction_count:
                            print(
                                f"[Stage5] FIX 3 CAP: gap '{(gap.topic_ar or gap.topic)[:40]}' "
                                f"{gap.case_count} → {max_friction_count} (exceeds max friction)"
                            )
                            gap.case_count = max_friction_count

                # Reconcile gap_table case counts against all_classified with BUDGET TRACKING
                # Root cause fix: prevent double-counting when multiple gaps match same sub_classification
                # Ground truth: sub_classification → actual case count
                actual_sub_counts = defaultdict(int)
                for case in state.all_classified:
                    actual_sub_counts[case.sub_classification] += 1

                original_gap_total = sum(g.case_count for g in state.gap_table)

                # Bridge: journey_map cluster text → set of sub_classifications it covers.
                # journey_map entries have sub_classification set exactly (enforced by Stage 4 prompt).
                cluster_to_subs: dict = defaultdict(set)
                for friction in state.journey_map:
                    if not friction.sub_classification:
                        continue
                    # Index by every available text field so gap topic matching has maximum coverage
                    for text_field in [
                        friction.cluster_ar,
                        friction.cluster,
                        friction.friction_point_ar,
                        friction.friction_point,
                    ]:
                        key = (text_field or "").strip().lower()
                        if key:
                            cluster_to_subs[key].add(friction.sub_classification)

                # BUDGET TRACKING: Create mutable budget from actual counts
                # Each gap claims from this budget; once claimed, it's gone (no double-counting)
                sub_budget = dict(actual_sub_counts)

                # Sort gaps by case_count descending — most impactful gets first claim on budget
                sorted_gaps = sorted(state.gap_table, key=lambda g: g.case_count, reverse=True)

                # Reconcile gap case_counts: deduct injected counts from budget to prevent double-counting
                # FIX: Validate injected counts against budget; don't recalculate from scratch
                for gap in sorted_gaps:
                    topic_lower = (gap.topic_ar or gap.topic or "").strip().lower()
                    matched_subs: set = set()

                    for cluster_key, subs in cluster_to_subs.items():
                        if cluster_key in topic_lower or topic_lower in cluster_key:
                            matched_subs.update(subs)

                    if matched_subs:
                        # The gap already has a case_count (from FIX 3 injection)
                        # Validate it against available budget, then deduct from budget
                        claimed_count = gap.case_count or 0
                        available_budget = sum(sub_budget.get(s, 0) for s in matched_subs)

                        if claimed_count <= available_budget:
                            # Gap claim is within budget — deduct from budget (no recalculation)
                            # Distribute deduction proportionally across matched subs
                            if available_budget > 0:
                                for sub in matched_subs:
                                    current = sub_budget.get(sub, 0)
                                    deduction = round(claimed_count * (current / available_budget))
                                    sub_budget[sub] = max(0, current - deduction)
                        else:
                            # Gap claim exceeds available budget — cap to available
                            capped = min(claimed_count, available_budget)
                            if capped != gap.case_count:
                                print(
                                    f"[Stage5] CAP gap '{(gap.topic_ar or gap.topic)[:40]}': "
                                    f"{gap.case_count} → {capped} (available_budget={available_budget})"
                                )
                            gap.case_count = capped
                            # Deduct capped amount from budget
                            if available_budget > 0:
                                for sub in matched_subs:
                                    current = sub_budget.get(sub, 0)
                                    deduction = round(capped * (current / available_budget))
                                    sub_budget[sub] = max(0, current - deduction)

                # Final reconciled total
                reconciled_gap_total = sum(g.case_count for g in state.gap_table)
                total_cases = state.total_cases or len(state.all_classified)

                # FINAL SAFETY CHECK: If injected counts exceed total cases, scale proportionally
                if reconciled_gap_total > total_cases:
                    print(
                        f"[Stage5] SAFETY SCALE: Gap table total {reconciled_gap_total} > {total_cases}. "
                        f"Scaling all gaps proportionally..."
                    )
                    scale_factor = total_cases / reconciled_gap_total if reconciled_gap_total > 0 else 1.0
                    for gap in state.gap_table:
                        original = gap.case_count
                        scaled = max(1, round(gap.case_count * scale_factor))
                        gap.case_count = scaled
                        if scaled != original:
                            print(
                                f"[Stage5] SCALE: gap '{(gap.topic_ar or gap.topic)[:40]}' "
                                f"{original} → {scaled} (factor={scale_factor:.2f})"
                            )

                    reconciled_gap_total = sum(g.case_count for g in state.gap_table)
                    print(
                        f"[Stage5] After scaling: {reconciled_gap_total} / {total_cases} cases"
                    )

                # ── FIX 4 (continued): Re-validate notification_opportunities in Stage 5 ──
                # After resync, re-apply sub-count caps as safety check
                if state.notification_opportunities:
                    actual_sub_counts_from_classified = defaultdict(int)
                    for case in (state.all_classified or []):
                        if case.sub_classification:
                            actual_sub_counts_from_classified[case.sub_classification] += 1

                    for i, notif in enumerate(state.notification_opportunities or []):
                        claimed = int(notif.get("cases_eliminated", 0))
                        notif_type = (notif.get("notification_type") or "").lower()

                        if claimed < 1:
                            continue

                        # Find best-matching sub-classification
                        best_cap = None
                        for sub_name, sub_count in actual_sub_counts_from_classified.items():
                            sub_norm = sub_name.lower()
                            notif_words = set(w for w in notif_type.split() if len(w) >= 3)
                            sub_words = set(w for w in sub_norm.split() if len(w) >= 3)
                            overlap = len(notif_words & sub_words)

                            if overlap > 0:
                                if best_cap is None or sub_count < best_cap:
                                    best_cap = sub_count

                        if best_cap and claimed > best_cap:
                            print(f"[Stage5] Re-capping notification cases_eliminated: {claimed} → {best_cap}")
                            state.notification_opportunities[i] = {
                                **notif,
                                "cases_eliminated": best_cap
                            }

                    # RESYNC proactive_notification_case_count from notification_opportunities
                    # Why: Stage 4 may have set a stale value; we must use the authoritative post-reconciliation count
                    authoritative_proactive = sum(
                        int(n.get("cases_eliminated", n.get("case_count", 0)))
                        for n in state.notification_opportunities
                    )
                    if authoritative_proactive != (state.proactive_notification_case_count or 0):
                        print(
                            f"[Stage5] Resyncing proactive count: {state.proactive_notification_case_count} → {authoritative_proactive} "
                            f"(from notification_opportunities)"
                        )
                        state.proactive_notification_case_count = authoritative_proactive

                # RECONCILE PROACTIVE NOTIFICATION COUNTS: Ensure gap_table proactive values sum to authoritative count
                # Issue: gap_table has LLM-generated proactive_notification_opportunity per gap,
                # but these may not sum to state.proactive_notification_case_count (from reconciled notification_opportunities).
                # Fix: Normalize gap_table proactive counts to use the authoritative total.
                if state.gap_table and state.proactive_notification_case_count and state.proactive_notification_case_count > 0:
                    gap_proactive_total = sum(
                        int(g.proactive_notification_opportunity or 0)
                        for g in state.gap_table
                    )

                    if gap_proactive_total != state.proactive_notification_case_count:
                        # Scale gap proactive counts proportionally to match authoritative total
                        print(
                            f"[Stage5] PROACTIVE RECONCILE: gap_table total {gap_proactive_total} → "
                            f"{state.proactive_notification_case_count} (authoritative from notification_opportunities)"
                        )

                        if gap_proactive_total > 0:
                            scale_factor = state.proactive_notification_case_count / gap_proactive_total
                            for gap in state.gap_table:
                                if gap.proactive_notification_opportunity:
                                    original = gap.proactive_notification_opportunity
                                    gap.proactive_notification_opportunity = int(round(
                                        gap.proactive_notification_opportunity * scale_factor
                                    ))
                                    if gap.proactive_notification_opportunity != original:
                                        print(
                                            f"[Stage5]   Gap '{(gap.topic_ar or gap.topic)[:40]}': "
                                            f"proactive {original} → {gap.proactive_notification_opportunity}"
                                        )
                        else:
                            # No proactive counts in gaps but state says there are opportunities
                            # Distribute the authoritative count evenly across eligible gaps
                            proactive_gaps = [g for g in state.gap_table if g.proactive_notification_opportunity]
                            if proactive_gaps:
                                per_gap = state.proactive_notification_case_count // len(proactive_gaps)
                                remainder = state.proactive_notification_case_count % len(proactive_gaps)
                                for i, gap in enumerate(proactive_gaps):
                                    gap.proactive_notification_opportunity = per_gap + (1 if i < remainder else 0)
                                    print(
                                        f"[Stage5]   Gap '{(gap.topic_ar or gap.topic)[:40]}': "
                                        f"proactive allocated {gap.proactive_notification_opportunity}"
                                    )
                    else:
                        print(
                            f"[Stage5] ✓ proactive_notification counts consistent: {gap_proactive_total} matches authoritative {state.proactive_notification_case_count}"
                        )

                # RECONCILE_SUMMARY: Log the transformation
                print(
                    f"[Stage5] RECONCILE_SUMMARY: "
                    f"LLM gap_table total: {original_gap_total} → "
                    f"reconciled: {reconciled_gap_total} / {total_cases} cases "
                    f"({reconciled_gap_total / total_cases * 100:.1f}%)"
                )

                # ASSERTION: Reconciled total must not exceed actual cases
                if reconciled_gap_total > total_cases:
                    raise RuntimeError(
                        f"[Stage5] VALIDATION FAILED: Gap table reconciled total {reconciled_gap_total} "
                        f"exceeds total cases {total_cases}. Budget tracking malfunction."
                    )

                if reconciled_gap_total > total_cases * 0.95:
                    print(
                        f"[Stage5] WARNING: Reconciled gap_table total {reconciled_gap_total} is {reconciled_gap_total / total_cases * 100:.1f}% of {total_cases} cases. "
                        f"This is legitimate if gaps span different sub_classifications with minimal overlap."
                    )

                print(f"[Stage5] ✓ gap_table case_counts reconciled with budget tracking (no double-counting)")

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

                    # Reconcile FAQ frequencies against actual case counts from journey_map and all_classified
                    print("[Stage5] Reconciling FAQ frequencies against journey_map and all_classified...")
                    state.validated_faqs = reconcile_faq_frequencies(validated, state.journey_map, state.all_classified)
                else:
                    # If no validations provided, assume all OK
                    for faq in state.faq_candidates:
                        faq.validation_status = 'OK'
                    # Reconcile FAQ frequencies against actual case counts from journey_map and all_classified
                    print("[Stage5] Reconciling FAQ frequencies against journey_map and all_classified...")
                    state.validated_faqs = reconcile_faq_frequencies(state.faq_candidates, state.journey_map, state.all_classified)

                break
        else:
            # No tool_use block found in this attempt
            print(f"[Stage5] WARNING: No tool call in LLM response on attempt {attempt}")

        if state.gap_table:
            print(f"[Stage5] ✓ gap_table populated with {len(state.gap_table)} rows on attempt {attempt}")
            break

        if attempt < MAX_ATTEMPTS:
            print(f"[Stage5] WARNING: gap_table empty after attempt {attempt} — retrying...")

    if not state.gap_table:
        print(f"[Stage5] WARNING: gap_table is empty after all {MAX_ATTEMPTS} LLM attempts — tool call may have failed or guidebook content unavailable")

    return state
