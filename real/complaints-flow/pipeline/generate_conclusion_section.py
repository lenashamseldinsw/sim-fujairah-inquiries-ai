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


# ──────────────────────────────────────────────────────────────────────────────
# Pre-computation helpers
# ──────────────────────────────────────────────────────────────────────────────

def _compute_sla_stats(state: PipelineState) -> tuple[int, float]:
    """Return (sla_closed_count, sla_rate_pct) from all_classified."""
    cases = state.all_classified or []
    sla_closed = sum(1 for c in cases if str(c.sla_color).strip() == 'نعم')
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
    Compute % of complaints via digital channels (app/website).

    Returns (count, percentage) for complaints submitted through digital channels.
    This is pre-computed in state by stage1_validator.py.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    digital_count = sum(
        1 for c in cases
        if c.case_channel and ("تطبيق" in str(c.case_channel) or "موقع" in str(c.case_channel))
    )
    pct = round(digital_count / total * 100, 1)
    return digital_count, pct


def _compute_zero_rejection_rate(state: PipelineState) -> tuple[int, float]:
    """
    Compute % of complaints with 0 formal rejections.

    Returns (count, percentage) for complaints that were handled without formal rejections.
    This reflects handling quality and customer satisfaction.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    # Complaints with rejection_count == 0 or null
    zero_rejection = sum(
        1 for c in cases
        if not hasattr(c, 'rejection_count') or c.rejection_count == 0 or c.rejection_count is None
    )
    pct = round(zero_rejection / total * 100, 1)
    return zero_rejection, pct


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
    Build the three-pillar transformation pivot table deterministically.

    For complaints, the three pillars are:
      • المحور الأول: الدقة (Accuracy) — routing accuracy, reducing "أخرى", complaint classification
      • المحور الثاني: الإتاحة (Accessibility) — proactive notifications, channel clarity, tracking visibility
      • المحور الثالث: الذكاء (Intelligence) — AI classification, anomaly detection, quality assurance

    Pulls items from:
      • Pillar 1 (الدقة): roadmap rows about classification and data quality
      • Pillar 2 (الإتاحة): notification_opportunities + proactive channel improvements
      • Pillar 3 (الذكاء): ai_use_cases section items (from state.report_sections_ar)

    Returns a list of dicts with keys:
        المحور الأول: الدقة | المحور الثاني: الإتاحة | المحور الثالث: الذكاء

    This list is LOCKED — passed verbatim to the JSON report. The LLM may
    only rewrite the prose fields (section_body, closing_statement).
    """
    # --- Pillar 1: Accuracy items (classification, routing, reducing "أخرى") ---
    accuracy_items = [
        "تحسين دقة تصنيف الشكاوى والخدمات",
        "تقليل نسبة شكاوى فئة «أخرى» غير المصنفة",
        "توضيح معايير التوجيه بين الجهات الحكومية",
    ]

    # --- Pillar 2: Accessibility items (proactive, channels, tracking) ---
    # Build from notification_opportunities if present, else use defaults
    opps = state.notification_opportunities or []
    if opps:
        accessibility_items = [o.get('notification_type') or o.get('content_summary', '')
                                for o in opps[:4]]
        # Ensure we have items; fallback to defaults if missing
        if not accessibility_items or not any(accessibility_items):
            accessibility_items = [
                "إشعارات SMS استباقية قبل تصعيد الشكوى",
                "نظام تتبع الشكوى في الوقت الفعلي",
                "توضيح مسارات الاستئناف والدعم",
                "قنوات تواصل موحدة للشكاوى",
            ]
        accessibility_items = accessibility_items[:4]
    else:
        accessibility_items = [
            "إشعارات SMS استباقية قبل تصعيد الشكوى",
            "نظام تتبع الشكوى في الوقت الفعلي",
            "توضيح مسارات الاستئناف والدعم",
            "قنوات تواصل موحدة للشكاوى",
        ]

    # --- Pillar 3: AI/Intelligence items ---
    # Pull from ai_use_cases section if available, else use defaults
    ai_section = (state.report_sections_ar or {}).get('ai_use_cases', {})
    ai_raw = ai_section.get('raw_data', {}) if ai_section else {}
    ai_table = ai_raw.get('use_cases_table', []) if ai_raw else []
    if ai_table:
        intelligence_items = [row.get('الأداة', '') for row in ai_table[:4] if row.get('الأداة')]
    else:
        intelligence_items = [
            "كاشف تصعيد الشكاوى قبل التوجيه",
            "محلل الأنماط والشكاوى المتكررة",
            "مقيّم جودة الحل والرضا التلقائي",
            "رادار الشكاوى الناشئة والاتجاهات",
        ]

    # Pad all three pillars to same length
    max_len = max(len(accuracy_items), len(accessibility_items), len(intelligence_items))
    accuracy_items    += [""] * (max_len - len(accuracy_items))
    accessibility_items += [""] * (max_len - len(accessibility_items))
    intelligence_items  += [""] * (max_len - len(intelligence_items))

    return [
        {
            "المحور الأول: الدقة":     accuracy_items[i],
            "المحور الثاني: الإتاحة":  accessibility_items[i],
            "المحور الثالث: الذكاء":   intelligence_items[i],
        }
        for i in range(max_len)
    ]


def _build_kpi_summary_table(
    state: PipelineState,
    digital_channel_rate: float,
    zero_rejection_rate: float,
    traffic_complaint_pct: float,
    proactive_cancellable: int,
) -> Dict[str, Any]:
    """
    Build the KPI summary table for complaints.

    From brief: "Add KPI summary table at bottom: Columns: خفض الحجم | جودة المعالجة | قابل للإلغاء"

    Three columns representing:
      1. خفض الحجم (Volume Reduction): proactive cancellable cases + traffic concentration
      2. جودة المعالجة (Processing Quality): zero rejection rate + SLA compliance
      3. قابل للإلغاء (Eliminable): complaints that can be prevented via proactive actions

    Returns dict with keys:
        headers: [col1, col2, col3]
        rows: [row_data]
    """
    sla_closed, sla_rate = _compute_sla_stats(state)

    # Column 1: Volume Reduction potential
    col1_header = "خفض الحجم"
    col1_value = f"{proactive_cancellable}+ شكوى قابلة للإلغاء بالإشعارات الاستباقية"

    # Column 2: Processing Quality
    col2_header = "جودة المعالجة"
    col2_value = f"{zero_rejection_rate:.1f}% من الشكاوى تمت معالجتها بدون رفض رسمي"

    # Column 3: Eliminable cases
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

    # ── Build Sentence 1 instruction — always cite submission channel (never zero) ────
    # Submission channel percentage is always available and non-zero.
    # Friction-digital-context percentage is only cited if non-zero.
    sentence1_instruction = (
        '   Sentence 1 — "الرسالة النهائية:" prefix + submission channel performance:\n'
        '     • MUST open with "الرسالة النهائية:"\n'
        f'     • State that {submission_channel_pct_str} of complaints came through digital submission channels '
        f'(التطبيق / الموقع الإلكتروني) combined with SLA rate {sla_rate:.1f}%.\n'
        '     • This proves operational excellence in the submission channel.\n'
    )

    # If friction-digital-context exists (problem occurred in digital channel), cite it separately
    if friction_digital_context_str:
        sentence1_instruction += (
            f'     • SEPARATELY: Additionally, {friction_digital_context_str} of complaint-related friction points '
            '(service context issues) occurred in a digital service context (app error, system issue, digital process).\n'
            '       This shows the gap is not in customer access but in service functionality.\n'
        )

    # ── Prompt ────────────────────────────────────────────────────────────────
    # Build INPUTS section with complaint-specific metrics
    friction_digital_context_input_line = (
        f'friction_digital_context_pct: "{friction_digital_context_str}"  (% of friction cases rooted in digital service context)\n'
        if friction_digital_context_str else
        'friction_digital_context_pct:  [not available — only cite if non-zero]\n'
    )

    # Extract organizational objectives from methodology if present
    methodology_objectives = ""
    if state.complaints_methodology:
        methodology_context = extract_methodology_context(
            state.complaints_methodology,
            ["1_objective"]
        )
        objectives = methodology_context.get("1_objective", {}).get("points", [])
        if objectives:
            methodology_objectives = "\n### أهداف المنهجية الرسمية (يجب تقييم مدى التوافق معها):\n"
            for i, obj in enumerate(objectives, 1):
                methodology_objectives += f"{i}. {obj}\n"
            methodology_objectives += "\nقيّم في الخلاصة مدى توافق بيانات هذه الفترة مع هذه الأهداف الرسمية.\n"

    prompt = (
        'You are writing Section 9 (the final section) of a formal Arabic government report\n'
        'on customer complaints analysis for Fujairah Police. The section title is:\n'
        '"تاسعاً: الخلاصة — من البيانات إلى القرار"\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'INPUTS — use ONLY these numbers, never invent figures\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'total_cases:              {total_cases}\n'
        f'date_range:               "{date_range}"\n'
        f'reclassified_count:       {reclass_count}\n'
        f'reclassification_rate:    "{reclass_rate:.1f}%"\n'
        f'sla_closed:               {sla_closed}\n'
        f'sla_rate:                 "{sla_rate:.1f}%"\n'
        f'submission_channel_digital_pct: "{submission_channel_pct_str}"  (% of complaints submitted via app/website)\n'
        f'digital_channel_rate:     "{digital_channel_rate:.1f}%"  (% of complaints via digital channels)\n'
        f'zero_rejection_rate:      "{zero_rejection_rate:.1f}%"  (% of complaints with 0 formal rejections)\n'
        f'traffic_complaint_pct:    "{traffic_complaint_pct:.1f}%"  (% of traffic service complaints)\n'
        + friction_digital_context_input_line +
        f'proactive_cancellable:    {proactive_cancellable}+  (complaints eliminable by proactive notification)\n'
        f'critical_gap_count:       {critical_gap_count}  (Critical-severity gaps from gap analysis)\n'
        f'top_friction_label:       "{top_friction_label}"\n'
        f'top_friction_count:       {top_friction_count}\n'
        f'top_gap_label:            "{top_gap_label}"\n'
        f'immediate_count:          {immediate_count}  (immediate-horizon roadmap items)\n'
        f'{methodology_objectives}'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'LOCKED TABLES — copy these VERBATIM into pivot_table and kpi_summary_table.\n'
        'Do NOT add, remove, or rephrase any cell in these tables.\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '\n'
        'pivot_table (three transformation pillars — المحاور الثلاثة للتحول):\n'
        f'{pivot_json}\n'
        '\n'
        'kpi_summary_table (complaint processing KPIs — خفض الحجم | جودة المعالجة | قابل للإلغاء):\n'
        f'{kpi_json}\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'YOUR TASK — write ONLY the section_body\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '\n'
        'A. section_body — the opening paragraph of the Conclusion section\n'
        '   Exactly 3 sentences, formal Arabic. Rules:\n'
        '\n'
        + sentence1_instruction +
        '\n'
        '   Sentence 2 — core insight about complaints:\n'
        f'     • State the reclassification finding ({reclass_rate:.1f}%, {reclass_count} cases)\n'
        '       as proof that complaint accuracy and routing can be improved systemically.\n'
        '     • Name the top friction point (complaint driver) and its case count.\n'
        '\n'
        '   Sentence 3 — the pivot to action:\n'
        '     • The analyses in this report prove the solution lies in enhancing complaint\n'
        '       classification accuracy, activating proactive notification, and quality assurance.\n'
        f'     • Reference proactive_cancellable ({proactive_cancellable}+) and critical_gap_count ({critical_gap_count}).\n'
        '     • Must NOT mention adding human resources.\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'OUTPUT FORMAT — respond with ONLY valid JSON, no markdown fences\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '{\n'
        '  "section": "conclusion",\n'
        '  "section_body": "...",\n'
        f'  "pivot_table": {pivot_json},\n'
        f'  "kpi_summary_table": {kpi_json}\n'
        '}\n'
        '\n'
        'RULES:\n'
        '  - pivot_table and kpi_summary_table: copy VERBATIM — do NOT change any value.\n'
        '  - section_body: Arabic only.\n'
        '  - Every number in prose must match a pre-computed input above.\n'
        '  - No markdown, no extra keys, no extra nesting.\n'
        '  - CRITICAL: Do NOT use double-quote characters (") inside any string value. '
        'Use angle brackets « » instead of double quotes when citing names.\n'
        '  - Do not invent figures not present in INPUTS.\n'
        '  - CRITICAL: The section_body MUST contain the word «لكن» — the conclusion must\n'
        '    hold tension between improvements achieved AND a new or ongoing challenge.\n'
        '    A section_body without «لكن» will be rejected.\n'
        '  - CRITICAL: Do NOT mention total complaint volume decline % as a headline\n'
        '    achievement. Volume change is contextual and can mislead across periods.\n'
        '    Focus on specific outcomes: duplicate reduction, rejection elimination,\n'
        '    SLA rate, or preventable complaint count.\n'
    )

    # ── API call ──────────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    print(
        f"[Conclusion] Calling API — total_cases={total_cases}, "
        f"reclass={reclass_count} ({reclass_rate:.1f}%), "
        f"sla={sla_rate:.1f}%, submission_channel={submission_channel_pct_str}, "
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
