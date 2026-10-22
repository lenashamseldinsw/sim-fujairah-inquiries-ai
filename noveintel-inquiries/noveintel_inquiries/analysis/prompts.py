"""
Prompts for the qualitative analysis behind S4–S6, and FAQ detection (Section 04).

Each writes table text in both languages in one call — ``*_ar`` fields in Arabic only,
``*_en`` fields in English only — so the English report needs no translation pass, and
no figure is ever re-emitted by a translator. Every one carries the shared style and
hard rules (``narratives.rules``) adapted to that bilingual shape, and none of them
asks for, or accepts, a number: items are tied to case groups and the engine counts.
"""
from __future__ import annotations

from ..narratives.rules import STYLE_RULES, vocabulary_lines

__all__ = ["analysis_system_prompt", "JOURNEY_TOOL", "FAQ_JUDGE_TOOL", "FAQ_MERGE_TOOL", "GAP_TOOL"]

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

# FAQ detection (``analysis.faqs``). Questions only: writing FAQ answers is outside the
# tool's scope (handoff START-HERE, Prerequisites "Out of scope"), so no field asks for one.
FAQ_JUDGE_TOOL = {
    "name": "judge_faq_groups",
    "description": "For each question group: whether one of its candidate catalogue entries already answers "
                   "it, and — only where asked — the customer's question in one line.",
    "input_schema": {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group_id": {"type": "string"},
                        "status": {
                            "type": "string", "enum": ["covered", "partial", "not_covered"],
                            "description": "covered: a candidate entry answers the question these customers ask. "
                                           "partial: an entry answers part of that very question (e.g. the steps but "
                                           "not the documents asked about). not_covered: no entry answers it — an "
                                           "entry on the same topic but a different question, another customer type "
                                           "or another condition does not count.",
                        },
                        "faq_ids": {
                            "type": "array", "items": {"type": "string"},
                            "description": "The candidate entries that answer it, best first. Empty when not_covered.",
                        },
                        "question_ar": {
                            "type": "string",
                            "description": "Only when write_question is true: the question as a customer asks it, "
                                           "one line ending in «؟», no answer. Otherwise empty.",
                        },
                        "question_en": {"type": "string", "description": "The same question in English, or empty."},
                    },
                    "required": ["group_id", "status", "faq_ids", "question_ar", "question_en"],
                },
            }
        },
        "required": ["groups"],
    },
}

FAQ_MERGE_TOOL = {
    "name": "merge_faq_questions",
    "description": "Which question groups ask the same customer question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "same_question": {
                "type": "array",
                "description": "Each item: two or more group ids that ask the same question, whatever the wording. "
                               "Groups about a different service, step or customer type are not the same question.",
                "items": {
                    "type": "object",
                    "properties": {"group_ids": {"type": "array", "items": {"type": "string"}}},
                    "required": ["group_ids"],
                },
            }
        },
        "required": ["same_question"],
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
