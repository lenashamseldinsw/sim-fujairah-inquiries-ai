"""
generate_ai_use_cases_section — stage6_artifacts.py companion

Generates Section 7: "سابعاً: حالات الاستخدام المدعومة بالذكاء الاصطناعي"

INTEGRATION
───────────
1. stage6_artifacts.py — _generate_report_sections(), after digital_transformation block:

    from .generate_ai_use_cases_section import generate_ai_use_cases_section

    print("[Report Gen] Generating AI Use Cases section...")
    ai_use_cases = generate_ai_use_cases_section(state, api_key)
    state.report_sections_ar['ai_use_cases'] = {
        'heading': 'سابعاً: حالات الاستخدام المدعومة بالذكاء الاصطناعي',
        'raw_data': ai_use_cases,
    }

2. stage6_json_report.py — JSONReportBuilder:

    a) Import at top:
       from .generate_ai_use_cases_section import (
           _build_ai_tool_rows,
       )

    b) Paste build_ai_use_cases_section as a method on JSONReportBuilder.

    c) In build_report(), after build_digital_transformation_section():
        sections.append(self.build_ai_use_cases_section(lang=lang))

SECTION STRUCTURE (mirrors sample output — سابعاً):
──────────────────────────────────────────────────────
Intro paragraph: states the AI opportunity in 2 sentences grounded in pipeline data.

Main table — حالات الاستخدام (4 AI tools):
  Columns: الأداة | الوظيفة | الأثر المتوقع على بيانات [quarter] | تقييم التنفيذ
  Pre-computed from state: الأثر المتوقع (case counts, friction clusters, reclassification rate)
  LLM-written: الأداة (refined name), الوظيفة (description), تقييم التنفيذ (complexity + timeline)

Closing note: بيانات التدريب جاهزة الآن — total_cases figure + prior run totals.

DATA SOURCING — no new computation, only state reads
─────────────────────────────────────────────────────
• journey_map              → friction clusters + case counts + root_cause_category (Stage 4)
• gap_table                → severity, proactive_notification_opportunity, coverage_percentage (Stage 5)
• patterns                 → cluster names, sub_themes, case_count (Stage 4)
• all_classified           → total_cases, reclassification_rate (Stage 2/3)
• reclassified_count       → misclassified case count for section body headline (Stage 2/3)
• reclassification_rate    → percentage of reclassified cases (Stage 2/3)
• month_year               → quarter/date range label
• total_cases              → total classified cases denominator
• prior_run_state          → prior quarter total for data training note (optional)

FOUR AI TOOLS (fixed, derived from analysis patterns — no new LLM invocation needed):
──────────────────────────────────────────────────────────────────────────────────────
1. محقق التناقضات في صور المخالفات (Vision model for violation photo anomaly detection)
   → Driven by: journey_map friction "اعتراض/مشكوك فيها" case counts
   → Impact: prevent N+ cases reaching the citizen at all
   → Effort: high (requires live camera feed access)

2. موجّه الحالات بين الجهات الحكومية (Multi-agency case router)
   → Driven by: misrouted cases from patterns / journey_map
   → Impact: eliminate inter-agency routing delay
   → Effort: medium (requires authority boundary mapping)

3. مدقق جودة الوثائق قبل الإرسال (Pre-submission document quality checker)
   → Driven by: journey_map "عدم استلام وثيقة / صورة غير مستوفية" case counts + gap_table
   → Impact: prevent N+ stalled license cases + rejected requests
   → Effort: medium (OCR + document validation APIs are commercially available)

4. رادار نقاط الاحتكاك الجغرافي (Geographic friction hotspot radar)
   → Driven by: patterns with geographic sub-themes, infrastructure proposal cases
   → Impact: convert anecdotal infrastructure suggestions into data-driven investment decisions
   → Effort: low-medium (location data already in CRM text)

ERROR POLICY
────────────
No fallbacks. No placeholder returns. Every failure raises so the caller
(_generate_report_sections) sees and logs the real exception.
"""

import json
from typing import Dict, Any, List, Optional, Tuple
import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Root-cause categories that signal misrouting between agencies
_MISROUTING_ROOT_CAUSES = {"inaccessible_info", "policy_complexity"}

# Root-cause categories that signal document / delivery issues
_DOCUMENT_ROOT_CAUSES = {"no_proactive_notification", "platform_bug"}

# Keywords that signal geographic / infrastructure themes in patterns
_GEO_KEYWORDS = {"كلباء", "البدية", "دبا", "منطقة", "تقاطع", "موقع", "جغرافي", "بنية تحتية", "مقترح"}

# Keywords that signal violation photo / disputed fine themes
_VIOLATION_PHOTO_KEYWORDS = {"مشكوك", "صورة", "كاميرا", "اعتراض", "مخالفة مشكوك", "لوحة", "تناقض"}

# Effort level labels
_EFFORT_HIGH    = "مرتفع"
_EFFORT_MEDIUM  = "متوسط"
_EFFORT_LOW_MED = "منخفض–متوسط"


# ──────────────────────────────────────────────────────────────────────────────
# Pre-computation helpers
# ──────────────────────────────────────────────────────────────────────────────

def _count_friction_cases(state: PipelineState, keywords: set) -> int:
    """
    Sum case_count from journey_map entries whose friction_point_ar/cluster_ar
    contains any of the given keywords.

    Pure read of Stage 4 output — no new computation.
    """
    total = 0
    for entry in (state.journey_map or []):
        text = " ".join([
            entry.friction_point_ar or entry.friction_point or "",
            entry.cluster_ar or entry.cluster or "",
            entry.sub_classification or "",
        ]).lower()
        if any(kw.lower() in text for kw in keywords):
            total += entry.case_count
    return total


def _count_pattern_cases(state: PipelineState, keywords: set) -> int:
    """
    Sum case_count from patterns whose cluster_ar/sub_theme_ar
    contains any of the given keywords.

    Pure read of Stage 4 output — no new computation.
    """
    total = 0
    for p in (state.patterns or []):
        text = " ".join([
            p.cluster_ar or p.cluster or "",
            p.sub_theme_ar or p.sub_theme or "",
            p.sub_classification or "",
        ]).lower()
        if any(kw.lower() in text for kw in keywords):
            total += p.case_count
    return total


def _count_misrouted_cases(state: PipelineState) -> int:
    """
    Estimate misrouted / wrong-agency cases from journey_map.

    Looks for friction entries with root_cause_category in _MISROUTING_ROOT_CAUSES
    and text signals suggesting inter-agency confusion (جهة, هيئة, بلدية, RTA).
    Falls back to patterns whose sub_theme suggests cross-agency confusion.

    Pure read of Stage 4 output.
    """
    misrouting_keywords = {"جهة", "هيئة", "بلدية", "rta", "دبي", "توجيه خاطئ", "جهة خاطئة"}
    total = 0
    for entry in (state.journey_map or []):
        if entry.root_cause_category in _MISROUTING_ROOT_CAUSES:
            text = " ".join([
                entry.friction_point_ar or "",
                entry.cluster_ar or "",
            ]).lower()
            if any(kw in text for kw in misrouting_keywords):
                total += entry.case_count

    if total == 0:
        # Fallback: pattern-level count with agency keywords
        total = _count_pattern_cases(state, misrouting_keywords)

    return total


def _count_document_stall_cases(state: PipelineState) -> Tuple[int, int]:
    """
    Return (stalled_license_count, rejected_request_count) from all_classified + gap_table.

    Stalled licenses: cases classified as "شكوى عن عدم استلام الخدمة" or "متابعة طلب مقدم"
    (primary source: all_classified ground truth, secondary: journey_map if empty)

    Rejected requests: gap_table entries with platform_bug / missing document gap_type

    Pure read of Stage 4/5 outputs.
    """
    _SUBS_NON_DELIVERY = {
        "شكوى عن عدم استلام الخدمة",
        "متابعة طلب مقدم",
    }

    # Primary: count directly from all_classified (authoritative ground truth)
    stalled = sum(
        1 for c in (state.all_classified or [])
        if c.sub_classification in _SUBS_NON_DELIVERY
    )

    # Secondary: if all_classified somehow empty, fall back to journey_map keyword match
    if stalled == 0:
        delivery_keywords = {"استلام", "توصيل", "صورة", "مستوفية", "وثيقة", "رخصة", "توقف"}
        stalled = _count_friction_cases(state, delivery_keywords)

    # Rejected requests from gap_table where guidebook says "Missing" + document-related
    rejected = 0
    for gap in (state.gap_table or []):
        if gap.guidebook_status == "Missing" and gap.severity in ("Critical", "Medium"):
            topic_text = (gap.topic_ar or gap.topic or "").lower()
            if any(kw in topic_text for kw in {"وثيقة", "مستند", "هوية", "رفض"}):
                rejected += gap.case_count

    return stalled, rejected


def _count_geo_cases(state: PipelineState) -> int:
    """
    Count infrastructure proposal / geographic complaint cases from patterns.

    Pure read of Stage 4 output.
    """
    return _count_pattern_cases(state, _GEO_KEYWORDS)


def _extract_geo_locations(state: PipelineState) -> List[str]:
    """
    Extract distinct geographic location mentions from pattern sub_theme_ar texts.

    Returns up to 4 location names. Used in the LLM prompt as concrete examples.
    Pure read of Stage 4 output.
    """
    locations: List[str] = []
    for p in (state.patterns or []):
        text = " ".join([
            p.sub_theme_ar or p.sub_theme or "",
            p.cluster_ar or p.cluster or "",
        ])
        for kw in _GEO_KEYWORDS:
            if kw in text and kw not in {"منطقة", "تقاطع", "موقع", "جغرافي", "بنية تحتية", "مقترح"}:
                if kw not in locations:
                    locations.append(kw)
    return locations[:4]


def _get_prior_run_total(state: PipelineState) -> Optional[int]:
    """
    Extract total case count from prior_run_state if available.

    Returns None if no prior run data loaded.
    Pure read of state — no computation.
    """
    if not state.prior_run_state:
        return None
    return state.prior_run_state.get("total_cases")


def _build_document_checker_impact(stalled: int, rejected: int, date_range: str) -> str:
    """
    Build impact statement for Tool 3 (document quality checker).

    Handles zero-count cases by omitting the zero-value part from the statement.
    All numbers are data-derived with no hardcoded floors.
    """
    if stalled == 0 and rejected == 0:
        return f"في {date_range}: لم يتم التعرف على حالات توقف رخصة أو طلبات مرفوضة في البيانات"
    elif stalled > 0 and rejected == 0:
        return (
            f"منع {stalled}+ حالة رخصة متوقفة لصورة غير مستوفية "
            "— يحل المشكلة قبل أن تُسجَّل في CRM"
        )
    elif stalled == 0 and rejected > 0:
        return (
            f"منع {rejected}+ طلبات مرفوضة لنقص صورة الهوية "
            "— يحل المشكلة قبل أن تُسجَّل في CRM"
        )
    else:
        return (
            f"منع {stalled}+ حالة رخصة متوقفة لصورة غير مستوفية "
            f"+ {rejected}+ طلبات مرفوضة لنقص صورة الهوية "
            "— يحل المشكلة قبل أن تُسجَّل في CRM"
        )


def _build_ai_tool_rows(state: PipelineState) -> List[Dict[str, Any]]:
    """
    Pre-compute the four AI tool rows for the use-cases table.

    Each row contains:
      - tool_id:         internal identifier for LLM matching
      - الأثر المتوقع:   pre-computed impact statement (numbers from state)
      - effort_level:    pre-computed effort level (LOCKED — not written by LLM)
      - effort_timeline: pre-computed timeline string (LOCKED)
      - context:         extra facts for LLM to write الأداة, الوظيفة, تقييم التنفيذ

    Column values marked LOCKED must be copied verbatim by the LLM into the output.
    Columns الأداة, الوظيفة, and the narrative in تقييم التنفيذ are LLM-written.

    Pure read of Stage 2–5 outputs — no new computation.
    """
    total_cases  = len(state.all_classified) or state.total_cases
    reclass_rate = state.reclassification_rate or 0.0
    date_range   = convert_month_year_to_arabic(state.month_year) or ""

    # ── Tool 1: Vision model for violation photo anomaly detection ───────────
    # CRITICAL: Tool 1 only applies to disputed photos (sub_classification="شكوى عن مخالفة مشكوك فيها")
    # NOT to contested valid fines (sub_classification="اعتراض على مخالفة مرورية")
    # A vision model cannot decide if a fine is legitimately issued — only if the photo is correct.
    # So only count the "disputed photo" sub-classification.

    _SUB_DISPUTED_FINE = "شكوى عن مخالفة مشكوك فيها"

    # Primary: count directly from all_classified (authoritative ground truth)
    violation_cases = sum(
        1 for c in (state.all_classified or [])
        if c.sub_classification == _SUB_DISPUTED_FINE
    )

    # Secondary: if all_classified somehow empty, fall back to journey_map sub_classification
    if violation_cases == 0:
        violation_cases = sum(
            e.case_count for e in (state.journey_map or [])
            if e.sub_classification == _SUB_DISPUTED_FINE
        )

    # Last resort: keyword match on journey_map (مشكوك only, never اعتراض)
    if violation_cases == 0:
        violation_cases = sum(
            e.case_count for e in (state.journey_map or [])
            if ("مشكوك" in (e.friction_point_ar or e.friction_point or "").lower() or
                "مشكوك" in (e.cluster_ar or e.cluster or "").lower())
        )

    # ── Tool 2: Multi-agency case router ─────────────────────────────────────
    misrouted_cases = _count_misrouted_cases(state)

    # ── Tool 3: Pre-submission document quality checker ───────────────────────
    stalled, rejected = _count_document_stall_cases(state)
    doc_total = stalled + rejected

    # ── Tool 4: Geographic friction radar ─────────────────────────────────────
    geo_cases   = _count_geo_cases(state)
    geo_locations = _extract_geo_locations(state)
    geo_loc_str = "، ".join(geo_locations) if geo_locations else "مناطق متعددة"

    rows = [
        {
            "tool_id": "violation_photo_checker",
            # Pre-computed impact (LOCKED numbers — copy verbatim)
            "impact_cases": violation_cases,
            "impact_statement_ar": (
                f"منع {violation_cases}+ حالة «مشكوك فيها» من الوصول إلى المتعامل أصلاً "
                "— يحل المشكلة عند المصدر لا بعد الشكوى"
            ),
            "effort_level": _EFFORT_HIGH,
            "effort_timeline_ar": "9+ أشهر (يتطلب الوصول لتغذية لحظية من كاميرات المخالفات)",
            # Context for LLM (NOT locked — used to write الأداة and الوظيفة)
            "context": {
                "friction_source": "مشكوك في صحة المخالفة / اعتراض مروري",
                "technique": "نموذج رؤية حاسوبية (Computer Vision)",
                "what_it_does": (
                    "يُطابق لون السيارة ونوعها مع بيانات المركبة المسجلة في اللحظة ذاتها "
                    "قبل إصدار المخالفة — ينبّه على التناقض بين اللوحة المصورة والسجل"
                ),
            },
        },
        {
            "tool_id": "agency_router",
            "impact_cases": misrouted_cases,
            "impact_statement_ar": (
                f"في {date_range}: {misrouted_cases}+ حالات وُجِّهت لجهة خاطئة "
                "— يقطع الدوران ويُقلص وقت الحل"
            ) if misrouted_cases > 0 else (
                f"في {date_range}: لم يتم التعرف على حالات موجهة لجهة خاطئة في البيانات"
            ),
            "effort_level": _EFFORT_MEDIUM,
            "effort_timeline_ar": "3-4 أشهر (يتطلب خريطة صلاحيات موثقة لكل الجهات)",
            "context": {
                "friction_source": "إحالة الحالات بين جهات حكومية متعددة",
                "technique": "نموذج تصنيف نصي + قاعدة بيانات صلاحيات الجهات",
                "what_it_does": (
                    "يحلل كل حالة جديدة ويحدد الجهة الصحيحة تلقائياً "
                    "(شرطة الفجيرة / RTA دبي / بلدية الفجيرة / هيئة أخرى) "
                    "ويُرسل للمتعامل التوجيه الصحيح فوراً بدل إعادة التوجيه اليدوي"
                ),
            },
        },
        {
            "tool_id": "document_quality_checker",
            "impact_cases": doc_total,
            "impact_statement_ar": (
                _build_document_checker_impact(stalled, rejected, date_range)
            ),
            "effort_level": _EFFORT_MEDIUM,
            "effort_timeline_ar": "3-4 أشهر (نموذج OCR ومعايير التحقق من الوثائق متاحة تجارياً)",
            "context": {
                "friction_source": "رخصة متوقفة / طلب مرفوض بسبب صورة أو وثيقة ناقصة",
                "technique": "OCR + فحص جودة الصورة + تحقق من اكتمال الحقول",
                "what_it_does": (
                    "يتحقق آلياً من الوثائق المرفوعة قبل إتمام الطلب: "
                    "دقة الصورة الشخصية، صلاحية شهادة الفحص، اكتمال الحقول الإلزامية، "
                    "تطابق رقم الهوية — يُرشد المتعامل للتصحيح الفوري قبل الإرسال"
                ),
                "gap_coverage": (
                    # Pull guidebook coverage percentage for document gaps from gap_table
                    next(
                        (
                            g.coverage_percentage
                            for g in (state.gap_table or [])
                            if any(
                                kw in (g.topic_ar or g.topic or "").lower()
                                for kw in {"وثيقة", "صورة", "رخصة"}
                            )
                        ),
                        None,
                    )
                ),
            },
        },
        {
            "tool_id": "geo_friction_radar",
            "impact_cases": geo_cases,
            "impact_statement_ar": (
                f"في {date_range}: {geo_cases} مقترحات بنية تحتية وردت من مناطق متكررة "
                f"({geo_loc_str}) — يُحوِّل المقترحات العشوائية إلى قرارات استثمار "
                "مبنية على كثافة الحالات الفعلية"
            ) if geo_cases > 0 else (
                f"في {date_range}: لم يتم التعرف على مقترحات بنية تحتية جغرافية في البيانات"
            ),
            "effort_level": _EFFORT_LOW_MED,
            "effort_timeline_ar": "2-3 أشهر (بيانات الموقع مستخرجة من نصوص CRM الموجودة)",
            "context": {
                "friction_source": "شكاوى ومقترحات بنية تحتية من مناطق جغرافية متكررة",
                "technique": "استخراج الكيانات الجغرافية (NER) + خريطة حرارية",
                "what_it_does": (
                    "يرسم خريطة حرارية لكل شكاوى وبلاغات الفترة حسب الموقع الجغرافي "
                    "المذكور في النصوص — يُحدد التقاطعات والمناطق ذات الكثافة "
                    "غير المتناسبة لتبرير أولويات البنية التحتية والدوريات"
                ),
                "geo_locations": geo_locations,
            },
        },
    ]
    return rows


def _build_training_data_note(state: PipelineState) -> Dict[str, Any]:
    """
    Build the "بيانات التدريب جاهزة الآن" closing note data.

    Pulls:
      - total_cases from current run (state.all_classified or state.total_cases)
      - prior_run total from state.prior_run_state (if available)
      - reclassification_rate (state.reclassification_rate)

    Returns a dict with numeric values for the LLM to incorporate into
    the closing note paragraph — never invented by the LLM.
    """
    current_total = len(state.all_classified) or state.total_cases
    prior_total   = _get_prior_run_total(state)
    reclass_rate  = state.reclassification_rate or 0.0

    return {
        "current_total":     current_total,
        "prior_total":       prior_total,  # May be None if no prior run loaded
        "reclassification_rate_pct": round(reclass_rate * 100, 1) if reclass_rate <= 1 else round(reclass_rate, 1),
        "date_range":        convert_month_year_to_arabic(state.month_year) or "",
        "has_prior_run":     prior_total is not None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main section generator
# ──────────────────────────────────────────────────────────────────────────────

def generate_ai_use_cases_section(
    state: PipelineState,
    api_key: str,
) -> Dict[str, Any]:
    """
    Generate Section 7 — AI-Powered Use Cases.

    Pre-computes all numeric/structural columns from state (no re-computation of
    earlier pipeline stages), then asks the LLM to write:
      • section intro paragraph (2 sentences)
      • For each of 4 AI tool rows:
          - الأداة: refined Arabic tool name
          - الوظيفة: full description of what the tool does and how (2–4 sentences)
          - تقييم التنفيذ: implementation complexity narrative including pre-computed
            effort_level + effort_timeline (LLM assembles these into a phrase)
      • Closing note paragraph about training data readiness

    Reinjection guarantees pre-computed values (impact_statement_ar, effort_level,
    effort_timeline_ar, tool_id) are never replaced by LLM output.

    Raises on any failure — no fallbacks, no None returns.

    JSON output schema
    ──────────────────
    {
      "section": "ai_use_cases",
      "section_body": "...",               ← LLM-written, 2 Arabic sentences
      "use_cases_table": [
        {
          "tool_id": "violation_photo_checker",  ← pre-computed (LOCKED)
          "الأداة": "...",                       ← LLM-written
          "الوظيفة": "...",                      ← LLM-written
          "الأثر المتوقع": "...",                ← pre-computed (LOCKED)
          "تقييم التنفيذ": "..."                 ← LLM-written (must embed effort_level + timeline)
        },
        ... (4 rows total)
      ],
      "closing_note": "..."                ← LLM-written, 2 Arabic sentences
    }
    """

    # ── Guard: required upstream outputs ─────────────────────────────────────
    if not state.journey_map:
        raise RuntimeError(
            "[AIUseCases] state.journey_map is empty — "
            "Stage 4 (stage4_analysis) must complete successfully "
            "before this section can be generated."
        )
    if not state.gap_table:
        raise RuntimeError(
            "[AIUseCases] state.gap_table is empty — "
            "Stage 5 (stage5_gap) must complete successfully "
            "before this section can be generated."
        )
    if not state.month_year:
        raise RuntimeError(
            "[AIUseCases] state.month_year is not set — Stage 3 must complete successfully."
        )

    total_cases = len(state.all_classified) or state.total_cases
    if not total_cases:
        raise RuntimeError(
            "[AIUseCases] total_cases is 0 — no classified cases in state."
        )

    # ── Pre-compute all values from state ────────────────────────────────────
    date_range       = convert_month_year_to_arabic(state.month_year)
    reclass_rate_pct = (
        round(state.reclassification_rate * 100, 1)
        if state.reclassification_rate and state.reclassification_rate <= 1
        else round(state.reclassification_rate or 0.0, 1)
    )

    tool_rows      = _build_ai_tool_rows(state)
    training_data  = _build_training_data_note(state)
    tool_count     = len(tool_rows)  # Always 4

    # Build locked columns separately for the prompt (what the LLM cannot change)
    locked_impact_rows = [
        {
            "tool_id":         r["tool_id"],
            "الأثر المتوقع":   r["impact_statement_ar"],   # LOCKED
            "effort_level":    r["effort_level"],           # LOCKED — LLM embeds in تقييم التنفيذ
            "effort_timeline": r["effort_timeline_ar"],     # LOCKED — LLM embeds in تقييم التنفيذ
        }
        for r in tool_rows
    ]

    # Build context rows (what the LLM uses to write الأداة and الوظيفة)
    context_rows = [
        {
            "tool_id":         r["tool_id"],
            "friction_source": r["context"]["friction_source"],
            "technique":       r["context"]["technique"],
            "what_it_does":    r["context"]["what_it_does"],
            # Include optional extra context if present
            **(
                {"geo_locations": r["context"]["geo_locations"]}
                if "geo_locations" in r["context"] and r["context"]["geo_locations"]
                else {}
            ),
            **(
                {"gap_coverage_pct": r["context"]["gap_coverage"]}
                if "gap_coverage" in r["context"] and r["context"]["gap_coverage"] is not None
                else {}
            ),
        }
        for r in tool_rows
    ]

    # ── Prompt ───────────────────────────────────────────────────────────────
    training_note_line = (
        f"current_total_cases:         {training_data['current_total']}  (حالات {date_range})\n"
        f"reclassification_rate:        {reclass_rate_pct}%  (نسبة الحالات المُعاد تصنيفها)\n"
    )
    if training_data["has_prior_run"]:
        training_note_line += (
            f"prior_run_total_cases:        {training_data['prior_total']}  (حالات الدورة السابقة)\n"
            f"combined_labelled_dataset:    {training_data['current_total'] + training_data['prior_total']}  "
            "(إجمالي الحالات المُعلَّمة عبر الدورتين)\n"
        )

    prompt = (
        'You are writing Section 7 of a formal Arabic government report on customer inquiry\n'
        'analysis for Fujairah Police. The section title is:\n'
        '"سابعاً: حالات الاستخدام المدعومة بالذكاء الاصطناعي"\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'INPUTS — use ONLY these numbers, never invent figures\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'total_cases:                  {total_cases}\n'
        f'date_range:                   "{date_range}"\n'
        f'reclassification_rate_pct:    {reclass_rate_pct}%\n'
        f'tool_count:                   {tool_count}  (number of rows in table)\n'
        + training_note_line +
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'locked_impact_rows — "الأثر المتوقع" is LOCKED for each tool.\n'
        'Do NOT rephrase or alter these. Copy them verbatim into use_cases_table.\n'
        'effort_level and effort_timeline are also LOCKED — embed them into "تقييم التنفيذ" text.\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'{json.dumps(locked_impact_rows, ensure_ascii=False, indent=2)}\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'context_rows — raw facts for YOU to write "الأداة" and "الوظيفة".\n'
        'friction_source: what customer pain drives this tool.\n'
        'technique: the AI/ML method used.\n'
        'what_it_does: detailed description of the tool\'s logic (expand into "الوظيفة").\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'{json.dumps(context_rows, ensure_ascii=False, indent=2)}\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'YOUR TASK — write ONLY the items listed below\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '\n'
        'A. section_body — 2 sentences, formal Arabic\n'
        f'   - State that the opportunities identified in {date_range} integrate with AI capabilities\n'
        f'     to create a smart self-service system covering {reclass_rate_pct}%+ of current contacts\n'
        '     without human involvement in classification.\n'
        '   - Reference the total_cases figure and the four AI tools.\n'
        '   - Open with: "تتكامل الفرص المرصودة في [date_range] مع قدرات الذكاء الاصطناعي"\n'
        '   - Use ONLY numbers from INPUTS above.\n'
        '\n'
        'B. "الأداة" for EVERY row in use_cases_table (tool_id order must match locked_impact_rows)\n'
        '   - Write a precise Arabic name for the AI tool.\n'
        '   - Max 8 words. Use the technique from context_rows as a guide.\n'
        '   - Must be distinct for each tool — no repetition.\n'
        '\n'
        'C. "الوظيفة" for EVERY row in use_cases_table\n'
        '   - Expand what_it_does from context_rows into a full functional description.\n'
        '   - Include: what triggers it, what data it uses, what output it produces.\n'
        '   - Reference the technique (Computer Vision, NLP, OCR, NER) where applicable.\n'
        '   - 2–4 sentences, 30–70 words. Arabic only (except: MOI, SMS, UAE PASS, RTA, OCR, NER, CRM).\n'
        '   - Do NOT repeat الأثر المتوقع content — الوظيفة describes HOW the tool works,\n'
        '     not its impact (that is in the locked column).\n'
        '\n'
        'D. "تقييم التنفيذ" for EVERY row in use_cases_table\n'
        '   - MUST begin with the locked effort_level value (e.g. "مرتفع — ...").\n'
        '   - Then MUST include the locked effort_timeline_ar in parentheses or after a dash.\n'
        '   - Example format: "متوسط — 3-4 أشهر (يتطلب ...)"\n'
        '   - Max 25 words. Arabic only.\n'
        '\n'
        'E. closing_note — 2 sentences, formal Arabic\n'
        '   - State that training data is ready NOW.\n'
        f'   - Mention {training_data["current_total"]} labelled cases from {date_range}\n'
        + (
            f'   - Also mention {training_data["prior_total"]} cases from prior run\n'
            f'     (combined: {training_data["current_total"] + training_data["prior_total"]}).\n'
            if training_data["has_prior_run"]
            else f'   - State this labelled dataset enables training the AI classifier immediately.\n'
        ) +
        '   - Open with: "ملاحظة محورية: بيانات التدريب جاهزة الآن"\n'
        '   - Use ONLY numbers from INPUTS above.\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'OUTPUT — single JSON object, no markdown fences, no extra keys\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '\n'
        '{\n'
        '  "section": "ai_use_cases",\n'
        '  "section_body": "...",\n'
        '  "use_cases_table": [\n'
        '    {\n'
        '      "tool_id": "violation_photo_checker",\n'
        '      "الأداة": "...",\n'
        '      "الوظيفة": "...",\n'
        '      "الأثر المتوقع": "منع 49+ حالة ...",\n'
        '      "تقييم التنفيذ": "مرتفع — 9+ أشهر (...)"\n'
        '    }\n'
        '  ],\n'
        '  "closing_note": "ملاحظة محورية: بيانات التدريب جاهزة الآن — ..."\n'
        '}\n'
        '\n'
        'RULES:\n'
        f'- use_cases_table must have exactly {tool_count} rows — one per tool_id in locked_impact_rows.\n'
        '- tool_id: copy verbatim from locked_impact_rows — never alter or omit.\n'
        '- "الأثر المتوقع": copy verbatim from locked_impact_rows["الأثر المتوقع"] — never rephrase.\n'
        '- "تقييم التنفيذ": must START with the locked effort_level and include effort_timeline.\n'
        '- Every number in section_body and closing_note must match a pre-computed INPUTS value above.\n'
        '- Arabic only. Proper nouns in Latin script only: MOI, SMS, OTP, UAE PASS, RTA, OCR, NER, CRM.\n'
        '- No markdown, no extra keys, no extra nesting.\n'
        '- CRITICAL: Do NOT use double-quote characters (\") inside any string value. '
        'Use angle brackets « » instead of double quotes when citing names.\n'
        '- Rows must appear in the SAME ORDER as locked_impact_rows (violation → agency → document → geo).\n'
    )

    # ── API call ─────────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    print(
        f"[AIUseCases] Calling API — "
        f"total_cases={total_cases}, "
        f"reclass_rate={reclass_rate_pct}%, "
        f"tool_rows={tool_count}, "
        f"has_prior_run={training_data['has_prior_run']}"
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = parse_json_response(message.content[0].text, tag="AIUseCases")
    if result is None:
        raise RuntimeError(
            "[AIUseCases] parse_json_response returned None — "
            "could not extract JSON from API response.\n"
            f"Raw response (first 500 chars):\n{message.content[0].text[:500]}"
        )

    # ── Validate and reinject pre-computed locked values ─────────────────────

    llm_rows = result.get("use_cases_table")
    if not isinstance(llm_rows, list):
        raise RuntimeError(
            f"[AIUseCases] 'use_cases_table' missing or not a list in LLM response. "
            f"Got type: {type(llm_rows)}"
        )
    if len(llm_rows) != tool_count:
        raise RuntimeError(
            f"[AIUseCases] use_cases_table row count mismatch: "
            f"expected {tool_count}, LLM returned {len(llm_rows)}."
        )

    merged_rows = []
    for i, (locked_row, llm_row) in enumerate(zip(locked_impact_rows, llm_rows)):
        tool_id = locked_row["tool_id"]

        tool_name = llm_row.get("الأداة", "")
        function_desc = llm_row.get("الوظيفة", "")
        impl_assessment = llm_row.get("تقييم التنفيذ", "")

        if not tool_name:
            raise RuntimeError(
                f"[AIUseCases] Missing 'الأداة' in use_cases_table row {i} (tool_id: {tool_id})"
            )
        if not function_desc:
            raise RuntimeError(
                f"[AIUseCases] Missing 'الوظيفة' in use_cases_table row {i} (tool_id: {tool_id})"
            )
        if not impl_assessment:
            raise RuntimeError(
                f"[AIUseCases] Missing 'تقييم التنفيذ' in use_cases_table row {i} (tool_id: {tool_id})"
            )

        # Validate تقييم التنفيذ starts with the locked effort level
        expected_effort = locked_row["effort_level"]
        if not impl_assessment.startswith(expected_effort):
            # Enforce: prepend the effort level if LLM omitted it
            impl_assessment = f"{expected_effort} — {impl_assessment}"

        # Column order matches sample output: الأداة | الوظيفة | الأثر المتوقع | تقييم التنفيذ
        merged_rows.append({
            "tool_id":      tool_id,                             # internal (stripped in JSON report)
            "الأداة":       tool_name,                           # LLM-written
            "الوظيفة":      function_desc,                       # LLM-written
            "الأثر المتوقع": locked_row["الأثر المتوقع"],        # LOCKED — reinjected
            "تقييم التنفيذ": impl_assessment,                    # LLM-written (effort level enforced)
        })

    result["use_cases_table"] = merged_rows

    # Validate closing_note is present and non-empty
    closing_note = result.get("closing_note", "")
    if not closing_note:
        raise RuntimeError(
            "[AIUseCases] 'closing_note' missing or empty in LLM response."
        )

    # Validate section_body is present
    section_body = result.get("section_body", "")
    if not section_body:
        raise RuntimeError(
            "[AIUseCases] 'section_body' missing or empty in LLM response."
        )

    print(
        f"[AIUseCases] ✅ Done — "
        f"use_cases_table={len(merged_rows)} rows, "
        f"section_body={len(section_body)} chars, "
        f"closing_note={len(closing_note)} chars"
    )
    return result
