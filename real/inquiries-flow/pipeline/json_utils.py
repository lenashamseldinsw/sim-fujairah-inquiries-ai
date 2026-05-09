"""
Shared JSON parsing utilities for report generation.

ISSUE 4 FIX: Consolidates _parse_json_response which was duplicated in:
  - generate_executive_summary_section
  - generate_methodology_section
  - generate_workload_map_section
"""

import json
import re
from typing import Dict, Any, Optional


def _repair_embedded_quotes(text: str) -> str:
    """
    Escape unescaped double quotes that appear INSIDE JSON string values.

    LLMs frequently embed Arabic citations like "اسم الموضوع" directly inside
    JSON string values, producing invalid JSON such as:
        "section_body": "...كانت أكبرها "اسم" بواقع..."

    This function detects embedded quotes by checking what character follows
    the closing candidate: if the next non-whitespace char is a structural JSON
    character (:  ,  }  ]) the quote is a real string delimiter; otherwise it
    is an embedded quote and gets escaped to \".
    """
    result = []
    in_str = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # Inside a string: handle escape sequences (skip the next char)
        if in_str and ch == '\\' and i + 1 < n:
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue

        if ch == '"':
            if not in_str:
                # Opening quote — enter string mode
                in_str = True
                result.append(ch)
            else:
                # Could be a closing quote or an embedded/unescaped quote.
                # Look ahead past whitespace to see what follows.
                j = i + 1
                while j < n and text[j] in ' \t\r\n':
                    j += 1
                next_ch = text[j] if j < n else ''

                if next_ch in (':,}]') or j >= n:
                    # Structural character → this is the real closing quote
                    in_str = False
                    result.append(ch)
                else:
                    # Non-structural character → embedded quote, escape it
                    result.append('\\"')
        else:
            result.append(ch)

        i += 1

    return ''.join(result)


def parse_json_response(response_text: str, tag: str = "JSONParse") -> Optional[Dict[str, Any]]:
    """
    Robustly extract a JSON object from LLM response text.

    Strategies tried in order:
      0. Direct parse (LLM returned raw JSON with no fences)
      1. Extract from markdown code block (multiple fence formats)
      2. rfind — extract from first '{' to last '}' (handles fences + trailing text)
      3. Balanced-brace walk (fallback for complex cases)
      4. Truncated-response recovery (response cut off mid-JSON)

    Each extraction strategy attempts json.loads directly, then with trailing-
    comma repair, then with embedded-quote repair, before giving up.

    Args:
        response_text: Raw LLM response (may contain markdown, prose, etc.)
        tag: Debug tag for logging (identifies calling context)

    Returns:
        Parsed JSON dict, or None if all strategies failed
    """

    def _try_loads(text: str) -> Optional[Dict[str, Any]]:
        """Try json.loads with progressively more aggressive repair."""
        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Trailing-comma repair (,} or ,])
        fixed = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 3. Embedded-quote repair (LLM uses " inside string values)
        repaired = _repair_embedded_quotes(text)
        if repaired != text:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
            # 4. Both repairs together
            fixed_repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
            try:
                return json.loads(fixed_repaired)
            except json.JSONDecodeError:
                pass

        return None

    stripped = response_text.strip()

    # ── Strategy 0: Direct parse ───────────────────────────────────────────────
    # Fast path when the LLM returns clean JSON without fences.
    if stripped.startswith('{'):
        result = _try_loads(stripped)
        if result is not None:
            return result

    # ── Strategy 1: Markdown code-fence extraction ─────────────────────────────
    # The LLM sometimes wraps JSON in ```json ... ``` despite instructions.
    # We try several patterns to handle common fence format variations.
    if '```' in response_text:
        fence_patterns = [
            r'```(?:json)?\s*\n([\s\S]*?)\n\s*```',  # standard: \n before closing
            r'```(?:json)?\s*\n([\s\S]*?)```',         # no \n before closing ```
            r'```(?:json)?\s*([\s\S]*?)```',            # no \n after opening either
        ]
        for pattern in fence_patterns:
            match = re.search(pattern, response_text)
            if match:
                extracted = match.group(1).strip()
                # Sanity check: if extracted equals (nearly) the whole response
                # the fence match failed to isolate anything useful.
                if extracted and len(extracted) < len(response_text):
                    result = _try_loads(extracted)
                    if result is not None:
                        return result
                    print(f"[{tag}] Fence pattern '{pattern[:30]}...' extracted "
                          f"{len(extracted)} chars but all parse attempts failed")

    # ── Strategy 2: rfind — first '{' to last '}' ─────────────────────────────
    # Robust against any surrounding text (fence markers, prose, etc.).
    # Works as long as the JSON object is syntactically the outermost structure.
    first = response_text.find('{')
    last = response_text.rfind('}')
    if first != -1 and last > first:
        candidate = response_text[first:last + 1]
        result = _try_loads(candidate)
        if result is not None:
            return result
        print(f"[{tag}] rfind candidate ({len(candidate)} chars) failed all repairs. "
              f"First 200: {candidate[:200]}")

    # ── Strategy 3: Balanced-brace walk ───────────────────────────────────────
    # More precise than rfind when there's nested structure after the main object.
    if first == -1:
        print(f"[{tag}] No '{{' found in response (length: {len(response_text)})")
        return None

    depth, in_str, escape = 0, False, False

    for i in range(first, len(response_text)):
        ch = response_text[i]
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                candidate = response_text[first:i + 1]
                result = _try_loads(candidate)
                if result is not None:
                    return result
                print(f"[{tag}] Balanced-brace candidate ({len(candidate)} chars) "
                      f"failed all repairs. First 200: {candidate[:200]}")
                return None

    # ── Strategy 4: Truncated-response recovery ────────────────────────────────
    if depth > 0:
        print(f"[{tag}] Response appears truncated (unclosed braces: depth={depth})")
        extracted = response_text[first:].rstrip()
        extracted = re.sub(r',\s*$', '', extracted.rstrip(',"\']'))
        candidate = extracted + ('}' * depth)
        result = _try_loads(candidate)
        if result is not None:
            print(f"[{tag}] Recovered truncated JSON by closing {depth} open brace(s)")
            return result
        print(f"[{tag}] Could not recover truncated JSON. "
              f"Last 300 chars: ...{response_text[-300:]}")
        return None

    print(f"[{tag}] No parseable JSON found (response length: {len(response_text)})")
    return None
