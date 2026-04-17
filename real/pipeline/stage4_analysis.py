"""
STAGE 4: Analysis (LLM)

Extracts:
- Patterns (clusters, sub-themes)
- Journey map (friction points, root causes)
- FAQ candidates (validated against guidebook in Stage 5)
- Self-service tags
- Notification opportunities

Uses Claude API with tool-use for structured output.
Guidebook is chunked and embedded at startup (chromadb, in-memory).
"""

import json
import anthropic
from typing import Dict, Any, List
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
            }
        },
        "required": ["patterns", "journey_map", "faq_candidates"]
    }
}


def build_analysis_system_prompt() -> str:
    """Build system prompt for analysis."""
    return """You are an expert business analyst for government customer service.
Analyze customer inquiries and complaints to extract:

1. PATTERNS - Clusters of similar cases (min 5 cases each)
   - Group by main theme
   - Identify sub-themes within each cluster
   - Provide example case numbers

2. JOURNEY MAP - Friction points customers experience
   - What causes customers to contact you?
   - What's the root cause? (missing info, inaccessible info, no proactive notification, platform bug, policy complexity)
   - How many cases per friction point?

3. FAQs - Questions answered repeatedly in the resolution
   - Extract actual Q&A from good resolution responses
   - These should help customers self-serve next time
   - Provide in both English and Arabic

4. SELF-SERVICE TAGS - Which issues could be self-serviceable
   - Fully self-serviceable (customer can do alone)
   - Requires system access (customer needs online account/portal)
   - Technical incident (cannot self-serve)

5. NOTIFICATION OPPORTUNITIES - Where proactive messaging helps
   - Status Follow-up cases: send automatic status updates
   - Information gaps: send helpful tips before customer asks
   - Annual processes: send calendar reminders

Return bilingual content (English and Arabic) for all human-readable fields.
Be specific with example case IDs and counts.
"""


def run_stage4(state: PipelineState, api_key: str) -> PipelineState:
    """
    Stage 4: Analysis.

    Input: state with all_classified cases
    Output: state with patterns, journey_map, faq_candidates, etc.
    """
    if not state.all_classified:
        return state

    client = anthropic.Anthropic(api_key=api_key)

    # Build case summary for LLM
    cases_text = "Cases to analyze:\n"
    for case in state.all_classified[:100]:  # Sample first 100 to avoid token limits
        cases_text += f"""
Case {case.case_number}: [{case.actual_contact_type}]
Description: {case.description[:200]}
Resolution: {case.resolution_response[:200]}
---"""

    # Call Claude with tool-use
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=build_analysis_system_prompt(),
        tools=[ANALYSIS_TOOL],
        messages=[
            {
                "role": "user",
                "content": f"Analyze these customer service cases:\n{cases_text}"
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
                        example_case_ids=p.get('example_case_ids', [])
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
                        case_count=j.get('case_count', 0)
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

            break

    return state
