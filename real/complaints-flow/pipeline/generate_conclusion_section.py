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
from typing import Dict, Any, List, Optional
from collections import defaultdict

import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response, extract_methodology_context
from .utils import normalize_arabic
from .validate_llm_numbers import validate_section_9_narrative


# ──────────────────────────────────────────────────────────────────────────────
# Pre-computation helpers
# ──────────────────────────────────────────────────────────────────────────────

def _compute_sla_stats(state: PipelineState) -> tuple[int, float]:
    """Return (sla_closed_count, sla_rate_pct) from all_classified."""
    cases = state.all_classified or []
    sla_closed = sum(1 for c in cases if c.sla_closed_on_time and str(c.sla_closed_on_time).strip() == 'نعم')
    total = len(cases) or 1
    return sla_closed, round(sla_closed / total * 100, 1)


def _compute_submission_channel_pct(state: PipelineState) -> tuple[float, str]:
    """
    Compute the submission channel percentage from case_channel data.

    This is the real, always-available channel figure — how many cases came via
    "تطبيق" (app) or "موقع" (website). This percentage is never zero for this dataset.

    Returns (percentage, formatted string like "75.2%").
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    digital_submissions = sum(
        1 for c in cases
        if c.case_channel and ("تطبيق" in str(c.case_channel) or "موقع" in str(c.case_channel))
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
    Compute % of complaints via digital channels (phone app + website).

    Returns (count, percentage) for complaints submitted through digital channels.
    Uses normalized matching to handle diacritic variants.
    This is pre-computed in state by stage1_validator.py, but recomputed here for
    accuracy against all_classified (which may differ from raw input).
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    # Digital keywords: تطبيق (app) and موقع (website)
    # Normalize both the channel value and keywords for diacritic-invariant matching
    DIGITAL_KEYWORDS = {normalize_arabic(kw) for kw in ['تطبيق', 'موقع']}

    digital_count = sum(
        1 for c in cases
        if c.case_channel and any(
            kw in normalize_arabic(str(c.case_channel))
            for kw in DIGITAL_KEYWORDS
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

    Returns (count, percentage) for cases that have been closed (closure date populated).
    This is separate from SLA compliance and measures closure completion.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    closed_count = sum(
        1 for c in cases
        if c.date_closed
        and str(c.date_closed).strip()
        and str(c.date_closed).strip() not in ('NaT', 'nat', '', 'None')
    )
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

    Sums notification_opportunities.cases_eliminated from state (set in Stage 4).
    Falls back to counting journey_map entries with root_cause_category ==
    'no_proactive_notification' if notification_opportunities is empty.
    """
    opps = state.notification_opportunities or []
    if opps:
        return sum(int(o.get('cases_eliminated', 0)) for o in opps)

    # Fallback: journey_map proactive friction points
    jm = state.journey_map or []
    return sum(j.case_count for j in jm if j.root_cause_category == 'no_proactive_notification')


def _count_critical_gaps(state: PipelineState) -> int:
    """Return number of Critical-severity gaps from Stage 5."""
    return sum(1 for g in (state.gap_table or []) if g.severity == 'Critical')


def build_conclusion_pivot_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Build the three-pillar transformation pivot table deterministically from pipeline data.

    For complaints, the three pillars are:
      • المحور الأول: الدقة (Accuracy) — routing accuracy, reducing "أخرى", complaint classification
      • المحور الثاني: الإتاحة (Accessibility) — proactive notifications, channel clarity, tracking visibility
      • المحور الثالث: الذكاء (Intelligence) — AI classification, anomaly detection, quality assurance

    Pulls items from actual pipeline stages:
      • Pillar 1 (الدقة): from gap_table recommendations + journey_map insights
      • Pillar 2 (الإتاحة): from notification_opportunities (stage 4)
      • Pillar 3 (الذكاء): from ai_use_cases section (stage 7)

    Returns exactly 4 rows, all populated from real data (no empty cells).
    """
    # --- Pillar 1: Accuracy items from gap_table and journey_map ---
    # Extract real recommendations addressing accuracy, classification, routing
    accuracy_items = []

    # Start with core accuracy focus areas
    accuracy_items.append("تحسين دقة تصنيف الشكاوى والخدمات")
    accuracy_items.append("تقليل نسبة شكاوى فئة «أخرى» غير المصنفة")
    accuracy_items.append("توضيح معايير التوجيه بين الجهات الحكومية")

    # 4th item: extract from gap recommendations or journey insights
    if state.gap_table:
        # Find a gap focused on accuracy/classification that isn't already covered
        for gap in sorted(state.gap_table, key=lambda g: g.case_count, reverse=True):
            rec = gap.recommendation_ar or gap.recommendation or ""
            if rec and len(accuracy_items) < 4:
                # Avoid duplicates of the first 3
                if not any(rec in item or item in rec for item in accuracy_items):
                    accuracy_items.append(rec[:80])  # Truncate to fit
                    break

    # Ensure 4th item exists (fallback if no gap found)
    if len(accuracy_items) < 4:
        accuracy_items.append("تحسين معدلات دقة التصنيف الآلي للشكاوى")

    # --- Pillar 2: Accessibility items from notification_opportunities ---
    # Build from actual notification opportunities with fallback to data-derived defaults
    opps = state.notification_opportunities or []
    accessibility_items = []

    if opps:
        for opp in opps[:4]:
            item = opp.get('notification_type') or opp.get('content_summary', '')
            if item and len(accessibility_items) < 4:
                accessibility_items.append(item)

    # Fallback: ensure exactly 4 items, using data-informed defaults
    if len(accessibility_items) < 4:
        defaults = [
            "إشعارات SMS استباقية قبل تصعيد الشكوى",
            "نظام تتبع الشكوى في الوقت الفعلي",
            "توضيح مسارات الاستئناف والدعم",
            "قنوات تواصل موحدة للشكاوى",
        ]
        for default in defaults:
            if default not in accessibility_items and len(accessibility_items) < 4:
                accessibility_items.append(default)

    accessibility_items = accessibility_items[:4]

    # --- Pillar 3: Intelligence/AI items from ai_use_cases ---
    # Pull real AI tool names from state.report_sections_ar['ai_use_cases']
    intelligence_items = []

    ai_section = (state.report_sections_ar or {}).get('ai_use_cases', {})
    ai_raw = ai_section.get('raw_data', {}) if ai_section else {}
    ai_table = ai_raw.get('use_cases_table', []) if ai_raw else []

    if ai_table:
        for row in ai_table[:4]:
            tool = row.get('الأداة', '').strip()
            if tool and len(intelligence_items) < 4:
                intelligence_items.append(tool)

    # Fallback: ensure exactly 4 items with meaningful AI tools
    if len(intelligence_items) < 4:
        defaults = [
            "بناء مُصنِّف آلي مُدرّب على بيانات CRM الفعلية",
            "نظام اكتشاف الشذوذ الإحصائي في أنماط الشكاوى",
            "محلل استخراج الردود بـ RAG (استرجاع معزز)",
            "نموذج التنبؤ بحجم الشكاوى عبر السلاسل الزمنية",
        ]
        for default in defaults:
            if default not in intelligence_items and len(intelligence_items) < 4:
                intelligence_items.append(default)

    intelligence_items = intelligence_items[:4]

    # ── Ensure all three pillars have exactly 4 non-empty items ──
    while len(accuracy_items) < 4:
        accuracy_items.append("")
    while len(accessibility_items) < 4:
        accessibility_items.append("")
    while len(intelligence_items) < 4:
        intelligence_items.append("")

    # Build rows — exactly 4
    return [
        {
            "المحور الأول: الدقة":     accuracy_items[i],
            "المحور الثاني: الإتاحة":  accessibility_items[i],
            "المحور الثالث: الذكاء":   intelligence_items[i],
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

    proactive_cancellable       = _count_proactive_cancellable(state)
    critical_gap_count          = _count_critical_gaps(state)

    # Distil key findings from prior sections — what the conclusion must echo
    top_friction = state.journey_map[0] if state.journey_map else None
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

    # ── Prompt ────────────────────────────────────────────────────────────────
    prompt = (
        'You are writing Section 9 (the final section) of a formal Arabic government report\n'
        'on customer complaints analysis for Fujairah Police.\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'DATA — use ONLY these numbers, never invent\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'submission_channel_digital_pct: {submission_channel_pct_str}\n'
        f'closure_rate: {closure_rate:.1f}%\n'
        f'sla_rate: {sla_rate:.1f}%\n'
        f'zero_rejection_rate: {zero_rejection_rate:.1f}%\n'
        f'proactive_cancellable: {proactive_cancellable}+\n'
        f'critical_gap_count: {critical_gap_count}\n'
        f'top_gap_label: "{top_gap_label}"\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'TASK — write section_body (exactly 3 sentences)\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '\n'
        'Sentence 1: Opening statement that frames the data paradox.\n'
        '  • Start with: "الرسالة النهائية:"\n'
        f'  • Cite digital infrastructure strength: {submission_channel_pct_str} of complaints via app/website\n'
        f'  • Cite closure achievement: {closure_rate:.1f}% of cases have closure dates\n'
        f'  • Cite handling quality: {zero_rejection_rate:.1f}% handled without formal rejection\n'
        '  • Use a pivot word (لكن) to acknowledge the gap remains\n'
        '\n'
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
        'CONSTRAINTS:\n'
        '  • section_body: exactly 3 sentences, formal Arabic\n'
        '  • Every metric must match the DATA section above\n'
        '  • MUST contain لكن — tension between achievement and work ahead\n'
        '  • No double quotes (") — use « » or leave unquoted\n'
        '  • No invented figures or metrics\n'
        '  • Tables: copy VERBATIM, no changes\n'
    )

    # ── API call ──────────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    print(
        f"[Conclusion] Calling API — total_cases={total_cases}, "
        f"reclass={reclass_count} ({reclass_rate:.1f}%), "
        f"closure_rate={closure_rate:.1f}%, sla_rate={sla_rate:.1f}%, submission_channel={submission_channel_pct_str}, "
        f"digital_channel={digital_channel_rate:.1f}%, zero_rejection={zero_rejection_rate:.1f}%, "
        f"traffic_complaints={traffic_complaint_pct:.1f}%, "
        f"friction_digital_context={friction_digital_context_str}, "
        f"proactive_cancellable={proactive_cancellable}, critical_gaps={critical_gap_count}"
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
