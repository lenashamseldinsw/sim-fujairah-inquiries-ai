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
        "required": ["patterns", "journey_map", "notification_opportunities", "self_service_tags", "proactive_notification_case_count"]
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

4. SELF-SERVICE TAGS - Which issues could be self-serviceable
   - Fully self-serviceable (customer can do alone)
   - Requires system access (customer needs online account/portal)
   - Technical incident (cannot self-serve)
   - Include top_level and sub_classification

5. NOTIFICATION OPPORTUNITIES - Where proactive messaging helps

   DEFINITION — "proactive notification" means a single automated SMS or email sent
   at the moment of a service action that would have given the customer all the
   information they needed, so they never had to contact support at all.

   ELIGIBLE buckets — count a case ONLY if it falls into one of these three:

   A. WRONG VEHICLE IMAGE IN FINE NOTIFICATION
      The fine notification was sent but showed the wrong vehicle photo or plate.
      Adding the correct vehicle image to the notification SMS would have allowed
      the customer to verify instantly — no call needed.
      Sub-classification: "اعتراض على مخالفة مرورية" with السبب containing
      "صورة المركبة في الإشعار تُظهر مركبة مختلفة".

   B. NON-DELIVERY OF A DOCUMENT OR SERVICE ALREADY PROCESSED
      The service was completed on the police side (licence printed, ownership
      issued, payment confirmed) but the customer never received it or a tracking
      link. An SMS with a delivery/tracking reference at dispatch would have
      prevented all follow-up.
      Sub-classifications: "شكوى عن عدم استلام الخدمة" where السبب contains
      "شكوى عدم استقبال وثيقة أو خدمة", or "شكوى عن عدم استلام الخدمة" where
      payment was taken but service not delivered.

   C. PROCESSING DELAY WITH NO STATUS UPDATE
      The customer submitted a request and received zero automated updates, so they
      called to ask "what is happening with my case?" An automated milestone SMS
      (submitted → under review → approved/rejected) would have eliminated the call.
      Sub-classification: "شكوى عن تأخر المعالجة" / "شكوى على تأخر المعالجة".

   INELIGIBLE — do NOT count, regardless of how the case reads:

   ✗ "اعتراض صريح على مخالفة مرورية" — the citizen contests the fine's validity.
     A notification cannot un-issue a fine or decide its legitimacy. Requires human
     adjudication. NOT proactive-notification-preventable.

   ✗ "اعتراض على مخالفة صحيحة (من الحل)" — fine confirmed correct in resolution.
     Notification of a correctly-issued fine would not have prevented contact.

   ✗ "خلل تقني / عطل في النظام" — platform bug (failed payment, duplicate charge,
     system error). A notification cannot fix a broken system. Requires engineering.

   ✗ "طلب تعديل أو تحديث بيانات" — data correction request. Requires staff with
     system write access. A read-only notification cannot correct data.

   ✗ "بلاغ أمني أو مروري" — security or traffic incident report. Customer is
     reporting an event, not following up on a service. Cannot be pre-empted.

   ✗ Any case where the resolution shows the customer needed a human decision,
     a system fix, a policy review, or physical action (مراجعة / تدقيق / إجراء).

   For proactive_notification_case_count: go through each case individually.
   Apply the ELIGIBLE/INELIGIBLE rules above. Count each case at most once.
   Count only cases that clearly match bucket A, B, or C above.
   When in doubt, do NOT count — under-counting is safer than over-counting.

   Also set root_cause_category = "no_proactive_notification" ONLY for journey_map
   friction points that match buckets A, B, or C above. All other friction points
   must use: platform_bug, missing_info, inaccessible_info, or policy_complexity.

CRITICAL: All output must be in Arabic only. This includes:
  - Table cell content (topics, descriptions, recommendations)
  - FAQ questions and answers
  - Friction point names and root cause text
  - All descriptive text
Only exceptions: Proper nouns such as 'MOI', 'SMS', 'OTP', 'UAE PASS' which remain in Latin script as universal brand names.
Be specific with example case IDs and counts.
"""


def build_faq_system_prompt() -> str:
    """Build system prompt for dedicated FAQ extraction.

    Simplified and focused: case-by-case frequency matching + semantic distinctness.
    CRITICAL: Enforce CASE-LEVEL semantic matching, not just category grouping.
    """
    return """You are an expert business analyst for government customer service.
Your ONLY task is to extract FAQ candidates from customer service cases.

TASK:
Extract actual Q&A pairs from case resolutions that address the same customer question.
All output MUST be in Arabic only (except proper nouns: MOI, SMS, OTP, UAE PASS).

MANDATORY RULES:

1. FREQUENCY = EXACT CASE MATCH (CASE-LEVEL, NOT CATEGORY-LEVEL)
   frequency = count of cases in evidence_case_ids where this FAQ's answer directly resolves that case's issue.

   ⚠️ CRITICAL: Just because two cases are in the same sub_classification does NOT mean they have the same FAQ.
   ⚠️ CRITICAL: frequency ≠ sub_classification case_count (most common error)
   ⚠️ CRITICAL: frequency ≤ evidence_case_ids.length() (always)

   Example:
   Sub_classification has 15 service center inquiry cases:
   - 10 asking about location (different aspects)
   - 5 asking about hours of operation

   FAQ "Where is the service center?"
   - evidence_case_ids = [cases that ask about location] (only 10)
   - frequency = 10 (NOT 15)
   - Cases asking "what are the hours" don't answer a "where is it" question

   STRICT RULE: Read each evidence case. Ask: "Does this case's description/resolution explicitly
   contain the specific aspect of the FAQ question?" If not, EXCLUDE it from evidence.

2. SEMANTIC DISTINCTNESS = CASE-LEVEL MATCHING
   Two cases in the same category are NOT evidence for the same FAQ unless they ask about
   the SAME SPECIFIC ASPECT.

   ❌ WRONG: "Where is the service center?" + "What are the hours?"
              (both service centers, but DIFFERENT questions → different FAQs)
   ❌ WRONG: Case is about "can I call instead of visiting" but FAQ asks "where is it"
              (same category, different issue → not evidence)

   ✅ RIGHT: Cases explicitly ask about location → FAQ about location
   ✅ RIGHT: Cases explicitly ask about hours → FAQ about hours

   BEFORE assigning a case as evidence, verify:
   - Does the case mention the SPECIFIC DETAIL the FAQ asks about?
   - Or just that it's in the same general category?

3. MULTI-FAQ RULE
   When multiple FAQs address the same sub_classification:
   - Each FAQ must have a DIFFERENT frequency (not all equal to category total)
   - Sum of frequencies should NOT exceed sub_classification case_count

   Example: sub_classification has 15 service center cases
   - FAQ1 "Where is the service center?" → evidence=[case_that_asks_location] → frequency=10
   - FAQ2 "What are the hours?" → evidence=[case_that_asks_hours] → frequency=5
   - Total: 10+5=15 ✓ (matches actual, different FAQs for different questions)

   NOT: Both FAQs frequency=15 ✗ (inflation)

4. EVIDENCE REQUIREMENT
   For each FAQ:
   - List 2-3+ specific case IDs as evidence
   - EACH case must explicitly contain the specific detail the FAQ asks about
   - Do NOT include a case just because it's in the same category
   - If unsure, EXCLUDE the case
   - Conservative > aggressive: 2-3 cases that explicitly match > 15 cases loosely related

5. SUB_CLASSIFICATION ASSIGNMENT
   - Copy sub_classification EXACTLY from the "=== top_level > sub_classification ===" section headers
   - Do NOT invent or paraphrase
   - Do NOT omit (sub_classification is required)

OUTPUT STRUCTURE:
{
  "question_ar": "أين أقرب مركز خدمة؟",
  "answer_ar": "يمكنك العثور على المركز من خلال الخريطة على الموقع الرسمي",
  "sub_classification": "لا تحديد موقع مركز الخدمة",
  "frequency": 10,
  "evidence_case_ids": ["case1", "case2", "case3"],
  "top_level": "استفسار"
}

⚠️ RED FLAG VALIDATION (if ANY are true, restart):
1. All FAQs in same sub_classification have identical frequency? → ❌ WRONG (copied category total)
2. Any FAQ frequency = sub_classification case_count? → ❌ WRONG
3. Sum of FAQ frequencies >> sub_classification case_count? → ❌ WRONG (over-counting)
4. Evidence case doesn't explicitly mention the specific detail in the FAQ question? → ❌ WRONG (category-level, not case-level)

If any red flag is true, restart your extraction.
"""


def _overlap_ratio(text_a: str, text_b: str, min_word_len: int = 3) -> float:
    """
    Compute word overlap ratio between two Arabic strings.
    Returns the proportion of words in text_a that also appear in text_b.
    Words shorter than min_word_len are ignored (prepositions, particles, etc.).
    Returns 0.0 if text_a has no qualifying words.
    """
    def words(text):
        return set(w for w in (text or "").strip().split() if len(w) >= min_word_len)

    words_a = words(text_a)
    words_b = words(text_b)

    if not words_a:
        return 0.0

    return len(words_a & words_b) / len(words_a)


def _reconcile_counts(
    journey_map: list,
    patterns: list,
    all_classified: list,
    notification_opportunities: list,
    proactive_case_count: int,
) -> tuple[list, list, list, dict]:
    """
    Reconcile LLM-supplied case_counts with authoritative counts from all_classified.

    For patterns: replace each case_count with the actual count of cases with that sub_classification.

    For journey_map: Cap LLM-supplied case_count at the sub_classification's actual count.
    When multiple friction points share the same sub_classification, ensure their combined
    count never exceeds the sub_classification's actual total. Use word-overlap matching
    to distribute the budget proportionally when exact matches don't exist.

    For notification_opportunities: cap cases_eliminated against the authoritative count
    from Stage 4 analysis (proactive_case_count), which is based on LLM per-case analysis.

    Args:
        journey_map: List of JourneyFriction objects from LLM
        patterns: List of PatternCluster objects from LLM
        all_classified: List of CaseRow objects (ground truth)
        notification_opportunities: List of notification opportunity dicts from LLM
        proactive_case_count: Authoritative count of cases that can be eliminated by proactive notification

    Returns:
        Tuple of (reconciled_journey_map, reconciled_patterns, reconciled_notification_opportunities, per_type_counts)
        where per_type_counts is Dict[str, int] mapping notification_type → cases_eliminated (Issue 3 fix)
    """
    # Build lookup: sub_classification → count (ground truth)
    actual_counts = defaultdict(int)
    for case in all_classified:
        actual_counts[case.sub_classification] += 1

    # Reconcile patterns: rebuild with updated case_count
    reconciled_patterns = []
    for pattern in patterns:
        actual_count = actual_counts.get(pattern.sub_classification, pattern.case_count)
        reconciled_pattern = pattern.model_copy(update={"case_count": actual_count})
        reconciled_patterns.append(reconciled_pattern)

    # ── Reconcile journey_map: per-sub_classification cap ──────────────────────
    # Group friction entries by sub_classification to enforce per-group capping
    frictions_by_sub = defaultdict(list)
    for i, friction in enumerate(journey_map):
        frictions_by_sub[friction.sub_classification or ""].append((i, friction))

    reconciled_journey_map = [None] * len(journey_map)  # Pre-allocate to preserve indices

    for sub_class, friction_group in frictions_by_sub.items():
        actual_count = actual_counts.get(sub_class, 0)

        if len(friction_group) == 1 and actual_count > 0:
            # Single friction point for this sub_classification — use the actual count directly
            idx, friction = friction_group[0]
            reconciled_journey_map[idx] = friction.model_copy(update={"case_count": actual_count})
            print(
                f"[Stage4] SINGLE-FRICTION: sub_classification='{sub_class}' "
                f"has 1 friction point — using actual count {actual_count} directly"
            )

        elif len(friction_group) > 1:
            # Multiple friction points share this sub_classification
            # Try to match each to specific cases using word-overlap
            print(
                f"[Stage4] MULTI-FRICTION: sub_classification='{sub_class}' "
                f"has {len(friction_group)} friction points, actual count={actual_count}"
            )

            # For each friction in the group, count exact case matches
            matched_counts = {}
            total_matched = 0
            for idx, friction in friction_group:
                friction_label = (
                    friction.friction_point_ar or
                    friction.friction_point or
                    friction.cluster_ar or
                    friction.cluster or ""
                ).strip()

                # Count cases that match this friction based on classification_reason
                if friction_label:
                    matched = sum(
                        1 for case in all_classified
                        if case.sub_classification == sub_class
                        and _overlap_ratio(friction_label, case.classification_reason) >= 0.5
                    )
                else:
                    matched = 0

                matched_counts[idx] = matched
                total_matched += matched

            # If word-overlap matching found counts that sum to actual_count, use those
            if total_matched > 0 and total_matched <= actual_count:
                # Distribute any unmatched remainder proportionally
                remainder = actual_count - total_matched
                for idx, friction in friction_group:
                    base_count = matched_counts[idx]
                    if total_matched > 0:
                        prop_remainder = round(base_count / total_matched * remainder)
                    else:
                        prop_remainder = 0
                    reconciled_count = base_count + prop_remainder
                    reconciled_journey_map[idx] = friction.model_copy(
                        update={"case_count": reconciled_count}
                    )

            else:
                # Word-overlap matching failed or gave inflated counts
                # Distribute actual_count proportionally across friction points
                # based on their LLM-supplied case_count as a weight
                llm_total = sum(f.case_count for _, f in friction_group)
                if llm_total > 0:
                    for idx, friction in friction_group:
                        proportion = friction.case_count / llm_total
                        scaled_count = round(proportion * actual_count)
                        reconciled_journey_map[idx] = friction.model_copy(
                            update={"case_count": scaled_count}
                        )
                    # Fix any rounding drift
                    actual_total = sum(
                        reconciled_journey_map[i].case_count for i, _ in friction_group
                    )
                    if actual_total != actual_count:
                        # Add/subtract the difference from the largest entry
                        largest_idx = max(
                            (i for i, _ in friction_group),
                            key=lambda i: reconciled_journey_map[i].case_count
                        )
                        f = reconciled_journey_map[largest_idx]
                        reconciled_journey_map[largest_idx] = f.model_copy(
                            update={"case_count": f.case_count + (actual_count - actual_total)}
                        )
                else:
                    # No LLM counts to use as weights — split equally
                    equal_share = actual_count // len(friction_group)
                    remainder = actual_count % len(friction_group)
                    for idx_offset, (idx, friction) in enumerate(friction_group):
                        count = equal_share + (1 if idx_offset < remainder else 0)
                        reconciled_journey_map[idx] = friction.model_copy(
                            update={"case_count": count}
                        )

        else:
            # No actual cases for this sub_classification — zero out all frictions
            for idx, friction in friction_group:
                reconciled_journey_map[idx] = friction.model_copy(update={"case_count": 0})

    # ── FINAL ENFORCEMENT: Hard ceiling per sub_classification ───────────────────────
    # After all reconciliation, enforce hard cap: no friction point can exceed
    # the actual count of cases with that sub_classification.
    # This is the authoritative ceiling and must be respected absolutely.
    for i, friction in enumerate(reconciled_journey_map):
        sub = friction.sub_classification
        if sub and sub in actual_counts:
            actual_count = actual_counts[sub]
            if friction.case_count > actual_count:
                print(
                    f"[Stage4] HARD CEILING CLAMP: friction '{friction.friction_point_ar or friction.friction_point}' "
                    f"(sub='{sub}'): {friction.case_count} → {actual_count} "
                    f"(authoritative sub_classification total)"
                )
                reconciled_journey_map[i] = friction.model_copy(update={"case_count": actual_count})

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

    # Extract final per-type counts for cross-section consistency (Issue 3 fix)
    reconciled_counts_by_type: Dict[str, int] = {}
    for n in reconciled_notifications:
        ntype = n.get("notification_type") or n.get("content_summary") or ""
        if ntype:
            reconciled_counts_by_type[ntype] = n.get("cases_eliminated", 0)

    return (reconciled_journey_map, reconciled_patterns, reconciled_notifications, reconciled_counts_by_type)


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
                        "frequency": {"type": "integer", "description": "Count of evidence_case_ids where this FAQ's answer directly resolves that case. Must equal or be less than evidence_case_ids.length(). Never use sub_classification total."},
                        "top_level": {"type": "string", "description": "Top-level category (شكوى, استفسار, etc.)"},
                        "sub_classification": {"type": "string", "description": "The sub-classification this FAQ addresses — must match one of the section headers exactly"},
                        "evidence_case_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "2-3+ specific case IDs that this FAQ answers. Frequency = count of these cases where the Q&A resolves the issue."
                        }
                    },
                    "required": ["question", "question_ar", "answer", "answer_ar", "frequency", "sub_classification", "evidence_case_ids"]
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
    Fallback retry for faq_candidates using the dedicated FAQ extraction prompt.

    Uses the full FAQ_ONLY_TOOL and detailed build_faq_system_prompt() for maximum accuracy.
    Runs up to 2 additional attempts.
    """
    system_prompt = build_faq_system_prompt()

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
                top_level=f.get("top_level", ""),
                sub_classification=f.get("sub_classification", ""),
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
        (state.journey_map,
         state.patterns,
         state.notification_opportunities,
         state.reconciled_notification_counts) = _reconcile_counts(
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
                    validation_status='PENDING',
                    top_level=f.get('top_level', ''),
                    sub_classification=f.get('sub_classification', '')
                )
                for f in analysis.get('faq_candidates', [])
            ]
            if new_faqs or not state.faq_candidates:
                state.faq_candidates = new_faqs
                # Debug: Print FAQ frequencies to identify if LLM is using consistent values
                if state.faq_candidates:
                    print(f"[Stage4] DEBUG: Generated {len(state.faq_candidates)} FAQ candidates:")
                    for i, faq in enumerate(state.faq_candidates, 1):
                        q_preview = (faq.question_ar or faq.question or '')[:40]
                        print(f"  FAQ {i}: freq={faq.frequency} | {q_preview}...")

            # VALIDATION: Check FAQ sub_classifications against valid patterns (Fix 3)
            if state.patterns:
                valid_sub_classifications = {p.sub_classification for p in state.patterns if p.sub_classification}
                for faq in state.faq_candidates:
                    sub = faq.sub_classification or ''
                    if sub and sub not in valid_sub_classifications:
                        q_preview = (faq.question_ar or faq.question or '')[:50]
                        print(f"[Stage4] WARNING: FAQ '{q_preview}' assigned unknown sub_classification '{sub}' — "
                              f"will be rejected in Stage 5. Valid values: {valid_sub_classifications}")
                    elif not sub:
                        q_preview = (faq.question_ar or faq.question or '')[:50]
                        print(f"[Stage4] WARNING: FAQ '{q_preview}' has no sub_classification — "
                              f"will be rejected in Stage 5. Assign to one of: {valid_sub_classifications}")

        # Parse self-service tags
        if 'self_service_tags' in analysis:
            state.self_service_tags = analysis.get('self_service_tags', [])

        # Parse notification opportunities
        if 'notification_opportunities' in analysis:
            state.notification_opportunities = analysis.get('notification_opportunities', [])

        # Parse authoritative proactive notification case count
        if 'proactive_notification_case_count' in analysis:
            state.proactive_notification_case_count = int(analysis['proactive_notification_case_count'])

        # Validate proactive_notification_case_count against ground truth from journey_map.
        # Only journey_map entries whose sub_classification falls within the three
        # eligible notification buckets (wrong vehicle image, non-delivery, processing
        # delay) are counted — all other root_cause_category="no_proactive_notification"
        # entries are treated as mislabelled and silently excluded from the count.
        _PROACTIVE_ELIGIBLE_SUBS = {
            # Bucket A — wrong vehicle image in fine notification
            "اعتراض على مخالفة مرورية",
            # Bucket B — non-delivery of completed service
            "شكوى عن عدم استلام الخدمة",
            # Bucket C — processing delay with no status update
            "شكوى على تأخر المعالجة",
            "شكوى عن تأخر المعالجة",
        }
        proactive_friction_count = sum(
            f.case_count for f in state.journey_map
            if f.root_cause_category == "no_proactive_notification"
            and (f.sub_classification or "") in _PROACTIVE_ELIGIBLE_SUBS
        )
        # Log any journey_map entries that claimed no_proactive_notification but
        # were rejected by the allowlist so they can be reviewed.
        rejected = [
            f for f in state.journey_map
            if f.root_cause_category == "no_proactive_notification"
            and (f.sub_classification or "") not in _PROACTIVE_ELIGIBLE_SUBS
        ]
        if rejected:
            print(
                f"[Stage4] ALLOWLIST: {len(rejected)} journey_map entry(ies) claimed "
                f"no_proactive_notification but sub_classification not in eligible set — excluded:"
            )
            for r in rejected:
                print(f"  sub_classification={r.sub_classification!r}, "
                      f"friction={r.friction_point_ar or r.friction_point!r}, "
                      f"case_count={r.case_count}")

        if proactive_friction_count > 0 and proactive_friction_count != state.proactive_notification_case_count:
            print(
                f"[Stage4] VALIDATION: proactive_notification_case_count discrepancy detected:\n"
                f"  LLM returned: {state.proactive_notification_case_count}\n"
                f"  Allowlist-filtered ground truth: {proactive_friction_count}\n"
                f"  → Using allowlist-filtered count"
            )
            state.proactive_notification_case_count = proactive_friction_count
        elif proactive_friction_count == 0 and state.proactive_notification_case_count > 0:
            print(
                f"[Stage4] VALIDATION: no eligible no_proactive_notification entries found "
                f"in journey_map after allowlist filter. LLM count={state.proactive_notification_case_count} "
                f"retained (journey_map may be incomplete — will be re-checked in Stage 5)."
            )

        # Reconcile counts: replace LLM-supplied case_counts with authoritative counts from state.all_classified
        print("[Stage4] Reconciling case counts with authoritative data from all_classified...")
        (state.journey_map,
         state.patterns,
         state.notification_opportunities,
         state.reconciled_notification_counts) = _reconcile_counts(
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