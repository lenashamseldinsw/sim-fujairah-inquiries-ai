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


MAX_ATTEMPTS = 3


def _strip_fences(text: str) -> str:
    """Remove accidental markdown code fences the model may add despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    return text


def translate_report_to_english(
    report_json: Dict[str, Any],
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> Optional[Dict[str, Any]]:
    """
    Translate all Arabic string values in report_json to English.

    Retries up to MAX_ATTEMPTS times if the LLM call fails or the response
    cannot be parsed as valid JSON.

    Args:
        report_json: The Arabic report dict produced by generate_json_report().
        api_key:     Anthropic API key.
        model:       Model slug — defaults to claude-sonnet-4-6 to match the pipeline.

    Returns:
        A deep copy of report_json with Arabic values replaced by English translations,
        or None if all attempts fail.
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

    client = anthropic.Anthropic(api_key=api_key)
    user_content = _USER_TEMPLATE.format(report_json_str=report_json_str)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            print(f"[TranslateEN] Retry attempt {attempt}/{MAX_ATTEMPTS}...")

        # --- LLM call ---
        try:
            message = client.messages.create(
                model=model,
                max_tokens=16000,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIError as exc:
            print(f"[TranslateEN] Anthropic API error on attempt {attempt}: {exc}")
            if attempt == MAX_ATTEMPTS:
                return None
            continue
        except Exception as exc:
            print(f"[TranslateEN] Unexpected error calling LLM on attempt {attempt}: {exc}")
            if attempt == MAX_ATTEMPTS:
                return None
            continue

        raw_response = message.content[0].text if message.content else ""
        raw_response = _strip_fences(raw_response)

        if not raw_response:
            print(f"[TranslateEN] Empty response from LLM on attempt {attempt}")
            if attempt == MAX_ATTEMPTS:
                return None
            continue

        # --- JSON parse ---
        try:
            translated = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            print(f"[TranslateEN] JSON parse failed on attempt {attempt}: {exc}")
            print(f"[TranslateEN] Raw response (first 500 chars): {raw_response[:500]}")
            if attempt == MAX_ATTEMPTS:
                return None
            continue

        if not isinstance(translated, dict):
            print(f"[TranslateEN] LLM returned unexpected type on attempt {attempt}: {type(translated)}")
            if attempt == MAX_ATTEMPTS:
                return None
            continue

        print(f"[TranslateEN] Translation complete (attempt {attempt}).")
        return translated

    return None
