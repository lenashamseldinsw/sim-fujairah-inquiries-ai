"""
STAGE 3: LLM Classifier

Classifies low-confidence cases from Stage 2 using Claude API.
Uses tool-use with array structure for batch efficiency without losing case numbers.
Cases with LLM confidence < 0.65 go to human_review_queue.
Uses Haiku for speed and cost efficiency on this high-volume task.
"""

import json
import anthropic
from typing import Dict, Any, List
from .state import PipelineState, CaseRow
from .stage2_rules import CONTACT_TYPES

# Confidence threshold — lowered from 0.85. At 0.85, valid classifications (0.65–0.8) got discarded.
LLM_LOW_CONFIDENCE_THRESHOLD = 0.65


# Tool schema for batch classification with proper case tracking
CLASSIFIER_TOOL = {
    "name": "classify_cases_batch",
    "description": "Classify a batch of customer service cases. Return one classification per case in order.",
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
                        "contact_type": {
                            "type": "string",
                            "enum": list(CONTACT_TYPES.values())
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0
                        },
                        "reason": {
                            "type": "string",
                            "description": "1-2 sentence explanation"
                        }
                    },
                    "required": ["case_number", "contact_type", "confidence", "reason"]
                }
            }
        },
        "required": ["classifications"]
    }
}


def build_system_prompt() -> str:
    """Build system prompt with taxonomy."""
    return """You are an expert customer service analyst for Fujairah Police.
Classify customer inquiries into one of 8 categories based on description and resolution.

TAXONOMY:
1. Technical Incident — System error, app crash, platform bug. Functionality broken or unavailable.
2. Location Inquiry — Questions about where services are or how to reach physical locations.
3. Cross-Entity Confusion — Customer contacted wrong government agency by mistake.
4. Status Follow-up — Customer tracking progress of a previously submitted case.
5. Service Request — Customer requests a specific service outcome (license, permit, certificate, data update).
6. Complex Financial Inquiry — Questions about payments, fees, deductions, financial calculations.
7. Pure Information Inquiry — Asking for information or clarification without requesting action.
8. Complaint — Formal dissatisfaction about service quality, staff conduct, or operational failure.

RULES:
- Base classification on actual customer intent, not just keywords.
- The Resolution Response reveals the true nature — use it to override initial impressions.
- A case that SOUNDS like inquiry but was RESOLVED by staff action → Service Request.
- System errors blocking a transaction → Technical Incident, not Service Request.
- Tracking prior submission → Status Follow-up, even if phrased as question.
- Return case_number exactly as provided.
- Return one entry per case in input order."""


def classify_with_llm(client: anthropic.Anthropic, cases: List[Dict], progress_callback=None) -> List[Dict]:
    """
    Classify cases using Claude Haiku with array tool-use for proper batch handling.

    Args:
        client: Anthropic API client
        cases: List of case dicts
        progress_callback: Optional function(batch_num, total_batches)

    Returns:
        List of classification results {case_number, contact_type, confidence, reason}
    """
    results = []
    batch_size = 30  # Safe size for array tool-use without truncation risk

    total_batches = (len(cases) + batch_size - 1) // batch_size
    print(f"[Stage3] Processing {len(cases)} cases in {total_batches} batches of {batch_size}")

    for batch_num, batch_idx in enumerate(range(0, len(cases), batch_size), 1):
        batch = cases[batch_idx:batch_idx + batch_size]

        if progress_callback:
            progress_callback(batch_num, total_batches)

        print(f"[Stage3] Batch {batch_num}/{total_batches} ({len(batch)} cases)...")

        # Build case list with clear ordering
        cases_text = "\n\n".join([
            f"Case Number: {case.get('case_number', 'N/A')}\n"
            f"Description: {case.get('description', '').strip()}\n"
            f"Resolution: {case.get('resolution_response', '').strip()}\n"
            f"Service: {case.get('service_name', '')}\n"
            f"Channel: {case.get('case_channel', '')}"
            for case in batch
        ])

        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",  # Haiku for speed/cost on bulk classification
                max_tokens=4000,
                system=build_system_prompt(),
                tools=[CLASSIFIER_TOOL],
                tool_choice={"type": "any"},  # Force tool use — no free-text fallback
                messages=[{
                    "role": "user",
                    "content": (
                        f"Classify these {len(batch)} cases. "
                        f"Return exactly one entry per case in the classifications array.\n\n"
                        f"{cases_text}"
                    )
                }]
            )

            # Extract tool call — should contain all classifications in one array
            tool_calls = [b for b in message.content if b.type == "tool_use"]

            if tool_calls:
                classifications = tool_calls[0].input.get("classifications", [])
                results.extend(classifications)

                # Fallback for any case the LLM missed (shouldn't happen but defensive)
                classified_numbers = {c["case_number"] for c in classifications}
                for case in batch:
                    cn = case.get("case_number", "")
                    if cn not in classified_numbers:
                        print(f"[Stage3] WARNING: Case {cn} missing from batch response")
                        results.append({
                            "case_number": cn,
                            "contact_type": "استفسار معلومات",
                            "confidence": 0.4,  # Below threshold → human review
                            "reason": "Not returned in LLM batch response"
                        })
            else:
                # No tool call — flag all cases in batch for human review
                print(f"[Stage3] WARNING: No tool call in batch {batch_num}")
                for case in batch:
                    results.append({
                        "case_number": case.get("case_number", ""),
                        "contact_type": "استفسار معلومات",
                        "confidence": 0.3,
                        "reason": "LLM returned no tool call for this batch"
                    })

        except Exception as e:
            print(f"[Stage3] Error in batch {batch_num}: {e}")
            for case in batch:
                results.append({
                    "case_number": case.get("case_number", ""),
                    "contact_type": case.get("actual_contact_type", "استفسار معلومات"),
                    "confidence": 0.4,
                    "reason": f"LLM batch error: {str(e)}"
                })

    return results


def normalize_contact_type(value: str) -> str:
    """
    Normalize contact_type to canonical CONTACT_TYPES values.

    Handles:
    - English labels from Stage 2 (Service Request → طلب خدمة)
    - Slight variations from LLM (معلومات → استفسار معلومات)
    - Out-of-enum values returned by LLM

    Args:
        value: Raw contact_type from LLM or Stage 2

    Returns:
        Canonical Arabic value from CONTACT_TYPES
    """
    canonical_values = list(CONTACT_TYPES.values())

    # If already canonical, return as-is
    if value in canonical_values:
        return value

    # Map English labels from Stage 2 to Arabic
    english_to_arabic = {
        'Technical Incident': 'بلاغ تقني',
        'Location Inquiry': 'استفسار عن الموقع',
        'Cross-Entity Confusion': 'خلط بين الجهات',
        'Status Follow-up': 'متابعة حالة',
        'Service Request': 'طلب خدمة',
        'Complex Financial Inquiry': 'استفسار مالي معقد',
        'Pure Information Inquiry': 'استفسار معلومات',
        'Complaint': 'شكوى',
    }

    if value in english_to_arabic:
        return english_to_arabic[value]

    # For partial matches or variations in Arabic (e.g., معلومات → استفسار معلومات)
    value_lower = value.lower().strip()

    # Build a fuzzy match dictionary
    match_map = {
        'معلومات': 'استفسار معلومات',
        'شكوى': 'شكوى',
        'طلب خدمة': 'طلب خدمة',
        'خدمة': 'طلب خدمة',
        'تقني': 'بلاغ تقني',
        'بلاغ': 'بلاغ تقني',
        'موقع': 'استفسار عن الموقع',
        'جهات': 'خلط بين الجهات',
        'متابعة': 'متابعة حالة',
        'حالة': 'متابعة حالة',
        'مالي': 'استفسار مالي معقد',
        'مالية': 'استفسار مالي معقد',
    }

    for keyword, canonical in match_map.items():
        if keyword in value_lower:
            return canonical

    # Default fallback
    print(f"[Stage3] WARNING: Unmapped contact_type '{value}' — defaulting to 'استفسار معلومات'")
    return 'استفسار معلومات'


def run_stage3(state: PipelineState, api_key: str, progress_callback=None) -> PipelineState:
    """
    Stage 3: LLM classifier.

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

        # Normalize contact_type to canonical value
        normalized_contact_type = normalize_contact_type(result["contact_type"])

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
            actual_contact_type=normalized_contact_type,
            classification_reason=result["reason"],
            confidence=result["confidence"],
            misclassification="OK"
        )

        if case.case_type and case.case_type != case.actual_contact_type:
            case.misclassification = f"Reclassified: {case.case_type} → {case.actual_contact_type}"

        if case.confidence < LLM_LOW_CONFIDENCE_THRESHOLD:
            human_review.append(case.model_dump())
        else:
            llm_classified.append(case)

    state.llm_classified = llm_classified
    state.human_review_queue = human_review

    print(f"[Stage3] Done — {len(llm_classified)} classified, {len(human_review)} to human review")
    return state
