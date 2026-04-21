"""
STAGE 3: LLM Classifier

Classifies low-confidence cases from Stage 2 using Claude API.
Uses tool-use for structured output (JSON).
Cases with LLM confidence < 0.85 go to human_review_queue.
"""

import json
import anthropic
from typing import Dict, Any, List
from .state import PipelineState, CaseRow
from .stage2_rules import CONTACT_TYPES

# LLM Classifier confidence threshold
LLM_LOW_CONFIDENCE_THRESHOLD = 0.85


# Tool schema for structured output
CLASSIFIER_TOOL = {
    "name": "classify_case",
    "description": "Classify a customer service case into one of 8 contact types based on description and resolution",
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_type": {
                "type": "string",
                "description": "One of: Technical Incident, Location Inquiry, Cross-Entity Confusion, Status Follow-up, Service Request, Complex Financial Inquiry, Pure Information Inquiry, Complaint",
                "enum": list(CONTACT_TYPES.values())
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score between 0.0 and 1.0",
                "minimum": 0.0,
                "maximum": 1.0
            },
            "reason": {
                "type": "string",
                "description": "Brief explanation of the classification (1-2 sentences)"
            }
        },
        "required": ["contact_type", "confidence", "reason"]
    }
}


def build_system_prompt() -> str:
    """Build system prompt with taxonomy and examples."""
    return """You are an expert customer service analyst for Fujairah Police.
Your task is to classify customer inquiries and complaints into one of 8 categories.

TAXONOMY:
1. Technical Incident — System error, app crash, platform bug. Customer reports functionality broken or unavailable.
2. Location Inquiry — Questions about where services are located or how to access physical locations.
3. Cross-Entity Confusion — Customer inquires about another government agency (e.g., pension authority) by mistake.
4. Status Follow-up — Customer tracking the progress of a previously submitted case or request.
5. Service Request — Customer requests a specific government service or action (license, permit, certificate, etc.).
6. Complex Financial Inquiry — Questions about financial calculations, deductions, payments, fees.
7. Pure Information Inquiry — Customer asks for information, guidance, or clarification on policies or procedures.
8. Complaint — Customer registers a formal complaint about service quality, staff conduct, or operational issues.

CLASSIFICATION RULES:
- Read the Description and Resolution Response carefully.
- Consider the customer's intent, not just keywords.
- If the description mentions a specific system problem → Technical Incident.
- If asking "where is" or resolution contains a map link → Location Inquiry.
- If mentioning another agency → Cross-Entity Confusion.
- If asking about a previous case status → Status Follow-up.
- If requesting a specific service outcome → Service Request.
- If asking about money, percentages, deductions → Complex Financial Inquiry.
- If asking "how do I" or "what is" without requesting action → Pure Information.
- If registering dissatisfaction or demanding improvement → Complaint.

Remember:
- Be objective and precise.
- Use the context clues from both Description and Resolution Response.
- Return confidence between 0.0 (uncertain) and 1.0 (certain).
"""


def classify_with_llm(client: anthropic.Anthropic, cases: List[Dict]) -> List[Dict]:
    """
    Classify cases using Claude API with batching.

    Batches multiple cases per API call for efficiency.
    1,000 cases processed in ~20-30 API calls instead of 1,000.

    Args:
        client: Anthropic API client
        cases: List of case dicts with case_number, description, resolution, etc.

    Returns:
        List of classification results {case_number, contact_type, confidence, reason}
    """
    results = []
    batch_size = 100  # Process 100 cases per API call (11 calls for 1,054 cases, ~38 seconds total)

    print(f"[Stage3] Processing {len(cases)} cases in batches of {batch_size}")

    for batch_idx in range(0, len(cases), batch_size):
        batch = cases[batch_idx:batch_idx + batch_size]
        print(f"[Stage3] Processing batch {batch_idx // batch_size + 1} ({len(batch)} cases)...")

        # Build batch context for LLM
        cases_text = "\n\n".join([
            f"""Case {i+1}:
Case Number: {case.get('case_number', 'N/A')}
Description: {case.get('description', '')}
Resolution Response: {case.get('resolution_response', '')}
Service Name: {case.get('service_name', '')}
Case Type: {case.get('case_type', '')}
Channel: {case.get('case_channel', '')}"""
            for i, case in enumerate(batch)
        ])

        # Call Claude with tool-use for batch
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=5000,  # Allows ~100 cases (50 tokens per classification)
                system=build_system_prompt(),
                tools=[CLASSIFIER_TOOL],
                messages=[
                    {
                        "role": "user",
                        "content": f"Please classify these {len(batch)} cases. Return a tool call for EACH case:\n\n{cases_text}"
                    }
                ]
            )

            # Extract all tool use results from batch
            tool_calls = [block for block in message.content if block.type == "tool_use"]

            for tool_call in tool_calls:
                tool_input = tool_call.input
                case_num = tool_input.get('case_number') or tool_input.get('case_num')

                classification = {
                    "case_number": case_num or '',
                    "contact_type": tool_input.get('contact_type', ''),
                    "confidence": float(tool_input.get('confidence', 0.0)),
                    "reason": tool_input.get('reason', '')
                }
                results.append(classification)

            # Fallback for cases not classified in batch
            classified_numbers = {r['case_number'] for r in results}
            for case in batch:
                if case.get('case_number') not in classified_numbers:
                    results.append({
                        "case_number": case.get('case_number', ''),
                        "contact_type": case.get('actual_contact_type', ''),
                        "confidence": case.get('confidence', 0.5),
                        "reason": 'Batch processing fallback'
                    })

        except Exception as e:
            print(f"[Stage3] Error processing batch: {e}")
            # Fallback: use rule-based classification
            for case in batch:
                results.append({
                    "case_number": case.get('case_number', ''),
                    "contact_type": case.get('actual_contact_type', ''),
                    "confidence": case.get('confidence', 0.5),
                    "reason": f'LLM batch failed: {str(e)}'
                })

    return results


def run_stage3(state: PipelineState, api_key: str) -> PipelineState:
    """
    Stage 3: LLM classifier.

    Input: state with llm_queue from Stage 2
    Output: state with llm_classified and human_review_queue
    """
    if not state.llm_queue:
        # No low-confidence cases to review
        state.llm_classified = []
        state.human_review_queue = []
        return state

    client = anthropic.Anthropic(api_key=api_key)

    # Classify cases
    llm_results = classify_with_llm(client, state.llm_queue)

    llm_classified = []
    human_review = []

    for result in llm_results:
        # Find original case
        orig_case = next(
            (c for c in state.llm_queue if c['case_number'] == result['case_number']),
            None
        )

        if orig_case:
            case = CaseRow(
                case_number=result['case_number'],
                case_title=orig_case.get('case_title', ''),
                date_opened=orig_case.get('date_opened', ''),
                case_channel=orig_case.get('case_channel', ''),
                description=orig_case.get('description', ''),
                resolution_response=orig_case.get('resolution_response', ''),
                sla_color=orig_case.get('sla_color', ''),
                case_type=orig_case.get('case_type', ''),
                service_name=orig_case.get('service_name', ''),
                actual_contact_type=result.get('contact_type', ''),
                classification_reason=result.get('reason', ''),
                confidence=result.get('confidence', 0.0),
                misclassification='OK'  # Will be updated if mismatch
            )

            # Check for misclassification
            if case.case_type != case.actual_contact_type and case.case_type:
                case.misclassification = f"Over-classified: {case.case_type} → {case.actual_contact_type}"

            if case.confidence < LLM_LOW_CONFIDENCE_THRESHOLD:
                human_review.append(case.model_dump())
            else:
                llm_classified.append(case)

    state.llm_classified = llm_classified
    state.human_review_queue = human_review

    return state
