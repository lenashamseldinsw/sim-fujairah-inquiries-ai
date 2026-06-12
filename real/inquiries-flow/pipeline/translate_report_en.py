"""
Translate Arabic report JSON to English.

Two strategies:
1. Single-call (legacy): Translates entire report_json in one LLM call
2. Parallel (recommended): Translates 9 report sections in parallel using threads

The parallel approach is preferred for large reports:
- Each section is ~7-8k tokens (safe, no timeout risk)
- 9 threads run simultaneously (~2 minutes total)
- Better fault tolerance (individual section retries)
- Terminology consistency (same time, same model)

Keys are never touched — only string values that contain Arabic text are translated.
Non-Arabic text (numbers, percentages, emojis, codes) is preserved as-is.

If the LLM call or JSON parsing fails for any reason, the function logs a warning
and returns None so the pipeline continues without crashing.
"""

import json
import anthropic
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


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
                max_tokens=24000,
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


def _translate_single_section_json(
    section_json_str: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> Optional[Dict[str, Any]]:
    """
    Translate a single report section JSON string to English.

    Args:
        section_json_str: JSON string of one report section
        api_key: Anthropic API key
        model: Model to use for translation

    Returns:
        Dict with translated section content, or None if translation fails
    """
    if not section_json_str or not api_key:
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        user_content = _USER_TEMPLATE.format(report_json_str=section_json_str)

        message = client.messages.create(
            model=model,
            max_tokens=16000,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        raw_response = message.content[0].text if message.content else ""
        raw_response = _strip_fences(raw_response)

        if not raw_response:
            return None

        translated = json.loads(raw_response)
        return translated if isinstance(translated, dict) else None

    except Exception as exc:
        print(f"[TranslateSingleSection] Error: {exc}")
        return None


def translate_complete_report_json_parallel(
    report_json: Dict[str, Any],
    api_key: str,
    max_workers: int = 9,
) -> Optional[Dict[str, Any]]:
    """
    Translate complete report JSON by splitting into 9 sections and translating in parallel.

    The report JSON has a 'sections' key containing 9 section dicts. Each section is translated
    independently with up to MAX_ATTEMPTS retries. Sections that fail are kept in Arabic.

    Args:
        report_json: Complete Arabic report JSON with 'sections' key
        api_key: Anthropic API key
        max_workers: Number of parallel threads (default 9)

    Returns:
        Complete English report JSON with same structure, or None if all sections fail
    """
    if not report_json:
        print("[TranslateReportParallel] report_json is empty — skipping translation.")
        return None

    if not api_key:
        print("[TranslateReportParallel] No API key provided — skipping translation.")
        return None

    # Extract sections from report JSON
    sections = report_json.get('sections', [])
    if not sections:
        print("[TranslateReportParallel] No sections found in report_json — skipping translation.")
        return None

    print(f"[TranslateReportParallel] Starting parallel translation of complete report ({len(sections)} sections)...")

    def translate_section_with_retry(section_index: int, section_data: Dict[str, Any]) -> tuple[int, Optional[Dict[str, Any]]]:
        """Translate one section of the report with up to MAX_ATTEMPTS retries."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                section_json_str = json.dumps(section_data, ensure_ascii=False, indent=2)
                translated = _translate_single_section_json(section_json_str, api_key)

                if translated:
                    if attempt > 1:
                        print(f"[TranslateReportParallel] ✓ Section {section_index+1}/{len(sections)} translated (attempt {attempt})")
                    else:
                        print(f"[TranslateReportParallel] ✓ Section {section_index+1}/{len(sections)} translated")
                    return section_index, translated

                # Empty response, retry
                print(f"[TranslateReportParallel] Section {section_index+1} attempt {attempt}: empty response, retrying...")
                if attempt == MAX_ATTEMPTS:
                    return section_index, None
                continue

            except json.JSONDecodeError as exc:
                print(f"[TranslateReportParallel] Section {section_index+1} attempt {attempt}: JSON parse failed: {exc}")
                if attempt == MAX_ATTEMPTS:
                    return section_index, None
                continue

            except Exception as exc:
                print(f"[TranslateReportParallel] Section {section_index+1} attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt == MAX_ATTEMPTS:
                    return section_index, None
                continue

        return section_index, None

    # Run all sections in parallel
    translated_sections: Dict[int, Dict[str, Any]] = {}
    successful_count = 0
    failed_indices = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all section translations
        futures = {
            executor.submit(translate_section_with_retry, idx, section): idx
            for idx, section in enumerate(sections)
        }

        # Collect results as they complete
        for future in as_completed(futures):
            section_index, translated = future.result()

            if translated:
                translated_sections[section_index] = translated
                successful_count += 1
            else:
                # Fallback: keep original Arabic section
                print(f"[TranslateReportParallel] ⚠️  Section {section_index+1} translation failed, keeping Arabic")
                translated_sections[section_index] = sections[section_index]
                failed_indices.append(section_index + 1)

    # Summary
    print(f"[TranslateReportParallel] ✅ Complete — {successful_count}/{len(sections)} sections translated")
    if failed_indices:
        print(f"[TranslateReportParallel] Failed sections kept in Arabic: {', '.join(map(str, failed_indices))}")

    # Reconstruct report JSON with translated sections in original order
    translated_sections_list = [translated_sections[i] for i in range(len(sections))]

    # Deep copy metadata and reconstruct with translated sections
    result = json.loads(json.dumps(report_json, ensure_ascii=False))
    result['sections'] = translated_sections_list

    return result if result else None
