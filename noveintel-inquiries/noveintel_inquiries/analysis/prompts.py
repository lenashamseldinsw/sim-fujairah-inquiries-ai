"""
Prompts for the qualitative analysis behind S4–S6.

Each writes table text in both languages in one call — ``*_ar`` fields in Arabic only,
``*_en`` fields in English only — so the English report needs no translation pass, and
no figure is ever re-emitted by a translator. Every one carries the shared style and
hard rules (``narratives.rules``) adapted to that bilingual shape, and none of them
asks for, or accepts, a number: items are tied to case groups and the engine counts.
"""
from __future__ import annotations

from ..narratives.rules import STYLE_RULES, vocabulary_lines

__all__ = ["analysis_system_prompt", "JOURNEY_TOOL", "FAQ_TOOL", "GAP_TOOL"]

_ROOT_CAUSE_CATEGORIES = [
    "missing_info", "inaccessible_info", "no_proactive_notification", "platform_bug", "policy_complexity",
]
_GAP_TYPES = ["missing_content", "unclear_content", "not_digital", "not_proactive", "policy_complexity"]


def analysis_system_prompt(entity: str, task: str, vocabulary: dict[str, dict[str, str]]) -> str:
    vocab = "\n".join(
        v for v in (vocabulary_lines(vocabulary.get("ar", {}), "ar"), vocabulary_lines(vocabulary.get("en", {}), "en")) if v
    )
    return f"""\
You analyse customer inquiries received by {entity or "a UAE government entity"} for a formal government report.

{task}

Language: every field ending in _ar is formal administrative Arabic only; every field ending in _en is formal English only. Service and sub-classification names are used exactly as given.

{STYLE_RULES["en"]}

Additional rules for this task:
- Never write a number of cases, a percentage or any other count in any field. Counts are computed by the engine from the groups you assign.
- Use only what the groups and their redacted samples show; do not invent services, events or policies.
- Never quote a sample case verbatim and never reproduce a placeholder such as [الاسم].
- Describe contact motives, never customer faults; name no staff member.
{vocab}
Return the result through the tool only."""


JOURNEY_TOOL = {
    "name": "map_journey",
    "description": "Journey frictions and proactive-notification opportunities, each tied to whole case groups.",
    "input_schema": {
        "type": "object",
        "properties": {
            "frictions": {
                "type": "array",
                "description": "Points in the customer journey that made customers contact the entity. Each group belongs to at most one friction.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name_ar": {"type": "string"},
                        "name_en": {"type": "string"},
                        "root_cause_category": {"type": "string", "enum": _ROOT_CAUSE_CATEGORIES},
                        "remedy_ar": {"type": "string", "description": "The improvement action, one sentence."},
                        "remedy_en": {"type": "string"},
                        "group_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name_ar", "name_en", "root_cause_category", "remedy_ar", "remedy_en", "group_ids"],
                },
            },
            "notification_opportunities": {
                "type": "array",
                "description": "Contacts a proactive notification at the right moment would make unnecessary. Each group belongs to at most one opportunity.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type_ar": {"type": "string"},
                        "type_en": {"type": "string"},
                        "trigger_ar": {"type": "string", "description": "The event that should send it."},
                        "trigger_en": {"type": "string"},
                        "message_ar": {"type": "string", "description": "A sample message, no personal data."},
                        "message_en": {"type": "string"},
                        "group_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["type_ar", "type_en", "trigger_ar", "trigger_en", "message_ar", "message_en", "group_ids"],
                },
            },
        },
        "required": ["frictions", "notification_opportunities"],
    },
}

FAQ_TOOL = {
    "name": "propose_faqs",
    "description": "Frequently asked questions the cases of one main service show, with matching keywords.",
    "input_schema": {
        "type": "object",
        "properties": {
            "faqs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_ar": {"type": "string"},
                        "question_en": {"type": "string"},
                        "answer_ar": {"type": "string", "description": "Grounded in the agents' resolutions."},
                        "answer_en": {"type": "string"},
                        "keywords_ar": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "3–6 distinctive Arabic words or short phrases a customer asking this question writes.",
                        },
                    },
                    "required": ["question_ar", "question_en", "answer_ar", "answer_en", "keywords_ar"],
                },
            }
        },
        "required": ["faqs"],
    },
}

GAP_TOOL = {
    "name": "assess_guidebook",
    "description": "For each friction, whether the service guidebook already answers it.",
    "input_schema": {
        "type": "object",
        "properties": {
            "gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "friction_id": {"type": "string"},
                        "topic_ar": {"type": "string"},
                        "topic_en": {"type": "string"},
                        "guidebook_status": {"type": "string", "enum": ["Covered", "Partially Covered", "Missing"]},
                        "guidebook_excerpt": {"type": "string", "description": "A short quote from the given guidebook text, or empty."},
                        "gap_type": {"type": "string", "enum": _GAP_TYPES},
                        "recommendation_ar": {"type": "string"},
                        "recommendation_en": {"type": "string"},
                    },
                    "required": ["friction_id", "topic_ar", "topic_en", "guidebook_status", "guidebook_excerpt", "gap_type", "recommendation_ar", "recommendation_en"],
                },
            }
        },
        "required": ["gaps"],
    },
}
