"""
generate_customer_journey_section — stage6_artifacts.py companion (Complaints Flow)

Generates Section 4: "رابعاً: التحليل الثاني — التحديات في رحلة المتعامل مع الشكاوى"

INTEGRATION
───────────
1. stage6_artifacts.py — _generate_report_sections(), after workload_map block:

    from .generate_customer_journey_section import generate_customer_journey_section

    print("[Report Gen] Generating Customer Journey Challenges section...")
    customer_journey = generate_customer_journey_section(state, api_key)
    if customer_journey:
        state.report_sections_ar['customer_journey'] = {
            'heading': 'رابعاً: التحليل الثاني — التحديات في رحلة المتعامل مع الشكاوى',
            'raw_data': customer_journey,
        }
    else:
        raise RuntimeError("[Report Gen] Customer Journey section generation failed")

2. stage6_json_report.py — JSONReportBuilder:

    a) Import at top:
       from .generate_customer_journey_section import _build_friction_rows

    b) Paste build_customer_journey_section as a method on JSONReportBuilder.

    c) In build_report(), after build_workload_map_section():

        journey_section = self.build_customer_journey_section(lang=lang)
        if journey_section:
            sections.append(journey_section)

SECTION STRUCTURE (mirrors sample output section_28):
─────────────────────────────────────────────────────
Section body: framing paragraph naming N friction points + quick-win highlight
Table: نقطة الاحتكاك | الحالات | السبب الجذري | الإجراء التحسيني
       (one row per friction point, sorted descending by case_count)
"""

import json
from typing import Dict, Any, List, Optional
from collections import defaultdict
import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response


# ==============================================================================
# Module-level helpers
# These are also pasted into stage6_json_report.py so the JSON builder
# can construct the section from state data directly (without repeating the LLM call).
# ==============================================================================

# Root-cause category → short Arabic label used inside the friction table
_ROOT_CAUSE_LABELS: Dict[str, str] = {
    "missing_info":               "معلومات مفقودة من الدليل",
    "inaccessible_info":          "معلومات موجودة لكنها صعبة الوصول",
    "no_proactive_notification":  "غياب الإشعار الاستباقي",
    "platform_bug":               "خلل تقني في المنصة",
    "policy_complexity":          "تعقيد إجراءات السياسة",
}

# Root-cause → severity emoji consistent with gap_analysis table
_ROOT_CAUSE_SEVERITY: Dict[str, str] = {
    "missing_info":               "🔴 حرجة",
    "inaccessible_info":          "🔴 حرجة",
    "no_proactive_notification":  "🟡 عالية",
    "platform_bug":               "🔴 حرجة",
    "policy_complexity":          "🟡 عالية",
}


def _build_friction_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Build pre-computed friction rows from state.journey_map.

    Sorted descending by case_count (highest friction first).
    Uses Arabic friction_point_ar / cluster_ar where available.

    Row schema (matches sample output table columns):
      نقطة الاحتكاك | الحالات | السبب الجذري

    The LLM adds الإجراء التحسيني in the prompt output.
    """
    rows = []
    for friction in sorted(state.journey_map, key=lambda f: f.case_count, reverse=True):
        point = friction.friction_point_ar or friction.friction_point or friction.cluster_ar or friction.cluster
        root_cause_label = _ROOT_CAUSE_LABELS.get(
            friction.root_cause_category,
            friction.root_cause_category  # fallback: raw enum value
        )
        rows.append({
            "نقطة الاحتكاك": point,
            "الحالات": str(friction.case_count),
            "السبب الجذري": root_cause_label,
        })
    return rows


def _build_friction_context(state: PipelineState) -> List[Dict[str, Any]]:
    """
    Join journey_map entries to gap_table intelligence for the prompt.
    Each entry carries: friction_point, case_count, root_cause_category,
    severity (from gap_table), guidebook_status, and recommendation_ar.
    No new computation — pure join of Stage 4 + Stage 5 outputs.
    """
    # Build a lookup from gap topic keywords to gap rows
    gap_lookup = {}
    for gap in (state.gap_table or []):
        key = (gap.topic_ar or gap.topic or "").strip()
        if key:
            gap_lookup[key] = gap

    context = []
    for f in sorted(state.journey_map, key=lambda x: x.case_count, reverse=True):
        point = f.friction_point_ar or f.friction_point or ""
        # Try to find a matching gap row by substring overlap
        matched_gap = None
        for gap_key, gap in gap_lookup.items():
            if gap_key in point or point in gap_key or f.cluster in gap_key:
                matched_gap = gap
                break

        entry = {
            "friction_point": point,
            "case_count": f.case_count,
            "root_cause_category": f.root_cause_category,
            "root_cause_label": _ROOT_CAUSE_LABELS.get(f.root_cause_category, f.root_cause_category),
        }
        if matched_gap:
            entry["guidebook_status"] = matched_gap.guidebook_status
            entry["gap_severity"] = matched_gap.severity
            entry["guidebook_recommendation"] = matched_gap.recommendation_ar or matched_gap.recommendation
            entry["proactive_notification_opportunity"] = matched_gap.proactive_notification_opportunity
        context.append(entry)
    return context


def _find_quick_win(state: PipelineState, total_cases: int) -> Optional[Dict[str, Any]]:
    """
    Identify the single highest-impact quick-win friction point.

    A quick-win is a friction point where:
      - notification_opportunities from Stage 5 is available (primary source)
      - OR root_cause is no_proactive_notification (easiest to fix — just send an SMS/email)
      - OR the gap_table has a corresponding proactive_notification_opportunity=True entry

    Returns a dict with keys: friction_point, case_count, pct_of_total, fix_type
    Returns None if no suitable quick-win found.
    """
    total = total_cases

    # 1. Use notification_opportunities computed by Stage 4 — already sorted/ranked
    if state.notification_opportunities:
        best_notif = max(
            state.notification_opportunities,
            key=lambda n: n.get('cases_eliminated', n.get('case_count', 0))
        )
        case_count = best_notif.get('cases_eliminated', best_notif.get('case_count', 0))
        if case_count > 0:
            return {
                "friction_point": best_notif.get('notification_type', ''),
                "case_count": case_count,
                "pct_of_total": round(case_count / total * 100, 1),
                "fix_type": f"إشعار استباقي عبر {best_notif.get('channel', 'SMS')} — {best_notif.get('content_summary', '')}",
            }

    # 2. Fall back: notification-based friction from journey_map
    notification_frictions = [
        f for f in state.journey_map
        if f.root_cause_category == "no_proactive_notification"
    ]
    if notification_frictions:
        best = max(notification_frictions, key=lambda f: f.case_count)
        return {
            "friction_point": best.friction_point_ar or best.friction_point,
            "case_count": best.case_count,
            "pct_of_total": round(best.case_count / total * 100, 1),
            "fix_type": "إشعار استباقي (SMS/بريد إلكتروني)",
        }

    # 3. Fall back: gap_table proactive_notification_opportunity from Stage 5
    if state.gap_table:
        notif_gaps = [g for g in state.gap_table if g.proactive_notification_opportunity]
        if notif_gaps:
            best_gap = max(notif_gaps, key=lambda g: g.case_count)
            return {
                "friction_point": best_gap.topic_ar or best_gap.topic,
                "case_count": best_gap.case_count,
                "pct_of_total": round(best_gap.case_count / total * 100, 1),
                "fix_type": "إشعار استباقي (SMS/بريد إلكتروني)",
            }

    # 4. Last resort: largest friction point overall
    if state.journey_map:
        best = max(state.journey_map, key=lambda f: f.case_count)
        return {
            "friction_point": best.friction_point_ar or best.friction_point,
            "case_count": best.case_count,
            "pct_of_total": round(best.case_count / total * 100, 1),
            "fix_type": "تحسين إجرائي",
        }

    return None


# ==============================================================================
# Prompt + API call
# ==============================================================================

def generate_customer_journey_section(
    state: PipelineState,
    api_key: str,
) -> Dict[str, Any]:
    """
    Generate Section 4 — Customer Journey Challenges (Complaints Flow).

    Mirrors the pattern of generate_workload_map_section():
      - Pre-compute all tables from state (never let LLM invent numbers)
      - Ask LLM to write prose + add الإجراء التحسيني column to the friction table
      - Safety-reinject pre-computed tables into the result before returning

    Args:
        state:   Pipeline state with journey_map, patterns, gap_table populated.
        api_key: Anthropic API key.

    Returns:
        Dict with keys matching the JSON output schema below.

    Raises:
        RuntimeError if journey_map is empty or API call fails.
    """
    if not state.journey_map:
        raise RuntimeError(
            "[CustomerJourney] state.journey_map is empty — "
            "Stage 4 (stage4_analysis) must complete successfully before this section can be generated."
        )

    try:
        # ── Pre-compute all numbers from state ────────────────────────────────
        # FIX 4: Use len(all_classified) consistently (matches workload map pattern)
        total_cases  = len(state.all_classified) or state.total_cases or 1
        date_range   = convert_month_year_to_arabic(state.month_year) or "Q1 2026"
        friction_count = len(state.journey_map)

        friction_rows = _build_friction_rows(state)
        # FIX 4: Pass total_cases explicitly to _find_quick_win
        quick_win     = _find_quick_win(state, total_cases)

        # FIX 2: Build friction_context with gap_table intelligence instead of bare root_cause_totals
        friction_context = _build_friction_context(state)

        # Top friction by case count (for the intro opening sentence)
        top_friction = max(state.journey_map, key=lambda f: f.case_count)
        top_friction_point  = top_friction.friction_point_ar or top_friction.friction_point
        top_friction_count  = top_friction.case_count
        top_friction_pct    = round(top_friction_count / total_cases * 100, 1)

        # Serialize for prompt
        friction_rows_json   = json.dumps(friction_rows,   ensure_ascii=False, indent=2)
        quick_win_json        = json.dumps(quick_win,       ensure_ascii=False) if quick_win else "null"
        # FIX 2: Use friction_context instead of root_cause_totals
        friction_context_json = json.dumps(friction_context, ensure_ascii=False, indent=2)

        # ── Prompt ────────────────────────────────────────────────────────────
        prompt = (
            'You are writing Section 4 of a formal Arabic government report on customer complaint analysis\n'
            'for Fujairah Police. The section title is\n'
            '"رابعاً: التحليل الثاني — التحديات في رحلة المتعامل مع الشكاوى".\n'
            '\n'
            'INPUTS — use ONLY these numbers, never invent figures\n'
            f'total_cases:         {total_cases}\n'
            f'date_range:          "{date_range}"\n'
            f'friction_count:      {friction_count}   (total distinct friction points identified)\n'
            f'top_friction_point:  "{top_friction_point}"\n'
            f'top_friction_count:  {top_friction_count}\n'
            f'top_friction_pct:    "{top_friction_pct}%"\n'
            f'quick_win:           {quick_win_json}\n'
            f'\n'
            'friction_context (join of Stage 4 journey_map + Stage 5 gap intelligence — use guidebook_recommendation to inform الإجراء التحسيني):\n'
            f'{friction_context_json}\n'
            '\n'
            'pre_computed_friction_table\n'
            '(copy نقطة الاحتكاك | الحالات | السبب الجذري verbatim — do NOT change any value):\n'
            f'{friction_rows_json}\n'
            '\n'
            '─────────────────────────────────────────────\n'
            'YOUR TASK — write ONLY the two items below\n'
            '─────────────────────────────────────────────\n'
            '\n'
            'A. section_body (the section\'s opening narrative paragraph)\n'
            '2–3 sentences, formal Arabic. Must:\n'
            f'  - Open: "يكشف التحليل المعمّق للبيانات النصية غير المهيكلة عن {friction_count} نقاط احتكاك'
            f' رئيسية في رحلة المتعامل مع الشكاوى، كل منها ينتج عن سبب جذري محدد قابل للمعالجة:"\n'
            f'  - Highlight the top friction: "النقطة الأكثر حدة هي {top_friction_point} التي تؤثر على {top_friction_count} حالة ({top_friction_pct}% من الإجمالي)."\n'
            '  - If quick_win is not null, add a sentence about the quick_win impact.\n'
            '  - End the paragraph with a colon (":") — the friction table follows immediately.\n'
            '  - CRITICAL: Use the EXACT injected values for top_friction_point, top_friction_count, and top_friction_pct.\n'
            '    Do NOT extract these from friction_context array or recalculate from data.\n'
            '\n'
            'B. الإجراء التحسيني column for EVERY row in pre_computed_friction_table\n'
            '  For each friction row, use friction_context[i].guidebook_recommendation as the\n'
            '  primary source for الإجراء التحسيني. Rephrase it into 1 concise Arabic sentence\n'
            '  (max 30 words). If no guidebook_recommendation is present for that row, derive\n'
            '  the action from the root_cause_label. Never invent numbers.\n'
            '  Do NOT change نقطة الاحتكاك, الحالات, or السبب الجذري.\n'
            '\n'
            'CRITICAL DISAMBIGUATION — Complaint Misrouting:\n'
            '  If any friction row describes complaints that were filed via the complaints\n'
            '  channel but actually relate to inquiries or other services, the friction point\n'
            '  correctly identifies this as misrouting — NOT a missing or inaccessible resource.\n'
            '  The الإجراء التحسيني for this row must reference process improvements to direct\n'
            '  complainants to the correct channel or clarifying the complaint intake process.\n'
            '  Do NOT reframe complaint misrouting as an information access issue.\n'
            '\n'
            '─────────────────────────────────────────────\n'
            'CRITICAL: INJECTED NUMBERS ARE FIXED FACTS\n'
            '─────────────────────────────────────────────\n'
            'The section_body MUST include these exact injected values:\n'
            f'  top_friction_point: "{top_friction_point}"\n'
            f'  top_friction_count: {top_friction_count}\n'
            f'  top_friction_pct: {top_friction_pct}%\n'
            '\n'
            'DO NOT derive these from friction_context or recalculate from case data.\n'
            'Copy them directly into the generated section_body string.\n'
            '\n'
            '─────────────────────────────────────────────\n'
            'OUTPUT — single JSON object, no markdown, no extra keys\n'
            '─────────────────────────────────────────────\n'
            '\n'
            '{\n'
            '  "section": "customer_journey",\n'
            '  "section_body": "...",\n'
            '  "friction_table": [\n'
            '    {\n'
            '      "نقطة الاحتكاك": "...",\n'
            '      "الحالات": "...",\n'
            '      "السبب الجذري": "...",\n'
            '      "الإجراء التحسيني": "..."\n'
            '    }\n'
            '  ]\n'
            '}\n'
            '\n'
            'RULES:\n'
            '- friction_table: copy نقطة الاحتكاك, الحالات, السبب الجذري verbatim — only ADD الإجراء التحسيني.\n'
            '- section_body: Arabic only. Every number must match a pre-computed input above.\n'
            '- No markdown, no extra keys, no extra nesting.\n'
            '- All prose must be in Arabic only.\n'
            '- CRITICAL: Do NOT use double-quote characters (\") inside any string value. '
            'Use angle brackets « » instead of double quotes when citing topic names.\n'
        )

        # ── API call ──────────────────────────────────────────────────────────
        client = anthropic.Anthropic(api_key=api_key)
        print(
            f"[CustomerJourney] Calling API — total_cases={total_cases}, "
            f"friction_count={friction_count}, "
            f"top_friction='{top_friction_point}' ({top_friction_count} cases)"
        )

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,  # FIX 6: Increased from 3000 (matches workload map)
            messages=[{"role": "user", "content": prompt}],
        )

        result = parse_json_response(message.content[0].text, tag="CustomerJourney")
        if result is None:
            raise RuntimeError(
                "[CustomerJourney] parse_json_response returned None — could not extract JSON from API response.\n"
                f"Raw response (first 500 chars):\n{message.content[0].text[:500]}"
            )

        # ── Safety-reinject: pre-computed columns must always be exact state data ──
        # Merge LLM's الإجراء التحسيني into the pre-computed rows, row by row.
        llm_rows = result.get("friction_table", [])
        if not isinstance(llm_rows, list):
            raise RuntimeError(
                f"[CustomerJourney] 'friction_table' missing or not a list in LLM response. "
                f"Got type: {type(llm_rows)}"
            )
        if len(llm_rows) != len(friction_rows):
            raise RuntimeError(
                f"[CustomerJourney] friction_table row count mismatch: "
                f"expected {len(friction_rows)}, LLM returned {len(llm_rows)}."
            )

        merged_friction_table = []
        for i, (pre_row, llm_row) in enumerate(zip(friction_rows, llm_rows)):
            action = llm_row.get("الإجراء التحسيني", "")
            if not action:
                raise RuntimeError(
                    f"[CustomerJourney] Missing 'الإجراء التحسيني' in friction_table row {i} "
                    f"(friction point: '{pre_row['نقطة الاحتكاك']}')"
                )
            merged_friction_table.append({
                **pre_row,                          # exact pre-computed values
                "الإجراء التحسيني": action,          # LLM-generated corrective action
            })

        result["friction_table"] = merged_friction_table

        # Guard assertion: verify reconciled counts don't exceed actual sub_classification counts
        from collections import defaultdict
        actual_sub_counts = defaultdict(int)
        for case in (state.all_classified or []):
            actual_sub_counts[case.sub_classification] += 1

        for friction in state.journey_map or []:
            actual_count = actual_sub_counts.get(friction.sub_classification, 0)
            if friction.case_count > actual_count:
                print(
                    f"[CustomerJourney] WARNING: friction '{friction.friction_point_ar}' "
                    f"case_count={friction.case_count} exceeds actual count={actual_count} "
                    f"for sub_classification='{friction.sub_classification}'. "
                    f"Reconciliation may not have completed successfully."
                )

        print(
            f"[CustomerJourney] OK — "
            f"friction_table={len(merged_friction_table)} rows"
        )
        return result

    except Exception as e:
        print(f"[CustomerJourney] ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise  # Don't silently return None — let caller see the error
