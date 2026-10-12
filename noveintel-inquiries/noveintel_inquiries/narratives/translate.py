"""
One call to render AI-generated Arabic labels in English for the English report.

Only labels no tenant column carries — root causes, umbrella names without a
confirmed English name, department and severity values. Catalogue names are never
sent here (see ``engine.localize``). Labels carry no figures, and anything that comes
back with a digit the original lacked is discarded.
"""
from __future__ import annotations

import json
import logging
import re

from ..core42 import FAST_MODEL, Core42Client

__all__ = ["translate_labels"]

logger = logging.getLogger(__name__)

_TOOL = {
    "name": "translate_labels",
    "description": "English renderings of short Arabic report labels, one per id.",
    "input_schema": {
        "type": "object",
        "properties": {
            "labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "en": {"type": "string"}},
                    "required": ["id", "en"],
                },
            }
        },
        "required": ["labels"],
    },
}

_SYSTEM = (
    "You render short Arabic labels from a UAE government customer-inquiries report in formal English. "
    "Keep each label's meaning and length; do not explain or add anything; keep «(جهة عمل)» as "
    "\"(employer)\"; write 'artificial intelligence' never 'AI'. Return through the tool only."
)
_DIGIT = re.compile(r"\d")


def translate_labels(labels: list[str], client: Core42Client | None = None) -> dict[str, str]:
    unique = [label for label in dict.fromkeys(labels) if label and label.strip()]
    if not unique:
        return {}
    client = client or Core42Client()
    out: dict[str, str] = {}
    for start in range(0, len(unique), 120):
        chunk = unique[start:start + 120]
        ids = {f"l{i}": label for i, label in enumerate(chunk)}
        try:
            message = client.messages.create(
                model=FAST_MODEL, max_tokens=6000, system=_SYSTEM, tools=[_TOOL],
                tool_choice={"type": "any"}, stage="narratives",
                messages=[{"role": "user", "content": json.dumps(
                    [{"id": k, "ar": v} for k, v in ids.items()], ensure_ascii=False)}],
            )
        except Exception as exc:
            logger.warning("Label translation failed: %s", exc)
            continue
        for block in message.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            for row in (block.input or {}).get("labels") or []:
                source = ids.get(str(row.get("id", "")))
                english = " ".join(str(row.get("en", "")).split())
                if source and english and (bool(_DIGIT.search(english)) <= bool(_DIGIT.search(source))):
                    out[source] = english
    return out
