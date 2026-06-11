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
from typing import Dict, Any, List, Optional
from collections import defaultdict
from .state import PipelineState, PatternCluster, JourneyFriction, FAQCandidate
from .json_utils import extract_methodology_context


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
                            "enum": [
                                "missing_info",
                                "inaccessible_info",
                                "no_proactive_notification",
                                "platform_bug",
                                "policy_complexity",
                                "wrong_channel_used",
                                "service_delivery_failure",
                                "processing_delay"
                            ]
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
                        "root_cause_category": {
                            "type": "string",
                            "enum": [
                                "missing_info",
                                "inaccessible_info",
                                "no_proactive_notification",
                                "platform_bug",
                                "policy_complexity",
                                "wrong_channel_used",
                                "service_delivery_failure",
                                "processing_delay"
                            ]
                        },
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
                        "content_summary": {"type": "string"},
                        "expected_impact": {
                            "type": "string",
                            "description": "Brief description of the expected business outcome (e.g., reduction in repeat complaints, improved citizen satisfaction). Must be grounded in the actual case analysis, not invented."
                        }
                    },
                    "required": ["notification_type", "cases_eliminated", "channel", "content_summary", "expected_impact"]
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


def build_analysis_system_prompt(methodology_context: Optional[Dict[str, Any]] = None) -> str:
    """Build system prompt for analysis with two-level taxonomy and complaints-specific disambiguation.

    Args:
        methodology_context: Optional extracted methodology sections for additional context
    """
    methodology_header = ""
    if methodology_context:
        # Build compact Arabic text block with methodology context
        methodology_header = "### السياق: منهجية إدارة الشكاوى الرسمية (الإصدار 4.0)\n\n"

        # Add receiving channels
        if methodology_context.get("5_1_receiving_channels"):
            channels = methodology_context["5_1_receiving_channels"].get("channels", [])
            if channels:
                methodology_header += "**القنوات الرسمية المعتمدة:**\n"
                methodology_header += "، ".join(channels) + "\n\n"

        # Add registration 24h rule
        if methodology_context.get("5_2_registration"):
            methodology_header += "**مبدأ التواصل الفوري:** يجب التواصل مع المتعامل خلال 24 ساعة من استلام الشكوى للاستيضاح عن المعلومات الناقصة.\n\n"

        # Add escalation rules
        if methodology_context.get("5_4_processing"):
            methodology_header += "**قواعد التصعيد:** يتم تصعيد الشكوى إلى مدير المركز في حال عدم القدرة على الحل في الوقت المحدد.\n\n"

        # Add proactive response
        if methodology_context.get("5_8_proactive_response"):
            methodology_header += "**المبدأ الاستباقي:** يجب متابعة وحصر جميع الشكاوى واتخاذ حلول استباقية لمنع تكرارها.\n\n"

    return methodology_header + """You are an expert business analyst for government customer service, specializing in complaint analysis.
Analyze customer complaints to extract insights grouped by two-level classification.

ANALYSIS INSTRUCTIONS:

1. PATTERNS - Clusters of similar cases (min 5 cases each)
   - Group FIRST by top_level, THEN by sub_classification
   - Identify main theme and sub-themes within each group
   - Provide example case numbers
   - Return both top_level and sub_classification for each pattern

2. JOURNEY MAP - Friction points customers experience
   - What causes customers to lodge complaints with Fujairah Police?
   - Map each friction point to a specific sub_classification
   - CRITICAL: sub_classification MUST be copied EXACTLY as it appears in the
     "=== top_level > sub_classification ===" section headers provided in the input.
     Do NOT paraphrase, translate, or invent sub_classification values.
     If a friction point spans multiple sub_classifications, pick the single best match.
   - What's the root cause? (missing_info, inaccessible_info, no_proactive_notification,
     platform_bug, policy_complexity, wrong_channel_used, service_delivery_failure, processing_delay)
   - How many cases per friction point?
   - Include top_level and sub_classification in each entry

   COMPLAINTS PIPELINE — CRITICAL DISAMBIGUATION:

   1. WRONG CHANNEL USED (wrong_channel_used):
      If a بلاغ (complaint) was submitted via the wrong channel (e.g., via inquiries channel
      instead of the dedicated complaints platform, or through an inappropriate method), the
      friction point is the channel miscommunication itself.
      - friction_point_ar: "تقديم البلاغ عبر القناة الخاطئة"
      - root_cause_category: "wrong_channel_used"
      This indicates a communication or awareness gap about complaint routing.

   2. TRAFFIC FINE DISPUTES - DISTINGUISH TYPES:
      Fine-related complaints come in three distinct categories. Use context to classify correctly:
      a) Disputed validity (citizen disputes the fine itself, questions radar accuracy, etc.)
      b) Photo mismatch (citizen states "the photo shows a different vehicle/plate" OR
         "I was not in Fujairah on that date")
      c) Appeal mechanism (citizen is attempting to formally contest or appeal the fine)
      Do NOT conflate these — each has different root causes and friction points.

   3. MISCONCEPTIONS IN FINE COMPLAINTS:
      Citizens may believe fines can be appealed/cancelled because they don't understand the
      process or lack confidence in its fairness. If the complaint shows skepticism about the
      fine process but no evidence of actual delivery failure, the friction is policy confusion.
      - friction_point_ar: "عدم وضوح آلية الاعتراض على المخالفات"
      - root_cause_category: "policy_complexity"

   4. REPEATED COMPLAINTS (مكررة pattern):
      If a complaint references an earlier complaint or case that was not resolved to the
      citizen's satisfaction, and this is a follow-up, the friction point is lack of
      proactive resolution follow-up.
      - friction_point_ar: "عدم المتابعة الاستباقية بعد تقديم بلاغ سابق"
      - root_cause_category: "no_proactive_notification"
      This indicates the system failed to proactively communicate closure/status.

   5. UNRESOLVED حفظ البلاغ (FILE PRESERVATION):
      If a citizen complains that a بلاغ was "حفظ" (filed/preserved) without follow-up or
      notification, the friction is absence of proactive status updates.
      - friction_point_ar: "حفظ البلاغ بدون إخطار الشاكي بالحالة"
      - root_cause_category: "no_proactive_notification"
      Customer did not receive ANY update after filing.

   6. OUT-OF-JURISDICTION CASES:
      If a complaint involves a matter clearly outside Fujairah Police authority (e.g., civil
      disputes, federal matters, or issues belonging to other emirates), the friction is
      policy/scope clarity.
      - friction_point_ar: "عدم وضوح نطاق الاختصاص والسلطات"
      - root_cause_category: "policy_complexity"
      Do NOT classify as service_delivery_failure — this is a scope issue, not a failure.

   7. SECURITY/CRIMINAL CASES (شكاوى أمنية وجنائية) — CRITICAL:
      Do NOT assign all security/criminal cases to a single friction point like "تأخر استجابة ميدانية".
      These cases are heterogeneous — each has distinct friction points:
      - Some involve حفظ البلاغ without notification (root_cause: no_proactive_notification)
      - Some involve processing_delay for specific sub-types (root_cause: processing_delay)
      - Some involve scope/jurisdiction issues (root_cause: policy_complexity)
      - Some involve wrong channel submission (root_cause: wrong_channel_used)
      ANALYZE EACH CASE INDIVIDUALLY and assign to the specific friction that matches.
      The case_count for any single friction point within this sub-classification must be
      derived from individual case evidence, NOT assumed to equal the sub-classification total.
      If you identify a single friction point that genuinely affects all 16 cases, provide
      strong evidence: list specific case IDs, quote relevant text from each case's description.

   FRICTION POINT COUNTING RULES:

   Each case belongs to exactly ONE friction cluster. When a case has multiple potential
   friction points, assign it to the PRIMARY one that best describes why the customer
   filed the complaint.

   case_count = the number of individual cases whose description OR resolution text contains
   explicit evidence of this specific friction point (using the disambiguation rules above).

   To count correctly:
   1. Read each case individually.
   2. Ask: does THIS case's text clearly demonstrate the friction?
      - For wrong_channel_used: does complaint say it was submitted wrongly or in wrong place?
      - For fine disputes: is the core complaint about validity, photo mismatch, or appeal?
      - For مكررة: does the complaint reference an earlier unresolved case?
      - For حفظ without notification: was the بلاغ filed but citizen received no updates?
      - For out-of-jurisdiction: is the issue clearly outside Fujairah's scope?
   3. case_count = sum of cases that pass step 2.

   Do NOT use the group header total as case_count.
   When in doubt, do NOT count the case.
   Under-counting is always safer than over-counting.

4. SELF-SERVICE TAGS - Which issues could be self-serviceable
   - Fully self-serviceable (customer can do alone)
   - Requires system access (customer needs online account/portal)
   - Technical incident (cannot self-serve)
   - Include top_level and sub_classification

5. NOTIFICATION OPPORTUNITIES - Where proactive messaging helps
   - Status Follow-up cases: send automatic status updates
   - Information gaps: send helpful tips before customer complains
   - Policy clarifications: proactively explain appeal processes

   For each notification opportunity:
   - notification_type: Brief type name (e.g., "إشعار فوري استلام" = immediate receipt notification)
   - cases_eliminated: Integer count of cases THIS specific notification would prevent
   - channel: Delivery method (e.g., "SMS + Push", "بريد إلكتروني + SMS", "رسالة تطبيق")
   - content_summary: Describe what information the notification includes and when it's sent.
     Examples: "إشعار عند كل تغيير + قيد المعالجة / مرفوض + السبب"
               "تنبية قبل انتهاء 30 يوم + معلومات الاستئناف مباشر + رابط مباشر للتحديث"
     Be specific about: WHEN it's sent (عند, قبل, عند كل, فور) and WHAT info it contains.
     Ground in actual case patterns from the data, not invented scenarios.
   - expected_impact: GROUNDED business outcome based on case analysis
     * Ground expected_impact in ACTUAL MEASURABLE impacts from the cases (e.g., if cases complained
       about lack of receipt confirmation, expected_impact should reflect "تقليص جوهري في شكاوى
       المتعاملين المكررة عند عدم تلقي الإشعار")
     * Do NOT invent percentage reductions unless explicitly shown in cases
     * Keep it factual and tied to the case evidence
     * Examples: "تقليص جوهري", "تقليل اصطدامات المتابعة", "إلغاء استفسارات ابتدائية"

   For proactive_notification_case_count: go through each case individually and count
   those where the customer's complaint could have been fully prevented by a single
   proactive notification at the moment of service action (e.g., sending appeal process
   information with a fine, notifying of complaint receipt and estimated timeline,
   sending proactive updates on complaint status). Do NOT count cases that require a
   human decision, system correction, policy review, or any back-and-forth interaction
   — those cannot be eliminated by notification alone.

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
Your ONLY task is to extract FAQ candidates from customer complaint cases.

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
   Sub_classification has 17 traffic violation cases:
   - 16 about Fujairah fines, errors, delays, disputes
   - 1 case about a fine issued BY OMAN (different jurisdiction)

   FAQ "Can I appeal a fine issued by OMAN through Fujairah Police?"
   - evidence_case_ids = [case_that_mentions_oman] (only 1)
   - frequency = 1 (NOT 17)
   - Cases mentioning only "Fujairah fines" don't answer an "Oman fine" question

   STRICT RULE: Read each evidence case. Ask: "Does this case's description/resolution explicitly
   contain the specific aspect of the FAQ question?" If not, EXCLUDE it from evidence.

2. SEMANTIC DISTINCTNESS = CASE-LEVEL MATCHING
   Two cases in the same category are NOT evidence for the same FAQ unless they ask about
   the SAME SPECIFIC ASPECT.

   ❌ WRONG: "Appeal a Fujairah traffic violation" + "Appeal an Oman traffic violation"
              (both traffic appeals, but DIFFERENT jurisdictions → different FAQs)
   ❌ WRONG: Case is about "error in vehicle photo" but FAQ asks "how to appeal"
              (same category, different issue → not evidence)

   ✅ RIGHT: Cases explicitly mention Oman → FAQ about Oman appeals
   ✅ RIGHT: Cases ask about documents needed → FAQ about required documents

   BEFORE assigning a case as evidence, verify:
   - Does the case mention the SPECIFIC DETAIL the FAQ asks about?
   - Or just that it's in the same general category?

3. MULTI-FAQ RULE
   When multiple FAQs address the same sub_classification:
   - Each FAQ must have a DIFFERENT frequency (not all equal to category total)
   - Sum of frequencies should NOT exceed sub_classification case_count

   Example: sub_classification has 12 appeal cases
   - FAQ1 "Can I appeal from another emirate?" → evidence=[case_that_mentions_emirate] → frequency=2
   - FAQ2 "What documents do I need?" → evidence=[case_that_mentions_documents] → frequency=8
   - FAQ3 "Where do I submit?" → evidence=[case_that_mentions_location] → frequency=2
   - Total: 2+8+2=12 ✓ (matches actual, different FAQs for different questions)

   NOT: All 3 FAQs frequency=12 ✗ (inflation)

4. EVIDENCE REQUIREMENT
   For each FAQ:
   - List 2-3+ specific case IDs as evidence
   - EACH case must explicitly contain the specific detail the FAQ asks about
   - Do NOT include a case just because it's in the same category
   - If unsure, EXCLUDE the case
   - Conservative > aggressive: 2-3 cases that explicitly match > 12 cases loosely related

5. SUB_CLASSIFICATION ASSIGNMENT
   - Copy sub_classification EXACTLY from the "=== top_level > sub_classification ===" section headers
   - Do NOT invent or paraphrase
   - Do NOT omit (sub_classification is required)

OUTPUT STRUCTURE:
{
  "question_ar": "هل يمكنني الاعتراض على مخالفة مرورية من سلطنة عمان؟",
  "answer_ar": "نعم، يمكنك تقديم اعتراض على سلطنة عمان عبر شرطة الفجيرة إذا...",
  "sub_classification": "اعتراض على مخالفة مرورية",
  "frequency": 2,
  "evidence_case_ids": ["case1", "case2"],
  "top_level": "شكوى"
}

⚠️ RED FLAG VALIDATION (if ANY are true, restart):
1. All FAQs in same sub_classification have identical frequency? → ❌ WRONG (copied category total)
2. Any FAQ frequency = sub_classification case_count? → ❌ WRONG
3. Sum of FAQ frequencies >> sub_classification case_count? → ❌ WRONG (over-counting)
4. Evidence case doesn't explicitly mention the specific detail in the FAQ question? → ❌ WRONG (category-level, not case-level)

If any red flag is true, restart your extraction.
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
            reconciled_count = remaining_budget
            sub_classification_budget[friction.sub_classification] = 0
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
                reconciled_count = remaining_budget
                sub_classification_budget[best_key] = 0
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

    # ── TASK 4 FIX: Cap single friction point claims within sub_classifications ───
    # Prevent a single friction point from claiming >50% of a sub_classification's total
    # UNLESS it is the ONLY friction point for that sub_classification.
    sub_to_frictions = defaultdict(list)
    for i, friction in enumerate(reconciled_journey_map):
        if friction.sub_classification:
            sub_to_frictions[friction.sub_classification].append((i, friction))

    for sub, friction_list in sub_to_frictions.items():
        if len(friction_list) < 2:
            continue  # Only apply cap when multiple friction points match same sub

        sub_actual = actual_counts.get(sub, 0)
        max_allowed = sub_actual * 0.5  # 50% cap per friction point

        for i, friction in friction_list:
            if friction.case_count > max_allowed:
                capped_count = round(max_allowed)
                print(
                    f"[Stage4] TASK 4 CAP: friction '{friction.friction_point_ar or friction.friction_point}' "
                    f"in sub_classification '{sub}' claims {friction.case_count} cases. "
                    f"This exceeds 50% of sub_classification total ({sub_actual} cases). "
                    f"Multiple friction points match this sub — capping to {capped_count} cases."
                )
                # ENFORCE the cap: update the reconciled_journey_map entry
                reconciled_journey_map[i] = friction.model_copy(update={"case_count": capped_count})

    # ── FIX 4: Reconcile notification_opportunities ────────────────────────────────
    # Cap cases_eliminated against:
    #   1. Total cases (proactive_case_count sanity check)
    #   2. Per-sub-classification sizes (prevent claiming more than actual sub-class has)

    # Step 1: Build sub-classification counts (ground truth)
    actual_sub_counts = defaultdict(int)
    for case in all_classified:
        if case.sub_classification:
            actual_sub_counts[case.sub_classification] += 1

    # Step 2: Cap proactive_case_count against actual total
    actual_total = len(all_classified)
    max_proactive_cases = min(proactive_case_count, actual_total)

    if proactive_case_count > actual_total:
        print(
            f"[Stage4] WARNING: proactive_notification_case_count={proactive_case_count} "
            f"exceeds total cases={actual_total}. Capping to {actual_total}."
        )

    # Step 3: Scale notification cases_eliminated proportionally to fit within proactive ceiling
    # Don't cap individually — that would allow multiple notifications to each exceed the ceiling.
    # Instead, compute total claimed, then scale all notifications proportionally.
    claimed_total = sum(
        n.get("cases_eliminated", 0)
        for n in notification_opportunities
        if n.get("cases_eliminated", 0) > 0
    )

    reconciled_notifications = []
    if claimed_total > max_proactive_cases and claimed_total > 0:
        # Scale all notifications proportionally to fit within ceiling
        scale_factor = max_proactive_cases / claimed_total
        print(
            f"[Stage4] Scaling notification_opportunities: total claimed {claimed_total} → "
            f"{max_proactive_cases} (scale factor: {scale_factor:.2f})"
        )

        for n in notification_opportunities:
            original_claimed = n.get("cases_eliminated", 0)

            if original_claimed < 1:
                reconciled_notifications.append(n)
                continue

            scaled_count = int(round(original_claimed * scale_factor))
            notification_type = n.get("notification_type", "")

            if scaled_count != original_claimed:
                print(
                    f"[Stage4] Scaled notification '{notification_type}' "
                    f"cases_eliminated: {original_claimed} → {scaled_count}"
                )

            reconciled_notifications.append({**n, "cases_eliminated": scaled_count})
    else:
        # Claimed total already fits within ceiling, use as-is
        reconciled_notifications = notification_opportunities

    print(
        f"[Stage4] ✓ Reconciled notification_opportunities: total {claimed_total} cases "
        f"within ceiling {max_proactive_cases}"
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
                        "top_level": {"type": "string", "description": "Official complaint category (e.g., 'شكوى', 'استفسار', 'طلب')"},
                        "question": {"type": "string", "description": "Question in English"},
                        "question_ar": {"type": "string", "description": "Question in Arabic"},
                        "answer": {"type": "string", "description": "Answer in English"},
                        "answer_ar": {"type": "string", "description": "Answer in Arabic"},
                        "frequency": {"type": "integer", "description": "Count of evidence_case_ids where this FAQ's answer directly resolves that case. Must equal or be less than evidence_case_ids.length(). Never use sub_classification total."},
                        "sub_classification": {
                            "type": "string",
                            "description": (
                                "The sub_classification value from the patterns list that this FAQ "
                                "most directly addresses. Must be copied verbatim from a sub_classification "
                                "in the provided patterns."
                            )
                        },
                        "evidence_case_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "2-3 specific case IDs that demonstrate this FAQ's relevance to actual customer issues"
                        }
                    },
                    "required": ["top_level", "question", "question_ar", "answer", "answer_ar", "frequency", "sub_classification", "evidence_case_ids"]
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
        "Extract FAQ candidates from these customer complaint cases.\n"
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
        "You are an expert business analyst for government customer service, specializing in complaint analysis. "
        "Your ONLY task is to identify the friction points that caused customers to file complaints "
        "with Fujairah Police — i.e., the reasons behind each complaint group. "
        "For every sub-classification group provided, return at least one friction point. "
        "All text (cluster_ar, friction_point_ar) MUST be in Arabic. "
        "root_cause_category must be one of: missing_info, inaccessible_info, "
        "no_proactive_notification, platform_bug, policy_complexity, wrong_channel_used, "
        "service_delivery_failure, processing_delay. "
        "case_count must not exceed the group size shown in the input."
    )

    base_user_content = (
        "Identify the customer journey friction points for these complaint groups.\n"
        "Return at least one friction point per sub-classification group.\n\n"
        + cases_text
    )

    for attempt in range(1, 3):
        nudge = (
            ""
            if attempt == 1
            else (
                "\n\nYour previous response returned an empty journey_map. "
                "Every group listed above has a reason customers filed a complaint — "
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
                case_ids=j.get("case_ids", []),
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

    # Extract methodology context if present
    methodology_context = None
    if state.complaints_methodology:
        methodology_context = extract_methodology_context(
            state.complaints_methodology,
            [
                "5_procedures.5_1_receiving_channels",
                "5_procedures.5_2_registration",
                "5_procedures.5_4_processing",
                "5_procedures.5_8_proactive_response"
            ]
        )
        if any(methodology_context.values()):
            print("[Stage4] Loaded methodology context for LLM prompt")

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

    base_user_content = f"Analyze these customer complaint cases grouped by two-level classification:\n{cases_text}"

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
                "filed complaints that could have been prevented. Look carefully at the "
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
                    case_ids=j.get('case_ids', []),
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
                # Debug: Print FAQ frequencies AND evidence_case_ids to verify semantic matching
                if state.faq_candidates:
                    print(f"[Stage4] DEBUG: Generated {len(state.faq_candidates)} FAQ candidates:")
                    for i, faq in enumerate(state.faq_candidates, 1):
                        q_preview = (faq.question_ar or faq.question or '')[:40]
                        evidence_ids = getattr(faq, 'evidence_case_ids', [])
                        print(f"  FAQ {i}: freq={faq.frequency} | evidence={evidence_ids} | {q_preview}...")

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

        # TASK 6 FIX: Update proactive_notification_case_count to match reconciled notification_opportunities
        # This ensures consistency across all sections (state value matches computed value from notifications)
        if state.notification_opportunities:
            original_count = state.proactive_notification_case_count
            state.proactive_notification_case_count = sum(
                int(n.get("cases_eliminated", n.get("case_count", 0)))
                for n in state.notification_opportunities
            )
            if state.proactive_notification_case_count != original_count:
                print(
                    f"[Stage4] TASK 6 UPDATE: proactive_notification_case_count {original_count} → "
                    f"{state.proactive_notification_case_count} (post-reconciliation from notification_opportunities)"
                )
            else:
                print(
                    f"[Stage4] ✓ proactive_notification_case_count consistent: {state.proactive_notification_case_count}"
                )

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
