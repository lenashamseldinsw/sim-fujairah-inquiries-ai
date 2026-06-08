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
Intro paragraph: "لماذا تستمر المشاكل رغم توفر قنوات استقبال الشكاوى الرقمية؟"
                  Quotes digital channel % from case_channel data; names the core finding.

Sub-section 5.1 — جدول الفجوات المُدمج (ربط التواصل بالفجوة)
  Table columns: الخدمة | الشكاوى | القناة الرسمية في دليل الخدمات | نوع الفجوة | التوصية
  Pre-computed from state: الخدمة, الشكاوى, القناة الرسمية في دليل الخدمات (from guidebook_status), نوع الفجوة
  LLM-written: التوصية

Sub-section 5.2 — الأسباب الجذرية لاستمرار المشاكل
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

# Root-cause category → short Arabic label (complaints-specific, kept in sync with customer_journey section)
_ROOT_CAUSE_LABELS: Dict[str, str] = {
    "missing_info":               "عدم توافر آلية تتبع الشكوى",
    "inaccessible_info":          "عدم كفاية الإشعارات الاستباقية",
    "no_proactive_notification":  "طول مدة معالجة الشكوى",
    "platform_bug":               "غياب آلية إبلاغ موحدة للمشاكل التقنية",
    "policy_complexity":          "تعقيد إجراءات المعالجة",
    "wrong_channel_used":         "استخدام قناة اتصال خاطئة",
    "service_delivery_failure":   "عدم تقديم الخدمة بشكل صحيح",
    "processing_delay":           "تأخر في معالجة البلاغ",
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


def _compute_gap_type_from_friction(
    gap_topic: str,
    state: PipelineState,
    guidebook_status: str = "",
    clarity: str = "",
) -> tuple[str, str]:
    """
    Compute gap_type and gap_type_ar dynamically from actual friction data.

    Returns (gap_type, gap_type_ar) tuple with values determined by:
    1. Root cause patterns in friction points for this topic
    2. Guidebook coverage status
    3. Actual complaint distribution

    Values from complaints flow Section 5.1:
    - "فجوة وعي واستخدام" — awareness/usage issue
      (users don't know about the service or how to use it)
    - "فجوة حقيقية" — real/genuine gap
      (missing feature, broken functionality, unavailable service)
    - "غير محدد" — undefined/unclassified
      (insufficient data to classify)
    """
    if not state.journey_map:
        return ("undefined", "غير محدد")

    # Find friction points for this gap topic (normalized comparison)
    gap_topic_lower = (gap_topic or "").lower().strip()
    matching_frictions = []

    for f in state.journey_map:
        # Check against all text fields of friction point
        friction_texts = [
            (f.friction_point_ar or "").lower(),
            (f.friction_point or "").lower(),
            (f.cluster_ar or "").lower(),
            (f.cluster or "").lower(),
        ]

        for text in friction_texts:
            if gap_topic_lower in text or text in gap_topic_lower:
                matching_frictions.append(f)
                break

    if not matching_frictions:
        # No friction matches — this is likely a "حقيقية" (real gap) with no visibility yet
        if guidebook_status == "Missing":
            return ("real_gap", "فجوة حقيقية")
        return ("undefined", "غير محدد")

    # Analyze root cause patterns from matching frictions
    root_cause_counts = defaultdict(int)
    total_cases = 0
    for friction in matching_frictions:
        cat = friction.root_cause_category or "unknown"
        root_cause_counts[cat] += friction.case_count
        total_cases += friction.case_count

    # Decision tree: classify gap type based on root causes
    # Priority 1: Missing content or platform bugs → "فجوة حقيقية"
    if guidebook_status == "Missing":
        return ("real_gap", "فجوة حقيقية")

    if "platform_bug" in root_cause_counts:
        return ("real_gap", "فجوة حقيقية")

    # Priority 2: Proactive notification opportunity → "فجوة وعي واستخدام"
    # (problem: users don't know about the service or how to use it)
    if "no_proactive_notification" in root_cause_counts:
        notif_pct = root_cause_counts["no_proactive_notification"] / total_cases * 100 if total_cases > 0 else 0
        if notif_pct > 30:  # Significant notification gap
            return ("awareness_usage_gap", "فجوة وعي واستخدام")

    # Priority 3: Clarity/readability issue → could be awareness gap or usability gap
    if clarity in ("bureaucratic", "unclear"):
        return ("awareness_usage_gap", "فجوة وعي واستخدام")

    # Fallback: undefined
    return ("undefined", "غير محدد")


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# Also paste into stage6_json_report.py for the JSON builder.
# ──────────────────────────────────────────────────────────────────────────────

def _build_guidebook_channel_status(gap) -> str:
    """
    Build a concise description of what's documented in the service guidebook
    for this service/topic.

    Uses guidebook_status (Covered | Partially Covered | Missing) and
    guidebook_excerpt to create a one-line summary of the official channel status.
    """
    status = gap.guidebook_status or "Unknown"
    excerpt = gap.guidebook_excerpt_ar or gap.guidebook_excerpt or ""

    if status == "Covered":
        if excerpt:
            return f"موثّق — {excerpt[:60]}"
        return "موثّق في دليل الخدمات"
    elif status == "Partially Covered":
        if excerpt:
            return f"موثّق جزئياً — {excerpt[:50]}"
        return "موثّق جزئياً في دليل الخدمات"
    else:  # Missing
        if excerpt:
            return f"غير موثّق — {excerpt[:60]}"
        return "غير موثّق في دليل الخدمات"


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
    while using a digital channel — app, website, online submission).

    Example: Customer filed a complaint through the app, encountered an error,
    then called us. We log the contact as "phone" (submission channel) but the
    underlying problem is "digital context" (occurred in the app).

    Inferred from journey_map: friction entries whose root_cause_category is
    platform_bug, or whose cluster/friction text contains digital service keywords.
    """
    if not state.journey_map:
        return 0.0

    _DIGITAL_ROOT_CAUSES = {"platform_bug", "no_proactive_notification"}
    _DIGITAL_KEYWORDS = {
        "تطبيق", "موقع", "إلكتروني", "moi", "online", "app",
        "شكوى", "إبلاغ", "رقمي", "بوابة", "نظام", "رفع",
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

    FIX 2: Derives 'الشكاوى' case count from journey_map (Section 4 source),
    not from gap_table (Stage 5 reconciliation). This ensures Section 5.1
    and Section 4 cite the same case counts for the same friction points.

    FILTER: Excludes gaps with zero case_count (nothing to display or analyze).

    Sort: Critical first, then by case_count descending.
    Columns locked here — LLM only adds التوصية.
    القناة الرسمية في دليل الخدمات is pre-computed from guidebook_status + excerpt.

    KEY FIX: نوع الفجوة is computed dynamically from friction data, not from LLM.
    This ensures accurate classification based on actual complaint patterns, not hallucination.

    Schema: الخدمة | الشكاوى | القناة الرسمية في دليل الخدمات | نوع الفجوة
    """
    def _journey_map_case_count(gap_topic: str) -> int:
        """
        Sum case_count across journey_map entries whose text matches this gap topic.
        Uses the same substring matching as _compute_gap_type_from_friction so the
        two columns are derived from the same friction-point scope.
        Falls back to gap.case_count if no journey_map match is found.
        """
        topic_lower = (gap_topic or "").lower().strip()
        if not topic_lower:
            return None

        matched = []
        for f in state.journey_map:
            for text in [
                (f.friction_point_ar or "").lower(),
                (f.friction_point or "").lower(),
                (f.cluster_ar or "").lower(),
                (f.cluster or "").lower(),
            ]:
                if topic_lower and (topic_lower in text or text in topic_lower):
                    matched.append(f)
                    break  # Found match in this friction entry, no need to check other text fields

        if matched:
            # Deduplicate by friction object identity before summing
            seen_ids = set()
            total = 0
            for f in matched:
                fid = id(f)
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    total += f.case_count
            return total
        return None  # Signal: no match found, caller uses gap.case_count as fallback

    sorted_gaps = sorted(
        state.gap_table,
        key=lambda g: (_SEVERITY_ORDER.get(g.severity, 9), -(g.case_count or 0))
    )

    rows = []
    for gap in sorted_gaps:
        topic = gap.topic_ar or gap.topic
        journey_count = _journey_map_case_count(topic)
        display_count = journey_count if journey_count is not None else gap.case_count

        # Filter: skip gaps with zero cases — nothing to display or analyze
        if not display_count or display_count == 0:
            continue

        rows.append({
            "الخدمة":                            topic,
            "الشكاوى":                          str(display_count),
            "القناة الرسمية في دليل الخدمات": _build_guidebook_channel_status(gap),
            "نوع الفجوة":                       _compute_gap_type_from_friction(
                topic,
                state,
                guidebook_status=gap.guidebook_status or "",
                clarity=gap.clarity_assessment or "",
            )[1],  # [1] = gap_type_ar (Arabic label)
        })

    return rows


def _build_root_cause_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Pre-computed rows for Section 5.2 table.

    De-duplicates journey_map by root_cause_category (summing case counts).
    Picks the highest-count friction point as the example text.
    Sort: descending by total case count.
    Columns locked here — LLM adds الحل.

    Schema: # | السبب الجذري | مثال على التحدي
    """
    rc_totals: Dict[str, int] = defaultdict(int)
    rc_best_friction: Dict[str, tuple] = {}  # cat → (count, text)

    for f in state.journey_map:
        cat = f.root_cause_category
        rc_totals[cat] += f.case_count
        text = f.friction_point_ar or f.friction_point
        current_best_count = rc_best_friction.get(cat, (0, ""))[0]
        if f.case_count >= current_best_count:
            rc_best_friction[cat] = (f.case_count, text)

    sorted_rc = sorted(rc_totals.items(), key=lambda x: x[1], reverse=True)

    rows = []
    for i, (cat, total_count) in enumerate(sorted_rc, 1):
        label = _ROOT_CAUSE_LABELS.get(cat, cat)
        best_count, example_text = rc_best_friction.get(cat, (0, ""))
        example_cell = f"{best_count} حالة — {example_text}" if example_text else str(total_count)
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


def _fix_section_body_counts(
    section_body: str,
    critical_count: int,
    medium_count: int,
    proactive_case_count: int,
    proactive_pct: float,
) -> str:
    """
    Replace LLM-generated gap severity counts in section_body with
    pre-computed locked values.

    The LLM receives critical_count and medium_count as INPUTS but may still
    write different numbers in section_body. This function overwrites any
    Arabic numeral pattern matching "N فجوات حرجة" or "N فجوات عالية" with
    the authoritative values, preserving surrounding prose unchanged.

    Also enforces proactive_case_count and proactive_pct for the same reason.
    """
    import re

    # Pattern: any Arabic/Latin digits immediately before these Arabic phrases
    # Covers: "5 فجوات حرجة", "٥ فجوات حرجة", etc.
    section_body = re.sub(
        r'\d+(?:\.\d+)?(?= فجوات? حرج)',
        str(critical_count),
        section_body,
    )
    section_body = re.sub(
        r'\d+(?:\.\d+)?(?= فجوات? عالية)',
        str(medium_count),
        section_body,
    )
    # Enforce proactive case count and percentage together when they appear
    # Pattern: "N حالة (X% من الإجمالي)" — fix both the count and the pct
    if proactive_case_count > 0:
        section_body = re.sub(
            r'\d+(?= حالة \(\d+(?:\.\d+)?% من الإجمالي\))',
            str(proactive_case_count),
            section_body,
        )
        section_body = re.sub(
            r'(?<=حالة \()\d+(?:\.\d+)?(?=% من الإجمالي\))',
            f"{proactive_pct:.1f}",
            section_body,
        )

    return section_body


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
      "section_body": "لماذا تستمر المشاكل...",
      "gap_table": [
        {
          "الخدمة": "...",                          ← Pre-computed
          "الشكاوى": "...",                        ← Pre-computed
          "القناة الرسمية في دليل الخدمات": "...",  ← Pre-computed (from guidebook_status)
          "نوع الفجوة": "...",                     ← Pre-computed (from friction analysis — DO NOT MODIFY)
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

    # Sum actual cases from all notification opportunities (post-reconciliation)
    proactive_case_count = sum(
        n.get("cases_eliminated", n.get("case_count", 0))
        for n in (state.notification_opportunities or [])
    )
    proactive_pct        = round(proactive_case_count / total_cases * 100, 1) if total_cases > 0 else 0

    # ── Prompt ────────────────────────────────────────────────────────────────
    proactive_instruction = (
        f'   - Add: يمكن تحويل {proactive_case_count} حالة '
        f'({proactive_pct}% من الإجمالي) عبر إشعار SMS/بريد إلكتروني استباقي دون أي تغيير في البنية التحتية.\n'
        f'   CRITICAL NUMBER CONSTRAINT: If you mention proactive notification cases in section_body,\n'
        f'   use EXACTLY {proactive_case_count} حالة ({proactive_pct}%). Do NOT use any other number.\n'
        if proactive_case_count > 0 else ''
    )

    prompt = (
        'You are writing Section 5 of a formal Arabic government report on complaint\n'
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
        '  - "guidebook_excerpt" + "guidebook_status" → inform وضع استقبال الشكاوى والمعالجة\n'
        '  - "proactive_notification": true → lead التوصية with "تفعيل إشعار SMS/بريد تلقائي..."\n'
        f'{json.dumps(gap_context, ensure_ascii=False, indent=2)}\n'
        '\n'
        'root_cause_context (aggregated from Stage 4 journey_map + Stage 4 notification_opportunities):\n'
        '  - "notification_opportunity" → use to write a concrete "الحل" for each root cause\n'
        f'{json.dumps(root_cause_context, ensure_ascii=False, indent=2)}\n'
        '\n'
        'pre_computed_gap_table — Section 5.1\n'
        '(الخدمة, الشكاوى, القناة الرسمية في دليل الخدمات, نوع الفجوة are LOCKED — copy verbatim; only ADD التوصية):\n'
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
        '   - Open with: "لماذا تستمر المشاكل رغم توفر قنوات استقبال الشكاوى الرقمية؟"\n'
        f'   - State the core finding: {submission_channel_pct}% of cases came through digital submission channels (تطبيق/موقع),\n'
        '     yet problems persist. The problem is not the absence of digital channels —\n'
        '     it is the absence of the right functions inside those channels.\n'
        + (
            f'     OPTIONAL: Additionally, {friction_digital_context_pct}% of friction cases are ROOTED IN A DIGITAL SERVICE CONTEXT\n'
            '     (app error, online submission, digital processing) — cite this if it strengthens the finding.\n'
            f'     Frame as: "{friction_digital_context_pct}% من الحالات نشأت في سياق رقمي (التطبيق / الموقع)"\n'
            if friction_digital_context_pct > 0 else
            '     Focus on submission channel percentage — friction_digital_context is not available.\n'
            '     Use gap count to anchor the claim: "المشكلة ليست في غياب القنوات الرقمية بل في غياب الوظائف\n'
            '     الصحيحة داخلها" with {critical_count} critical gaps identified.\n'
        )
        + f'   - Mention {critical_count} critical gaps and {medium_count} high-severity gaps,\n'
        + f'     citing «{top_gap_name}» as the largest ({top_gap_count} cases). Use « » (angle brackets), never double quotes, around topic names.\n'
        + proactive_instruction +
        '\n'
        'B. "التوصية" for EVERY row in pre_computed_gap_table\n'
        '   - Use recommendation_from_stage5 from gap_context as primary source.\n'
        '   - Rephrase into a concise Arabic imperative, max 25 words.\n'
        '   - If proactive_notification=true, lead with "تفعيل إشعار SMS/بريد تلقائي..."\n'
        '\n'
        'C. "الحل" for EVERY row in pre_computed_root_cause_table\n'
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
        '      "الخدمة": "...",\n'
        '      "الشكاوى": "...",\n'
        '      "القناة الرسمية في دليل الخدمات": "...",\n'
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
        '- الخدمة, الشكاوى, القناة الرسمية في دليل الخدمات, نوع الفجوة: copy verbatim from pre_computed_gap_table.\n'
        '  ** CRITICAL: نوع الفجوة (gap type) is derived from friction analysis in the pipeline — DO NOT INVENT OR MODIFY.\n'
        '     Always copy the value from pre_computed_gap_table exactly as-is. Common values are:\n'
        '     - "فجوة حقيقية" (real/genuine gap — missing feature or broken functionality)\n'
        '     - "فجوة وعي واستخدام" (awareness/usage gap — users don\'t know about the service)\n'
        '     - "غير محدد" (undefined/unclassified gap)\n'
        '- #, السبب الجذري, مثال على التحدي: copy verbatim from pre_computed_root_cause_table.\n'
        '- Every number in section_body must match a pre-computed input above.\n'
        '- Arabic only. Proper nouns only in Latin script: MOI, SMS, UAE PASS.\n'
        '- No markdown, no extra keys, no extra nesting.\n'
        '- CRITICAL: Do NOT use double-quote characters (\") inside any string value. '
        'To cite a topic name in section_body, use angle brackets « » instead of double quotes.\n'
        '- CRITICAL DISAMBIGUATION — Complaint Processing: if any gap row involves\n'
        '  issues with complaint submission, tracking, or notification processes, focus\n'
        '  the recommendation on improving the complaint handling workflow and proactive\n'
        '  communication channels, NOT on changing the underlying complaint criteria.\n'
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

    # ── Enforce locked counts in section_body ────────────────────────────────
    # The LLM receives critical_count/medium_count as inputs but may still write
    # different values. Overwrite with pre-computed values before any downstream use.
    raw_section_body = result.get("section_body", "")
    fixed_section_body = _fix_section_body_counts(
        raw_section_body,
        critical_count=critical_count,
        medium_count=medium_count,
        proactive_case_count=proactive_case_count,
        proactive_pct=proactive_pct,
    )
    if fixed_section_body != raw_section_body:
        print(
            f"[DigitalGaps] section_body counts corrected: "
            f"critical={critical_count}, medium={medium_count}, "
            f"proactive={proactive_case_count} ({proactive_pct}%)"
        )
    result["section_body"] = fixed_section_body

    # Post-generation validation — warn if section_body still contains numbers exceeding total_cases
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
        توصية = llm_row.get("التوصية", "")

        if not توصية:
            raise RuntimeError(
                f"[DigitalGaps] Missing 'التوصية' in gap_table row {i} "
                f"(topic: '{pre_row['الخدمة']}')"
            )

        # Column order matches sample output: الخدمة | الشكاوى | القناة الرسمية في دليل الخدمات | نوع الفجوة | التوصية
        merged_gap_table.append({
            "الخدمة":                            pre_row["الخدمة"],
            "الشكاوى":                          pre_row["الشكاوى"],
            "القناة الرسمية في دليل الخدمات": pre_row["القناة الرسمية في دليل الخدمات"],
            "نوع الفجوة":                       pre_row["نوع الفجوة"],
            "التوصية":                          توصية,
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
