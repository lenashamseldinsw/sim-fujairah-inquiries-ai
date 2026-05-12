"""
Translate Arabic report JSON to English.

Sends the entire report_json produced by stage6_json_report.generate_json_report()
to claude-sonnet-4-6 in a single call, asking it to return the same structure
with every Arabic string value translated to English.

Keys are never touched — only string values that contain Arabic text are translated.
Non-Arabic text (numbers, percentages, emojis, codes) is preserved as-is.

If the LLM call or JSON parsing fails for any reason, the function logs a warning
and returns None so the pipeline continues without crashing.
"""

import json
import anthropic
from typing import Dict, Any, Optional


_SYSTEM_PROMPT = """\
You are a professional Arabic-to-English translator specialising in UAE government and police reports.
Your task is to translate a JSON document from Arabic to English.

Rules:
1. Return the EXACT same JSON structure — same keys, same nesting, same arrays.
2. Translate every Arabic string value to clear, formal English appropriate for a government/police report.
3. Preserve numbers, percentages, emojis, ISO dates, hex colour codes, and any non-Arabic text exactly as-is.
4. Do NOT add, remove, or rename any keys.
5. Return ONLY the raw JSON — no markdown code fences, no explanation, no commentary.
"""

_USER_TEMPLATE = """\
Translate the Arabic string values in the following JSON to English.
Return only the translated JSON.

<json>
{report_json_str}
</json>
"""


def translate_report_to_english(
    report_json: Dict[str, Any],
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> Optional[Dict[str, Any]]:
    """
    Translate all Arabic string values in report_json to English.

    Uses the same LLM (claude-sonnet-4-6) and Anthropic client as the rest of
    the pipeline.  The full JSON is sent in a single call — it is well within the
    model's 200k-token context window.

    Args:
        report_json: The Arabic report dict produced by generate_json_report().
        api_key:     Anthropic API key.
        model:       Model slug — defaults to claude-sonnet-4-6 to match the pipeline.

    Returns:
        A deep copy of report_json with Arabic values replaced by English translations,
        or None if the call fails for any reason.
    """
    if not report_json:
        print("[TranslateEN] report_json is empty — skipping translation.")
        return None

    if not api_key:
        print("[TranslateEN] No API key provided — skipping translation.")
        return None

    try:
        report_json_str = json.dumps(report_json, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[TranslateEN] Could not serialise report_json: {exc}")
        return None

    print(f"[TranslateEN] Sending report JSON ({len(report_json_str):,} chars) to {model} for translation...")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=16000,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": _USER_TEMPLATE.format(report_json_str=report_json_str),
                }
            ],
        )
    except anthropic.APIError as exc:
        print(f"[TranslateEN] Anthropic API error: {exc}")
        return None
    except Exception as exc:
        print(f"[TranslateEN] Unexpected error calling LLM: {exc}")
        return None

    raw_response = message.content[0].text if message.content else ""

    # Strip accidental markdown fences the model may add despite instructions
    raw_response = raw_response.strip()
    if raw_response.startswith("```"):
        lines = raw_response.splitlines()
        # Drop first line (```json or ```) and last line (```)
        inner_lines = lines[1:] if lines[-1].strip() == "```" else lines[1:]
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        raw_response = "\n".join(inner_lines).strip()

    try:
        translated = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        print(f"[TranslateEN] Failed to parse LLM response as JSON: {exc}")
        print(f"[TranslateEN] Raw response (first 500 chars): {raw_response[:500]}")
        return None

    if not isinstance(translated, dict):
        print(f"[TranslateEN] LLM returned unexpected type: {type(translated)}")
        return None

    print("[TranslateEN] Translation complete.")
    return translated
