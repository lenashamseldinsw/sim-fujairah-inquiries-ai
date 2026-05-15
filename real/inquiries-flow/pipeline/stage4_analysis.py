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


JOURNEY_MAP_ONLY_TOOL = {
    "name": "extract_journey_map",
    "description": "Extract friction points in the customer journey grouped by sub-classification",
    "input_schema": {
        "type": "object",
        "properties": {
            "journey_map": {
                "type": "array",
                "description": "Friction points that caused customers to contact Fujairah Police",
                "items": {
                    "type": "object",
                    "properties": {
                        "top_level": {"type": "string"},
                        "sub_classification": {"type": "string"},
                        "cluster": {"type": "string"},
                        "cluster_ar": {"type": "string"},
                        "friction_point": {"type": "string"},
                        "friction_point_ar": {"type": "string"},
                        "root_cause_category": {
                            "type": "string",
                            "enum": ["missing_info", "inaccessible_info", "no_proactive_notification", "platform_bug", "policy_complexity"]
                        },
                        "case_count": {"type": "integer"}
                    },
                    "required": ["top_level", "sub_classification", "cluster_ar", "friction_point_ar", "root_cause_category", "case_count"]
                }
            }
        },
        "required": ["journey_map"]
    }
}


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

   CRITICAL DISAMBIGUATION — Traffic Fine Friction Points:
   When cases show a citizen disputing a fine because "the photo shows a different vehicle"
   or "the vehicle in the photo is not mine", the friction point is NOT "missing vehicle photo
   in fine notification". The notification EXISTS — the problem is the photo shows the WRONG vehicle.
   Correct friction_point_ar: "صورة المركبة في إشعار المخالفة تُظهر مركبة مختلفة"
   Correct root_cause_category: "platform_bug" (radar plate-matching system error)
   Do NOT classify this as "no_proactive_notification" — the notification was sent; the data is wrong.

   FRICTION POINT DISAMBIGUATION RULES:

   1. "صورة المركبة تُظهر مركبة مختلفة / مخالفة على متعامل لم يكن في الفجيرة":
      ONLY include cases where the citizen explicitly states:
      (a) the photo shows a different vehicle/plate, OR
      (b) they were physically absent from Fujairah on the date of the fine.
      Do NOT include cases where the citizen merely disputes the fine amount,
      requests removal of a fine confirmed non-existent, or asks about a fine
      procedure — those belong to other friction groups or are standalone طلب cases.

   2. "عدم وضوح حالة طلب تجديد الرخصة / تسجيل المركبة":
      ONLY include cases where the citizen submitted a renewal or registration
      request previously and is following up because they received NO status update.
      Do NOT include cases where the citizen is asking about requirements,
      making a first-time request, or following up on a fine-related matter.

   3. "اعتراض على صحة المخالفة — غياب قناة رقمية":
      ONLY include cases where the citizen is formally contesting the fine's
      validity AND references the lack of a digital appeal channel.
      Do NOT include cases that are mere inquiries about a fine, or cases where
      the fine was confirmed non-existent in the resolution.

   FREQUENCY COUNTING RULE (reinforced):
   Count each case exactly once. A case can only belong to ONE friction cluster.
   If a case has features matching multiple clusters, assign it to the cluster
   that best describes the PRIMARY friction experienced.

   CASE-LEVEL COUNTING — HOW TO DERIVE case_count:
   The section headers show the TOTAL cases per sub_classification group (e.g. "(8 cases)").
   These group totals are NOT the case_count for a friction point.

   case_count = the number of individual cases whose description OR resolution text
   contains explicit evidence of this specific friction point's qualifying criteria
   (defined in the disambiguation rules above).

   To count correctly:
   1. Read each case in the relevant group(s) individually.
   2. Ask: does THIS case's text explicitly demonstrate the friction?
      - For wrong-vehicle / absent-from-Fujairah: only count if the case text says
        "صورة المخالفة تُظهر سيارة أخرى" OR "لم أكن في الفجيرة" (or equivalent).
        Do NOT count cases that merely dispute a fine without this specific evidence.
      - For licence renewal / no status update: only count if the citizen previously
        submitted a request and is following up because they received NO update.
        Do NOT count first-time requests or requirement inquiries.
   3. case_count = sum of cases that pass step 2.

   Do NOT use the group header total as case_count.
   When in doubt about a case, do NOT count it.
   Under-counting is always safer than over-counting.

3. FAQs - Questions answered repeatedly in the resolution
   - Extract actual Q&A from good resolution responses
   - Tag with the top_level category
   - These should help customers self-serve next time
   - ISSUE 4: All output MUST be in Arabic only. Topic names, questions, answers, descriptions.
   - Proper nouns only (MOI, SMS, OTP, UAE PASS) may remain in Latin script.

   FREQUENCY COUNTING RULE (CRITICAL):
   Set frequency = the EXACT count of cases in the dataset where this specific question
   was the PRIMARY driver of the customer contact. Count each case exactly once.
   Do NOT extrapolate or estimate beyond the cases provided.
   Do NOT add "+" to frequencies — return the exact integer count.
   A frequency of 1 means exactly 1 case. Only assign frequency > 1 if multiple DISTINCT
   cases show the SAME question as their primary concern.
   Under-counting is better than over-counting — if unsure, use 1.

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
            # Exact sub_classification match — cap and deduct from budget
            # to prevent two friction points from double-counting the same cases
            remaining_budget = sub_classification_budget.get(friction.sub_classification, 0)
            reconciled_count = min(friction.case_count, remaining_budget)
            sub_classification_budget[friction.sub_classification] = max(
                0, remaining_budget - reconciled_count
            )
        else:
            # No exact match — LLM returned an approximate or merged sub_classification.
            # Try word-overlap against actual_counts keys to find the closest match.
            cluster_text = (
                friction.sub_classification or
                friction.cluster_ar or
                friction.cluster or
                friction.friction_point_ar or
                friction.friction_point or ""
            ).strip().lower()

            best_key = None
            best_overlap = 0
            for sub_key in actual_counts:
                if not sub_key:
                    continue
                sub_norm = sub_key.strip().lower()
                words_a = set(w for w in cluster_text.split() if len(w) >= 3)
                words_b = set(w for w in sub_norm.split() if len(w) >= 3)
                overlap = len(words_a & words_b)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_key = sub_key

            if best_key and best_overlap >= 1:
                # Plausible fuzzy match — use that key's remaining budget
                remaining_budget = sub_classification_budget.get(best_key, 0)
                reconciled_count = min(friction.case_count, remaining_budget)
                sub_classification_budget[best_key] = max(0, remaining_budget - reconciled_count)
                print(
                    f"[Stage4] FUZZY MATCH: friction '{friction.cluster_ar or friction.cluster}' "
                    f"sub_classification={friction.sub_classification!r} → matched '{best_key}' "
                    f"(overlap={best_overlap}) count: {friction.case_count} → {reconciled_count}"
                )
            else:
                # No match at all — cap against total remaining budget across all sub_classifications.
                # This ensures the LLM's inflated count can never exceed the remaining case pool,
                # even when sub_classification is completely unrecognisable.
                total_remaining = sum(sub_classification_budget.values())
                reconciled_count = min(friction.case_count, total_remaining)
                print(
                    f"[Stage4] WARNING: No match for friction '{friction.cluster_ar or friction.cluster}' "
                    f"(sub_classification={friction.sub_classification!r}) — "
                    f"capping against total_remaining={total_remaining}, was {friction.case_count} → {reconciled_count}"
                )

        reconciled_friction = friction.model_copy(update={"case_count": reconciled_count})
        reconciled_journey_map.append(reconciled_friction)

    # ── Cross-friction consistency check ──────────────────────────────────────
    # For friction entries sharing the same (top_level, root_cause_category),
    # combined case_count must not exceed the actual count of cases with that
    # top_level in all_classified. Fully data-driven — no hardcoded numbers.
    top_level_actual = defaultdict(int)
    for case in all_classified:
        if case.top_level:
            top_level_actual[case.top_level] += 1

    group_index = defaultdict(list)  # (top_level, root_cause_category) → [(idx, friction)]
    for i, friction in enumerate(reconciled_journey_map):
        key = (friction.top_level or '', friction.root_cause_category or '')
        group_index[key].append((i, friction))

    for (top_level, root_cause), group in group_index.items():
        if not top_level or len(group) < 2:
            continue
        combined = sum(f.case_count for _, f in group)
        ceiling = top_level_actual.get(top_level, combined)
        if combined > ceiling:
            print(
                f"[Stage4] CROSS-FRICTION CAP: top_level='{top_level}' "
                f"root_cause='{root_cause}' combined={combined} > ceiling={ceiling}. "
                f"Scaling down proportionally across {len(group)} friction entries."
            )
            for idx, friction in group:
                scaled = max(0, round(friction.case_count / combined * ceiling))
                reconciled_journey_map[idx] = friction.model_copy(
                    update={"case_count": scaled}
                )
            # Fix rounding drift so group total == ceiling exactly
            actual_total = sum(reconciled_journey_map[i].case_count for i, _ in group)
            if actual_total != ceiling:
                largest_i = max((i for i, _ in group),
                                key=lambda i: reconciled_journey_map[i].case_count)
                f = reconciled_journey_map[largest_i]
                reconciled_journey_map[largest_i] = f.model_copy(
                    update={"case_count": f.case_count + (ceiling - actual_total)}
                )

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


FAQ_ONLY_TOOL = {
    "name": "extract_faqs",
    "description": "Extract FAQ candidates from customer service case resolution responses.",
    "input_schema": {
        "type": "object",
        "properties": {
            "faq_candidates": {
                "type": "array",
                "description": "FAQ candidates extracted from resolution responses. Return at least one per sub-classification group.",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Question in English"},
                        "question_ar": {"type": "string", "description": "Question in Arabic"},
                        "answer": {"type": "string", "description": "Answer in English"},
                        "answer_ar": {"type": "string", "description": "Answer in Arabic"},
                        "frequency": {"type": "integer", "description": "How many cases relate to this FAQ"}
                    },
                    "required": ["question", "question_ar", "answer", "answer_ar", "frequency"]
                }
            }
        },
        "required": ["faq_candidates"]
    }
}


def _retry_faq_only(
    state: PipelineState,
    client: anthropic.Anthropic,
    cases_text: str,
) -> PipelineState:
    """
    Focused fallback retry for faq_candidates when all main Stage 4 attempts produced an empty result.

    Uses a minimal tool schema (faq_candidates only) and a shorter, laser-focused prompt to
    reduce cognitive load on the model. Runs up to 2 additional attempts.
    """
    system_prompt = (
        "You are an expert business analyst for government customer service. "
        "Your ONLY task is to identify the most common questions customers asked and the answers "
        "they received, based on the case descriptions and resolutions provided. "
        "For every sub-classification group provided, return at least one FAQ. "
        "All text (question_ar, answer_ar) MUST be in Arabic. "
        "frequency must not exceed the group size shown in the input."
    )

    base_user_content = (
        "Extract FAQ candidates from these customer service cases.\n"
        "Return at least one FAQ per sub-classification group.\n\n"
        + cases_text
    )

    for attempt in range(1, 3):
        nudge = (
            ""
            if attempt == 1
            else (
                "\n\nYour previous response returned an empty faq_candidates list. "
                "Every group listed above has a common question customers asked — identify it. "
                "Return at least one FAQ per group."
            )
        )
        print(f"[Stage4] faq-only focused retry (attempt {attempt}/2)...")
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8000,
                system=system_prompt,
                tools=[FAQ_ONLY_TOOL],
                tool_choice={"type": "any"},
                messages=[{"role": "user", "content": base_user_content + nudge}],
            )
        except Exception as e:
            print(f"[Stage4] faq-only retry attempt {attempt} API error: {e}")
            continue

        analysis = None
        for block in message.content:
            if block.type == "tool_use":
                analysis = block.input
                break

        if not analysis:
            print(f"[Stage4] faq-only retry attempt {attempt}: no tool call in response")
            continue

        raw_items = analysis.get("faq_candidates", [])
        if not raw_items:
            print(f"[Stage4] faq-only retry attempt {attempt}: LLM returned empty faq_candidates")
            continue

        state.faq_candidates = [
            FAQCandidate(
                question=f.get("question", ""),
                question_ar=f.get("question_ar", ""),
                answer=f.get("answer", ""),
                answer_ar=f.get("answer_ar", ""),
                frequency=f.get("frequency", 0),
                validation_status="PENDING",
            )
            for f in raw_items
        ]

        if state.faq_candidates:
            print(f"[Stage4] ✓ faq-only retry succeeded: {len(state.faq_candidates)} FAQ candidates")
            return state

    print("[Stage4] WARNING: faq-only focused retry also failed — faq_candidates remains empty.")
    return state


def _retry_journey_map_only(
    state: PipelineState,
    client: anthropic.Anthropic,
    cases_text: str,
) -> PipelineState:
    """
    Focused fallback retry for journey_map when all main Stage 4 attempts produced an empty result.

    Uses a minimal tool schema (journey_map only) and a shorter, laser-focused prompt to
    reduce cognitive load on the model and maximise the chance of getting friction points.
    Runs up to 2 additional attempts.
    """
    system_prompt = (
        "You are an expert business analyst for government customer service. "
        "Your ONLY task is to identify the friction points that caused customers to contact "
        "Fujairah Police — i.e., the reasons behind each enquiry group. "
        "For every sub-classification group provided, return at least one friction point. "
        "All text (cluster_ar, friction_point_ar) MUST be in Arabic. "
        "root_cause_category must be one of: missing_info, inaccessible_info, "
        "no_proactive_notification, platform_bug, policy_complexity. "
        "case_count must not exceed the group size shown in the input."
    )

    base_user_content = (
        "Identify the customer journey friction points for these case groups.\n"
        "Return at least one friction point per sub-classification group.\n\n"
        + cases_text
    )

    for attempt in range(1, 3):
        nudge = (
            ""
            if attempt == 1
            else (
                "\n\nYour previous response returned an empty journey_map. "
                "Every group listed above has a reason customers contacted support — "
                "identify it. Return at least one friction point per group."
            )
        )
        print(f"[Stage4] journey_map-only focused retry (attempt {attempt}/2)...")
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                system=system_prompt,
                tools=[JOURNEY_MAP_ONLY_TOOL],
                tool_choice={"type": "any"},
                messages=[{"role": "user", "content": base_user_content + nudge}],
            )
        except Exception as e:
            print(f"[Stage4] journey_map-only retry attempt {attempt} API error: {e}")
            continue

        analysis = None
        for block in message.content:
            if block.type == "tool_use":
                analysis = block.input
                break

        if not analysis:
            print(f"[Stage4] journey_map-only retry attempt {attempt}: no tool call in response")
            continue

        raw_items = analysis.get("journey_map", [])
        if not raw_items:
            print(f"[Stage4] journey_map-only retry attempt {attempt}: LLM returned empty journey_map")
            continue

        state.journey_map = [
            JourneyFriction(
                cluster=j.get("cluster", ""),
                cluster_ar=j.get("cluster_ar", ""),
                friction_point=j.get("friction_point", ""),
                friction_point_ar=j.get("friction_point_ar", ""),
                root_cause_category=j.get("root_cause_category", ""),
                case_count=j.get("case_count", 0),
                top_level=j.get("top_level", ""),
                sub_classification=j.get("sub_classification", ""),
            )
            for j in raw_items
        ]

        # Reconcile counts against ground truth
        state.journey_map, state.patterns, state.notification_opportunities = _reconcile_counts(
            state.journey_map,
            state.patterns,
            state.all_classified,
            state.notification_opportunities,
            state.proactive_notification_case_count,
        )

        if state.journey_map:
            print(f"[Stage4] ✓ journey_map-only retry succeeded: {len(state.journey_map)} friction points")
            return state

    print("[Stage4] WARNING: journey_map-only focused retry also failed — journey_map remains empty.")
    return state


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

    # Build exact sub_classification values list for the LLM to reference
    exact_sub_classifications = sorted(set(
        case.sub_classification for case in state.all_classified
        if case.sub_classification
    ))

    # Build case summary: all groups with samples from each
    cases_text = (
        "VALID sub_classification VALUES (copy these EXACTLY — no other values are accepted):\n"
        + "\n".join(f"  - {s}" for s in exact_sub_classifications)
        + "\n\n"
        + "Cases aggregated by classification (top_level > sub_classification):\n"
    )
    for (top_level, sub_classification), cases in sorted(groups.items()):
        cases_text += f"\n=== {top_level} > {sub_classification} ({len(cases)} cases) ===\n"
        # Sample up to 15 cases per cluster for diversity while staying within token budget
        for case in cases[:15]:
            cases_text += f"Case {case.case_number}:\n"
            cases_text += f"  Description: {case.description[:150]}\n"
            cases_text += f"  Resolution: {case.resolution_response[:150]}\n"

    base_user_content = f"Analyze these customer service cases grouped by two-level classification:\n{cases_text}"

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        # On retries, append an explicit nudge to return friction points
        if attempt == 1:
            user_content = base_user_content
        else:
            user_content = (
                base_user_content
                + "\n\nIMPORTANT: Your previous response returned an empty journey_map. "
                "Every real customer service dataset has friction points — reasons customers "
                "had to contact support that could have been prevented. Look carefully at the "
                "case descriptions and identify at least one friction point per sub-classification "
                "group. Do NOT return an empty journey_map array."
            )

        print(f"[Stage4] Calling LLM (attempt {attempt}/{max_attempts})...")
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=build_analysis_system_prompt(),
            tools=[ANALYSIS_TOOL],
            tool_choice={"type": "any"},  # Force tool use to prevent silent fallback to text
            messages=[{"role": "user", "content": user_content}],
        )

        # Extract tool use result
        analysis = None
        for block in message.content:
            if block.type == "tool_use":
                analysis = block.input
                break
        else:
            print(f"[Stage4] WARNING: No tool call in LLM response on attempt {attempt}")
            if attempt < max_attempts:
                continue

        if analysis is None:
            break

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

        # Parse FAQ candidates — only overwrite if the new result is non-empty,
        # or if state is currently empty. This preserves FAQs captured on an earlier
        # retry attempt that happened to return journey_map=[] but non-empty FAQs.
        if 'faq_candidates' in analysis:
            new_faqs = [
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
            if new_faqs or not state.faq_candidates:
                state.faq_candidates = new_faqs

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

        if state.journey_map:
            break  # Success — stop retrying

        if attempt < max_attempts:
            print(f"[Stage4] journey_map still empty after attempt {attempt} — retrying with explicit nudge...")
        else:
            print(
                f"[Stage4] WARNING: journey_map is empty after {max_attempts} attempts. "
                "Attempting focused journey_map-only retry..."
            )

    if not state.journey_map:
        state = _retry_journey_map_only(state, client, cases_text)

    if not state.journey_map:
        print(
            "[Stage4] WARNING: journey_map is empty after all attempts. "
            "The customer_journey report section will be skipped."
        )

    if not state.faq_candidates and state.all_classified:
        print("[Stage4] faq_candidates is empty after all main attempts — running focused faq-only retry...")
        state = _retry_faq_only(state, client, cases_text)

    if not state.faq_candidates:
        print(
            "[Stage4] WARNING: faq_candidates is empty after all attempts. "
            "The digital_transformation report section will be skipped."
        )

    return state
