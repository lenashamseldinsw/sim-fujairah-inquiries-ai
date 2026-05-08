"""
STAGE 3: LLM Classifier

Classifies low-confidence cases from Stage 2 using Claude API.
Uses two-level taxonomy: top_level and sub_classification.
Uses tool-use with array structure for batch efficiency.
Cases with LLM confidence < 0.65 go to human_review_queue.
Uses Haiku for speed and cost efficiency on this high-volume task.
"""

import json
import anthropic
from typing import Dict, Any, List
from .state import PipelineState, CaseRow
from .stage2_rules import SUB_CLASSIFICATIONS

# Confidence threshold — lowered from 0.85. At 0.85, valid classifications (0.65–0.8) got discarded.
LLM_LOW_CONFIDENCE_THRESHOLD = 0.65

# Build all sub-classifications into a flat list for enum
ALL_SUB_CLASSIFICATIONS = []
for subs in SUB_CLASSIFICATIONS.values():
    ALL_SUB_CLASSIFICATIONS.extend(subs)

# Tool schema for batch classification with two-level taxonomy
CLASSIFIER_TOOL = {
    "name": "classify_cases_batch",
    "description": "Classify a batch of customer service cases using two-level taxonomy. Return one classification per case in order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "description": "One entry per case, in the same order as the input",
                "items": {
                    "type": "object",
                    "properties": {
                        "case_number": {
                            "type": "string",
                            "description": "The case number exactly as provided"
                        },
                        "top_level": {
                            "type": "string",
                            "enum": ["شكوى", "استفسار", "طلب", "شكر وثناء"],
                            "description": "Top-level category"
                        },
                        "sub_classification": {
                            "type": "string",
                            "enum": ALL_SUB_CLASSIFICATIONS,
                            "description": "Domain-specific sub-classification"
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0
                        },
                        "reason": {
                            "type": "string",
                            "description": "1-2 sentence explanation in Arabic only"
                        }
                    },
                    "required": ["case_number", "top_level", "sub_classification", "confidence", "reason"]
                }
            }
        },
        "required": ["classifications"]
    }
}


def build_system_prompt() -> str:
    """Build system prompt with two-level taxonomy."""
    return """You are an expert customer service analyst for Fujairah Police.
Classify customer inquiries using a two-level taxonomy.

TOP-LEVEL CATEGORIES (4 types):
- شكوى (Complaint) - Formal dissatisfaction or issue report
- استفسار (Inquiry) - Request for information or clarification
- طلب (Request) - Requesting a specific service or action
- شكر وثناء (Praise) - Positive feedback or compliment

COMPLAINT SUB-CLASSIFICATIONS (شكوى):
- تقديم بلاغ أمني أو مروري (Filing a security/traffic report)
- اعتراض على مخالفة مرورية (Contesting a traffic fine)
- شكوى عامة (General complaint)
- شكوى عن مخالفة مشكوك فيها (Suspected erroneous fine)
- شكوى على خطأ تقني أو في النظام (Technical/system error)
- شكوى عن عدم استلام الخدمة (Non-receipt of document/service)
- شكوى على عدم الرد (Lack of response)
- شكوى على تأخر المعالجة (Processing delay)

REQUEST SUB-CLASSIFICATIONS (طلب):
- طلب توصيل أو استلام (Document delivery/collection)
- طلب خدمة عام (General service request)
- طلب تصريح سلاح أو ترخيص (Weapon permit/license request)
- طلب تجديد رخصة أو ملكية (License/vehicle registration renewal)
- طلب إصدار شهادة أو وثيقة (Certificate/document issuance)
- طلب سداد مخالفة (Traffic fine payment)
- طلب فتح ملف أو بلاغ (Opening a formal case/report)
- طلب تعديل أو تحديث بيانات (Data update/correction)
- طلب تصريح خاص (Special permit)
- متابعة طلب مقدم (Follow-up on submitted request)

INQUIRY SUB-CLASSIFICATIONS (استفسار):
- استفسار عام (General inquiry)
- استفسار عن الرخص والمركبات (License & vehicle inquiry)
- استفسار عن الإجراءات والمتطلبات (Procedural requirements)
- استفسار تقني (Technical/app inquiry)
- استفسار عن البلاغات الأمنية (Security report inquiry)
- استفسار عن الأسلحة والتراخيص (Weapons licensing inquiry)

PRAISE SUB-CLASSIFICATIONS (شكر وثناء):
- شكر وتقدير عام (General praise)

CLASSIFICATION GUIDELINES:

⚠️  RECLASSIFICATION INDICATORS — These must override first impressions:

1. SERVICE FAILURE INDICATORS → CLASSIFY AS شكوى (COMPLAINT):
   - Money charged but service not delivered (e.g., "تم دفع مبلغ X دون استلام الخدمة")
   - Service promised but not received despite payment
   - System error caused financial or operational loss
   - Document issued incorrectly or not issued despite full payment
   → KEY: "Service failure" = Complaint, even if worded as neutral statement

2. UNRESOLVED FOLLOW-UP ISSUES → CLASSIFY AS طلب (REQUEST):
   - Customer circles back asking "what do I do now?" or "what's next?"
   - Process described as stuck or incomplete (e.g., "في دوامة" / "كل مرة نفس الموضوع")
   - Asks for specific action to resolve (e.g., "هل يحق لي..." / "ماذا يجب أن أفعل")
   - Seeks permission or eligibility (e.g., "هل يحق لي الحصول على")
   → KEY: "What should I do?" = Request for action

3. PURE INFORMATION-SEEKING → CLASSIFY AS استفسار (INQUIRY):
   - Customer only asks "what is the status?" or "when will X happen?"
   - No complaint about delay, only asks for information about timeline
   - No service failure mentioned
   - No request for action to resolve — just wants to know facts
   → KEY: "Tell me about X" (no problem statement) = Inquiry

SPECIAL RECLASSIFICATION RULES:

Rule A — Multi-part messages:
   If a case contains BOTH a complaint AND a request/inquiry:
   - Complaint component takes precedence → Classify as شكوى
   - Only if purely neutral information-seeking: classify as استفسار

Rule B — Authority/process confusion:
   If customer is stuck in bureaucratic loops (bounced between departments):
   - AND asking to resolve it → طلب (Request for action to untangle)
   - AND only asking for clarification → استفسار (Inquiry about jurisdiction)

Rule C — Payment issues:
   - "دفعت مبلغ X دون استلام" → شكوى (COMPLAINT: paid without service)
   - "كم المبلغ المطلوب" → استفسار (INQUIRY: asking fee amount)
   - "ماذا أفعل لاسترجاع المبلغ" → طلب (REQUEST: asking for refund action)

Rule D — Resolution reveals the true nature:
   Always read the Resolution Response to determine what actually happened,
   not just what the customer said. If the resolution shows any of the following,
   the case is a شكوى (COMPLAINT) regardless of how neutrally the description is worded:
   - A refund was issued ("تم إعادة المبلغ" / "تم استرداد")
   - A system error was confirmed or corrected ("تم تحديث البرنامج" / "خطأ في النظام")
   - A service failure was acknowledged ("تبين وجود خلل" / "لم يتم الإصدار")
   - Escalation or coordination with another department was required to fix a problem
   → KEY: If the resolution fixed something that was broken, a failure occurred —
     the customer's neutral phrasing does not change the classification.

RULES:
- Base classification on actual customer intent and situation, not just keywords.
- The Description field reveals what actually happened — use it to override keywords.
- The Resolution Response shows how it was handled — compare to what customer describes.
- Service failure + no resolution = Complaint. Stuck process + asking to fix = Request.
- Sub-classification MUST be a valid child of the chosen top_level.
- Return case_number exactly as provided.
- Return one entry per case in input order.
- ALL OUTPUT MUST BE IN ARABIC ONLY. Provide reasons (explanations) entirely in Arabic."""


def classify_with_llm(client: anthropic.Anthropic, cases: List[Dict], progress_callback=None) -> List[Dict]:
    """
    Classify cases using Claude Haiku with array tool-use for proper batch handling.

    Args:
        client: Anthropic API client
        cases: List of case dicts
        progress_callback: Optional function(batch_num, total_batches)

    Returns:
        List of classification results {case_number, top_level, sub_classification, confidence, reason}
    """
    results = []
    batch_size = 25  # Reduced from 30 — balances efficiency with response completeness (each ~150 tokens = 2250 total, safe margin under 8000 max)

    total_batches = (len(cases) + batch_size - 1) // batch_size
    print(f"[Stage3] Processing {len(cases)} cases in {total_batches} batches of {batch_size}")

    for batch_num, batch_idx in enumerate(range(0, len(cases), batch_size), 1):
        batch = cases[batch_idx:batch_idx + batch_size]

        if progress_callback:
            pct = 0.30 + ((batch_num / total_batches) * 0.10)  # Progress spans 30% to 40%
            progress_callback(pct, f"معالجة الدفعة {batch_num}/{total_batches}", f"Processing batch {batch_num}/{total_batches}")

        print(f"[Stage3] Batch {batch_num}/{total_batches} ({len(batch)} cases)...")

        # Build case list with Stage 2 hints
        cases_text = "\n\n".join([
            f"Case Number: {case.get('case_number', 'N/A')}\n"
            f"Description: {case.get('description', '').strip()}\n"
            f"Resolution: {case.get('resolution_response', '').strip()}\n"
            f"Service: {case.get('service_name', '')}\n"
            f"Channel: {case.get('case_channel', '')}\n"
            f"Stage 2 hint: {case.get('top_level', 'N/A')} > {case.get('sub_classification', 'N/A')}"
            for case in batch
        ])

        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",  # Haiku for speed/cost on bulk classification
                max_tokens=8000,  # Increased from 4000 — need room for 30 case classifications (each ~150 tokens)
                system=build_system_prompt(),
                tools=[CLASSIFIER_TOOL],
                tool_choice={"type": "any"},  # Force tool use — no free-text fallback
                messages=[{
                    "role": "user",
                    "content": (
                        f"Classify these {len(batch)} cases using the two-level taxonomy. "
                        f"Return exactly one entry per case in the classifications array.\n\n"
                        f"{cases_text}"
                    )
                }]
            )

            # Extract tool call — should contain all classifications in one array
            tool_calls = [b for b in message.content if b.type == "tool_use"]

            # Check for truncation
            if message.stop_reason == "max_tokens":
                print(f"[Stage3] ERROR: Batch {batch_num} response was truncated (hit max_tokens limit)")
                print(f"[Stage3] Current max_tokens: 8000. Consider increasing further or reducing batch_size.")

            if tool_calls:
                classifications = tool_calls[0].input.get("classifications", [])

                # Check if we got all expected classifications
                if len(classifications) < len(batch):
                    print(f"[Stage3] WARNING: Batch {batch_num} incomplete — got {len(classifications)}/{len(batch)} classifications")
                    print(f"[Stage3] stop_reason: {message.stop_reason}")

                results.extend(classifications)

                # Fallback for any case the LLM missed (shouldn't happen but defensive)
                classified_numbers = {c["case_number"] for c in classifications}
                for case in batch:
                    cn = case.get("case_number", "")
                    if cn not in classified_numbers:
                        print(f"[Stage3] WARNING: Case {cn} missing from batch response")
                        results.append({
                            "case_number": cn,
                            "top_level": case.get("top_level", "استفسار"),
                            "sub_classification": case.get("sub_classification", "استفسار عام"),
                            "confidence": 0.4,  # Below threshold → human review
                            "reason": "لم يتم إرجاع الحالة في رد الدفعة"
                        })
            else:
                # No tool call — flag all cases in batch for human review
                print(f"[Stage3] WARNING: No tool call in batch {batch_num}")
                for case in batch:
                    results.append({
                        "case_number": case.get("case_number", ""),
                        "top_level": case.get("top_level", "استفسار"),
                        "sub_classification": case.get("sub_classification", "استفسار عام"),
                        "confidence": 0.3,
                        "reason": "لم يتم استدعاء أداة تصنيف في هذه الدفعة"
                    })

        except Exception as e:
            print(f"[Stage3] Error in batch {batch_num}: {e}")
            for case in batch:
                results.append({
                    "case_number": case.get("case_number", ""),
                    "top_level": case.get("top_level", "استفسار"),
                    "sub_classification": case.get("sub_classification", "استفسار عام"),
                    "confidence": 0.4,
                    "reason": f"خطأ في معالجة الدفعة: {str(e)}"
                })

    return results


def normalize_classification(top_level: str, sub_classification: str) -> tuple[str, str]:
    """
    Normalize classification to canonical values.

    Handles variations from LLM output and maps to valid taxonomy.

    Args:
        top_level: Raw top_level from LLM or Stage 2
        sub_classification: Raw sub_classification from LLM or Stage 2

    Returns:
        (normalized_top_level, normalized_sub_classification)
    """
    # Canonical top-level values
    canonical_top_levels = ["شكوى", "استفسار", "طلب", "شكر وثناء"]
    canonical_subs = ALL_SUB_CLASSIFICATIONS

    # If already canonical, return as-is
    if top_level in canonical_top_levels and sub_classification in canonical_subs:
        return top_level, sub_classification

    # Normalize top_level
    if top_level not in canonical_top_levels:
        # Try fuzzy match on top_level
        tl_lower = top_level.lower().strip()
        for canonical in canonical_top_levels:
            if canonical in tl_lower or tl_lower in canonical:
                top_level = canonical
                break
        else:
            # Default fallback
            top_level = "استفسار"

    # Normalize sub_classification with keyword-based matching
    if sub_classification not in canonical_subs:
        sc_lower = sub_classification.lower().strip()

        # Build keyword map for fuzzy matching (key words → canonical string)
        keyword_map = {}
        for canonical in canonical_subs:
            canonical_lower = canonical.lower()
            # Extract key words from canonical (split by common delimiters)
            words = [w for w in canonical_lower.replace('أو', ' ').replace('و', ' ').split() if w]
            for word in words:
                if len(word) > 2:  # Skip short words
                    keyword_map[word] = canonical

        # Try to match using keywords
        matched = False
        for keyword, canonical in keyword_map.items():
            if keyword in sc_lower:
                sub_classification = canonical
                matched = True
                break

        if not matched:
            # Fallback based on top_level
            if top_level in SUB_CLASSIFICATIONS:
                sub_classification = SUB_CLASSIFICATIONS[top_level][0]
            else:
                sub_classification = "استفسار عام"

    return top_level, sub_classification


def run_stage3(state: PipelineState, api_key: str, progress_callback=None) -> PipelineState:
    """
    Stage 3: LLM classifier with two-level taxonomy.

    Input: state with llm_queue from Stage 2
    Output: state with llm_classified and human_review_queue
    """
    if not state.llm_queue:
        state.llm_classified = []
        state.human_review_queue = []
        return state

    client = anthropic.Anthropic(api_key=api_key)
    llm_results = classify_with_llm(client, state.llm_queue, progress_callback=progress_callback)

    # Index results by case_number for fast lookup
    results_by_number = {r["case_number"]: r for r in llm_results}

    llm_classified = []
    human_review = []

    for orig_case in state.llm_queue:
        cn = orig_case.get("case_number", "")
        result = results_by_number.get(cn)

        if not result:
            print(f"[Stage3] WARNING: Case {cn} has no result after all batches")
            human_review.append(orig_case)
            continue

        # Normalize classifications to canonical values
        top_level, sub_classification = normalize_classification(
            result.get("top_level", "استفسار"),
            result.get("sub_classification", "استفسار عام")
        )

        case = CaseRow(
            case_number=cn,
            case_title=orig_case.get("case_title", ""),
            date_opened=orig_case.get("date_opened", ""),
            case_channel=orig_case.get("case_channel", ""),
            description=orig_case.get("description", ""),
            resolution_response=orig_case.get("resolution_response", ""),
            sla_color=orig_case.get("sla_color", ""),
            case_type=orig_case.get("case_type", ""),
            service_name=orig_case.get("service_name", ""),
            actual_contact_type=top_level,
            classification_reason=result["reason"],
            confidence=result["confidence"],
            misclassification="OK",
            top_level=top_level,
            sub_classification=sub_classification,
            admin=orig_case.get('admin', ''),
        )

        if case.case_type and case.case_type != case.top_level:
            case.misclassification = f"Reclassified: {case.case_type} → {case.top_level}"

        if case.confidence < LLM_LOW_CONFIDENCE_THRESHOLD:
            human_review.append(case.model_dump())
        else:
            llm_classified.append(case)

    state.llm_classified = llm_classified
    state.human_review_queue = human_review

    print(f"[Stage3] Done — {len(llm_classified)} classified, {len(human_review)} to human review")
    return state
