"""
generate_digital_gaps_section — stage6_artifacts.py companion

Generates Section 5: "خامساً: التحليل الثالث — تحليل الفجوات الرقمية"

INTEGRATION
───────────
1. stage6_artifacts.py — _generate_report_sections(), after customer_journey block:

    from .generate_digital_gaps_section import generate_digital_gaps_section

    print("[Report Gen] Generating Digital Gaps section...")
    digital_gaps = generate_digital_gaps_section(state, api_key)
    state.report_sections_ar['digital_gaps'] = {
        'heading': 'خامساً: التحليل الثالث — تحليل الفجوات الرقمية',
        'raw_data': digital_gaps,
    }

2. stage6_json_report.py — JSONReportBuilder:

    a) Import at top:
       from .generate_digital_gaps_section import _build_gap_rows, _build_root_cause_rows

    b) Paste build_digital_gaps_section as a method on JSONReportBuilder.

    c) In build_report(), after build_customer_journey_section():
        sections.append(self.build_digital_gaps_section(lang=lang))

SECTION STRUCTURE (mirrors sample output section_29 — خامساً: تحليل الفجوات الرقمية):
─────────────────────────────────────────────────────────────────────────────────────
Intro paragraph: "لماذا تستمر المشكلات رغم توفر التطبيق والموقع الإلكتروني؟"
                  Quotes digital channel % from case_channel data; names the core finding.

Sub-section 5.1 — جدول الفجوات المُدمج (ربط التواصل بالفجوة)
  Table columns: الموضوع | الحالات | وضع التطبيق / الموقع الحالي | نوع الفجوة | التوصية
  Pre-computed from state: الموضوع, الحالات, نوع الفجوة
  LLM-written: وضع التطبيق / الموقع الحالي, التوصية

Sub-section 5.2 — الأسباب الجذرية لاستمرار المشكلات
  Table columns: # | السبب الجذري | مثال على التحدي | الحل
  Pre-computed from state: #, السبب الجذري, مثال على التحدي
  LLM-written: الحل

DATA SOURCING — no new computation, only state reads
─────────────────────────────────────────────────────
• gap_table               → topics, case_counts, severity, gap_type, recommendations (Stage 5)
• journey_map             → root_cause_category, friction text for digital context % inference (Stage 4)
• notification_opportunities → concrete channel/fix text per root cause (Stage 4)
• month_year              → report date range

ERROR POLICY
────────────
No fallbacks. No placeholder returns. Every failure raises so the caller
(_generate_report_sections) sees and logs the real exception.
"""

import json
from typing import Dict, Any, List
from collections import defaultdict
import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_SEVERITY_EMOJI: Dict[str, str] = {
    "Critical": "🔴 حرجة",
    "Medium":   "🟡 عالية",
    "Adequate": "🟢 كافية",
}

# Root-cause category → short Arabic label (kept in sync with customer_journey section)
_ROOT_CAUSE_LABELS: Dict[str, str] = {
    "missing_info":               "غياب مسار رقمي مخصص",
    "inaccessible_info":          "ضعف التوعية بالقنوات الرقمية المتاحة",
    "no_proactive_notification":  "ضعف الإشعار الاستباقي",
    "platform_bug":               "غياب آلية إبلاغ تقني منظمة",
    "policy_complexity":          "تعقيد إجراءات السياسة",
}

# Sort order for severity (Critical first)
_SEVERITY_ORDER = {"Critical": 0, "Medium": 1, "Adequate": 2}

# Single authoritative definition of digital submission channels
# Used in all sections and conclusion to ensure consistency
# Supports Arabic and English variations of channel names
_DIGITAL_SUBMISSION_CHANNELS = {
    "تطبيق", "app", "application",           # App
    "موقع", "website", "web",                # Website
    "بريد", "email",                          # Email
    "NCRM", "ncrm"                            # NCRM
}


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# Also paste into stage6_json_report.py for the JSON builder.
# ──────────────────────────────────────────────────────────────────────────────

def _compute_submission_channel_pct(state: PipelineState) -> float:
    """
    % of cases submitted via digital channels (app, website, email, or NCRM).

    Returns pre-calculated value from state.digital_channel_pct if available
    (set by stage6_artifacts during executive summary). Otherwise calculates
    from state.all_classified to ensure consistency across all sections.
    """
    # Use pre-calculated value from stage6_artifacts if available
    if hasattr(state, 'digital_channel_pct') and state.digital_channel_pct is not None:
        return state.digital_channel_pct

    # Fallback: calculate if not yet set (should not happen in normal flow)
    cases = state.all_classified or []
    total = len(cases) or 1

    digital_submissions = sum(
        1 for c in cases
        if c.case_channel and any(
            kw in str(c.case_channel) for kw in _DIGITAL_SUBMISSION_CHANNELS
        )
    )
    return round(digital_submissions / total * 100, 1)


def _friction_digital_context_pct(state: PipelineState) -> float:
    """
    % of friction cases rooted in a digital/self-service context.

    CONTEXT INFERENCE (not submission channel):
    The metric is NOT the CRM submission channel (how the customer contacted us —
    usually phone) but the SERVICE CONTEXT (whether the underlying problem occurred
    while using a digital channel — app, website, online renewal).

    Example: Customer renewed their license online, got an error in the app, then
    called us. We log the contact as "phone" (submission channel) but the underlying
    problem is "digital context" (occurred in the app).

    Inferred from journey_map: friction entries whose root_cause_category is
    platform_bug, or whose cluster/friction text contains digital service keywords.
    """
    if not state.journey_map:
        return 0.0

    _DIGITAL_ROOT_CAUSES = {"platform_bug", "no_proactive_notification"}
    _DIGITAL_KEYWORDS = {
        "تطبيق", "موقع", "إلكتروني", "moi", "online", "app",
        "تجديد", "دفع", "رقمي", "بوابة", "نظام", "رفع",
    }

    total_friction_cases = sum(f.case_count for f in state.journey_map)
    if not total_friction_cases:
        return 0.0

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

    return round(digital_cases / total_friction_cases * 100, 1)


def _build_gap_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Pre-computed rows for Section 5.1 table.

    FILTER: Excludes gaps with zero case_count — nothing to display or analyze.

    Sort: Critical first, then by case_count descending.
    Columns locked here — LLM adds وضع التطبيق / الموقع الحالي and التوصية.

    Schema: الموضوع | الحالات | الشدّة | نوع الفجوة
    """
    sorted_gaps = sorted(
        state.gap_table,
        key=lambda g: (_SEVERITY_ORDER.get(g.severity, 9), -(g.case_count or 0))
    )
    return [
        {
            "الموضوع":    gap.topic_ar or gap.topic,
            "الحالات":    str(gap.case_count),
            "الشدّة":      _SEVERITY_EMOJI.get(gap.severity, gap.severity),
            "نوع الفجوة": gap.gap_type_ar or gap.gap_type or "—",
        }
        for gap in sorted_gaps
        if gap.case_count  # Filter: skip gaps with zero cases
    ]


def _build_root_cause_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Pre-computed rows for Section 5.2 root-cause table.

    Case counts are derived from state.all_classified (ground truth), not from
    summing journey_map, to prevent double-counting when multiple friction
    points share the same root_cause_category.

    Each case is counted exactly once per root_cause_category.
    Columns locked here — LLM adds الحل.

    Schema: # | السبب الجذري | مثال على التحدي
    """
    # Step 1: Build mappings from journey_map
    # - rc_to_subs: root_cause_category → set of sub_classifications (for dedup)
    # - sub_to_rc: sub_classification → root_cause_category (for case lookup)
    # - rc_best_friction: root_cause_category → (count, text) for example cell
    rc_to_subs: Dict[str, set] = defaultdict(set)
    sub_to_rc: Dict[str, str] = {}  # Issue 2 fix: direct sub→cat mapping
    rc_best_friction: Dict[str, tuple] = {}  # cat → (count, text)

    for f in state.journey_map:
        cat = f.root_cause_category
        if f.sub_classification:
            rc_to_subs[cat].add(f.sub_classification)
            # Issue 2 fix: map sub_classification to root_cause_category for all_classified lookup
            sub_to_rc[f.sub_classification] = cat
        text = f.friction_point_ar or f.friction_point
        current_best = rc_best_friction.get(cat, (0, ""))[0]
        if f.case_count >= current_best:
            rc_best_friction[cat] = (f.case_count, text)

    # Step 2: Count actual cases per root_cause_category — each case counted once
    # Dedup by case_number so each case is counted at most once per category,
    # even if multiple sub_classifications map to the same root_cause_category
    seen_per_cat: Dict[str, set] = defaultdict(set)
    rc_actual_totals: Dict[str, int] = defaultdict(int)

    for case in (state.all_classified or []):
        sub = case.sub_classification
        cat = sub_to_rc.get(sub)
        if cat is None:
            for c, subs in rc_to_subs.items():
                if sub in subs:
                    cat = c
                    break
        if cat and case.case_number not in seen_per_cat[cat]:
            seen_per_cat[cat].add(case.case_number)
            rc_actual_totals[cat] += 1

    # DIAGNOSTIC: Log mappings for debugging Issue 2
    print(f"[RootCauseRows] sub_to_rc mapping: {sub_to_rc}")
    print(f"[RootCauseRows] rc_actual_totals: {dict(rc_actual_totals)}")

    # Step 3: Sort by actual total count descending
    sorted_rc = sorted(rc_actual_totals.items(), key=lambda x: x[1], reverse=True)

    # Step 4: Build rows with locked case counts
    rows = []
    sorted_rc = sorted(
        [(cat, rc_best_friction.get(cat, (0, ""))[0]) for cat in rc_actual_totals],
        key=lambda x: x[1],
        reverse=True,
    )

    # Step 4: Build rows — count is the best single friction point for this category,
    # so it matches section 4 friction table and section 5.1 gap table exactly.
    rows = []
    for i, (cat, total_count) in enumerate(sorted_rc, 1):
        label = _ROOT_CAUSE_LABELS.get(cat, cat)
        _, example_text = rc_best_friction.get(cat, (0, ""))

        # Use the authoritative total (not best_count) in the example cell
        example_cell = (
            f"{total_count} حالة — {example_text}" if example_text else str(total_count)
        )
        rows.append({
            "#":               str(i),
            "السبب الجذري":    label,
            "مثال على التحدي": example_cell,
        })
    return rows


def _build_gap_prompt_context(state: PipelineState) -> List[Dict[str, Any]]:
    """
    Enriched gap context for the LLM prompt (Section 5.1).

    Joins gap_table with guidebook intelligence from Stage 5.
    The LLM uses guidebook_status, guidebook_excerpt, and
    recommendation_from_stage5 to write informed column values.
    FILTER: Excludes gaps with zero case_count — no data to inform recommendations.
    No new computation — pure read of Stage 5 outputs.
    """
    sorted_gaps = sorted(
        state.gap_table,
        key=lambda g: (_SEVERITY_ORDER.get(g.severity, 9), -(g.case_count or 0))
    )
    return [
        {
            "topic":                      gap.topic_ar or gap.topic,
            "case_count":                 gap.case_count,
            "severity":                   gap.severity,
            "severity_emoji":             _SEVERITY_EMOJI.get(gap.severity, gap.severity),
            "guidebook_status":           gap.guidebook_status,
            "guidebook_excerpt":          gap.guidebook_excerpt_ar or gap.guidebook_excerpt or "",
            "coverage_percentage":        gap.coverage_percentage,
            "clarity_assessment":         gap.clarity_assessment or "",
            "format_assessment":          gap.format_assessment or "",
            "has_visual_guidance":        gap.has_visual_guidance,
            "proactive_notification":     gap.proactive_notification_opportunity,
            "gap_type":                   gap.gap_type_ar or gap.gap_type,
            "recommendation_from_stage5": gap.recommendation_ar or gap.recommendation,
        }
        for gap in sorted_gaps
        if gap.case_count  # Filter: skip gaps with zero cases
    ]


def _build_root_cause_prompt_context(state: PipelineState, rc_rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Enriched root-cause context for the LLM prompt (Section 5.2).

    Joins pre-computed root-cause rows with notification_opportunities so
    the LLM can write a concrete "الحل" for each root cause.
    No new computation — pure read of Stage 4 outputs.
    """
    notif_lookup: Dict[str, Dict] = {}
    for n in (state.notification_opportunities or []):
        key = (n.get("notification_type") or n.get("content_summary") or "").strip()
        if key:
            notif_lookup[key] = n

    context = []
    for row in rc_rows:
        label = row["السبب الجذري"]
        notif_match = next(
            (nv for nk, nv in notif_lookup.items() if label[:10] in nk or nk[:10] in label),
            None
        )
        entry: Dict[str, Any] = {
            "rank":          row["#"],
            "root_cause_ar": label,
            "example":       row["مثال على التحدي"],
        }
        if notif_match:
            entry["notification_opportunity"] = {
                "channel":          notif_match.get("channel", ""),
                "content_summary":  notif_match.get("content_summary", ""),
                "cases_eliminated": notif_match.get(
                    "cases_eliminated", notif_match.get("case_count", 0)
                ),
            }
        context.append(entry)
    return context


# ──────────────────────────────────────────────────────────────────────────────
# Main section generator
# ──────────────────────────────────────────────────────────────────────────────

def generate_digital_gaps_section(
    state: PipelineState,
    api_key: str,
) -> Dict[str, Any]:
    """
    Generate Section 5 — Digital Gaps Analysis.

    Pre-computes all numeric columns from state, then asks the LLM to write
    only prose and the two context-dependent columns per table. Reinjection
    guarantees pre-computed values are never replaced by LLM output.

    Raises on any failure — no fallbacks, no None returns.

    JSON output schema
    ──────────────────
    {
      "section": "digital_gaps",
      "section_body": "لماذا تستمر المشكلات...",
      "gap_table": [
        {
          "الموضوع": "...",
          "الحالات": "...",
          "وضع التطبيق / الموقع الحالي": "...",   ← LLM-written
          "نوع الفجوة": "...",
          "التوصية": "..."                          ← LLM-written (refined from Stage 5 rec)
        }
      ],
      "root_cause_table": [
        {
          "#": "1",
          "السبب الجذري": "...",
          "مثال على التحدي": "...",
          "الحل": "..."                             ← LLM-written
        }
      ]
    }
    """
    if not state.gap_table:
        raise RuntimeError(
            "[DigitalGaps] state.gap_table is empty — "
            "Stage 5 (stage5_gap) must complete successfully before this section can be generated."
        )
    if not state.journey_map:
        raise RuntimeError(
            "[DigitalGaps] state.journey_map is empty — "
            "Stage 4 (stage4_analysis) must complete successfully before this section can be generated."
        )

    total_cases = len(state.all_classified) or state.total_cases
    if not total_cases:
        raise RuntimeError(
            "[DigitalGaps] total_cases is 0 — no classified cases in state."
        )

    if not state.month_year:
        raise RuntimeError(
            "[DigitalGaps] state.month_year is not set — Stage 3 must complete successfully."
        )

    # ── Pre-compute all values from state ─────────────────────────────────────
    date_range         = convert_month_year_to_arabic(state.month_year)
    submission_channel_pct     = _compute_submission_channel_pct(state)
    friction_digital_context_pct = _friction_digital_context_pct(state)
    gap_rows           = _build_gap_rows(state)
    root_cause_rows    = _build_root_cause_rows(state)
    # Sum of case counts across ALL root cause categories — used to clarify
    # that any total cited in section 5.2 is cumulative, not sub-type-specific.
    total_rc_cases = sum(
        int(r["مثال على التحدي"].split()[0])
        for r in root_cause_rows
        if r.get("مثال على التحدي", "").split()
        and r["مثال على التحدي"].split()[0].isdigit()
    )
    gap_context        = _build_gap_prompt_context(state)
    root_cause_context = _build_root_cause_prompt_context(state, root_cause_rows)

    # Derived scalars for the section body (excluding zero-case gaps)
    non_zero_gaps = [g for g in state.gap_table if g.case_count]
    if not non_zero_gaps:
        raise RuntimeError(
            "[DigitalGaps] No gaps with non-zero case counts — "
            "cannot determine top gap for narrative."
        )
    sorted_gap_indices = sorted(
        range(len(non_zero_gaps)),
        key=lambda i: (
            _SEVERITY_ORDER.get(non_zero_gaps[i].severity, 9),
            -(non_zero_gaps[i].case_count or 0)
        )
    )
    top_gap       = non_zero_gaps[sorted_gap_indices[0]]
    top_gap_name  = top_gap.topic_ar or top_gap.topic
    top_gap_count = top_gap.case_count

    critical_count = sum(1 for g in state.gap_table if g.severity == "Critical" and g.case_count)
    medium_count   = sum(1 for g in state.gap_table if g.severity == "Medium" and g.case_count)

    proactive_gaps       = [g for g in state.gap_table if g.proactive_notification_opportunity]
    proactive_case_count = state.proactive_notification_case_count or sum(g.case_count for g in proactive_gaps)
    proactive_pct        = round(proactive_case_count / total_cases * 100, 1) if total_cases else 0.0

    # ── Prompt ────────────────────────────────────────────────────────────────
    proactive_instruction = (
        f'   - Add: يمكن تحويل {proactive_case_count} حالة '
        f'({proactive_pct}% من الإجمالي) عبر إشعار SMS/بريد إلكتروني استباقي دون أي تغيير في البنية التحتية.\n'
        f'   CRITICAL NUMBER CONSTRAINT: If you mention proactive notification cases in section_body,\n'
        f'   use EXACTLY {proactive_case_count} حالة ({proactive_pct}%). Do NOT use any other number.\n'
        if proactive_case_count > 0 else ''
    )

    prompt = (
        'You are writing Section 5 of a formal Arabic government report on customer inquiry\n'
        'analysis for Fujairah Police. The section title is:\n'
        '"خامساً: التحليل الثالث — تحليل الفجوات الرقمية"\n'
        '\n'
        'INPUTS — use ONLY these numbers, never invent figures\n'
        f'total_cases:                        {total_cases}\n'
        f'date_range:                         "{date_range}"\n'
        f'submission_channel_digital_pct:     {submission_channel_pct}%  (% of cases submitted via app/website)\n'
        + (f'friction_digital_context_pct:      {friction_digital_context_pct}%  (% of friction cases rooted in digital service context)\n' if friction_digital_context_pct > 0 else
           'friction_digital_context_pct:      [not available — use gap count to anchor the finding instead]\n')
        + f'critical_gap_count:                {critical_count}\n'
        f'medium_gap_count:                  {medium_count}\n'
        f'top_gap_topic:                     "{top_gap_name}"\n'
        f'top_gap_case_count:                {top_gap_count}\n'
        f'proactive_case_count:              {proactive_case_count}\n'
        f'proactive_pct:                     {proactive_pct}%\n'
        '\n'
        'gap_context (Stage 5 gap_table enriched with guidebook intelligence):\n'
        '  - "recommendation_from_stage5" → primary source for التوصية column\n'
        '  - "guidebook_excerpt" + "guidebook_status" → inform وضع التطبيق / الموقع الحالي\n'
        '  - "proactive_notification": true → lead التوصية with "تفعيل إشعار SMS/بريد تلقائي..."\n'
        f'{json.dumps(gap_context, ensure_ascii=False, indent=2)}\n'
        '\n'
        'root_cause_context (aggregated from Stage 4 journey_map + Stage 4 notification_opportunities):\n'
        '  - "notification_opportunity" → use to write a concrete "الحل" for each root cause\n'
        f'{json.dumps(root_cause_context, ensure_ascii=False, indent=2)}\n'
        '\n'
        'pre_computed_gap_table — Section 5.1\n'
        '(الموضوع, الحالات, الشدّة, نوع الفجوة are LOCKED — copy verbatim; only ADD the two new columns):\n'
        f'{json.dumps(gap_rows, ensure_ascii=False, indent=2)}\n'
        '\n'
        'pre_computed_root_cause_table — Section 5.2\n'
        '(#, السبب الجذري, مثال على التحدي are LOCKED — copy verbatim; only ADD الحل):\n'
        f'{json.dumps(root_cause_rows, ensure_ascii=False, indent=2)}\n'
        '\n'
        '─────────────────────────────────────────────\n'
        'YOUR TASK — write ONLY the items listed below\n'
        '─────────────────────────────────────────────\n'
        '\n'
        'A. section_body — 2 sentences, formal Arabic\n'
        '   - Open with: "لماذا تستمر المشكلات رغم توفر التطبيق والموقع الإلكتروني؟"\n'
        f'   - State the core finding: {submission_channel_pct}% of cases came through digital submission channels (التطبيق / الموقع الإلكتروني/ بريد الكتروني/NCRM),\n'
        '     yet problems persist. The problem is not the absence of digital channels —\n'
        '     it is the absence of the right functions inside those channels.\n'
        f'   - Mention {critical_count} critical gaps and {medium_count} high-severity gaps,\n'
        + f'     citing «{top_gap_name}» as the largest ({top_gap_count} cases). Use « » (angle brackets), never double quotes, around topic names.\n'
        + proactive_instruction
        + f'   - When referencing the total of {total_rc_cases} cases in the root causes table:\n'
        + f'     Clarify explicitly that this is the cumulative total across ALL root cause\n'
        + f'     sub-types in the table (خطأ تقني + ضعف الإشعار الاستباقي + تعقيد السياسات + غيرها).\n'
        + f'     Do NOT imply it refers only to the specific platform failures mentioned in section 5.1.\n'
        + '\n'
        'B. "وضع التطبيق / الموقع الحالي" for EVERY row in pre_computed_gap_table\n'
        '   - Use guidebook_excerpt + guidebook_status from gap_context.\n'
        '   - Describe what currently exists in the app/website AND what is missing.\n'
        '   - 1–2 Arabic sentences, max 40 words per row.\n'
        '   - Name the existing feature; state the missing action/workflow explicitly.\n'
        '\n'
        'C. "التوصية" for EVERY row in pre_computed_gap_table\n'
        '   - Use recommendation_from_stage5 from gap_context as primary source.\n'
        '   - Rephrase into a concise Arabic imperative, max 25 words.\n'
        '   - If proactive_notification=true, lead with "تفعيل إشعار SMS/بريد تلقائي..."\n'
        '\n'
        'D. "الحل" for EVERY row in pre_computed_root_cause_table\n'
        '   - Use notification_opportunity from root_cause_context where present.\n'
        '   - Concrete and actionable Arabic, max 20 words.\n'
        '\n'
        '─────────────────────────────────────────────\n'
        'OUTPUT — single JSON object, no markdown fences, no extra keys\n'
        '─────────────────────────────────────────────\n'
        '\n'
        '{\n'
        '  "section": "digital_gaps",\n'
        '  "section_body": "...",\n'
        '  "gap_table": [\n'
        '    {\n'
        '      "الموضوع": "...",\n'
        '      "الحالات": "...",\n'
        '      "الشدّة": "🔴 حرجة",\n'
        '      "وضع التطبيق / الموقع الحالي": "...",\n'
        '      "نوع الفجوة": "...",\n'
        '      "التوصية": "..."\n'
        '    }\n'
        '  ],\n'
        '  "root_cause_table": [\n'
        '    {\n'
        '      "#": "1",\n'
        '      "السبب الجذري": "...",\n'
        '      "مثال على التحدي": "...",\n'
        '      "الحل": "..."\n'
        '    }\n'
        '  ]\n'
        '}\n'
        '\n'
        'RULES:\n'
        '- gap_table must have exactly the same number of rows as pre_computed_gap_table.\n'
        '- root_cause_table must have exactly the same number of rows as pre_computed_root_cause_table.\n'
        '- الموضوع, الحالات, الشدّة, نوع الفجوة: copy verbatim from pre_computed_gap_table.\n'
        '- #, السبب الجذري, مثال على التحدي: copy verbatim from pre_computed_root_cause_table.\n'
        '- Every number in section_body must match a pre-computed input above.\n'
        '- Arabic only. Proper nouns only in Latin script: MOI, SMS, UAE PASS.\n'
        '- No markdown, no extra keys, no extra nesting.\n'
        '- CRITICAL: Do NOT use double-quote characters (\") inside any string value. '
        'To cite a topic name in section_body, use angle brackets « » instead of double quotes.\n'
        '- CRITICAL DISAMBIGUATION — Traffic Fine Wrong Vehicle gap: if any gap row is about\n'
        '  citizens disputing fines due to vehicle photo mismatch, the gap is NOT about\n'
        '  missing photo notification. The recommendation must address fixing the radar\n'
        '  plate-matching system, NOT adding a photo to the notification.\n'
    )

    # ── API call ──────────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    print(
        f"[DigitalGaps] Calling API — total_cases={total_cases}, "
        f"gap_count={len(state.gap_table)}, "
        f"root_cause_count={len(root_cause_rows)}, "
        f"critical={critical_count}, submission_channel={submission_channel_pct}%, "
        f"friction_digital_context={friction_digital_context_pct}%"
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = parse_json_response(message.content[0].text, tag="DigitalGaps")
    if result is None:
        # Show more of the response for debugging
        response_text = message.content[0].text
        response_len = len(response_text)
        show_chars = min(1500, response_len)
        raise RuntimeError(
            "[DigitalGaps] parse_json_response returned None — could not extract JSON from API response.\n"
            f"Response length: {response_len} chars\n"
            f"Raw response (first {show_chars} chars):\n{response_text[:show_chars]}"
        )

    # Task 11: Post-generation validation — warn if section_body contains numbers exceeding total_cases
    section_body_check = result.get("section_body", "")
    import re as _re
    numbers_in_body = [int(n) for n in _re.findall(r'\b(\d+)\b', section_body_check) if int(n) > 1]
    for n in numbers_in_body:
        if n > total_cases:
            print(
                f"[DigitalGaps] WARNING: section_body contains number {n} which exceeds "
                f"total_cases={total_cases}. This may indicate LLM hallucinated a count."
            )

    # ── Reinject pre-computed values — LLM output must never override state data ──

    # Table 5.1
    llm_gap_rows = result.get("gap_table")
    if not isinstance(llm_gap_rows, list):
        raise RuntimeError(
            f"[DigitalGaps] 'gap_table' missing or not a list in LLM response. "
            f"Got type: {type(llm_gap_rows)}"
        )
    if len(llm_gap_rows) != len(gap_rows):
        raise RuntimeError(
            f"[DigitalGaps] gap_table row count mismatch: "
            f"expected {len(gap_rows)}, LLM returned {len(llm_gap_rows)}."
        )

    merged_gap_table = []
    for i, (pre_row, llm_row) in enumerate(zip(gap_rows, llm_gap_rows)):
        app_status = llm_row.get("وضع التطبيق / الموقع الحالي", "")
        توصية      = llm_row.get("التوصية", "")

        if not app_status:
            raise RuntimeError(
                f"[DigitalGaps] Missing 'وضع التطبيق / الموقع الحالي' in gap_table row {i} "
                f"(topic: '{pre_row['الموضوع']}')"
            )
        if not توصية:
            raise RuntimeError(
                f"[DigitalGaps] Missing 'التوصية' in gap_table row {i} "
                f"(topic: '{pre_row['الموضوع']}')"
            )

        # Column order matches sample output: الموضوع | الحالات | الشدّة | وضع التطبيق | نوع الفجوة | التوصية
        merged_gap_table.append({
            "الموضوع":                     pre_row["الموضوع"],
            "الحالات":                     pre_row["الحالات"],
            "الشدّة":                      pre_row["الشدّة"],
            "وضع التطبيق / الموقع الحالي": app_status,
            "نوع الفجوة":                  pre_row["نوع الفجوة"],
            "التوصية":                      توصية,
        })

    result["gap_table"] = merged_gap_table

    # Table 5.2
    llm_rc_rows = result.get("root_cause_table")
    if not isinstance(llm_rc_rows, list):
        raise RuntimeError(
            f"[DigitalGaps] 'root_cause_table' missing or not a list in LLM response. "
            f"Got type: {type(llm_rc_rows)}"
        )
    if len(llm_rc_rows) != len(root_cause_rows):
        raise RuntimeError(
            f"[DigitalGaps] root_cause_table row count mismatch: "
            f"expected {len(root_cause_rows)}, LLM returned {len(llm_rc_rows)}."
        )

    merged_rc_table = []
    for i, (pre_row, llm_row) in enumerate(zip(root_cause_rows, llm_rc_rows)):
        حل = llm_row.get("الحل", "")
        if not حل:
            raise RuntimeError(
                f"[DigitalGaps] Missing 'الحل' in root_cause_table row {i} "
                f"(root cause: '{pre_row['السبب الجذري']}')"
            )
        merged_rc_table.append({
            "#":               pre_row["#"],
            "السبب الجذري":    pre_row["السبب الجذري"],
            "مثال على التحدي": pre_row["مثال على التحدي"],
            "الحل":            حل,
        })

    result["root_cause_table"] = merged_rc_table

    print(
        f"[DigitalGaps] ✅ Done — "
        f"gap_table={len(merged_gap_table)} rows, "
        f"root_cause_table={len(merged_rc_table)} rows"
    )
    return result
