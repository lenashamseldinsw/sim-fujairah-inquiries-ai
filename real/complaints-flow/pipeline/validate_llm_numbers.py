"""
validate_llm_numbers.py

Enforce locked percentages and case counts in LLM-generated narratives.
Prevents hallucination where LLM substitutes different numbers without validation.
"""

import re
from typing import Tuple, Dict, Any
from .state import PipelineState


def enforce_locked_percentages(
    text: str,
    state: PipelineState,
    section_name: str = ""
) -> Tuple[str, Dict[str, Any]]:
    """
    Validate and correct percentage values in LLM-generated text.

    Checks for common percentage claims and validates them against actual data.

    Returns:
        (corrected_text, validation_report)
        - corrected_text: Text with invalid percentages replaced with correct values
        - validation_report: Dict with found_issues, corrections_made, details
    """
    report = {
        "section": section_name,
        "found_issues": [],
        "corrections_made": 0,
        "details": []
    }

    corrected = text

    # Pattern 1: Closure rate claims "X% معدل الإغلاق" or similar
    closure_patterns = [
        r'(\d+(?:\.\d+)?)\s*%?\s*(?:معدل|نسبة)\s*الإغلاق',
        r'(?:معدل|نسبة)\s*الإغلاق\s*[:|=]?\s*(\d+(?:\.\d+)?)\s*%',
    ]

    actual_closure_rate = _compute_closure_rate(state)
    for pattern in closure_patterns:
        matches = re.finditer(pattern, corrected)
        for match in matches:
            try:
                claimed_rate = float(match.group(1))
                if abs(claimed_rate - actual_closure_rate) > 0.5:  # Allow small rounding diffs
                    report["found_issues"].append(
                        f"Closure rate mismatch: LLM claimed {claimed_rate}% but actual is {actual_closure_rate}%"
                    )
                    corrected = corrected.replace(
                        match.group(0),
                        match.group(0).replace(str(claimed_rate), str(actual_closure_rate))
                    )
                    report["corrections_made"] += 1
                    report["details"].append(f"Corrected closure rate: {claimed_rate}% → {actual_closure_rate}%")
            except (ValueError, IndexError):
                pass

    # Pattern 2: Rejection rate claims "X% معدل الرفض" or similar
    rejection_patterns = [
        r'(\d+(?:\.\d+)?)\s*%?\s*(?:معدل|نسبة)\s*الرفض',
        r'(?:معدل|نسبة)\s*الرفض\s*[:|=]?\s*(\d+(?:\.\d+)?)\s*%',
    ]

    actual_rejection_rate = state.rejection_rate or 0.0
    for pattern in rejection_patterns:
        matches = re.finditer(pattern, corrected)
        for match in matches:
            try:
                claimed_rate = float(match.group(1))
                if abs(claimed_rate - actual_rejection_rate) > 0.5:  # Allow small rounding diffs
                    report["found_issues"].append(
                        f"Rejection rate mismatch: LLM claimed {claimed_rate}% but actual is {actual_rejection_rate}%"
                    )
                    corrected = corrected.replace(
                        match.group(0),
                        match.group(0).replace(str(claimed_rate), str(actual_rejection_rate))
                    )
                    report["corrections_made"] += 1
                    report["details"].append(f"Corrected rejection rate: {claimed_rate}% → {actual_rejection_rate}%")
            except (ValueError, IndexError):
                pass

    # Pattern 3: Digital channel rate claims
    digital_patterns = [
        r'(\d+(?:\.\d+)?)\s*%?\s*(?:من التقديمات|عبر القنوات الرقمية)',
        r'(?:القنوات الرقمية|التقديمات الرقمية)\s*[:|=]?\s*(\d+(?:\.\d+)?)\s*%',
    ]

    actual_digital_rate = state.digital_channel_rate or 0.0
    for pattern in digital_patterns:
        matches = re.finditer(pattern, corrected)
        for match in matches:
            try:
                claimed_rate = float(match.group(1))
                if abs(claimed_rate - actual_digital_rate) > 0.5:
                    report["found_issues"].append(
                        f"Digital channel rate mismatch: LLM claimed {claimed_rate}% but actual is {actual_digital_rate}%"
                    )
                    corrected = corrected.replace(
                        match.group(0),
                        match.group(0).replace(str(claimed_rate), str(actual_digital_rate))
                    )
                    report["corrections_made"] += 1
                    report["details"].append(f"Corrected digital rate: {claimed_rate}% → {actual_digital_rate}%")
            except (ValueError, IndexError):
                pass

    return corrected, report


def enforce_locked_case_counts(
    text: str,
    state: PipelineState,
    section_name: str = ""
) -> Tuple[str, Dict[str, Any]]:
    """
    Validate and correct case count claims in LLM-generated text.

    Checks for claims like "X حالة" and validates against actual data.

    Returns:
        (corrected_text, validation_report)
    """
    report = {
        "section": section_name,
        "found_issues": [],
        "corrections_made": 0,
        "details": []
    }

    corrected = text
    total_cases = len(state.all_classified) or state.total_cases or 0

    # Pattern: "X حالة" (case count claims)
    case_count_pattern = r'(\d+)\s*(?:\+)?\s*(?:حالة|حالات)'

    # Map context to expected values
    context_values = {
        "closed": state.closed_cases_count,
        "rejected": sum(1 for c in state.all_classified if c.case_status and c.case_status.strip() == 'طلب مرفوض'),
        "total": total_cases,
    }

    matches = list(re.finditer(case_count_pattern, corrected))
    for match in reversed(matches):  # Reverse to preserve positions when replacing
        try:
            claimed_count = int(match.group(1))

            # Check if any locked value is exceeded
            if claimed_count > total_cases:
                report["found_issues"].append(
                    f"Case count {claimed_count} exceeds total cases {total_cases}"
                )
                # Don't correct, just flag - context matters for what should be corrected
                report["details"].append(
                    f"Found potentially invalid case count {claimed_count} at position {match.start()}"
                )
        except (ValueError, IndexError):
            pass

    return corrected, report


def _compute_closure_rate(state: PipelineState) -> float:
    """Compute closure rate as percentage."""
    total = len(state.all_classified) or state.total_cases or 1
    closed = state.closed_cases_count or 0
    return round((closed / total * 100), 1) if total > 0 else 0.0


def validate_section_9_narrative(
    text: str,
    state: PipelineState
) -> Dict[str, Any]:
    """
    Validate Section 9 conclusion narrative against actual metrics.

    Returns comprehensive validation report with all found issues.
    """
    report = {
        "section": "الخلاصة والتوصيات",
        "total_issues": 0,
        "percentage_validations": {},
        "case_count_validations": {},
        "corrections_applied": False
    }

    # Validate percentages
    pct_text, pct_report = enforce_locked_percentages(text, state, "Section 9")
    report["percentage_validations"] = pct_report
    report["total_issues"] += pct_report["corrections_made"]

    # Validate case counts
    count_text, count_report = enforce_locked_case_counts(text, state, "Section 9")
    report["case_count_validations"] = count_report
    report["total_issues"] += len(count_report["found_issues"])

    return report
