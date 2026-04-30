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

    Tries three strategies in order:
      1. Extract from markdown code block (```json ... ```)
      2. Find first '{' and match balanced braces
      3. If mismatched braces, try fixing trailing commas before '}' / ']'

    Args:
        response_text: Raw LLM response (may contain markdown, prose, etc.)
        tag: Debug tag for logging (identifies calling context)

    Returns:
        Parsed JSON dict, or None if parsing failed
    """
    # Strategy 1: Try markdown code block first
    match = re.search(r'```\s*(?:json)?\s*\n(.*?)(?:\n```|$)', response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 2: Find first '{' and match balanced braces
    first = response_text.find('{')
    if first == -1:
        print(f"[{tag}] No JSON object found in response")
        return None

    depth, in_str, escape = 0, False, False
    last_closing_pos = -1

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
                last_closing_pos = i
                candidate = response_text[first:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Strategy 3: Try fixing trailing commas
                    fixed = re.sub(r',(\s*[}\]])', r'\1', candidate)
                    try:
                        return json.loads(fixed)
                    except json.JSONDecodeError as e:
                        print(f"[{tag}] JSON parse failed: {e}")
                        print(f"[{tag}] First 500 chars: {candidate[:500]}")
                        return None

    # If we reach here and still have unclosed braces, the response is truncated
    # Try to fix by closing the JSON structure
    if depth > 0:
        print(f"[{tag}] Response appears truncated (unclosed braces: depth={depth})")
        # Try to close all unclosed braces and parse
        candidate = response_text[first:].rstrip() + ('}' * depth)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Try with trailing comma fix
            fixed = re.sub(r',(\s*[}\]])', r'\1', candidate)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError as e:
                print(f"[{tag}] Could not recover truncated JSON: {e}")
                return None

    return None
