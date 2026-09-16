"""
Repair layer for JSON that a gateway model produced.

Even with ``response_format={"type": "json_object"}``, gateway models produce
unparseable output in five recurring ways, all handled before any parse is
attempted:

  1. ``<think>...</think>`` reasoning blocks — closed, or unclosed because the
     response was truncated mid-thought.
  2. Markdown code fences.
  3. Prose before and/or after the JSON object.
  4. Trailing commas.
  5. Truncation — the model hit its output ceiling mid-JSON. Core42 does this
     far more often than other providers; the truncation-close step exists
     solely because of it.

Two rules hold throughout: every stage runs on the fence-stripped *original*
rather than on the previous stage's output, so a failed repair cannot corrupt
the next attempt; and on total failure the input is returned unchanged, so the
caller's ``json.loads`` raises an error naming the offending line rather than a
generic "could not repair".
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Non-printables are stripped while PRESERVING Arabic: this pipeline's output is
# predominantly Arabic, and a naive "strip non-printable" pass deletes all of it.
_AGGRESSIVE_KEEP = (
    r"[^\x09\x0A\x0D\x20-\x7E"        # tab/LF/CR + printable ASCII
    r"\u00A0-\u024F"                  # Latin-1 supplement + Latin Extended-A/B
    r"\u2000-\u206F\u2190-\u21FF"     # general punctuation, arrows
    r"\u0600-\u06FF\u0750-\u077F"     # Arabic + Arabic supplement
    r"\uFB50-\uFDFF\uFE70-\uFEFF]"    # Arabic presentation forms A/B
)


def close_truncated_json(text: str) -> str:
    """Close any unclosed strings/arrays/objects in a truncated JSON response.

    Known limitation: truncation immediately after a key with no colon yet
    (``{"a": 1, "bc``) yields ``{"a": 1, "bc"}``, which is invalid. The
    trailing-comma pass usually rescues it; when it does not, the retry loop
    takes over.
    """
    in_string = False
    escape_next = False
    depth_stack: List[str] = []

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        # Escape handling is required: an escaped quote inside a string would
        # otherwise flip in_string and desynchronise the whole walk.
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            # Brackets count only outside strings — a brace inside prose is not nesting.
            if ch in "{[":
                depth_stack.append(ch)
            elif ch == "}" and depth_stack and depth_stack[-1] == "{":
                depth_stack.pop()
            elif ch == "]" and depth_stack and depth_stack[-1] == "[":
                depth_stack.pop()

    closing = '"' if in_string else ""
    # Reverse stack order, so a truncated nested object closes inner-to-outer.
    for open_char in reversed(depth_stack):
        closing += "}" if open_char == "{" else "]"
    return text + closing


def escape_control_chars_in_strings(text: str) -> str:
    """Escape bare newline / carriage-return / tab found inside JSON string values.

    Only those three are escaped; every other character is passed through so the
    aggressive-clean step can still handle it. Existing escape sequences are
    forwarded intact via escape_next.
    """
    result: List[str] = []
    in_string = False
    escape_next = False
    replacements = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == "\\" and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch in replacements:
            result.append(replacements[ch])
        else:
            result.append(ch)
    return "".join(result)


def _strip_reasoning_and_fences(text: str) -> str:
    # Strip closed <think> blocks FIRST — before fence detection, since a
    # truncated reasoning block can otherwise swallow the fence.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # An unclosed <think> means a truncated response: everything from <think>
    # onward is reasoning noise — discard it and use what came before.
    open_think = text.find("<think>")
    if open_think != -1:
        text = text[:open_think].strip()

    if "```json" in text:
        start = text.find("```json") + 7
        end = text.rfind("```")
        if end > start:
            text = text[start:end].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    return text


def _drop_trailing_commas(text: str) -> str:
    return re.sub(r",\s*]", "]", re.sub(r",\s*}", "}", text))


def clean_llm_json(text: str) -> str:
    """Best-effort cleanup of an LLM response to extract valid JSON.

    Each stage attempts a parse and returns immediately on success, so no stage
    assumes the previous stage's repair was correct. On total failure the input
    is returned unchanged.
    """
    text = _strip_reasoning_and_fences(text or "")

    # Fast path: already valid. A clean response costs one json.loads.
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    for candidate in (_drop_trailing_commas(text),
                      _drop_trailing_commas(escape_control_chars_in_strings(text))):
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Extract from first { to last } (strips leading/trailing prose)
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start >= 0 and brace_end > brace_start:
        raw = text[brace_start:brace_end]
        for candidate in (_drop_trailing_commas(raw),
                          _drop_trailing_commas(escape_control_chars_in_strings(raw))):
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Aggressive Unicode-safe clean: strip non-printables, keeping Arabic.
        aggressive = re.sub(_AGGRESSIVE_KEEP, " ", raw)
        aggressive = aggressive.replace("}{", "}, {").replace("][", "], [")
        candidate = _drop_trailing_commas(escape_control_chars_in_strings(aggressive))
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Last resort: the response is truncated — close all open structures.
    if brace_start >= 0:
        closed = _drop_trailing_commas(
            close_truncated_json(escape_control_chars_in_strings(text[brace_start:]))
        )
        try:
            json.loads(closed)
            # Never repair truncated content silently: that is how half-empty
            # reports ship.
            logger.warning(
                "clean_llm_json: response was truncated and repaired by closing open "
                "JSON structures. Some field values may be incomplete."
            )
            return closed
        except json.JSONDecodeError:
            pass

    return text  # the caller's parse will raise a clear error


def loads_repaired(text: str) -> Optional[Dict[str, Any]]:
    """Parse LLM output into a dict, repairing it first. None if unparseable."""
    if not text:
        return None
    try:
        value: Any = json.loads(clean_llm_json(text))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Core42 JSON parse failed after repair: %s", exc)
        return None
    return value if isinstance(value, dict) else None
