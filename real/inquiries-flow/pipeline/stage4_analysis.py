"""
STAGE 4: Analysis (LLM)

Extracts:
- Patterns (clusters, sub-themes)
- Journey map (friction points, root causes)
- FAQ candidates (validated against guidebook in Stage 5)
- Self-service tags
- Notification opportunities

Groups cases by (top_level, sub_classification) tuple for domain-specific analysis.
Uses Claude API with tool-use for structured output.
Guidebook is chunked and embedded at startup (chromadb, in-memory).
"""

import json
import anthropic
from typing import Dict, Any, List
from collections import defaultdict
from .state import PipelineState, PatternCluster, JourneyFriction, FAQCandidate


ANALYSIS_TOOL = {
    "name": "analyze_cases",
    "description": "Analyze customer cases to extract patterns, friction points, FAQs, and opportunities",
    "input_schema": {
        "type": "object",
        "properties": {
            "patterns": {
                "type": "array",
                "description": "List of identified patterns/clusters (min 5 cases per cluster)",
                "items": {
                    "type": "object",
                    "properties": {
                        "top_level": {"type": "string"},
                        "sub_classification": {"type": "string"},
                        "cluster": {"type": "string"},
                        "cluster_ar": {"type": "string"},
                        "sub_theme": {"type": "string"},
                        "sub_theme_ar": {"type": "string"},
                        "case_count": {"type": "integer"},
                        "example_case_ids": {"type": "array", "items": {"type": "string"}}
                    }
                }
            },
            "journey_map": {
                "type": "array",
                "description": "Friction points in customer journey",
                "items": {
                    "type": "object",
                    "properties": {
                        "top_level": {"type": "string"},
                        "sub_classification": {"type": "string"},
                        "cluster": {"type": "string"},
                        "cluster_ar": {"type": "string"},
                        "friction_point": {"type": "string"},
                        "friction_point_ar": {"type": "string"},
                        "root_cause_category": {"type": "string", "enum": ["missing_info", "inaccessible_info", "no_proactive_notification", "platform_bug", "policy_complexity"]},
                        "case_count": {"type": "integer"}
                    }
                }
            },
            "faq_candidates": {
                "type": "array",
                "description": "FAQ candidates extracted from resolution responses",
                "items": {
                    "type": "object",
                    "properties": {
                        "top_level": {"type": "string"},
                        "question": {"type": "string"},
                        "question_ar": {"type": "string"},
                        "answer": {"type": "string"},
                        "answer_ar": {"type": "string"},
                        "frequency": {"type": "integer"}
                    }
                }
            },
            "self_service_tags": {
                "type": "array",
                "description": "Cases that could be self-serviceable",
                "items": {
                    "type": "object",
                    "properties": {
                        "top_level": {"type": "string"},
                        "sub_classification": {"type": "string"},
                        "cluster": {"type": "string"},
                        "self_service_tag": {"type": "string", "enum": ["fully_self_serviceable", "requires_system_access", "technical_incident"]},
                        "deflection_channel": {"type": "string"}
                    }
                }
            },
            "notification_opportunities": {
                "type": "array",
                "description": "Cases that could be eliminated with proactive notifications",
                "items": {
                    "type": "object",
                    "properties": {
                        "notification_type": {"type": "string"},
                        "cases_eliminated": {"type": "integer"},
                        "channel": {"type": "string"},
                        "content_summary": {"type": "string"}
                    }
                }
            },
            "proactive_notification_case_count": {
                "type": "integer",
                "description": (
                    "Count of cases across ALL sub-classifications where a proactive "
                    "SMS or email notification sent at the time of service (e.g., fine image, "
                    "delivery tracking link, or status update) would have prevented the customer "
                    "from contacting support at all. Count each case exactly once. "
                    "This is the authoritative upper bound for notification_opportunities."
                )
            }
        },
        "required": ["patterns", "journey_map", "faq_candidates", "notification_opportunities", "self_service_tags", "proactive_notification_case_count"]
    }
}


def build_analysis_system_prompt() -> str:
    """Build system prompt for analysis with two-level taxonomy."""
    return """You are an expert business analyst for government customer service.
Analyze customer inquiries and complaints to extract insights grouped by two-level classification.

ANALYSIS INSTRUCTIONS:

1. PATTERNS - Clusters of similar cases (min 5 cases each)
   - Group FIRST by top_level, THEN by sub_classification
   - Identify main theme and sub-themes within each group
   - Provide example case numbers
   - Return both top_level and sub_classification for each pattern

2. JOURNEY MAP - Friction points customers experience
   - What causes customers to contact Fujairah Police?
   - Map each friction point to a specific sub_classification
   - CRITICAL: sub_classification MUST be copied EXACTLY as it appears in the
     "=== top_level > sub_classification ===" section headers provided in the input.
     Do NOT paraphrase, translate, or invent sub_classification values.
     If a friction point spans multiple sub_classifications, pick the single best match.
   - What's the root cause? (missing info, inaccessible info, no proactive notification, platform bug, policy complexity)
   - How many cases per friction point?
   - Include top_level and sub_classification in each entry

3. FAQs - Questions answered repeatedly in the resolution
   - Extract actual Q&A from good resolution responses
   - Tag with the top_level category
   - These should help customers self-serve next time
   - ISSUE 4: All output MUST be in Arabic only. Topic names, questions, answers, descriptions.
   - Proper nouns only (MOI, SMS, OTP, UAE PASS) may remain in Latin script.

4. SELF-SERVICE TAGS - Which issues could be self-serviceable
   - Fully self-serviceable (customer can do alone)
   - Requires system access (customer needs online account/portal)
   - Technical incident (cannot self-serve)
   - Include top_level and sub_classification

5. NOTIFICATION OPPORTUNITIES - Where proactive messaging helps
   - Status Follow-up cases: send automatic status updates
   - Information gaps: send helpful tips before customer asks
   - Annual processes: send calendar reminders

   For proactive_notification_case_count: go through each case individually and count
   those where the customer's contact could have been fully prevented by a single
   proactive notification at the moment of service action (e.g., attaching the fine
   vehicle photo to the fine notification, sending a delivery tracking link when a
   document is dispatched, sending a status update when a case is processed). Do NOT
   count cases that require a human decision, system correction, policy review, or
   any back-and-forth interaction — those cannot be eliminated by notification alone.

CRITICAL: All output must be in Arabic only. This includes:
  - Table cell content (topics, descriptions, recommendations)
  - FAQ questions and answers
  - Friction point names and root cause text
  - All descriptive text
Only exceptions: Proper nouns such as 'MOI', 'SMS', 'OTP', 'UAE PASS' which remain in Latin script as universal brand names.
Be specific with example case IDs and counts.
"""


def _reconcile_counts(
    journey_map: list,
    patterns: list,
    all_classified: list,
    notification_opportunities: list,
    proactive_case_count: int,
) -> tuple[list, list, list]:
    """
    Reconcile LLM-supplied case_counts with authoritative counts from all_classified.

    For patterns: replace each case_count with the actual count of cases with that sub_classification.

    For journey_map: Cap LLM-supplied case_count at the remaining sub_classification budget
    to prevent double-counting across multiple friction points in the same group.
    Reconciled count never exceeds the actual sub_classification count.

    For notification_opportunities: cap cases_eliminated against the authoritative count
    from Stage 4 analysis (proactive_case_count), which is based on LLM per-case analysis.

    Args:
        journey_map: List of JourneyFriction objects from LLM
        patterns: List of PatternCluster objects from LLM
        all_classified: List of CaseRow objects (ground truth)
        notification_opportunities: List of notification opportunity dicts from LLM
        proactive_case_count: Authoritative count of cases that can be eliminated by proactive notification

    Returns:
        Tuple of (reconciled_journey_map, reconciled_patterns, reconciled_notification_opportunities)
    """
    # Build lookup: sub_classification → count (ground truth)
    actual_counts = defaultdict(int)
    for case in all_classified:
        actual_counts[case.sub_classification] += 1

    # Reconcile patterns: rebuild with updated case_count
    reconciled_patterns = []
    for pattern in patterns:
        actual_count = actual_counts.get(pattern.sub_classification, pattern.case_count)
        # Use model_copy to create a new instance with reconciled count (Pydantic immutability)
        reconciled_pattern = pattern.model_copy(update={"case_count": actual_count})
        reconciled_patterns.append(reconciled_pattern)

    # Reconcile journey_map: track how much of each sub_classification's budget has been allocated
    sub_classification_budget = dict(actual_counts)  # mutable copy

    reconciled_journey_map = []
    for friction in journey_map:
        actual_count = actual_counts.get(friction.sub_classification)
        if actual_count is not None:
            # Exact match — cap LLM count at actual, and deduct from budget
            # to prevent two friction points from double-counting the same cases
            remaining_budget = sub_classification_budget.get(friction.sub_classification, 0)
            reconciled_count = min(friction.case_count, remaining_budget)
            sub_classification_budget[friction.sub_classification] = max(
                0, remaining_budget - reconciled_count
            )
        else:
            # No exact match (sub_classification is None or approximate string from LLM)
            # Keep the LLM count rather than silently zeroing it out
            reconciled_count = friction.case_count
            print(
                f"[Stage4] WARNING: No exact sub_classification match for friction "
                f"'{friction.cluster_ar or friction.cluster}' "
                f"(sub_classification={friction.sub_classification!r}) — "
                f"keeping LLM count {friction.case_count}"
            )

        reconciled_friction = friction.model_copy(update={"case_count": reconciled_count})
        reconciled_journey_map.append(reconciled_friction)

    # Reconcile notification_opportunities: cap cases_eliminated against the authoritative
    # count from Stage 4 analysis (proactive_case_count), which is based on LLM per-case analysis.
    # Distribute the capped budget proportionally across all notification opportunities.

    # Cap proactive_case_count against actual total to prevent LLM inflation
    actual_total = len(all_classified)
    max_proactive_cases = min(proactive_case_count, actual_total)

    if proactive_case_count > actual_total:
        print(
            f"[Stage4] WARNING: proactive_notification_case_count={proactive_case_count} "
            f"exceeds total cases={actual_total}. Capping to {actual_total}."
        )

    # Sum what the LLM claimed across all notification opportunities
    llm_total = sum(
        n.get("cases_eliminated", 0) for n in notification_opportunities
        if isinstance(n.get("cases_eliminated"), int)
    )

    reconciled_notifications = []
    for n in notification_opportunities:
        llm_count = n.get("cases_eliminated", 0)
        if not isinstance(llm_count, int) or llm_total == 0:
            reconciled_notifications.append(n)
            continue

        # Scale proportionally, then round to int, minimum 1 if original > 0
        scaled = round(llm_count / llm_total * max_proactive_cases)
        scaled = max(1, scaled) if llm_count > 0 else 0
        reconciled_notifications.append({**n, "cases_eliminated": scaled})

    print(
        f"[Stage4] Reconciled notification_opportunities: "
        f"LLM total={llm_total} → capped to {max_proactive_cases} "
        f"(authoritative per-case count from LLM)"
    )

    return (reconciled_journey_map, reconciled_patterns, reconciled_notifications)


def run_stage4(state: PipelineState, api_key: str) -> PipelineState:
    """
    Stage 4: Analysis with two-level taxonomy grouping.

    Input: state with all_classified cases
    Output: state with patterns, journey_map, faq_candidates, etc.
    """
    if not state.all_classified:
        return state

    client = anthropic.Anthropic(api_key=api_key)

    # Aggregate cases by (top_level, sub_classification) tuple for structured analysis
    groups = defaultdict(list)
    for case in state.all_classified:
        key = (case.top_level, case.sub_classification)
        groups[key].append(case)

    # Build case summary: all groups with samples from each
    cases_text = "Cases aggregated by classification (top_level > sub_classification):\n"
    for (top_level, sub_classification), cases in sorted(groups.items()):
        cases_text += f"\n=== {top_level} > {sub_classification} ({len(cases)} cases) ===\n"
        # Sample up to 15 cases per cluster for diversity while staying within token budget
        for case in cases[:15]:
            cases_text += f"Case {case.case_number}:\n"
            cases_text += f"  Description: {case.description[:150]}\n"
            cases_text += f"  Resolution: {case.resolution_response[:150]}\n"

    # Call Claude with tool-use
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=build_analysis_system_prompt(),
        tools=[ANALYSIS_TOOL],
        tool_choice={"type": "any"},  # Force tool use to prevent silent fallback to text
        messages=[
            {
                "role": "user",
                "content": f"Analyze these customer service cases grouped by two-level classification:\n{cases_text}"
            }
        ]
    )

    # Extract tool use result
    for block in message.content:
        if block.type == "tool_use":
            analysis = block.input

            # Parse patterns
            if 'patterns' in analysis:
                state.patterns = [
                    PatternCluster(
                        cluster=p.get('cluster', ''),
                        cluster_ar=p.get('cluster_ar', ''),
                        sub_theme=p.get('sub_theme', ''),
                        sub_theme_ar=p.get('sub_theme_ar', ''),
                        case_count=p.get('case_count', 0),
                        example_case_ids=p.get('example_case_ids', []),
                        top_level=p.get('top_level', ''),
                        sub_classification=p.get('sub_classification', '')
                    )
                    for p in analysis.get('patterns', [])
                ]

            # Parse journey map
            if 'journey_map' in analysis:
                state.journey_map = [
                    JourneyFriction(
                        cluster=j.get('cluster', ''),
                        cluster_ar=j.get('cluster_ar', ''),
                        friction_point=j.get('friction_point', ''),
                        friction_point_ar=j.get('friction_point_ar', ''),
                        root_cause_category=j.get('root_cause_category', ''),
                        case_count=j.get('case_count', 0),
                        top_level=j.get('top_level', ''),
                        sub_classification=j.get('sub_classification', '')
                    )
                    for j in analysis.get('journey_map', [])
                ]

            # Parse FAQ candidates
            if 'faq_candidates' in analysis:
                state.faq_candidates = [
                    FAQCandidate(
                        question=f.get('question', ''),
                        question_ar=f.get('question_ar', ''),
                        answer=f.get('answer', ''),
                        answer_ar=f.get('answer_ar', ''),
                        frequency=f.get('frequency', 0),
                        validation_status='PENDING'
                    )
                    for f in analysis.get('faq_candidates', [])
                ]

            # Parse self-service tags
            if 'self_service_tags' in analysis:
                state.self_service_tags = analysis.get('self_service_tags', [])

            # Parse notification opportunities
            if 'notification_opportunities' in analysis:
                state.notification_opportunities = analysis.get('notification_opportunities', [])

            # Parse authoritative proactive notification case count
            if 'proactive_notification_case_count' in analysis:
                state.proactive_notification_case_count = int(analysis['proactive_notification_case_count'])

            # Reconcile counts: replace LLM-supplied case_counts with authoritative counts from state.all_classified
            print("[Stage4] Reconciling case counts with authoritative data from all_classified...")
            state.journey_map, state.patterns, state.notification_opportunities = _reconcile_counts(
                state.journey_map,
                state.patterns,
                state.all_classified,
                state.notification_opportunities,
                state.proactive_notification_case_count,
            )
            print(f"[Stage4] ✓ Reconciliation complete: {len(state.patterns)} patterns, {len(state.journey_map)} friction points")

            break
    else:
        # No tool call found — log warning
        print("[Stage4] WARNING: No tool call in LLM response — patterns, journey_map, etc. may be empty")

    return state
