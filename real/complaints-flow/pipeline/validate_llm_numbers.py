"""
validate_llm_numbers.py

Enforce locked percentages and case counts in LLM-generated narratives.
Prevents hallucination where LLM substitutes different numbers without validation.
"""

import re
from typing import Tuple, Dict, Any, Optional
from .state import PipelineState

# Arabic punctuation that delimits clauses
_CLAUSE_DELIMITERS = '،.؛\n'
_NEGATION_TOKENS = ('دون', 'بلا', 'بدون', 'لا يوجد', 'بمعدل صفر')


def _local_clause_bounds(text: str, pos: int, max_chars: int = 25) -> Tuple[int, int]:
    """
    Return (start, end) indices of the clause containing `pos`.
    Bounded by Arabic punctuation or `max_chars` on each side — whichever is closer.
    """
    start = pos
    for i in range(pos - 1, max(0, pos - max_chars) - 1, -1):
        if text[i] in _CLAUSE_DELIMITERS:
            start = i + 1
            break
        start = i

    end = pos
    for i in range(pos, min(len(text), pos + max_chars)):
        if text[i] in _CLAUSE_DELIMITERS:
            end = i
            break
        end = i + 1

    return start, end


def _best_metric_match(
    context: str,
    pct_pos_in_context: int,
    locked: Dict[str, Tuple[float, list, float]],
) -> Optional[Tuple[str, float, float]]:
    """
    Score each candidate metric by:
      - keyword presence in context (required)
      - distance from keyword to percentage (closer = better)
      - number of distinct keywords matched (more = better)

    Return the best match, or None if no metric scores above threshold,
    OR if two metrics tie within 1 character of distance (ambiguous → bail out).
    """
    scores = []
    for metric_name, (actual_val, keywords, tolerance) in locked.items():
        best_dist = None
        match_count = 0
        for kw in keywords:
            idx = context.find(kw)
            while idx != -1:
                d = abs(idx - pct_pos_in_context)
                if best_dist is None or d < best_dist:
                    best_dist = d
                match_count += 1
                idx = context.find(kw, idx + 1)
        if best_dist is not None:
            scores.append((metric_name, actual_val, tolerance, best_dist, match_count))

    if not scores:
        return None

    # Sort: closest keyword first, then most matches
    scores.sort(key=lambda s: (s[3], -s[4]))

    # Ambiguity guard: if two metrics tie within 1 char distance, bail out
    if len(scores) >= 2 and scores[1][3] - scores[0][3] <= 1:
        return None

    name, actual, tol, _, _ = scores[0]
    return (name, actual, tol)


def enforce_locked_percentages(
    text: str,
    state: PipelineState,
    section_name: str = ""
) -> Tuple[str, Dict[str, Any]]:
    """
    Two-pass validation with clause awareness:
      1. Find every percentage in the text.
      2. For each match, examine ONLY the local clause to identify which metric it refers to.
      3. If the claimed value diverges from the actual value, substitute.

    Fixes Round 4's over-correction by:
      - Bounding context to clause boundaries (not 40 characters)
      - Scoring keyword proximity (closest keyword wins, not first in dict)
      - Guarding against negations like "دون رفض" (reject without rejection = opposite)
      - Bailing out on ambiguous cases (two metrics equally close)
    """
    report = {
        "section": section_name,
        "found_issues": [],
        "corrections_made": 0,
        "details": []
    }

    # Compute all locked actual values
    locked: Dict[str, Tuple[float, list, float]] = {
        # name → (actual_value, list_of_arabic_keywords, drift_tolerance)
        "closure_rate":   (_compute_closure_rate(state), ["إغلاق", "أُغلقت", "أغلقت", "مغلقة"], 1.0),
        "rejection_rate": (state.rejection_rate or 0.0, ["معدل الرفض", "نسبة الرفض", "مرفوضة", "مرفوض"], 0.5),
        "digital_rate":   (state.digital_channel_rate or 0.0, ["القنوات الرقمية", "التطبيق", "الموقع الإلكتروني"], 0.5),
        "sla_on_time_rate": (_compute_sla_on_time_rate(state), ["الوقت المحدد", "في الوقت", "ضمن الوقت"], 0.5),
        "reclassification_rate": (state.reclassification_rate or 0.0, ["التصنيف", "تصنيف خاطئ", "اقتران خلل التصنيف", "مُصنَّفة بشكل خاطئ"], 0.5),
    }

    # Pass 1: find every percentage
    pct_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*%')

    # Iterate in reverse so substitutions don't shift later positions
    matches = list(pct_pattern.finditer(text))
    corrected = text

    for match in reversed(matches):
        try:
            claimed = float(match.group(1))
        except ValueError:
            continue

        # Pass 2: bound context to local clause (Arabic punctuation or 25 chars)
        clause_start, clause_end = _local_clause_bounds(text, match.start(), max_chars=25)
        context = text[clause_start:clause_end]
        pct_pos_in_context = match.start() - clause_start

        # Check for negation in context
        if any(neg in context for neg in _NEGATION_TOKENS):
            continue

        # Score candidate metrics with proximity weighting
        matched_metric = _best_metric_match(context, pct_pos_in_context, locked)
        if matched_metric is None:
            continue

        metric_name, actual_val, tolerance = matched_metric

        # Skip if within tolerance
        if abs(claimed - actual_val) <= tolerance:
            continue

        # Substitute the number — use the exact string form found in the doc
        old_number_str = match.group(1)
        # Preserve format: if the doc said "80" use "92"; if "80.0" use "92.0"
        if '.' in old_number_str:
            new_number_str = f"{actual_val:.1f}"
        else:
            new_number_str = f"{int(round(actual_val))}"

        # Replace just the captured number, not the whole match (which includes %)
        old_full = match.group(0)  # "80.0%"
        new_full = old_full.replace(old_number_str, new_number_str, 1)
        corrected = corrected[:match.start()] + new_full + corrected[match.end():]

        report["found_issues"].append(
            f"{metric_name}: LLM claimed {claimed}% but actual is {actual_val}% "
            f"(clause: ...{context.strip()}...)"
        )
        report["corrections_made"] += 1
        report["details"].append(
            f"Corrected {metric_name}: {claimed}% → {actual_val}%"
        )

    return corrected, report


def enforce_locked_case_counts(
    text: str,
    state: PipelineState,
    section_name: str = ""
) -> Tuple[str, Dict[str, Any]]:
    """
    Validate and correct case count claims in LLM-generated text.

    Checks for claims like "X حالة" or "X+ شكوى" (must be explicitly marked).
    Corrects proactive_cancellable counts based on notification_opportunities.

    IMPORTANT: Pattern requires explicit "حالة/حالات" marker to avoid matching percentages.

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

    # Pattern: "X حالة" or "X+ شكوى" — MUST have explicit case marker
    # This prevents matching numbers in percentages like "44.44%"
    case_count_pattern = r'(\d+)\s*(?:\+)?\s*(?:حالة|حالات|شكوى|شكاوى)'

    # Get locked case count values
    proactive_actual = _compute_proactive_cancellable_count(state)
    closure_actual = _compute_closure_rate(state) * total_cases / 100 if total_cases else 0
    closure_actual = int(round(closure_actual))

    # Keywords that indicate which metric the number refers to
    keywords_map = {
        "proactive": (proactive_actual, ["إشعار", "استباقي", "إخطار", "إشعارات", "التنبيه", "قابل للإلغاء"]),
        "closure": (closure_actual, ["إغلاق", "مغلقة", "أُغلقت", "closed"]),
    }

    matches = list(re.finditer(case_count_pattern, corrected))
    for match in reversed(matches):  # Reverse to preserve positions when replacing
        try:
            claimed_count = int(match.group(1))

            # Check if proactive_cancellable is mentioned in nearby context
            context_start = max(0, match.start() - 50)
            context_end = min(len(text), match.end() + 50)
            context = text[context_start:context_end].lower()

            # Determine which metric this number refers to
            best_metric = None
            best_score = 0

            for metric_name, (actual_val, keywords) in keywords_map.items():
                score = sum(1 for kw in keywords if kw in context)
                if score > best_score:
                    best_score = score
                    best_metric = (metric_name, actual_val)

            # If we identified a metric and the claim diverges, correct it
            if best_metric and claimed_count != best_metric[1]:
                metric_name, actual_val = best_metric
                if actual_val > 0:  # Only correct if we have a meaningful actual value
                    old_match = match.group(0)
                    # Preserve "+", "حالة", "حالات" suffix if present
                    has_plus = '+' in old_match
                    case_marker = ""
                    if 'حالات' in old_match:
                        case_marker = "حالات" if actual_val != 1 else "حالة"
                    elif 'حالة' in old_match:
                        case_marker = "حالات" if actual_val != 1 else "حالة"
                    elif 'شكاوى' in old_match:
                        case_marker = "شكاوى" if actual_val != 1 else "شكوى"
                    elif 'شكوى' in old_match:
                        case_marker = "شكاوى" if actual_val != 1 else "شكوى"

                    new_str = str(actual_val)
                    if has_plus and metric_name == "proactive":
                        new_str += "+"
                    if case_marker:
                        new_str += " " + case_marker

                    corrected = corrected[:match.start()] + new_str + corrected[match.end():]
                    report["found_issues"].append(
                        f"{metric_name.title()} count: claimed {claimed_count} but actual is {actual_val} "
                        f"(context: ...{context.strip()}...)"
                    )
                    report["corrections_made"] += 1

        except (ValueError, IndexError):
            pass

    return corrected, report


def _compute_closure_rate(state: PipelineState) -> float:
    """
    Compute closure rate as percentage.

    Uses SAME logic as generate_conclusion_section._compute_closure_rate:
    Count cases where date_closed is truthy AND has non-empty string representation.
    This ensures consistency with Section 3.3 (Resolution Analysis).
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    # Match the logic from generate_conclusion_section._compute_closure_rate:
    # Check if date_closed attribute exists AND is truthy AND has non-empty string representation
    closed = sum(
        1 for c in cases
        if c.date_closed and str(c.date_closed).strip()
    )
    return round((closed / total * 100), 1) if total > 0 else 0.0


def _compute_sla_on_time_rate(state: PipelineState) -> float:
    """
    SLA on-time rate from sla_closed_on_time == 'نعم'.

    CRITICAL: Returns 0.0 if column is entirely empty (all cases have no SLA data).
    This prevents LLM hallucination of percentages for columns with no data.
    """
    total = len(state.all_classified) or state.total_cases or 1

    # Count cases with non-empty SLA data
    cases_with_sla_data = sum(
        1 for c in state.all_classified
        if c.sla_closed_on_time and c.sla_closed_on_time.strip()
    )

    # If no cases have SLA data, column is empty — suppress metric
    if cases_with_sla_data == 0:
        return 0.0

    # Count on-time closures among those with SLA data
    on_time = sum(
        1 for c in state.all_classified
        if c.sla_closed_on_time and c.sla_closed_on_time.strip() == 'نعم'
    )
    return round(on_time / total * 100, 1) if total > 0 else 0.0


def _compute_proactive_cancellable_count(state: PipelineState) -> int:
    """
    Compute proactive cancellable case count from notification_opportunities.

    This is the authoritative count used consistently across all sections.
    Uses actual data from state.notification_opportunities (post-reconciliation from Stage 4),
    not cached values from state.proactive_notification_case_count.
    """
    if not state.notification_opportunities:
        return 0

    total = sum(
        int(n.get("cases_eliminated", n.get("case_count", 0)))
        for n in state.notification_opportunities
    )

    # TASK 6 FIX: Assert consistency with state.proactive_notification_case_count
    # Both should match after Stage 4 reconciliation
    if state.proactive_notification_case_count != total:
        print(
            f"[validate_llm_numbers] WARNING: proactive_notification_case_count {state.proactive_notification_case_count} "
            f"does not match computed sum from notification_opportunities {total}. "
            f"This may indicate state was not updated after reconciliation."
        )

    return total


def _detect_duplicate_citations(text: str) -> Dict[str, Any]:
    """
    TASK 9 FIX: Detect suspicious duplicate citations of the same number within 200 characters.

    Example: "24 شكوى مكررة... ... 24 شكوى مرفوضة" (same 24 cited twice)
    This may indicate the LLM is double-counting the same group as two separate groups.

    Returns a dict with found_duplicates list and warning_details.
    """
    report = {
        "found_duplicates": [],
        "warning_details": []
    }

    # Find all digit sequences (case counts, percentages, etc.)
    number_pattern = re.compile(r'\b(\d+(?:\.\d+)?)\s*(?:%|شكوى|حالة)?\b')
    matches = list(number_pattern.finditer(text))

    # For each match, check if the same number appears within 200 chars
    for i, match1 in enumerate(matches):
        num1 = match1.group(1)
        pos1 = match1.start()

        for match2 in matches[i+1:]:
            num2 = match2.group(1)
            pos2 = match2.start()

            # Same number within 200 chars?
            if num1 == num2 and (pos2 - pos1) <= 200:
                context_start = max(0, pos1 - 40)
                context_end = min(len(text), pos2 + 40)
                context = text[context_start:context_end]

                warning = {
                    "number": num1,
                    "distance_chars": pos2 - pos1,
                    "context": context.replace('\n', ' ')[:100]
                }
                report["found_duplicates"].append(warning)
                report["warning_details"].append(
                    f"Number '{num1}' appears twice within {pos2 - pos1} characters. "
                    f"Context: ...{context[:80]}..."
                )

    return report


def validate_section_9_narrative(
    text: str,
    state: PipelineState
) -> Tuple[str, Dict[str, Any]]:
    """
    Validate Section 9 conclusion narrative against actual metrics.

    Returns (corrected_text, validation_report) — corrected text has invalid metrics replaced.
    """
    report = {
        "section": "الخلاصة والتوصيات",
        "total_issues": 0,
        "percentage_validations": {},
        "case_count_validations": {},
        "duplicate_citations": {},
        "corrections_applied": False
    }

    # Validate percentages
    pct_text, pct_report = enforce_locked_percentages(text, state, "Section 9")
    report["percentage_validations"] = pct_report
    report["total_issues"] += pct_report["corrections_made"]

    # Validate case counts
    count_text, count_report = enforce_locked_case_counts(pct_text, state, "Section 9")
    report["case_count_validations"] = count_report
    report["total_issues"] += len(count_report["found_issues"])

    # TASK 9 FIX: Detect duplicate citations
    dup_report = _detect_duplicate_citations(count_text)
    report["duplicate_citations"] = dup_report
    if dup_report["found_duplicates"]:
        report["total_issues"] += len(dup_report["found_duplicates"])
        for warning in dup_report["warning_details"]:
            print(f"[Section 9] TASK 9 WARNING: {warning}")

    corrected_text = count_text
    report["corrections_applied"] = report["total_issues"] > 0

    return corrected_text, report
