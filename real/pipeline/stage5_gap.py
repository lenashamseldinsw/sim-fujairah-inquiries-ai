"""
STAGE 5: Gap Analysis (LLM, guidebook-based)

Evaluates guidance gaps using the embedded guidebook.
No web scraping — guidebook PDF is the sole reference.

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
from .guidebook import GuidebookSearchIndex


GAP_ANALYSIS_TOOL = {
    "name": "analyze_gaps",
    "description": "Analyze information gaps and guidebook coverage based on customer interactions",
    "input_schema": {
        "type": "object",
        "properties": {
            "gap_table": {
                "type": "array",
                "description": "List of identified gaps and recommendations",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "topic_ar": {"type": "string"},
                        "case_count": {"type": "integer"},
                        "guidebook_status": {"type": "string"},
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


def build_gap_analysis_prompt(
    patterns: List[Dict],
    journey_map: List[Dict],
    search_index: Optional[GuidebookSearchIndex] = None
) -> str:
    """Build prompt for gap analysis with guidebook context from semantic search."""
    patterns_text = json.dumps(patterns, ensure_ascii=False, indent=2)
    journey_text = json.dumps(journey_map, ensure_ascii=False, indent=2)

    # Build guidebook context from semantic search
    guidebook_context = ""
    if search_index:
        # Search for relevant guidebook sections using all friction topics
        queries = [p.get('description', p.get('topic', '')) for p in patterns[:5]]  # Top 5 patterns
        relevant_chunks = set()

        for query in queries:
            if query:
                results = search_index.query(query, top_k=3)
                for result in results:
                    relevant_chunks.add(result['text'])

        if relevant_chunks:
            guidebook_context = "\n\n".join(sorted(relevant_chunks)[:3000])  # Limit to 3000 chars
        else:
            guidebook_context = "(No matching guidebook sections found for the identified patterns)"
    else:
        guidebook_context = "(Guidebook search index not available)"

    return f"""You are evaluating information gaps in government customer service.

Given:
1. Identified friction points and patterns from customer interactions
2. Relevant excerpts from the customer services guidebook (retrieved via semantic search)

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

Guidebook Content (retrieved via semantic search):
{guidebook_context}

For each major friction topic:
- Assess severity (Critical = many customers struggling, Medium = some issues, Adequate = well-covered)
- Provide specific, actionable recommendations for improvement
- Consider both content improvements and notification strategies

Return bilingual output (English and Arabic) for all recommendations.
"""


def run_stage5(
    state: PipelineState,
    api_key: str,
    search_index: Optional[GuidebookSearchIndex] = None
) -> PipelineState:
    """
    Stage 5: Gap analysis.

    Input: state with patterns, journey_map, faq_candidates from Stage 4
    Output: state with gap_table and validated_faqs

    Args:
        state: Pipeline state
        api_key: Anthropic API key
        search_index: GuidebookSearchIndex for semantic search on guidebook
    """
    if not state.journey_map:
        return state

    client = anthropic.Anthropic(api_key=api_key)

    # Build analysis prompt with guidebook context from semantic search
    prompt = build_gap_analysis_prompt(
        [p.model_dump() for p in state.patterns],
        [j.model_dump() for j in state.journey_map],
        search_index
    )

    # Call Claude with tool-use
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system="You are an expert analyst of government customer service. Provide gap analysis based on the guidebook and customer interaction patterns. Return detailed, bilingual recommendations.",
        tools=[GAP_ANALYSIS_TOOL],
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    # Extract tool use result
    for block in message.content:
        if block.type == "tool_use":
            analysis = block.input

            # Parse gap table
            if 'gap_table' in analysis:
                state.gap_table = [
                    GapRow(
                        topic=g.get('topic', ''),
                        topic_ar=g.get('topic_ar', ''),
                        case_count=g.get('case_count', 0),
                        guidebook_status=g.get('guidebook_status', ''),
                        gap_type=g.get('gap_type', ''),
                        gap_type_ar=g.get('gap_type_ar', ''),
                        severity=g.get('severity', 'Medium'),
                        recommendation=g.get('recommendation', ''),
                        recommendation_ar=g.get('recommendation_ar', '')
                    )
                    for g in analysis.get('gap_table', [])
                ]

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

    return state
