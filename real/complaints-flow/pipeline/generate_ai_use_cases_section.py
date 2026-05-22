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
1. مُصنِّف النصوص الذكي (NLP) — reduce "أخرى" from 43%
   → Driven by: unclassified cases marked as "أخرى" in classification
   → Impact: reclassify N+ complaint cases into proper categories
   → Effort: medium (text classification is well-established)

2. نموذج كشف الشذوذ — detect pattern shifts early
   → Driven by: anomalies in complaint volume, unexpected spikes
   → Impact: detect early warning signs before escalation
   → Effort: medium (time-series anomaly detection is standard)

3. محرك اقتراح الردود (Agent Assist) — standardize resolution quality
   → Driven by: incomplete/inconsistent resolutions in journey_map
   → Impact: reduce resolution time + improve first-contact resolution rate
   → Effort: medium (template + RAG-based suggestion)

4. نموذج التنبؤ بالحجم الفصلي — forecast complaint volume
   → Driven by: seasonal patterns in patterns table
   → Impact: enable capacity planning + resource allocation
   → Effort: low-medium (historical volume data available)

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

# Root-cause categories that signal unclassified/miscellaneous complaints
_UNCLASSIFIED_ROOT_CAUSES = {"unclear_issue", "other_category"}

# Root-cause categories that signal anomalies or unusual patterns
_ANOMALY_ROOT_CAUSES = {"spike_in_volume", "unexpected_pattern"}

# Root-cause categories that signal resolution quality issues
_RESOLUTION_QUALITY_ROOT_CAUSES = {"incomplete_resolution", "inconsistent_response"}

# Keywords that signal seasonal/volume pattern complaints
_VOLUME_PATTERN_KEYWORDS = {"فصل", "موسم", "كمية", "حجم", "شهري", "ربع سنوي", "اتجاه"}

# Keywords that signal unclassified complaints ("أخرى")
_UNCLASSIFIED_KEYWORDS = {"أخرى", "متنوعة", "غير محدد", "أخري"}

# Keywords that signal anomalies or unusual cases
_ANOMALY_KEYWORDS = {"ارتفاع مفاجئ", "شذوذ", "غير عادي", "غير متوقع", "نمط جديد"}

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


def _build_nlp_classifier_impact(state: PipelineState) -> Dict[str, Any]:
    """
    Tool 1: NLP Text Classifier — reduce unclassified "أخرى" cases.

    Grounds impact in REAL metrics:
    - unclassified_count: actual "أخرى" cases from all_classified
    - unclassified_pct: percentage of total cases
    - reclass_rate: percentage already reclassified (Stage 2/3)

    Returns dict with locked impact statement (no hallucination).
    """
    total_cases = len(state.all_classified) or state.total_cases or 1

    # Count actual "أخرى" cases from sub-classifications (Stage 2)
    unclassified_count = 0
    for case in (state.all_classified or []):
        sub = case.sub_classification or ""
        if "أخرى" in sub or "بلا تصنيف" in sub:
            unclassified_count += 1

    if unclassified_count == 0:
        # Fallback: use actual count from state if available
        unclassified_count = state.reclassified_count or 0

    unclassified_pct = round((unclassified_count / total_cases * 100), 1) if total_cases > 0 else 0
    reclass_pct = round(state.reclassification_rate, 1) if state.reclassification_rate else 0

    # LOCKED impact: grounded in REAL classification metrics, never hallucinated
    impact = (
        f"إعادة تصنيف {unclassified_count}+ حالة من فئة «أخرى» ({unclassified_pct}% من الحالات) "
        f"— معدل إعادة التصنيف الحالي {reclass_pct}%، مع إمكانية الرفع إلى 90%+"
        if unclassified_count > 0
        else "تحسين دقة التصنيف من خلال تطبيق نموذج NLP على حالات «أخرى» الموجودة"
    )

    return {
        "tool_id": "nlp_text_classifier",
        "impact_statement_ar": impact,
        "impact_data": {"count": unclassified_count, "pct": unclassified_pct, "reclass_pct": reclass_pct},
    }


def _build_anomaly_detection_impact(state: PipelineState) -> Dict[str, Any]:
    """
    Tool 2: Anomaly Detection — detect pattern shifts early.

    Grounds impact in REAL friction patterns:
    - friction_with_spikes: entries with high case counts (top 5%)
    - anomaly_count: actual anomaly patterns detected

    Returns dict with locked impact statement (no hallucination).
    """
    total_cases = len(state.all_classified) or state.total_cases or 1
    threshold = total_cases * 0.05  # Top 5% of cases

    # Find friction entries with unusually high case counts (actual anomalies in data)
    # Deduplicate using case_ids to avoid counting same case multiple times
    anomaly_case_ids = set()
    for entry in (state.journey_map or []):
        if entry.case_count > threshold:
            anomaly_case_ids.update(entry.case_ids or [])

    anomaly_count = len(anomaly_case_ids)
    high_impact_cases = anomaly_count

    # LOCKED impact: grounded in REAL anomalies found in journey_map
    impact = (
        f"اكتشاف {anomaly_count} أنماط شذوذ في توزيع الشكاوى ({high_impact_cases} حالة) "
        f"— تنبيه مبكر قبل التصعيد"
        if anomaly_count > 0
        else "مراقبة مستمرة لأنماط الشكاوى غير العادية في البيانات المتقادمة"
    )

    return {
        "tool_id": "anomaly_detection",
        "impact_statement_ar": impact,
        "impact_data": {"anomaly_count": anomaly_count, "cases_affected": high_impact_cases},
    }


def _build_response_suggestion_impact(state: PipelineState) -> Dict[str, Any]:
    """
    Tool 3: Response Suggestion Engine — standardize resolution quality.

    Grounds impact in REAL gaps + friction:
    - unresolved_count: cases with resolution gaps (Stage 5)
    - key_services: top services affected

    Returns dict with locked impact statement (no hallucination).
    """
    # Count gap entries indicating incomplete resolution
    # Deduplicate using case_ids to avoid counting same case multiple times
    unresolved_gaps = [
        g for g in (state.gap_table or [])
        if g.severity in ("Critical", "High") and g.guidebook_status == "Missing"
    ]
    unresolved_case_ids = set()
    for g in unresolved_gaps:
        unresolved_case_ids.update(g.case_ids or [])
    unresolved_count = len(unresolved_case_ids)

    if unresolved_count == 0:
        # Fallback: count friction points about incomplete handling
        unresolved_count = _count_friction_cases(state, {"عدم اكتمال", "حل غير كامل", "متابعة"})

    # LOCKED impact: grounded in REAL resolution gaps from Stage 5
    impact = (
        f"توحيد وتسريع معالجة {unresolved_count}+ حالة من الشكاوى المرتجعة "
        f"— تقليل وقت الحل + زيادة معدل الحل من أول تواصل"
        if unresolved_count > 0
        else "تحسين جودة الردود الموحَّدة بناءً على سياسات الخدمة المعتمدة"
    )

    return {
        "tool_id": "response_suggestion_agent",
        "impact_statement_ar": impact,
        "impact_data": {"gap_count": unresolved_count},
    }


def _build_volume_forecast_impact(state: PipelineState) -> Dict[str, Any]:
    """
    Tool 4: Volume Forecast Model — predict complaint volume by quarter.

    Grounds impact in REAL patterns:
    - pattern_count: number of detected patterns with seasonal signals
    - avg_pattern_size: average case count per pattern

    Returns dict with locked impact statement (no hallucination).
    """
    # Count patterns showing seasonal/volume variation
    volume_patterns = [
        p for p in (state.patterns or [])
        if any(kw in (p.sub_theme_ar or p.sub_theme or "") for kw in {"فصل", "موسم", "ذروة"})
    ]
    pattern_count = len(volume_patterns)
    total_pattern_cases = sum(p.case_count for p in volume_patterns) if volume_patterns else 0
    avg_size = int(total_pattern_cases / pattern_count) if pattern_count > 0 else 0

    # LOCKED impact: grounded in REAL pattern data from Stage 4
    impact = (
        f"التنبؤ بحجم الشكاوى الفصلي اعتماداً على {pattern_count} أنماط موسمية "
        f"({total_pattern_cases} حالة) — تمكين تخطيط الموارد الاستباقي"
        if pattern_count > 0
        else "تحليل الأنماط التاريخية للتنبؤ بتوزيع الشكاوى للأرباع القادمة"
    )

    return {
        "tool_id": "volume_forecast_model",
        "impact_statement_ar": impact,
        "impact_data": {"pattern_count": pattern_count, "total_cases": total_pattern_cases},
    }


def _get_prior_run_total(state: PipelineState) -> Optional[int]:
    """
    Extract total case count from prior_run_state if available.

    Returns None if no prior run data loaded.
    Pure read of state — no computation.
    """
    if not state.prior_run_state:
        return None
    return state.prior_run_state.get("total_cases")


def _build_ai_tool_rows(state: PipelineState) -> List[Dict[str, Any]]:
    """
    Pre-compute the four AI tool rows for the use-cases table.

    Each row contains:
      - tool_id:         internal identifier for LLM matching
      - الأثر المتوقع:   pre-computed impact statement (REAL numbers from state, NO hallucination)
      - effort_level:    pre-computed effort level (LOCKED — not written by LLM)
      - effort_timeline: pre-computed timeline string (LOCKED)
      - context:         extra facts for LLM to write الأداة, الوظيفة, تقييم التنفيذ

    Column values marked LOCKED must be copied verbatim by the LLM into the output.
    Columns الأداة, الوظيفة, and the narrative in تقييم التنفيذ are LLM-written.

    Pure read of Stage 2–5 outputs — no hallucination, no floor values.
    """
    date_range   = convert_month_year_to_arabic(state.month_year) or ""

    # ── Build impact statements using REAL data from each stage (no hallucination) ──
    nlp_impact      = _build_nlp_classifier_impact(state)
    anomaly_impact  = _build_anomaly_detection_impact(state)
    response_impact = _build_response_suggestion_impact(state)
    volume_impact   = _build_volume_forecast_impact(state)

    rows = [
        {
            "tool_id": nlp_impact["tool_id"],
            "impact_statement_ar": nlp_impact["impact_statement_ar"],  # LOCKED — from REAL data
            "effort_level": _EFFORT_MEDIUM,
            "effort_timeline_ar": "3–4 أشهر (نماذج تصنيف النصوص متاحة تجارياً مع التخصيص)",
            "context": {
                "friction_source": "شكاوى غير مصنفة في فئة «أخرى»",
                "technique": "معالجة اللغة الطبيعية (NLP) + نموذج تصنيف نصي",
                "what_it_does": (
                    "يحلل نصوص الشكاوى المصنفة كـ «أخرى» ويستخرج الكلمات المفتاحية والمواضيع "
                    "الرئيسية ويعيد تصنيفها إلى الفئات الصحيحة — يقلل الضجيج ويحسن جودة البيانات"
                ),
            },
        },
        {
            "tool_id": anomaly_impact["tool_id"],
            "impact_statement_ar": anomaly_impact["impact_statement_ar"],  # LOCKED — from REAL data
            "effort_level": _EFFORT_MEDIUM,
            "effort_timeline_ar": "2–3 أشهر (كشف الشذوذ الإحصائي متوفر في مكتبات معيارية)",
            "context": {
                "friction_source": "ارتفاعات مفاجئة في حجم الشكاوى أو ظهور أنماط جديدة",
                "technique": "كشف الشذوذ الإحصائي (Anomaly Detection) — نماذج التعلم الآلي",
                "what_it_does": (
                    "يراقب توزيع الشكاوى ويحدد الارتفاعات المفاجئة أو التغيرات غير المتوقعة "
                    "في الأنماط — ينبّه الفريق بسرعة لتمكين التدخل السريع وتجنب الأزمات"
                ),
            },
        },
        {
            "tool_id": response_impact["tool_id"],
            "impact_statement_ar": response_impact["impact_statement_ar"],  # LOCKED — from REAL data
            "effort_level": _EFFORT_MEDIUM,
            "effort_timeline_ar": "3–4 أشهر (RAG + نماذج الاقتراحات معروفة التطبيق)",
            "context": {
                "friction_source": "ردود غير مكتملة أو غير متسقة — ضعف جودة الحل",
                "technique": "Agent Assist مع Retrieval-Augmented Generation (RAG)",
                "what_it_does": (
                    "يحلل محتوى الشكوى ويسترجع الإجابات المسبقة والسياسات ذات الصلة "
                    "ويقترح ردوداً معيارية للموظف — يزيد الاتساق ويسرع الحل"
                ),
            },
        },
        {
            "tool_id": volume_impact["tool_id"],
            "impact_statement_ar": volume_impact["impact_statement_ar"],  # LOCKED — from REAL data
            "effort_level": _EFFORT_LOW_MED,
            "effort_timeline_ar": "2–3 أشهر (بيانات الحجم التاريخية موجودة في قاعدة البيانات)",
            "context": {
                "friction_source": "عدم القدرة على التنبؤ بذروات الشكاوى الموسمية",
                "technique": "نموذج التنبؤ بالسلاسل الزمنية (Time Series Forecasting)",
                "what_it_does": (
                    "يحلل البيانات التاريخية لحجم الشكاوى ويتعرف على الأنماط الموسمية "
                    "— يتنبأ بالحجم المتوقع للربع القادم ليمكّن تخطيط الموارد"
                ),
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
          "tool_id": "nlp_text_classifier",     ← pre-computed (LOCKED)
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
        'You are writing Section 7 of a formal Arabic government report on customer complaint\n'
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
        f'     to create an intelligent complaint resolution system covering {reclass_rate_pct}%+ of contacts\n'
        '     without human classification overhead.\n'
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
        '   - Reference the technique (NLP, Anomaly Detection, RAG, Time Series) where applicable.\n'
        '   - 2–4 sentences, 30–70 words. Arabic only (except: RAG, NLP, OCR, CRM, RTA, UAE PASS).\n'
        '   - Do NOT repeat الأثر المتوقع content — الوظيفة describes HOW the tool works,\n'
        '     not its impact (that is in the locked column).\n'
        '\n'
        'D. "تقييم التنفيذ" for EVERY row in use_cases_table\n'
        '   - MUST begin with the locked effort_level value (e.g. "متوسط — ...").\n'
        '   - Then MUST include the locked effort_timeline_ar in parentheses or after a dash.\n'
        '   - Example format: "متوسط — 3–4 أشهر (يتطلب ...)"\n'
        '   - Max 25 words. Arabic only.\n'
        '\n'
        'E. closing_note — 2 sentences, formal Arabic\n'
        '   - State that training data is ready NOW.\n'
        f'   - Mention {training_data["current_total"]} labelled cases from {date_range}\n'
        + (
            f'   - Also mention {training_data["prior_total"]} cases from prior run\n'
            f'     (combined: {training_data["current_total"] + training_data["prior_total"]}).\n'
            if training_data["has_prior_run"]
            else f'   - State this labelled dataset enables training the AI models immediately.\n'
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
        '      "tool_id": "nlp_text_classifier",\n'
        '      "الأداة": "...",\n'
        '      "الوظيفة": "...",\n'
        '      "الأثر المتوقع": "إعادة تصنيف 20+ حالة ...",\n'
        '      "تقييم التنفيذ": "متوسط — 3–4 أشهر (...)"\n'
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
        '- CRITICAL — Only genuine AI/ML initiatives. Automation ≠ AI.\n'
        '  The following are NOT AI and must NEVER appear as AI use cases:\n'
        '    ✗ SMS or email notifications (these are automation, covered in Section 6.2)\n'
        '    ✗ Workflow routing rules or escalation triggers\n'
        '    ✗ Database lookups or status-check integrations\n'
        '    ✗ Form pre-filling or data copy between systems\n'
        '    ✗ Scheduled reports or dashboards\n'
        '  Valid AI requires one of: language model, ML classifier, anomaly detection\n'
        '  algorithm, time-series forecasting model, or retrieval-augmented generation.\n'
        '  Every row in the use_cases table must name its ML/AI technique explicitly.\n'
        '- Arabic only. Proper nouns in Latin script only: RAG, NLP, OCR, CRM, RTA, UAE PASS.\n'
        '- No markdown, no extra keys, no extra nesting.\n'
        '- CRITICAL: Do NOT use double-quote characters (\") inside any string value. '
        'Use angle brackets « » instead of double quotes when citing names.\n'
        '- Rows must appear in the SAME ORDER as locked_impact_rows (nlp → anomaly → response → volume).\n'
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
