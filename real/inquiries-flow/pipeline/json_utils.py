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


def parse_json_response(response_text: str, tag: str = "JSONParse") -> Optional[Dict[str, Any]]:
    """
    Robustly extract a JSON object from LLM response text.

    Tries multiple strategies in order:
      1. Direct parse (LLM returned raw JSON with no fences)
      2. Extract from markdown code block (handles various fence formats)
      3. Find first '{' and match balanced braces
      4. If mismatched braces, try fixing truncated response

    Args:
        response_text: Raw LLM response (may contain markdown, prose, etc.)
        tag: Debug tag for logging (identifies calling context)

    Returns:
        Parsed JSON dict, or None if all strategies failed
    """

    def _try_loads(text: str) -> Optional[Dict[str, Any]]:
        """Try json.loads; on failure, attempt trailing-comma repair."""
        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Fix trailing commas before } or ]
        fixed = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None

    stripped = response_text.strip()

    # Strategy 0: Direct parse — LLM returned clean JSON without fences
    if stripped.startswith('{'):
        result = _try_loads(stripped)
        if result is not None:
            return result

    # Strategy 1: Extract from markdown code block.
    # The LLM sometimes wraps JSON in ```json ... ``` despite being asked not to.
    # We try several fence patterns to handle edge cases:
    #   - closing ``` on its own line (standard)
    #   - closing ``` immediately after the last char (no preceding newline)
    #   - missing closing ``` (response ends mid-fence)
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
                # Guard: if extracted is huge (whole response) the fence match failed
                if extracted and len(extracted) < len(response_text):
                    result = _try_loads(extracted)
                    if result is not None:
                        return result
                    print(f"[{tag}] Fence extracted {len(extracted)} chars but parse failed; trying next pattern")

    # Strategy 2: Find first '{' and walk balanced braces
    first = response_text.find('{')
    if first == -1:
        print(f"[{tag}] No JSON object found in response (length: {len(response_text)})")
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
                # Found balanced braces but still can't parse — log and give up
                print(f"[{tag}] Balanced braces found but parse failed. First 300 chars: {candidate[:300]}")
                return None

    # Strategy 3: Response is truncated (unclosed braces)
    if depth > 0:
        print(f"[{tag}] Response appears truncated (unclosed braces: depth={depth})")
        extracted = response_text[first:].rstrip()
        # Remove trailing incomplete element (comma, dangling quote/bracket)
        extracted = re.sub(r',\s*$', '', extracted.rstrip(',"\']'))
        candidate = extracted + ('}' * depth)
        result = _try_loads(candidate)
        if result is not None:
            print(f"[{tag}] Recovered truncated JSON by closing {depth} open brace(s)")
            return result
        print(f"[{tag}] Could not recover truncated JSON. Last 300 chars: ...{response_text[-300:]}")
        return None

    print(f"[{tag}] No parseable JSON found in response (length: {len(response_text)})")
    return None
