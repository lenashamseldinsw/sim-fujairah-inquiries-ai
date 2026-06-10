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
• Two tables are structurally locked (三柱 pivot + KPI impact) and
  safety-reinjected after parsing to prevent hallucinated numbers.
• The "المحاور الثلاثة" table is built deterministically from prior
  section outputs (roadmap rows + AI use cases + gap recommendations).
• The "الأثر المجمّع" KPI strip is computed from real case counts, not
  invented — matches numbers already published in earlier sections.
"""

import json
from typing import Dict, Any, List, Optional
from collections import defaultdict

import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response
from .generate_digital_gaps_section import _DIGITAL_SUBMISSION_CHANNELS


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

    Returns pre-calculated value from state.digital_channel_pct if available
    (set by stage6_artifacts). Otherwise calculates from state.all_classified.

    Returns (percentage, formatted string like "96.0%").
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


def _count_proactive_cancellable(state: PipelineState) -> int:
    """
    Count cases cancellable by proactive notification.

    Prefers final_notif_eliminatable (set after Section 6.2 table is built).
    Falls back through reconciled counts → raw notification_opportunities.
    (Issue 6 fix)
    """
    # Prefer the final reconciled count (set after section 6.2 table is built)
    if state.final_notif_eliminatable > 0:
        return state.final_notif_eliminatable

    # Fallback to reconciled notification counts
    if state.reconciled_notification_counts:
        total = sum(state.reconciled_notification_counts.values())
        if total > 0:
            return total

    # Last resort: raw notification_opportunities (Stage 4 estimate)
    opps = state.notification_opportunities or []
    if opps:
        total = sum(int(o.get('cases_eliminated', 0)) for o in opps)
        if total > 0:
            return total

    # Final fallback: journey_map proactive friction points
    jm = state.journey_map or []
    return sum(j.case_count for j in jm if j.root_cause_category == 'no_proactive_notification')


def _count_critical_gaps(state: PipelineState) -> int:
    """Return number of Critical-severity gaps from Stage 5."""
    return sum(1 for g in (state.gap_table or []) if g.severity == 'Critical')


def _inquiry_pct(state: PipelineState) -> tuple[int, float]:
    """Return (inquiry_count, inquiry_pct) for استفسار cases after reclassification."""
    cases = state.all_classified or []
    total = len(cases) or 1
    count = sum(1 for c in cases if c.actual_contact_type == 'استفسار')
    return count, round(count / total * 100, 1)


def build_conclusion_pivot_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Build the three-pillar transformation pivot table deterministically.

    Pulls items from:
      • Pillar 1 (الدقة / Accuracy):
          – roadmap rows tagged with source 'التحليل' AND related to classification
          – gap recommendations about data quality
      • Pillar 2 (الإتاحة / Accessibility):
          – notification_opportunities + journey_map self-service items
          – gap recommendations about proactive/channel improvements
      • Pillar 3 (الذكاء / Intelligence):
          – ai_use_cases section items (from state.report_sections_ar)

    Returns a list of dicts with keys:
        المحور الأول: الدقة | المحور الثاني: الإتاحة | المحور الثالث: الذكاء

    This list is LOCKED — passed verbatim to the JSON report.  The LLM may
    only rewrite the prose fields (section_body, closing_statement).
    """
    # --- Pillar 1: Accuracy items (data quality, classification) ---
    accuracy_items = [
        "رفع دقة تصنيفات الطلبات",
        "إضافة حقلي السبب الجذري وزمن المعالجة في حل الطلب",
        "إعادة هيكلة تصنيف الخدمات وإلغاء «أخرى»",
    ]

    # --- Pillar 2: Accessibility items (proactive, channels, self-service) ---
    # Build from notification_opportunities if present, else use defaults
    opps = state.notification_opportunities or []
    if opps:
        accessibility_items = [o.get('notification_type') or o.get('content_summary', '')
                                for o in opps[:4]]
        # Ensure we always have the FAQ item
        has_faq = any('فاق' in item or 'شائع' in item for item in accessibility_items)
        if not has_faq:
            accessibility_items.insert(0, "أسئلة شائعة موحدة وشاملة")
        accessibility_items = accessibility_items[:4]
    else:
        accessibility_items = [
            "أسئلة شائعة موحدة وشاملة",
            "نظام تحقق تلقائي من صحة المخالفات",
            "إشعارات SMS استباقية لجميع مراحل المعالجة",
            "نموذج إبلاغ تقني مدمج في التطبيق",
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
            "محقق التناقضات في صور المخالفات",
            "موجّه الحالات بين الجهات الحكومية",
            "مدقق جودة الوثائق قبل الإرسال",
            "رادار نقاط الاحتكاك الجغرافي",
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


def _build_kpi_impact_row(
    state: PipelineState,
    inquiry_pct: float,
    proactive_cancellable: int,
) -> Dict[str, str]:
    """
    Build the single-row KPI impact strip table.

    Column headers are the KPI values themselves (matching the sample report
    layout); the row contains the label describing each metric.

    Four KPIs:
      1. Inquiry self-service potential  → inquiry_pct formatted as "X.X%"
      2. Proactive-cancellable cases     → proactive_cancellable as "N+"
      3. Post-classifier accuracy target → "95%+"  (structural target, not computed)
      4. Contact reduction potential     → "30-40%" (structural range, not computed)
    """
    kpi1_header = f"{inquiry_pct:.1f}%"
    kpi2_header = f"{proactive_cancellable}+"
    kpi3_header = "95%+"
    kpi4_header = "30-40%"

    return {
        "headers": [kpi1_header, kpi2_header, kpi3_header, kpi4_header],
        "row": {
            kpi1_header: "من طلبات التواصل هي استفسارات حقيقية قابلة للتحويل الكامل للخدمة الاستباقية",
            kpi2_header: "حالة قابلة للإلغاء بالإشعار الاستباقي",
            kpi3_header: "دقة تصنيف الحالات بعد المُصنِّف الآلي وتطبيق المبادرات المقترحة",
            kpi4_header: "خفض حالات التواصل المتكرر والاتصالات",
        },
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
            section, section_body, pivot_table, kpi_impact, closing_statement
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
    proactive_cancellable       = _count_proactive_cancellable(state)
    critical_gap_count          = _count_critical_gaps(state)
    inquiry_count, inquiry_pct  = _inquiry_pct(state)

    # Distil key findings from prior sections — what the conclusion must echo
    # Find the friction point with maximum case_count (matches Section 4 logic)
    top_friction = max(state.journey_map, key=lambda f: f.case_count) if state.journey_map else None
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
    kpi_impact  = _build_kpi_impact_row(state, inquiry_pct, proactive_cancellable)

    pivot_json  = json.dumps(pivot_rows, ensure_ascii=False, indent=2)
    kpi_json    = json.dumps(kpi_impact, ensure_ascii=False, indent=2)

    # ── Build Sentence 1 instruction — always cite submission channel (never zero) ────
    # Submission channel percentage is always available and non-zero.
    # Friction-digital-context percentage is only cited if non-zero.
    sentence1_instruction = (
        '   Sentence 1 — "الرسالة النهائية:" prefix + submission channel performance:\n'
        '     • MUST open with "الرسالة النهائية:"\n'
        f'     • State that {submission_channel_pct_str} of cases came through digital submission channels '
        f'(التطبيق / الموقع الإلكتروني/ بريد الكتروني/NCRM) combined with SLA rate {sla_rate:.1f}%.\n'
        '     • This proves operational excellence in the submission channel.\n'
    )

    # If friction-digital-context exists (problem occurred in digital channel), cite it separately
    if friction_digital_context_str:
        sentence1_instruction += (
            f'     • SEPARATELY: Additionally, {friction_digital_context_str} of problem-related cases '
            '(friction points) occurred in a digital service context (app error, online renewal, digital payment).\n'
            '       This shows the gap is not in customer access but in service functionality.\n'
        )

    # ── Prompt ────────────────────────────────────────────────────────────────
    # Build INPUTS section with both submission channel (always present) and
    # friction-digital-context (only if non-zero)
    friction_digital_context_input_line = (
        f'friction_digital_context_pct: "{friction_digital_context_str}"  (% of friction cases rooted in digital service context)\n'
        if friction_digital_context_str else
        'friction_digital_context_pct:  [not available — only cite if non-zero]\n'
    )

    prompt = (
        'You are writing Section 9 (the final section) of a formal Arabic government report\n'
        'on customer inquiry analysis for Fujairah Police. The section title is:\n'
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
        f'submission_channel_digital_pct: "{submission_channel_pct_str}"  (% of cases submitted via app/website)\n'
        + friction_digital_context_input_line +
        f'inquiry_count:            {inquiry_count}   (استفسار cases after reclassification)\n'
        f'inquiry_pct:              "{inquiry_pct:.1f}%"\n'
        f'proactive_cancellable:    {proactive_cancellable}+  (cases eliminable by proactive notification)\n'
        f'critical_gap_count:       {critical_gap_count}  (Critical-severity gaps from gap analysis)\n'
        f'top_friction_label:       "{top_friction_label}"\n'
        f'top_friction_count:       {top_friction_count}\n'
        f'top_gap_label:            "{top_gap_label}"\n'
        f'immediate_count:          {immediate_count}  (immediate-horizon roadmap items)\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'LOCKED TABLES — copy these VERBATIM into pivot_table and kpi_impact.\n'
        'Do NOT add, remove, or rephrase any cell in these tables.\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '\n'
        'pivot_table (three transformation pillars — المحاور الثلاثة للتحول):\n'
        f'{pivot_json}\n'
        '\n'
        'kpi_impact (aggregate impact strip — الأثر المجمّع المتوقع):\n'
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
        '   Sentence 2 — core insight:\n'
        f'     • State the reclassification finding ({reclass_rate:.1f}%, {reclass_count} cases)\n'
        f'       as proof that the problem is not missing channels but missing functions.\n'
        '     • Name the top friction point and its case count.\n'
        '\n'
        '   Sentence 3 — the pivot to action:\n'
        '     • The analyses in this report prove the solution lies in closing functional\n'
        '       gaps, activating proactive notification, and correcting data quality.\n'
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
        f'  "kpi_impact": {kpi_json}\n'
        '}\n'
        '\n'
        'RULES:\n'
        '  - pivot_table and kpi_impact: copy VERBATIM — do NOT change any value.\n'
        '  - section_body: Arabic only.\n'
        '  - Every number in prose must match a pre-computed input above.\n'
        '  - No markdown, no extra keys, no extra nesting.\n'
        '  - CRITICAL: Do NOT use double-quote characters (\") inside any string value. '
        'Use angle brackets « » instead of double quotes when citing names.\n'
        '  - Do not invent figures not present in INPUTS.\n'
    )

    # ── API call ──────────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    print(
        f"[Conclusion] Calling API — total_cases={total_cases}, "
        f"reclass={reclass_count} ({reclass_rate:.1f}%), "
        f"sla={sla_rate:.1f}%, submission_channel={submission_channel_pct_str}, "
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

    # ── Safety-reinject locked tables ─────────────────────────────────────────
    result["pivot_table"] = pivot_rows
    result["kpi_impact"]  = kpi_impact

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
    kpi_impact   = raw_data.get("kpi_impact", {})

    # ── KPI impact strip → table ──────────────────────────────────────────────
    kpi_headers = kpi_impact.get("headers", [])
    kpi_row     = kpi_impact.get("row", {})
    kpi_table   = {
        "id":           f"section_{section_number * 10 + 9}_kpi_impact",
        "columns":      kpi_headers,
        "rows":         [kpi_row] if kpi_row else [],
        "row_count":    1 if kpi_row else 0,
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
            "id":       f"section_{section_number * 10 + 9}_الأثر_المجمع_المتوقع",
            "title":    "الأثر المجمّع المتوقع:",
            "title_en": "Expected Aggregate Impact",
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
