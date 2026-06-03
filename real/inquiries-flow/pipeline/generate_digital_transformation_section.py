"""
generate_digital_transformation_section — stage6_artifacts.py companion

Generates Section 6: "سادساً: التحليل الرابع — خطة التحويل الرقمي"

INTEGRATION
───────────
1. stage6_artifacts.py — _generate_report_sections(), after digital_gaps block:

    from .generate_digital_transformation_section import generate_digital_transformation_section

    print("[Report Gen] Generating Digital Transformation section...")
    digital_transform = generate_digital_transformation_section(state, api_key)
    state.report_sections_ar['digital_transformation'] = {
        'heading': 'سادساً: التحليل الرابع — خطة التحويل الرقمي',
        'raw_data': digital_transform,
    }

2. stage6_json_report.py — JSONReportBuilder:

    a) Import at top:
       from .generate_digital_transformation_section import (
           _build_faq_rows_for_transform,
           _build_notification_rows,
       )

    b) Paste build_digital_transformation_section as a method on JSONReportBuilder.

    c) In build_report(), after build_digital_gaps_section():
        sections.append(self.build_digital_transformation_section(lang=lang))

SECTION STRUCTURE (mirrors sample output section 5 — سادساً: خطة التحويل الرقمي):
──────────────────────────────────────────────────────────────────────────────────────
Intro paragraph: states what the section delivers and why (from computed data).

Sub-section 6.1 — الأسئلة الشائعة ذات الأولوية
  Table columns: # | السؤال | الإجابة المقترحة | التكرار
  Pre-computed from state: #, التكرار (from validated_faqs frequency, sorted desc)
  LLM-written: السؤال, الإجابة المقترحة (sharpened/contextualised from FAQ candidates)

Sub-section 6.2 — مسار إلغاء N حالة بالإشعار الاستباقي
  Table columns: نوع الإشعار | الحالات المُلغاة | محتوى الإشعار (مثال) | القناة | الأثر المتوقع
  Pre-computed from state: نوع الإشعار, الحالات المُلغاة, القناة (from notification_opportunities)
  LLM-written: محتوى الإشعار (مثال), الأثر المتوقع

DATA SOURCING — no new computation, only state reads
─────────────────────────────────────────────────────
• validated_faqs           → questions, answers, frequency — for 6.1 FAQ table (Stage 5)
• faq_candidates           → fallback if validated_faqs empty (Stage 4)
• notification_opportunities → notification type, channel, cases_eliminated — for 6.2 (Stage 4)
• journey_map              → friction_point, case_count — to derive notification rows if
                             notification_opportunities is empty (Stage 4)
• all_classified           → total_cases, date_range (Stage 2/3)
• month_year               → report date range
• total_cases              → denominator for percentage calculations
• gap_table                → proactive_notification_opportunity flag — supplements
                             notification rows with gap intelligence (Stage 5)

ERROR POLICY
────────────
No fallbacks. No placeholder returns. Every failure raises so the caller
(_generate_report_sections) sees and logs the real exception.
"""

import json
from typing import Dict, Any, List, Optional
from collections import defaultdict
import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Maps notification_opportunity channel values to display strings
_CHANNEL_DISPLAY: Dict[str, str] = {
    "sms":      "SMS",
    "SMS":      "SMS",
    "app":      "إشعار التطبيق",
    "email":    "بريد إلكتروني",
    "push":     "إشعار التطبيق",
    "both":     "SMS / إشعار التطبيق",
    "sms_app":  "SMS / إشعار التطبيق",
}

# Root-cause → default notification type label (fallback when notification_opportunities is empty)
_RC_NOTIFICATION_TYPE: Dict[str, str] = {
    "no_proactive_notification":  "تتبع توصيل الوثائق والرخص",
    "missing_info":               "تأكيد استلام البلاغ / الطلب",
    "inaccessible_info":          "تحديث مراحل معالجة الطلب",
    "platform_bug":               "تنبيه خطأ تقني مع رقم مرجعي",
    "policy_complexity":          "تذكير تجديد الرخص والملكيات",
}

_RC_NOTIFICATION_CHANNEL: Dict[str, str] = {
    "no_proactive_notification":  "SMS",
    "missing_info":               "SMS / إشعار التطبيق",
    "inaccessible_info":          "SMS / إشعار التطبيق",
    "platform_bug":               "إشعار التطبيق",
    "policy_complexity":          "SMS / إشعار التطبيق",
}

# Max FAQ rows to include in 6.1 table (mirror sample output cap of 7)
_MAX_FAQ_ROWS = 7


def _compute_notification_impact(cases_eliminated: int, total_cases: int) -> str:
    """
    Pre-compute expected impact statement for notification row.

    Derives concrete percentage reduction and case count from cases_eliminated.
    This value is LOCKED — the LLM must copy it verbatim in the final prose cell.

    Args:
        cases_eliminated: Number of cases this notification would prevent
        total_cases: Total cases in the dataset (denominator for percentage)

    Returns:
        Locked impact statement with concrete numbers (e.g. "إلغاء 15 حالة (30% من الحالات)")
    """
    if cases_eliminated == 0 or total_cases == 0:
        return "لا يوجد تأثير متوقع على هذه العينة"

    pct = round(cases_eliminated / total_cases * 100, 1) if total_cases > 0 else 0

    # Format case count in Arabic (singular, dual, plural)
    if cases_eliminated == 1:
        cases_text = "حالة واحدة"
    elif cases_eliminated == 2:
        cases_text = "حالتان"
    elif 3 <= cases_eliminated <= 10:
        cases_text = f"{cases_eliminated} حالات"
    else:
        cases_text = f"{cases_eliminated} حالة"

    return f"إلغاء {cases_text} ({pct}% من إجمالي الحالات)"


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# Also paste into stage6_json_report.py for the JSON builder.
# ──────────────────────────────────────────────────────────────────────────────

def _build_faq_rows_for_transform(state: PipelineState) -> List[Dict[str, str]]:
    """
    Pre-computed rows for Section 6.1 FAQ table.

    Uses validated_faqs (Stage 5) if available; falls back to faq_candidates (Stage 4).
    Sorted by actual sub_classification case count (not LLM frequency estimate).
    Capped at _MAX_FAQ_ROWS.

    Task 12 Fix: Cap FAQ frequency against actual sub_classification case count from
    state.all_classified to prevent Stage 4 LLM over-counting from inflating the table.
    Also sort by actual counts, not LLM estimates, so FAQs appear in order of impact.

    Schema returned: # | التكرار
    (السؤال and الإجابة المقترحة are written by the LLM from faq context)
    """
    source = state.validated_faqs if state.validated_faqs else state.faq_candidates

    # Build sub_classification counts from all_classified (ground truth)
    # MUST be built before sorting so we can use it as the sort key
    sub_counts: Dict[str, int] = defaultdict(int)
    for case in (state.all_classified or []):
        if case.sub_classification:
            sub_counts[case.sub_classification] += 1

    # Sort by actual sub_classification count, not by LLM frequency estimate
    # This ensures FAQ ranking reflects actual case distribution
    def _sort_key(faq):
        sub = getattr(faq, "sub_classification", None)
        return sub_counts.get(sub, faq.frequency) if sub else faq.frequency

    sorted_faqs = sorted(source, key=_sort_key, reverse=True)

    rows = []
    for i, faq in enumerate(sorted_faqs[:_MAX_FAQ_ROWS], 1):
        raw_freq = faq.frequency

        # Look up sub_classification from FAQ to get the authoritative case count
        faq_sub_class = getattr(faq, "sub_classification", None)

        if faq_sub_class and faq_sub_class in sub_counts:
            # Use the actual sub_classification count as the authoritative frequency
            capped_freq = sub_counts[faq_sub_class]
            source = "sub_classification"
        elif faq_sub_class and not (faq_sub_class in sub_counts):
            # FAQ has sub_classification but it doesn't match any cases (data mismatch)
            # Fall back to raw frequency capped against max sub-count
            max_sub_count = max(sub_counts.values()) if sub_counts else raw_freq
            capped_freq = min(raw_freq, max_sub_count)
            source = "fallback (no sub_class match)"
            if not faq_sub_class:
                print(
                    f"[DigitalTransform] WARNING: FAQ #{i} has sub_classification='{faq_sub_class}' "
                    f"but no matching cases. Using fallback cap."
                )
        elif sub_counts:
            # No sub_classification on FAQ — fall back to max sub-count as loose upper bound
            max_sub_count = max(sub_counts.values())
            capped_freq = min(raw_freq, max_sub_count)
            source = "fallback (no sub_class)"
        else:
            capped_freq = raw_freq
            source = "no sub_counts"

        if capped_freq != raw_freq and source != "no sub_counts":
            print(
                f"[DigitalTransform] FAQ frequency: rank={i}, "
                f"sub_classification={faq_sub_class!r}, original={raw_freq} → capped={capped_freq} ({source})"
            )

        # Display: show exact integer (no "+" suffix for capped values)
        freq_display = str(capped_freq)

        rows.append({
            "#":        str(i),
            "التكرار":  freq_display,
        })
    return rows


def _build_faq_prompt_context(state: PipelineState) -> List[Dict[str, Any]]:
    """
    Enriched FAQ context for the LLM prompt (Section 6.1).

    Provides raw Q&A text so the LLM can sharpen phrasing and add
    operational context from the resolved cases. Sorted by actual sub_classification
    case count to match the display order. No new computation — pure read of Stage 4/5 outputs.
    """
    source = state.validated_faqs if state.validated_faqs else state.faq_candidates

    # Build sub_classification counts (same as in _build_faq_rows_for_transform)
    sub_counts: Dict[str, int] = defaultdict(int)
    for case in (state.all_classified or []):
        if case.sub_classification:
            sub_counts[case.sub_classification] += 1

    # Sort by actual sub_classification count for consistency with display order
    def _sort_key(faq):
        sub = getattr(faq, "sub_classification", None)
        return sub_counts.get(sub, faq.frequency) if sub else faq.frequency

    sorted_faqs = sorted(source, key=_sort_key, reverse=True)

    return [
        {
            "rank":        i,
            "frequency":   faq.frequency,
            "question_ar": faq.question_ar or faq.question,
            "answer_ar":   faq.answer_ar or faq.answer,
            "top_level":   getattr(faq, "top_level", ""),
            "sub_classification": getattr(faq, "sub_classification", ""),
        }
        for i, faq in enumerate(sorted_faqs[:_MAX_FAQ_ROWS], 1)
    ]


def _count_delivery_stall_cases(state: PipelineState) -> int:
    """
    Count cases with ONLY the specific document delivery failure sub-classification.

    The expert's criterion is strict: only cases where the sub_classification is
    EXACTLY "شكوى عن عدم استلام الخدمة". Do NOT include "متابعة طلب مقدم" — only
    confirmed delivery failures.

    This is the authoritative count for the notification table row about document delivery alerts.
    Used to compute الحالات المُلغاة and to calibrate الأثر المتوقع percentages.
    """
    DELIVERY_FAILURE_SUB_CLASS = "شكوى عن عدم استلام الخدمة"
    count = 0
    for case in (state.all_classified or []):
        if case.sub_classification == DELIVERY_FAILURE_SUB_CLASS:
            count += 1
    return count


def _build_notification_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Pre-computed rows for Section 6.2 proactive notification table.

    Primary source: state.notification_opportunities (Stage 4).
    Supplement / fallback: derive rows from journey_map root-cause categories
    (Stage 4) filtered by proactive_notification_opportunity=True from gap_table
    (Stage 5) so we only surface gaps confirmed as SMS/email-resolvable.

    Sort: by cases_eliminated descending (so highest-impact row is first).

    Schema returned: نوع الإشعار | الحالات المُلغاة | القناة | الأثر المتوقع (LOCKED)
    (محتوى الإشعار is written by the LLM; الأثر المتوقع is pre-computed and locked)

    SPECIAL HANDLING for delivery notification rows:
    - If a notification is about document delivery alerts (e.g., SMS notification for delivery tracking),
      its cases_eliminated MUST be capped at the actual count of "شكوى عن عدم استلام الخدمة" cases.
    - This ensures the notification table row about delivery aligns with Section 7 Tool 3 impact.
    """
    rows: List[Dict[str, str]] = []
    total_cases = len(state.all_classified) or state.total_cases
    delivery_stall_count = _count_delivery_stall_cases(state)

    # ── Primary: notification_opportunities from Stage 4 ─────────────────────
    if state.notification_opportunities:
        sorted_notifs = sorted(
            state.notification_opportunities,
            key=lambda n: n.get("cases_eliminated", 0),
            reverse=True,
        )
        for n in sorted_notifs:
            notif_type = n.get("notification_type") or n.get("content_summary") or ""
            cases = n.get("cases_eliminated", 0)

            # ── SPECIAL OVERRIDE: delivery notification rows ──────────────────────────
            # If this notification is about document delivery, ALWAYS use the authoritative
            # count from all_classified, regardless of whether Stage 4 over- or under-reported it.
            # This ensures Section 6.2 notification row always aligns with Section 7 Tool 3 impact.
            if (isinstance(cases, int) and
                notif_type and
                any(kw in notif_type for kw in {"توصيل", "وثيقة", "استلام"}) and
                delivery_stall_count > 0):
                if cases != delivery_stall_count:
                    print(
                        f"[DigitalTransform] DELIVERY OVERRIDE: "
                        f"'{notif_type}' {cases} → {delivery_stall_count} "
                        f"(authoritative delivery_stall count from all_classified)"
                    )
                cases = delivery_stall_count

            channel_raw = n.get("channel", "")
            channel = _CHANNEL_DISPLAY.get(channel_raw, channel_raw or "SMS / إشعار التطبيق")
            # Pre-compute expected impact with concrete numbers (LOCKED field)
            impact_statement = _compute_notification_impact(
                cases if isinstance(cases, int) else 0,
                total_cases
            )
            rows.append({
                "نوع الإشعار":    notif_type,
                "الحالات المُلغاة": (
                    f"{cases} حالة" if isinstance(cases, int) and cases == 1
                    else "حالتان" if isinstance(cases, int) and cases == 2
                    else f"{cases} حالات" if isinstance(cases, int) and 3 <= cases <= 10
                    else f"{cases} حالة" if isinstance(cases, int) and cases > 10
                    else f"{cases}+ حالة"
                ),
                "القناة":          channel,
                "الأثر المتوقع":   impact_statement,  # LOCKED — LLM must copy verbatim
            })
        return rows

    # ── Fallback: derive from journey_map + gap_table proactive flags ─────────
    # Identify root-cause categories confirmed as proactive-resolvable (Stage 5)
    proactive_rc_cats: set = set()
    for gap in (state.gap_table or []):
        if gap.proactive_notification_opportunity:
            # Match gap topic to a journey friction point by case_count proximity
            # (gap_table and journey_map share cluster/topic ancestry from Stage 4/5)
            proactive_rc_cats.add("no_proactive_notification")  # always include
            # Also infer from gap_type if it contains notification language
            if "إشعار" in (gap.gap_type_ar or gap.gap_type or ""):
                proactive_rc_cats.add("no_proactive_notification")
            if "توصيل" in (gap.topic_ar or gap.topic or ""):
                proactive_rc_cats.add("no_proactive_notification")

    # Aggregate journey_map by root_cause_category
    rc_totals: Dict[str, int] = defaultdict(int)
    rc_best_friction: Dict[str, str] = {}
    for f in (state.journey_map or []):
        cat = f.root_cause_category
        rc_totals[cat] += f.case_count
        if f.case_count >= rc_totals.get(cat, 0) - f.case_count:
            rc_best_friction[cat] = f.friction_point_ar or f.friction_point

    # Include all root causes that have a proactive notification mapping
    # (not just the ones flagged — we always include "no_proactive_notification" +
    #  any others with non-zero counts that the LLM determined are notif-resolvable)
    eligible_cats = (
        proactive_rc_cats
        if proactive_rc_cats
        else set(_RC_NOTIFICATION_TYPE.keys())
    )

    sorted_rc = sorted(
        [(cat, cnt) for cat, cnt in rc_totals.items() if cat in eligible_cats],
        key=lambda x: x[1],
        reverse=True,
    )

    for cat, total_count in sorted_rc:
        notif_type = _RC_NOTIFICATION_TYPE.get(cat, cat)
        channel = _RC_NOTIFICATION_CHANNEL.get(cat, "SMS / إشعار التطبيق")
        cases_str = (
            f"{total_count} حالة" if total_count == 1
            else "حالتان" if total_count == 2
            else f"{total_count} حالات" if 3 <= total_count <= 10
            else f"{total_count} حالة"
        )
        # Pre-compute expected impact with concrete numbers (LOCKED field)
        impact_statement = _compute_notification_impact(total_count, total_cases)
        rows.append({
            "نوع الإشعار":    notif_type,
            "الحالات المُلغاة": cases_str,
            "القناة":          channel,
            "الأثر المتوقع":   impact_statement,  # LOCKED — LLM must copy verbatim
        })

    # Always include renewal reminder row if not already present
    renewal_labels = {"تذكير", "تجديد"}
    has_renewal = any(
        any(k in r["نوع الإشعار"] for k in renewal_labels) for r in rows
    )
    if not has_renewal:
        # Renewal reminder is speculative (no direct case count) — use placeholder
        rows.append({
            "نوع الإشعار":    "تذكير تجديد الرخص والملكيات",
            "الحالات المُلغاة": "متعدد",
            "القناة":          "SMS / إشعار التطبيق",
            "الأثر المتوقع":   "منع حالات تأخر التجديد المتكررة",  # LOCKED placeholder
        })

    return rows


def _build_notification_prompt_context(state: PipelineState, notif_rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Enriched notification context for the LLM prompt (Section 6.2).

    Joins pre-computed notification rows with gap_table proactive data and
    journey_map friction text so the LLM can write informed sample message
    content and realistic impact statements.
    No new computation — pure read of Stage 4/5 outputs.
    """
    # Build proactive gap lookup by topic keyword for context enrichment
    proactive_gaps = [g for g in (state.gap_table or []) if g.proactive_notification_opportunity]
    gap_context_by_topic: Dict[str, Dict[str, Any]] = {}
    for g in proactive_gaps:
        topic_key = (g.topic_ar or g.topic or "").strip()
        if topic_key:
            gap_context_by_topic[topic_key] = {
                "guidebook_status": g.guidebook_status,
                "coverage_pct":     g.coverage_percentage,
                "recommendation":   g.recommendation_ar or g.recommendation,
            }

    context = []
    for row in notif_rows:
        notif_type = row["نوع الإشعار"]
        cases_str  = row["الحالات المُلغاة"]
        channel    = row["القناة"]
        impact_locked = row.get("الأثر المتوقع", "")

        # Try to match to a proactive gap for extra context
        gap_extra: Optional[Dict[str, Any]] = None
        for topic_key, gap_info in gap_context_by_topic.items():
            # Simple substring match between notification type and gap topic
            if any(
                word in topic_key for word in notif_type.split()
                if len(word) > 2
            ):
                gap_extra = gap_info
                break

        entry: Dict[str, Any] = {
            "notification_type": notif_type,
            "cases_eliminated":  cases_str,
            "channel":           channel,
            "impact_locked":     impact_locked,  # LOCKED — must be copied verbatim
        }
        if gap_extra:
            entry["gap_context"] = gap_extra

        context.append(entry)

    return context


def _total_notif_cases(notif_rows: List[Dict[str, str]], state: PipelineState) -> int:
    """
    Compute total eliminatable cases from notification rows for section body headline.

    Prefers the authoritative proactive_notification_case_count from Stage 4.
    Falls back to summing cases_eliminated from notification_opportunities if that's unavailable.
    """
    if state.proactive_notification_case_count:
        return state.proactive_notification_case_count

    if state.notification_opportunities:
        return sum(
            n.get("cases_eliminated", 0) for n in state.notification_opportunities
            if isinstance(n.get("cases_eliminated"), int)
        )
    # Fallback: proactive gap_table case counts
    return sum(
        g.case_count for g in (state.gap_table or [])
        if g.proactive_notification_opportunity
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main section generator
# ──────────────────────────────────────────────────────────────────────────────

def generate_digital_transformation_section(
    state: PipelineState,
    api_key: str,
) -> Dict[str, Any]:
    """
    Generate Section 6 — Digital Transformation Plan.

    Pre-computes all numeric/structural columns from state (no re-computation of
    earlier pipeline stages), then asks the LLM to write:
      • section intro paragraph (2 sentences)
      • 6.1: السؤال + الإجابة المقترحة for each FAQ row
      • 6.2: محتوى الإشعار (مثال) for each notification row

    Reinjection guarantees pre-computed values (rank, frequency, notification type,
    cases eliminated, channel, الأثر المتوقع) are never replaced by LLM output.

    Raises on any failure — no fallbacks, no None returns.

    JSON output schema
    ──────────────────
    {
      "section": "digital_transformation",
      "section_body": "...",           ← LLM-written, 2 Arabic sentences
      "faq_table": [
        {
          "#": "1",
          "السؤال": "...",             ← LLM-written (sharpened from faq context)
          "الإجابة المقترحة": "...",   ← LLM-written (operational, step-by-step)
          "التكرار": "49+"            ← pre-computed from validated_faqs.frequency
        }
      ],
      "notification_table": [
        {
          "نوع الإشعار": "...",        ← pre-computed
          "الحالات المُلغاة": "...",   ← pre-computed
          "محتوى الإشعار (مثال)": "...", ← LLM-written sample SMS/push text
          "القناة": "...",             ← pre-computed
          "الأثر المتوقع": "..."       ← pre-computed (LOCKED — copy verbatim)
        }
      ]
    }
    """

    # ── Guard: required upstream outputs ─────────────────────────────────────
    faqs_available = bool(state.validated_faqs or state.faq_candidates)
    if not faqs_available:
        print(
            "[DigitalTransform] WARNING: Both state.validated_faqs and state.faq_candidates are empty — "
            "Stage 4 (stage4_analysis) and Stage 5 (stage5_gap) must complete successfully "
            "before this section can be generated. Returning empty section."
        )
        return {}
    if not state.journey_map and not state.notification_opportunities:
        raise RuntimeError(
            "[DigitalTransform] state.journey_map and state.notification_opportunities are both "
            "empty — Stage 4 must complete successfully before this section can be generated."
        )
    if not state.month_year:
        raise RuntimeError(
            "[DigitalTransform] state.month_year is not set — Stage 3 must complete successfully."
        )

    total_cases = len(state.all_classified) or state.total_cases
    if not total_cases:
        raise RuntimeError(
            "[DigitalTransform] total_cases is 0 — no classified cases in state."
        )

    # ── Pre-compute all values from state ────────────────────────────────────
    date_range       = convert_month_year_to_arabic(state.month_year)
    faq_rows         = _build_faq_rows_for_transform(state)        # pre-computed #, التكرار
    faq_context      = _build_faq_prompt_context(state)            # raw Q&A for LLM
    notif_rows       = _build_notification_rows(state)             # pre-computed type, cases, channel
    notif_context    = _build_notification_prompt_context(state, notif_rows)

    total_notif_cases = _total_notif_cases(notif_rows, state)
    notif_pct         = round(total_notif_cases / total_cases * 100, 1) if total_cases else 0.0
    faq_count         = len(faq_rows)
    notif_count       = len(notif_rows)

    # Total eliminatable cases string for section body ("30+" style)
    notif_headline = (
        f"{total_notif_cases}+"
        if total_notif_cases > 0
        else "عدد من"
    )

    # ── Prompt ───────────────────────────────────────────────────────────────
    prompt = (
        'You are writing Section 6 of a formal Arabic government report on customer inquiry\n'
        'analysis for Fujairah Police. The section title is:\n'
        '"سادساً: التحليل الرابع — خطة التحويل الرقمي"\n'
        '\n'
        'INPUTS — use ONLY these numbers, never invent figures\n'
        f'total_cases:             {total_cases}\n'
        f'date_range:              "{date_range}"\n'
        f'faq_count:               {faq_count}  (number of rows in 6.1 FAQ table)\n'
        f'notif_count:             {notif_count}  (number of rows in 6.2 notification table)\n'
        f'total_eliminatable:      {notif_headline}  (total cases eliminatable by proactive notifications)\n'
        f'notif_pct:               {notif_pct}%  (% of total_cases eliminatable by notifications)\n'
        '\n'
        'faq_context — raw FAQ data from Stage 4/5 (validated_faqs + frequency):\n'
        '  Each entry: rank, frequency, question_ar (raw Q text), answer_ar (raw answer), top_level\n'
        '  The LLM must SHARPEN these into clear, customer-facing Arabic Q&A pairs.\n'
        '  Questions must be phrased as the customer would type them (first person).\n'
        '  Answers must be step-by-step, operational, referencing MOI / UAE PASS where relevant.\n'
        f'{json.dumps(faq_context, ensure_ascii=False, indent=2)}\n'
        '\n'
        'notif_context — notification opportunity data from Stage 4/5:\n'
        '  Each entry: notification_type (the row label), cases_eliminated, channel,\n'
        '  and optionally gap_context (guidebook coverage + recommendation from Stage 5).\n'
        '  The LLM must write a realistic sample Arabic SMS/push message for محتوى الإشعار\n'
        '  and a concrete impact statement for الأثر المتوقع.\n'
        f'{json.dumps(notif_context, ensure_ascii=False, indent=2)}\n'
        '\n'
        'pre_computed_faq_table — Section 6.1\n'
        '(# and التكرار are LOCKED — copy verbatim; ADD السؤال and الإجابة المقترحة):\n'
        f'{json.dumps(faq_rows, ensure_ascii=False, indent=2)}\n'
        '\n'
        'pre_computed_notification_table — Section 6.2\n'
        '(نوع الإشعار, الحالات المُلغاة, القناة, الأثر المتوقع are LOCKED — copy verbatim;\n'
        ' ADD محتوى الإشعار (مثال) only):\n'
        f'{json.dumps(notif_rows, ensure_ascii=False, indent=2)}\n'
        '\n'
        '─────────────────────────────────────────────\n'
        'YOUR TASK — write ONLY the items listed below\n'
        '─────────────────────────────────────────────\n'
        '\n'
        'A. section_body — 2 sentences, formal Arabic\n'
        f'   - State that section delivers {faq_count} prioritised FAQs extracted\n'
        f'     from {date_range} data plus a proactive notification pathway.\n'
        f'   - State that {notif_headline} contacts ({notif_pct}% of total) could be\n'
        '     eliminated with a simple notification system — no structural change required.\n'
        '   - Open with: "هذه الأسئلة مستخرجة من الأنماط الأكثر تكراراً في البيانات النصية"\n'
        '     (first sentence of 6.1 intro) OR write a 2-sentence section preamble as above.\n'
        '   - Use ONLY numbers from INPUTS above.\n'
        '\n'
        'B. "السؤال" for EVERY row in pre_computed_faq_table\n'
        '   - Rephrase from question_ar in faq_context into natural first-person Arabic.\n'
        '   - Max 25 words per question.\n'
        '   - Do NOT invent new questions — sharpen the provided ones.\n'
        '\n'
        'C. "الإجابة المقترحة" for EVERY row in pre_computed_faq_table\n'
        '   - Use answer_ar from faq_context as the base.\n'
        '   - Add concrete steps where possible (app path, required documents, timelines).\n'
        '   - Reference MOI / UAE PASS in Latin script where applicable.\n'
        '   - Max 80 words per answer. Arabic only (except proper nouns).\n'
        '\n'
        'D. "محتوى الإشعار (مثال)" for EVERY row in pre_computed_notification_table\n'
        '   - Write a realistic Arabic SMS or push notification message template.\n'
        '   - Use [X] as placeholder for variable data (case number, tracking number, date).\n'
        '   - Max 30 words. Wrap in Arabic quotation marks «».\n'
        '\n'
        'E. "الأثر المتوقع" for EVERY row in pre_computed_notification_table\n'
        '   - **LOCKED FIELD — copy the الأثر المتوقع value verbatim from the pre-computed row.**\n'
        '   - Do NOT rewrite or paraphrase this field.\n'
        '   - Do NOT generate a different impact statement.\n'
        '   - The value is pre-computed from actual case counts and must not be changed.\n'
        '\n'
        '─────────────────────────────────────────────\n'
        'OUTPUT — single JSON object, no markdown fences, no extra keys\n'
        '─────────────────────────────────────────────\n'
        '\n'
        '{\n'
        '  "section": "digital_transformation",\n'
        '  "section_body": "...",\n'
        '  "faq_table": [\n'
        '    {\n'
        '      "#": "1",\n'
        '      "السؤال": "...",\n'
        '      "الإجابة المقترحة": "...",\n'
        '      "التكرار": "49+"\n'
        '    }\n'
        '  ],\n'
        '  "notification_table": [\n'
        '    {\n'
        '      "نوع الإشعار": "...",\n'
        '      "الحالات المُلغاة": "...",\n'
        '      "محتوى الإشعار (مثال)": "...",\n'
        '      "القناة": "...",\n'
        '      "الأثر المتوقع": "..."\n'
        '    }\n'
        '  ]\n'
        '}\n'
        '\n'
        'RULES:\n'
        f'- faq_table must have exactly {faq_count} rows (same as pre_computed_faq_table).\n'
        f'- notification_table must have exactly {notif_count} rows (same as pre_computed_notification_table).\n'
        '- #, التكرار: copy verbatim from pre_computed_faq_table — never alter.\n'
        '- نوع الإشعار, الحالات المُلغاة, القناة: copy verbatim from pre_computed_notification_table.\n'
        '- Every number in section_body must match a pre-computed input above.\n'
        '- Arabic only. Proper nouns in Latin script only: MOI, SMS, OTP, UAE PASS.\n'
        '- محتوى الإشعار examples must use «» Arabic quotation marks.\n'
        '- No markdown, no extra keys, no extra nesting.\n'
        '- CRITICAL: Do NOT use double-quote characters (\") inside any string value. '
        'Use angle brackets « » instead of double quotes when citing names.\n'
    )

    # ── API call ─────────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    print(
        f"[DigitalTransform] Calling API — "
        f"total_cases={total_cases}, "
        f"faq_rows={faq_count}, "
        f"notif_rows={notif_count}, "
        f"eliminatable={notif_headline} ({notif_pct}%)"
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = parse_json_response(message.content[0].text, tag="DigitalTransform")
    if result is None:
        raise RuntimeError(
            "[DigitalTransform] parse_json_response returned None — "
            "could not extract JSON from API response.\n"
            f"Raw response (first 500 chars):\n{message.content[0].text[:500]}"
        )

    # ── Reinject pre-computed values — LLM output must never override state data ──

    # Table 6.1: FAQ table
    llm_faq_rows = result.get("faq_table")
    if not isinstance(llm_faq_rows, list):
        raise RuntimeError(
            f"[DigitalTransform] 'faq_table' missing or not a list in LLM response. "
            f"Got type: {type(llm_faq_rows)}"
        )
    if len(llm_faq_rows) != faq_count:
        raise RuntimeError(
            f"[DigitalTransform] faq_table row count mismatch: "
            f"expected {faq_count}, LLM returned {len(llm_faq_rows)}."
        )

    merged_faq_table = []
    for i, (pre_row, llm_row) in enumerate(zip(faq_rows, llm_faq_rows)):
        question = llm_row.get("السؤال", "")
        answer   = llm_row.get("الإجابة المقترحة", "")

        if not question:
            raise RuntimeError(
                f"[DigitalTransform] Missing 'السؤال' in faq_table row {i} (rank {pre_row['#']})"
            )
        if not answer:
            raise RuntimeError(
                f"[DigitalTransform] Missing 'الإجابة المقترحة' in faq_table row {i} "
                f"(rank {pre_row['#']})"
            )

        # Column order matches sample output: # | السؤال | الإجابة المقترحة | التكرار
        merged_faq_table.append({
            "#":                pre_row["#"],
            "السؤال":           question,
            "الإجابة المقترحة": answer,
            "التكرار":          pre_row["التكرار"],
        })

    result["faq_table"] = merged_faq_table

    # Table 6.2: Notification table
    llm_notif_rows = result.get("notification_table")
    if not isinstance(llm_notif_rows, list):
        raise RuntimeError(
            f"[DigitalTransform] 'notification_table' missing or not a list in LLM response. "
            f"Got type: {type(llm_notif_rows)}"
        )
    if len(llm_notif_rows) != notif_count:
        raise RuntimeError(
            f"[DigitalTransform] notification_table row count mismatch: "
            f"expected {notif_count}, LLM returned {len(llm_notif_rows)}."
        )

    merged_notif_table = []
    for i, (pre_row, llm_row) in enumerate(zip(notif_rows, llm_notif_rows)):
        sample_msg = llm_row.get("محتوى الإشعار (مثال)", "")

        if not sample_msg:
            raise RuntimeError(
                f"[DigitalTransform] Missing 'محتوى الإشعار (مثال)' in notification_table "
                f"row {i} (type: '{pre_row['نوع الإشعار']}')"
            )

        # Column order matches sample output:
        # نوع الإشعار | الحالات المُلغاة | محتوى الإشعار (مثال) | القناة | الأثر المتوقع
        # All other columns are LOCKED — taken from pre_row, not llm_row
        merged_notif_table.append({
            "نوع الإشعار":           pre_row["نوع الإشعار"],
            "الحالات المُلغاة":      pre_row["الحالات المُلغاة"],
            "محتوى الإشعار (مثال)": sample_msg,
            "القناة":                pre_row["القناة"],
            "الأثر المتوقع":         pre_row["الأثر المتوقع"],  # LOCKED — always from pre_row
        })

    result["notification_table"] = merged_notif_table

    print(
        f"[DigitalTransform] ✅ Done — "
        f"faq_table={len(merged_faq_table)} rows, "
        f"notification_table={len(merged_notif_table)} rows"
    )
    return result
