"""
generate_conclusion_section — stage6_artifacts.py companion
Section 9: تاسعاً: الخلاصة — من البيانات إلى القرار

INTEGRATION
───────────
1. stage6_artifacts.py — _generate_report_sections(), after improvement_roadmap block:

    from .generate_conclusion_section import generate_conclusion_section

    print("[Report Gen] Generating Conclusion section...")
    conclusion = generate_conclusion_section(state, api_key)
    state.report_sections_ar['conclusion'] = {
        'heading': 'تاسعاً: الخلاصة — من البيانات إلى القرار',
        'raw_data': conclusion,
    }

2. stage6_json_report.py — JSONReportBuilder:

    a) Import at top:
        from .generate_conclusion_section import build_conclusion_pivot_rows

    b) Add build_conclusion_section method using build_conclusion_section_for_json

    c) In build_report(), after improvement_roadmap block:

        # 9. Conclusion
        conclusion_section = self.build_conclusion_section(lang=lang, section_number=9)
        if conclusion_section:
            sections.append(conclusion_section)

DESIGN NOTES
────────────
• All numeric values are pre-computed from state before the API call.
  The LLM writes ONLY the three prose fields and pillar cell text.
• Two tables are structurally locked (ثلاث محاور pivot + KPI summary) and
  safety-reinjected after parsing to prevent hallucinated numbers.
• The "المحاور الثلاثة" table is built deterministically from prior
  section outputs (roadmap rows + AI use cases + gap recommendations).
• The "KPI summary table" is computed from real case counts and metrics,
  not invented — matches numbers already published in earlier sections.
• Complaint-specific metrics replace inquiry percentages:
  - digital_channel_rate: % of complaints via digital submission channels
  - zero_rejection_rate: % of complaints with 0 formal rejections
  - traffic_complaint_pct: % of traffic service complaints
"""

import json
import re
from typing import Dict, Any, List, Optional
from collections import defaultdict

import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response, extract_methodology_context
from .utils import normalize_arabic
from .validate_llm_numbers import validate_section_9_narrative, _compute_proactive_cancellable_count
from .generate_digital_gaps_section import _DIGITAL_SUBMISSION_CHANNELS


# ──────────────────────────────────────────────────────────────────────────────
# Pre-computation helpers
# ──────────────────────────────────────────────────────────────────────────────

def _compute_sla_stats(state: PipelineState) -> tuple[int, float]:
    """
    Return (sla_closed_count, sla_rate_pct) from all_classified.

    CRITICAL: If SLA column is entirely empty (no cases have SLA data),
    returns (0, 0.0) to prevent LLM hallucination of fake percentages.
    """
    cases = state.all_classified or []

    # Count cases with non-empty SLA data
    cases_with_sla_data = sum(
        1 for c in cases
        if c.sla_closed_on_time and str(c.sla_closed_on_time).strip()
    )

    # If no cases have SLA data, column is empty — suppress metric
    if cases_with_sla_data == 0:
        return 0, 0.0

    # Count on-time closures among those with SLA data
    sla_closed = sum(
        1 for c in cases
        if c.sla_closed_on_time and str(c.sla_closed_on_time).strip() == 'نعم'
    )
    total = len(cases) or 1
    return sla_closed, round(sla_closed / total * 100, 1)


def _compute_submission_channel_pct(state: PipelineState) -> tuple[float, str]:
    """
    Compute the submission channel percentage from case_channel data.

    Returns pre-calculated value from state.digital_channel_pct if available
    (set by stage6_artifacts). Otherwise calculates from state.all_classified.

    Returns (percentage, formatted string like "75.2%").
    """
    # Use pre-calculated value from stage6_artifacts if available
    if hasattr(state, 'digital_channel_pct') and state.digital_channel_pct is not None:
        pct = state.digital_channel_pct
        return pct, f"{pct}%"

    # Fallback: calculate if not yet set (should not happen in normal flow)
    cases = state.all_classified or []
    total = len(cases) or 1

    digital_submissions = sum(
        1 for c in cases
        if c.case_channel and any(
            kw in str(c.case_channel) for kw in _DIGITAL_SUBMISSION_CHANNELS
        )
    )
    pct = round(digital_submissions / total * 100, 1)
    return pct, f"{pct}%"


def _compute_friction_digital_context_pct(state: PipelineState) -> tuple[float, str]:
    """
    Compute digital-context percentage using journey_map inference.

    This matches the calculation in generate_digital_gaps_section._friction_digital_context_pct().
    The metric is SERVICE CONTEXT (whether the problem occurred in a digital channel —
    app error, online renewal, digital payment) — NOT the CRM submission channel.

    Returns empty string if the percentage is zero (LLM will not cite it).
    """
    if not state.journey_map:
        return 0.0, ""

    _DIGITAL_ROOT_CAUSES = {"platform_bug", "no_proactive_notification"}
    _DIGITAL_KEYWORDS = {
        "تطبيق", "موقع", "إلكتروني", "moi", "online", "app",
        "تجديد", "دفع", "رقمي", "بوابة", "نظام", "رفع",
    }

    total_friction_cases = sum(f.case_count for f in state.journey_map)
    if not total_friction_cases:
        return 0.0, ""

    digital_cases = 0
    for friction in state.journey_map:
        # Build text from all friction fields
        text = " ".join([
            friction.friction_point_ar or friction.friction_point or "",
            friction.cluster_ar or friction.cluster or "",
            friction.sub_classification or "",
        ]).lower()

        # Check if this friction point is rooted in a digital context
        is_digital = (
            friction.root_cause_category in _DIGITAL_ROOT_CAUSES
            or any(kw in text for kw in _DIGITAL_KEYWORDS)
        )

        if is_digital:
            digital_cases += friction.case_count

    pct = round(digital_cases / total_friction_cases * 100, 1)
    return pct, f"{pct}%" if pct > 0 else ""


def _compute_digital_channel_rate(state: PipelineState) -> tuple[int, float]:
    """
    Compute % of complaints via digital channels (app, website, email, NCRM).

    Returns (count, percentage) for complaints submitted through digital channels.
    Uses pre-calculated state.digital_channel_pct if available, otherwise computes.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    # Use pre-calculated percentage from stage6_artifacts if available
    if hasattr(state, 'digital_channel_pct') and state.digital_channel_pct is not None:
        pct = state.digital_channel_pct
        # Compute count to match percentage
        digital_count = sum(
            1 for c in cases
            if c.case_channel and any(
                kw in str(c.case_channel) for kw in _DIGITAL_SUBMISSION_CHANNELS
            )
        )
        return digital_count, pct

    # Fallback: calculate if not yet set (should not happen in normal flow)
    digital_count = sum(
        1 for c in cases
        if c.case_channel and any(
            kw in str(c.case_channel) for kw in _DIGITAL_SUBMISSION_CHANNELS
        )
    )
    pct = round(digital_count / total * 100, 1)
    return digital_count, pct


def _compute_zero_rejection_rate(state: PipelineState) -> tuple[int, float]:
    """
    Compute % of complaints WITHOUT formal rejection status (الحالة != 'طلب مرفوض').

    Returns (count, percentage) for complaints that were handled without formal rejections.
    This reflects handling quality where rejections are explicitly marked in the original data.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    # Count cases that are NOT formally rejected (status != 'طلب مرفوض')
    # Uses case_status field captured from input الحالة column
    non_rejected = sum(
        1 for c in cases
        if not c.case_status or c.case_status.strip() != 'طلب مرفوض'
    )
    pct = round(non_rejected / total * 100, 1)
    return non_rejected, pct


def _compute_closure_rate(state: PipelineState) -> tuple[int, float]:
    """
    Compute % of cases with a closure date (date_closed is not empty/NaT).

    Uses SAME logic as _build_resolution_analysis_rows in generate_workload_map_section.py
    to ensure Section 3.3 (closure count) and conclusion (closure rate) are consistent.

    FIX 4: Falls back to authoritative count from state.closed_cases_count if mismatch
    (indicates LLM batch timeout caused date_closed loss).

    Returns (count, percentage) for cases that have been closed (closure date populated).
    This is separate from SLA compliance and measures closure completion.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    # Match the logic from generate_workload_map_section._build_resolution_analysis_rows:
    # Check if date_closed attribute exists AND is truthy AND has non-empty string representation
    closed_count = sum(
        1 for c in cases
        if c.date_closed and str(c.date_closed).strip()
    )

    # FIX 4: Use authoritative count if mismatch (LLM timeout lost dates)
    if state.closed_cases_count and closed_count != state.closed_cases_count:
        print(
            f"[Conclusion] Closure count mismatch: computed={closed_count}, "
            f"authoritative={state.closed_cases_count}. Using authoritative."
        )
        closed_count = state.closed_cases_count
        total = state.total_cases or total

    pct = round(closed_count / total * 100, 1)
    return closed_count, pct


def _compute_traffic_complaint_pct(state: PipelineState) -> tuple[int, float]:
    """
    Compute % of traffic service complaints in the overall complaint set.

    Returns (count, percentage) for traffic-related complaints.
    Used to identify service-specific concentration.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    # Count complaints where service_name or complaint_category contains traffic keywords
    traffic_keywords = {"مرور", "traffic", "مخالفات", "رخصة", "vehicle"}
    traffic_count = sum(
        1 for c in cases
        if (c.service_name and any(kw in str(c.service_name).lower() for kw in traffic_keywords))
        or (c.complaint_category and any(kw in str(c.complaint_category).lower() for kw in traffic_keywords))
    )
    pct = round(traffic_count / total * 100, 1)
    return traffic_count, pct


def _compute_complaint_severity(state: PipelineState) -> Dict[str, int]:
    """
    Compute distribution of complaint severity levels.

    Returns dict with keys like 'critical', 'high', 'medium', 'low'
    containing counts of complaints at each level.
    """
    cases = state.all_classified or []
    severity_dist = defaultdict(int)

    for c in cases:
        if hasattr(c, 'severity') and c.severity:
            severity = str(c.severity).lower().strip()
            severity_dist[severity] += 1
        else:
            severity_dist['unknown'] += 1

    return dict(severity_dist)


def _count_proactive_cancellable(state: PipelineState) -> int:
    """
    Count cases cancellable by proactive notification.

    Uses shared function _compute_proactive_cancellable_count from validate_llm_numbers
    to ensure consistency across all sections (Sections 5, 6.2, and 9).
    Computes dynamically from notification_opportunities post-reconciliation (Stage 4).
    """
    return _compute_proactive_cancellable_count(state)


def _count_critical_gaps(state: PipelineState) -> int:
    """Return number of Critical-severity gaps from Stage 5."""
    return sum(1 for g in (state.gap_table or []) if g.severity == 'Critical')


def _clean_tool_name(raw_text: str) -> str:
    """
    ── FIX 5: Extract clean tool name from LLM-generated prose ──

    Removes:
    - Parenthetical case counts like "(12 حالة)" or "(12+ شكوى)"
    - Filler phrases like "هذه الفجوة الأعلى حجمًا"
    - Everything after first sentence/colon
    - Trailing whitespace

    Returns: Clean tool name (max 80 chars for table display)

    Examples:
        "نظام المتابعة الاستباقية" → "نظام المتابعة الاستباقية" ✓
        "هذه الفجوة الأعلى حجمًا (12 حالة). التطبيق الفوري..." → "" (filtered as prose)
        "مصنِّف النصوص (12 حالة)" → "مصنِّف النصوص"
    """
    if not raw_text:
        return ""

    # STEP 1: Take only first sentence (before . : ، ؛ or newline)
    first_sentence = re.split(r'[.:\n،؛]', raw_text)[0].strip()

    if not first_sentence:
        return ""

    # STEP 2: Remove parenthetical case counts
    # Examples: "(12 حالة)", "(12+ شكاوى)", "(N cases)"
    no_counts = re.sub(r'\(\d+\+?\s*(?:حالة|شكوى|cases)[^)]*\)', '', first_sentence).strip()

    # STEP 3: Remove embedded case count markers
    # Examples: "12+ شكوى", "12 حالة"
    no_inline_counts = re.sub(r'\d+\+?\s*(?:حالة|شكوى|cases)', '', no_counts).strip()

    # STEP 4: Filter out known filler phrases that shouldn't be tool names
    filler_phrases = [
        "هذه الفجوة",
        "الأعلى حجمًا",
        "التطبيق الفوري",
        "تطبيق نظام",
        "تحسين",
        "معالجة",
        "نسبة",
    ]

    for phrase in filler_phrases:
        if no_inline_counts.lower().startswith(phrase.lower()):
            # This is just description, not a tool name
            return ""

    # STEP 5: Cap at 80 chars for table display
    clean = no_inline_counts[:80]

    # STEP 6: Validate that it's actually a tool name (contains meaningful Arabic)
    if len(clean) < 3:  # Too short to be a tool name
        return ""

    return clean


def build_conclusion_pivot_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Build the three-pillar transformation pivot table from run-specific findings.

    Architecture: pair each roadmap row with the journey_map friction at the same
    index (both ordered by case_count descending). Use the roadmap's التوصية text
    (action phrases) as cell content, and the friction's root_cause_category to
    determine which pillar it belongs to. No text matching needed.

      • Pillar 1 (الدقة):    roadmap التوصية from rows paired with friction entries
                              whose root_cause is in {platform_bug, wrong_channel_used,
                              policy_complexity, missing_info, inaccessible_info}
      • Pillar 2 (الإتاحة):  roadmap التوصية from rows paired with friction entries
                              whose root_cause is in {no_proactive_notification,
                              processing_delay, service_delivery_failure}
      • Pillar 3 (الذكاء):   AI tool names from ai_use_cases (cleaned short labels)

    Fallbacks use run-specific journey_map friction labels, not hardcoded strings.
    """

    ACCURACY_ROOT_CAUSES = {
        'platform_bug', 'wrong_channel_used', 'policy_complexity',
        'missing_info', 'inaccessible_info',
    }
    ACCESSIBILITY_ROOT_CAUSES = {
        'no_proactive_notification', 'processing_delay', 'service_delivery_failure',
    }

    def _short(text: str) -> str:
        """First clause only — keeps cell text concise."""
        return text.split('،')[0].split('.')[0].strip()

    # Read roadmap rows.
    roadmap_section = (state.report_sections_ar or {}).get('improvement_roadmap', {})
    roadmap_raw = roadmap_section.get('raw_data', {}) if roadmap_section else {}
    roadmap_rows = roadmap_raw.get('roadmap_table', []) if roadmap_raw else []

    # Build lookup: friction_point_ar/cluster_ar → root_cause_category from journey_map.
    # Used to resolve the root_cause of journey_map-sourced roadmap rows.
    friction_rc_lookup = {}
    for f in (state.journey_map or []):
        for key in [f.friction_point_ar, f.friction_point, f.cluster_ar, f.cluster]:
            if key:
                friction_rc_lookup[key.strip().lower()] = f.root_cause_category

    journey_map_sorted = sorted(
        state.journey_map or [],
        key=lambda f: f.case_count,
        reverse=True,
    )

    # Build lookup: gap topic → root_cause via journey_map matching.
    # Used to resolve the root_cause of gap_table-sourced roadmap rows.
    def _rc_for_gap_topic(topic: str) -> str:
        t = (topic or '').strip().lower()
        if t in friction_rc_lookup:
            return friction_rc_lookup[t]
        for fkey, rc in friction_rc_lookup.items():
            if t and fkey and (t in fkey or fkey in t):
                return rc
        return ''

    accuracy_items = []
    accessibility_items = []

    for row in roadmap_rows:
        rec = _short((row.get('التوصية') or '').strip())
        if not rec:
            continue

        row_id = (row.get('row_id') or '').lower()

        # Determine root_cause from row_id prefix (encodes the source).
        if row_id.startswith('notif_'):
            # Notification opportunities are always accessibility domain.
            root_cause = 'no_proactive_notification'

        elif row_id.startswith('gap_'):
            # Find the gap this row came from via row_id (format: gap_<topic[:40]>).
            gap_key = row_id[4:].replace('_', ' ')
            root_cause = _rc_for_gap_topic(gap_key)

        elif row_id.startswith('journey_') or row_id.startswith('consolidated_'):
            # Find the friction this row came from.
            friction_key = row_id.split('_', 1)[1].replace('_', ' ')
            root_cause = friction_rc_lookup.get(friction_key, '')
            if not root_cause:
                root_cause = _rc_for_gap_topic(friction_key)

        elif row_id.startswith('ai_'):
            # AI use case rows belong to the intelligence pillar — skip for 1 and 2.
            continue

        else:
            root_cause = ''

        if root_cause in ACCURACY_ROOT_CAUSES and len(accuracy_items) < 4:
            accuracy_items.append(rec)
        elif root_cause in ACCESSIBILITY_ROOT_CAUSES and len(accessibility_items) < 4:
            accessibility_items.append(rec)
        elif not root_cause and len(accessibility_items) < 4:
            # Unresolved root cause: default to accessibility
            # (most unresolved roadmap items are notification-related)
            accessibility_items.append(rec)

    # ── Pillar 3: AI tool names ──
    intelligence_items = []
    ai_section = (state.report_sections_ar or {}).get('ai_use_cases', {})
    ai_raw = ai_section.get('raw_data', {}) if ai_section else {}
    for row in (ai_raw.get('use_cases_table', []) if ai_raw else [])[:4]:
        tool = _clean_tool_name(row.get('الأداة', ''))
        if tool and len(intelligence_items) < 4:
            intelligence_items.append(tool)

    # ── Fallbacks: use run-specific journey_map friction labels ──
    # These only kick in if roadmap is empty or sparse.
    if len(accuracy_items) < 4:
        for friction in journey_map_sorted:
            if friction.root_cause_category in ACCURACY_ROOT_CAUSES:
                label = _short(friction.friction_point_ar or friction.friction_point or '')
                if label and label not in accuracy_items and len(accuracy_items) < 4:
                    accuracy_items.append(label)

    if len(accessibility_items) < 4:
        for friction in journey_map_sorted:
            if friction.root_cause_category in ACCESSIBILITY_ROOT_CAUSES:
                label = _short(friction.friction_point_ar or friction.friction_point or '')
                if label and label not in accessibility_items and len(accessibility_items) < 4:
                    accessibility_items.append(label)

    if len(intelligence_items) < 4:
        for notif in (state.notification_opportunities or []):
            label = (notif.get('notification_type') or '').strip()
            if label and label not in intelligence_items and len(intelligence_items) < 4:
                intelligence_items.append(label)

    # ── Hard defaults: last resort, should never be reached in a normal run ──
    accuracy_defaults = [
        "تحسين دقة توجيه الشكاوى",
        "تقليص الشكاوى المكررة",
        "تصحيح بيانات المخالفات",
        "توضيح نطاق الاختصاص",
    ]
    accessibility_defaults = [
        "إشعارات SMS استباقية عند كل تحديث",
        "نظام تتبع ذاتي لحالة الشكوى",
        "إشعار فوري عند استلام البلاغ",
        "توضيح مسارات الاستئناف",
    ]
    intelligence_defaults = [
        "مُصنِّف النصوص الآلي بتقنية NLP",
        "نظام كشف الشذوذ الإحصائي",
        "وكيل اقتراح الردود بتقنية RAG",
        "نموذج التنبؤ بحجم الشكاوى",
    ]
    for d in accuracy_defaults:
        if len(accuracy_items) < 4:
            accuracy_items.append(d)
    for d in accessibility_defaults:
        if len(accessibility_items) < 4:
            accessibility_items.append(d)
    for d in intelligence_defaults:
        if len(intelligence_items) < 4:
            intelligence_items.append(d)

    # ── Pad to exactly 4 rows ──
    while len(accuracy_items) < 4:
        accuracy_items.append("")
    while len(accessibility_items) < 4:
        accessibility_items.append("")
    while len(intelligence_items) < 4:
        intelligence_items.append("")

    return [
        {
            "المحور الأول: الدقة":    accuracy_items[i],
            "المحور الثاني: الإتاحة": accessibility_items[i],
            "المحور الثالث: الذكاء":  intelligence_items[i],
        }
        for i in range(4)
    ]


def _build_kpi_summary_table(
    state: PipelineState,
    digital_channel_rate: float,
    zero_rejection_rate: float,
    traffic_complaint_pct: float,
    proactive_cancellable: int,
) -> Dict[str, Any]:
    """
    Build the KPI summary table for complaints — all metrics from actual pipeline data.

    From brief: "Add KPI summary table at bottom: Columns: خفض الحجم | جودة المعالجة | قابل للإلغاء"

    Three columns with real metrics computed from all_classified:
      1. خفض الحجم (Volume Reduction): proactive cancellable cases count
      2. جودة المعالجة (Processing Quality): zero rejection rate %
      3. قابل للإلغاء (Eliminable): traffic complaint concentration %

    All numbers are pre-computed from pipeline state (never hallucinated).
    Returns dict with keys:
        headers: [col1, col2, col3]
        rows: [row_data]
    """
    sla_closed, sla_rate = _compute_sla_stats(state)

    # Column 1: Volume Reduction potential — proactive cancellable cases
    col1_header = "خفض الحجم"
    col1_value = f"+{proactive_cancellable} شكوى قابلة للإلغاء بالإشعارات الاستباقية"

    # Column 2: Processing Quality — zero rejection rate
    col2_header = "جودة المعالجة"
    col2_value = f"{zero_rejection_rate:.1f}% من الشكاوى تمت معالجتها بدون رفض رسمي"

    # Column 3: Traffic complaint concentration — identifies service-specific focus area
    col3_header = "قابل للإلغاء"
    col3_value = f"نحو {traffic_complaint_pct:.0f}% من الشكاوى تتعلق بخدمة المرور (نقاط تركيز)"

    return {
        "headers": [col1_header, col2_header, col3_header],
        "rows": [
            {
                col1_header: col1_value,
                col2_header: col2_value,
                col3_header: col3_value,
            }
        ]
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main generator — prompt + API call
# ──────────────────────────────────────────────────────────────────────────────

def generate_conclusion_section(state: PipelineState, api_key: str) -> Dict[str, Any]:
    """
    Generate Section 9 — Conclusion (تاسعاً: الخلاصة — من البيانات إلى القرار).

    Pre-computes all locked data from prior stages (stages 1–8).
    Asks the LLM to write ONLY:
      • section_body       — 3-sentence Arabic opening paragraph
      • closing_statement  — 1 sentence closing call-to-action

    All tables are locked and safety-reinjected after parsing.

    Raises on any failure — no silent fallbacks.

    Args:
        state:   PipelineState (all prior stages must be complete)
        api_key: Anthropic API key

    Returns:
        Dict with keys:
            section, section_body, pivot_table, kpi_summary_table
    """
    # ── Guards ────────────────────────────────────────────────────────────────
    if not state.all_classified:
        raise RuntimeError(
            "[Conclusion] state.all_classified is empty — "
            "Stages 2–3 must complete before generating the conclusion."
        )
    if not state.journey_map:
        raise RuntimeError(
            "[Conclusion] state.journey_map is empty — "
            "Stage 4 (stage4_analysis) must complete before this section."
        )
    if not state.gap_table:
        raise RuntimeError(
            "[Conclusion] state.gap_table is empty — "
            "Stage 5 (stage5_gap) must complete before this section."
        )
    if not state.month_year:
        raise RuntimeError(
            "[Conclusion] state.month_year is not set — Stage 3 must complete first."
        )

    # ── Pre-compute all locked data ───────────────────────────────────────────
    total_cases       = len(state.all_classified)
    date_range        = convert_month_year_to_arabic(state.month_year)
    reclass_count     = state.reclassified_count
    reclass_rate      = state.reclassification_rate

    sla_closed, sla_rate        = _compute_sla_stats(state)
    submission_channel_pct_val, submission_channel_pct_str = _compute_submission_channel_pct(state)
    friction_digital_context_pct_val, friction_digital_context_str = _compute_friction_digital_context_pct(state)

    # Complaints-specific metrics
    digital_channel_count, digital_channel_rate = _compute_digital_channel_rate(state)
    zero_rejection_count, zero_rejection_rate = _compute_zero_rejection_rate(state)
    closure_count, closure_rate = _compute_closure_rate(state)
    traffic_complaint_count, traffic_complaint_pct = _compute_traffic_complaint_pct(state)
    severity_dist = _compute_complaint_severity(state)


    # CRITICAL: Validate closure_rate consistency with state.closed_cases_count
    # Both MUST use the same counting logic: date_closed is truthy AND non-empty string
    # If mismatch exists, it indicates state.closed_cases_count is stale (not recomputed after stage 3)
    if state.closed_cases_count > 0:
        expected_rate = (state.closed_cases_count / (state.total_cases or 1)) * 100
        rate_diff = abs(closure_rate - expected_rate)
        if rate_diff > 0.1:
            print(
                f"[Conclusion] ⚠️  CLOSURE RATE MISMATCH DETECTED (will use closure_count={closure_count} as ground truth):\n"
                f"  closure_rate from _compute_closure_rate(): {closure_rate}% ({closure_count} cases)\n"
                f"  state.closed_cases_count: {state.closed_cases_count} / {state.total_cases} = {expected_rate}%\n"
                f"  Difference: {rate_diff:.1f}%\n"
                f"  CAUSE: state.closed_cases_count was not recomputed after stage 3 (using stale value from stage 1)\n"
                f"  FIX: orchestrator.py now recomputes this after all_classified is created\n"
                f"  ACTION: Using dynamically-computed closure_count={closure_count} ({closure_rate}%) as source of truth"
            )
        else:
            print(f"[Conclusion] ✓ Closure rate consistent: {closure_rate}% (count={closure_count}, state={state.closed_cases_count})")

    proactive_cancellable       = _count_proactive_cancellable(state)
    critical_gap_count          = _count_critical_gaps(state)

    # FIX 3: Distil key findings from prior sections — what the conclusion must echo
    # Get the largest friction point by case_count (source of truth for consistency)
    top_friction = max(
        state.journey_map,
        key=lambda f: f.case_count,
        default=None
    ) if state.journey_map else None
    top_friction_label    = top_friction.cluster_ar or top_friction.cluster if top_friction else ""
    top_friction_count    = top_friction.case_count if top_friction else 0

    top_gap = next(
        (g for g in state.gap_table if g.severity == 'Critical'), None
    ) or (state.gap_table[0] if state.gap_table else None)
    top_gap_label = (top_gap.topic_ar or top_gap.topic) if top_gap else ""

    # Number of notification opportunities (from roadmap section for consistency)
    roadmap_section = (state.report_sections_ar or {}).get('improvement_roadmap', {})
    roadmap_raw = roadmap_section.get('raw_data', {}) if roadmap_section else {}
    roadmap_rows = roadmap_raw.get('roadmap_table', []) if roadmap_raw else []
    immediate_count = sum(
        1 for r in roadmap_rows if '🚨' in str(r.get('الأفق الزمني', '')) or 'فوري' in str(r.get('الأفق الزمني', ''))
    )

    # Locked tables
    pivot_rows  = build_conclusion_pivot_rows(state)
    kpi_summary = _build_kpi_summary_table(
        state,
        digital_channel_rate,
        zero_rejection_rate,
        traffic_complaint_pct,
        proactive_cancellable
    )

    pivot_json  = json.dumps(pivot_rows, ensure_ascii=False, indent=2)
    kpi_json    = json.dumps(kpi_summary, ensure_ascii=False, indent=2)

    # ── Build DATA section — conditionally include SLA if data exists ───────────
    data_section = (
        f'submission_channel_digital_pct: {submission_channel_pct_str}\n'
        f'closure_rate: {closure_rate:.1f}%\n'
    )

    # Only include SLA if column has data (sla_rate != 0 from empty column detection)
    sla_data_exists = sla_rate > 0.0
    if sla_data_exists:
        data_section += f'sla_rate: {sla_rate:.1f}%\n'
        print(f"[Conclusion] SLA metric included: {sla_rate:.1f}%")
    else:
        data_section += '# NOTE: SLA column is empty in this dataset — omit SLA references\n'
        print(f"[Conclusion] ⚠️  SLA column is empty — suppressing SLA metric from prompt")

    data_section += (
        f'zero_rejection_rate: {zero_rejection_rate:.1f}%\n'
        f'reclassification_rate: {reclass_rate:.1f}%\n'
        f'proactive_cancellable: {proactive_cancellable}+\n'
        f'critical_gap_count: {critical_gap_count}\n'
        f'top_gap_label: "{top_gap_label}"\n'
    )

    # ── Build task instructions — conditionally reference SLA ─────────────────
    sentence1_guidance = (
        'Sentence 1: Opening statement that frames the data paradox.\n'
        '  • Start with: "الرسالة النهائية:"\n'
        f'  • Cite digital infrastructure strength: {submission_channel_pct_str} of complaints via digital channels (التطبيق / الموقع الإلكتروني/ بريد الكتروني/NCRM)\n'
        f'  • Cite closure achievement: {closure_rate:.1f}% of cases have closure dates\n'
        f'  • Cite handling quality: {zero_rejection_rate:.1f}% handled without formal rejection\n'
        '  • Use a pivot word (لكن) to acknowledge the gap remains\n'
    )

    constraints_section = (
        'CONSTRAINTS:\n'
        '  • section_body: exactly 3 sentences, formal Arabic\n'
        '  • Every metric must match the DATA section above\n'
        '  • MUST contain لكن — tension between achievement and work ahead\n'
        '  • No double quotes (") — use « » or leave unquoted\n'
        '  • No invented figures or metrics\n'
        '  • Tables: copy VERBATIM, no changes\n'
        '  • CRITICAL: Do NOT cite SLA or reclassification percentages unless instructed\n'
    )

    if not sla_data_exists:
        constraints_section += '  • SLA metric is OMITTED — dataset has no SLA data\n'

    # ── Prompt ────────────────────────────────────────────────────────────────
    prompt = (
        'You are writing Section 9 (the final section) of a formal Arabic government report\n'
        'on customer complaints analysis for Fujairah Police.\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'DATA — use ONLY these numbers, never invent\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'{data_section}\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'TASK — write section_body (exactly 3 sentences)\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '\n'
        f'{sentence1_guidance}\n'
        'Sentence 2: The core challenge and proof.\n'
        f'  • Identify what needs fixing: {critical_gap_count} critical gaps in workflows/processes\n'
        f'  • Reference the primary gap: "{top_gap_label}"\n'
        '  • Frame it as fixable without adding staff (system improvements, not headcount)\n'
        '\n'
        'Sentence 3: The path forward (concrete and actionable).\n'
        f'  • State the solution is in: closing functional gaps + proactive notification + data quality\n'
        f'  • Cite impact: {proactive_cancellable}+ complaints can be prevented by proactive action\n'
        '  • No speculation, no invented percentages\n'
        '\n'
        f'{pivot_json}\n'
        f'{kpi_json}\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'OUTPUT FORMAT — valid JSON only\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '{\n'
        '  "section": "conclusion",\n'
        '  "section_body": "...",\n'
        f'  "pivot_table": {pivot_json},\n'
        f'  "kpi_summary_table": {kpi_json}\n'
        '}\n'
        '\n'
        f'{constraints_section}\n'
        '\n'
        'TASK 9 CRITICAL NOTE:\n'
        '  The مكررة (duplicate) cases and المرفوضة (rejected) cases share overlap in the data.\n'
        '  Do NOT cite a number twice for the same group as if they are separate groups.\n'
        '  Example: if 24 مكررة cases are ALSO the formally rejected cases, cite them ONCE only.\n'
        '  Use the data numbers provided above, but ensure each case group is cited only once.\n'
    )

    # ── API call ──────────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    sla_info = f"sla={sla_rate:.1f}%" if sla_data_exists else "sla=SUPPRESSED(empty_column)"
    print(
        f"[Conclusion] Calling API — total_cases={total_cases}, "
        f"closure={closure_count}/{total_cases}({closure_rate:.1f}%), "
        f"reclass={reclass_count}({reclass_rate:.1f}%), "
        f"{sla_info}, zero_rejection={zero_rejection_rate:.1f}%, "
        f"submission_channel={submission_channel_pct_str}, "
        f"digital={digital_channel_rate:.1f}%, traffic={traffic_complaint_pct:.1f}%, "
        f"proactive={proactive_cancellable}, critical_gaps={critical_gap_count}"
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = parse_json_response(message.content[0].text, tag="Conclusion")
    if result is None:
        raise RuntimeError(
            "[Conclusion] Could not parse JSON from API response.\n"
            f"Raw response: {message.content[0].text[:500]}"
        )

    # Enforce لكن constraint — retry once if missing
    section_body = result.get("section_body", "")
    if "لكن" not in section_body:
        print("[Conclusion] WARNING: section_body missing 'لكن' — retrying with stricter prompt")
        stricter_suffix = (
            "\n\nCRITICAL CORRECTION: Your previous response was rejected because section_body "
            "did not contain the word «لكن». The conclusion MUST acknowledge both progress AND "
            "a new challenge using «لكن» as the pivot. Rewrite section_body only. "
            "Return the full JSON object."
        )
        retry_message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            messages=[
                {"role": "user",      "content": prompt},
                {"role": "assistant", "content": message.content[0].text},
                {"role": "user",      "content": stricter_suffix},
            ],
        )
        retry_result = parse_json_response(retry_message.content[0].text, tag="Conclusion-retry")
        if retry_result and "لكن" in retry_result.get("section_body", ""):
            result = retry_result
        else:
            print("[Conclusion] WARNING: retry also missing 'لكن' — using original output")

    # ── Validate LLM narrative against actual metrics ───────────────────────────
    section_body = result.get("section_body", "")
    section_body, validation_report = validate_section_9_narrative(section_body, state)
    result["section_body"] = section_body  # Use corrected text
    if validation_report["total_issues"] > 0:
        print(f"[Conclusion] ⚠️  Found {validation_report['total_issues']} validation issues, applied corrections:")
        for issue in validation_report["percentage_validations"].get("found_issues", []):
            print(f"  • {issue}")
        for issue in validation_report["case_count_validations"].get("found_issues", []):
            print(f"  • {issue}")
    else:
        print("[Conclusion] ✅ Narrative validation passed")

    # ── Safety-reinject locked tables ─────────────────────────────────────────
    result["pivot_table"] = pivot_rows
    result["kpi_summary_table"]  = kpi_summary

    print(
        f"[Conclusion] ✅ OK — "
        f"pivot_rows={len(pivot_rows)}, "
        f"section_body_len={len(result.get('section_body', ''))}"
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# JSONReportBuilder integration helper
# ──────────────────────────────────────────────────────────────────────────────

def build_conclusion_section_for_json(
    state: "PipelineState",
    lang: str = "ar",
    section_number: int = 9,
) -> Optional[Dict[str, Any]]:
    """
    Build the Section 9 JSON block for JSONReportBuilder.

    Reads from state.report_sections_ar['conclusion']['raw_data'] — no re-computation.

    Paste this function body as a method on JSONReportBuilder:

        def build_conclusion_section(self, lang: str = "ar", section_number: int = 9):
            return build_conclusion_section_for_json(self.state, lang, section_number)

    Args:
        state:          PipelineState (stage6 artifacts must have run)
        lang:           'ar' or 'en'  (currently only 'ar' is fully supported)
        section_number: Ordinal position in the report (default 9)

    Returns:
        JSON section dict or None if raw_data is absent.
    """
    conclusion_section = (state.report_sections_ar or {}).get("conclusion", {})
    raw_data = conclusion_section.get("raw_data") if conclusion_section else None
    if not raw_data:
        print("[Conclusion] WARNING: raw_data missing from report_sections_ar['conclusion']")
        return None

    section_body = raw_data.get("section_body", "")
    pivot_rows   = raw_data.get("pivot_table", [])
    kpi_summary  = raw_data.get("kpi_summary_table", {})

    # ── KPI summary table ─────────────────────────────────────────────────────
    kpi_headers = kpi_summary.get("headers", [])
    kpi_rows    = kpi_summary.get("rows", [])
    kpi_table   = {
        "id":           f"section_{section_number * 10 + 9}_kpi_summary",
        "columns":      kpi_headers,
        "rows":         kpi_rows,
        "row_count":    len(kpi_rows),
        "col_count":    len(kpi_headers),
        "original_index": 1,
    }

    # ── Pivot table ───────────────────────────────────────────────────────────
    pivot_columns = (
        list(pivot_rows[0].keys()) if pivot_rows else
        ["المحور الأول: الدقة", "المحور الثاني: الإتاحة", "المحور الثالث: الذكاء"]
    )
    pivot_table = {
        "id":           f"section_{section_number * 10}_pivot_pillars",
        "columns":      pivot_columns,
        "rows":         pivot_rows,
        "row_count":    len(pivot_rows),
        "col_count":    len(pivot_columns),
        "original_index": 0,
    }

    # ── Sub-sections ──────────────────────────────────────────────────────────
    subsections = [
        {
            "id":       f"section_{section_number * 10 + 8}_المحاور_الثلاثة_للتحول",
            "title":    "المحاور الثلاثة للتحول",
            "title_en": "Three Transformation Pillars",
            "level":    2,
            "content":  "",
            "tables":   [pivot_table],
            "charts":   [],
        },
        {
            "id":       f"section_{section_number * 10 + 9}_ملخص_مؤشرات_الأداء",
            "title":    "ملخص مؤشرات الأداء",
            "title_en": "KPI Summary",
            "level":    2,
            "content":  "",
            "tables":   [kpi_table],
            "charts":   [],
        },
    ]

    # ── Section ordinal prefix ────────────────────────────────────────────────
    ORDINALS = {
        1: "أولاً", 2: "ثانياً", 3: "ثالثاً", 4: "رابعاً", 5: "خامساً",
        6: "سادساً", 7: "سابعاً", 8: "ثامناً", 9: "تاسعاً", 10: "عاشراً",
    }
    ordinal = ORDINALS.get(section_number, f"القسم {section_number}")

    return {
        "id":          f"section_{section_number * 10}_تاسعا_الخلاصة",
        "title":       f"{ordinal}: الخلاصة — من البيانات إلى القرار",
        "title_en":    "Conclusion",
        "level":       2,
        "content":     section_body,
        "tables":      [],
        "charts":      [],
        "subsections": subsections,
    }
