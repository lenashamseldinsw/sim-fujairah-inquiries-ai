"""
generate_improvement_roadmap_section — stage6_artifacts.py companion

Generates Section 8: "ثامناً: خارطة الطريق التحسينية المقترحة"
(Improvement Roadmap)

INTEGRATION
───────────
1. stage6_artifacts.py — _generate_report_sections(), after ai_use_cases block:

    from .generate_improvement_roadmap_section import generate_improvement_roadmap_section

    print("[Report Gen] Generating Improvement Roadmap section...")
    roadmap = generate_improvement_roadmap_section(state, api_key)
    state.report_sections_ar['improvement_roadmap'] = {
        'heading': 'ثامناً: خارطة الطريق التحسينية المقترحة',
        'raw_data': roadmap,
    }

2. stage6_json_report.py — JSONReportBuilder:

    a) Import at top:
       from .generate_improvement_roadmap_section import _build_display_roadmap_rows

    b) Paste build_improvement_roadmap_section as a method on JSONReportBuilder.

    c) In build_report(), after build_ai_use_cases_section():
        sections.append(self.build_improvement_roadmap_section(lang=lang))

SECTION STRUCTURE (mirrors sample output — ثامناً):
─────────────────────────────────────────────────────
Intro paragraph: 2 sentences tying the roadmap to the four prior analyses.

Main table — خارطة الطريق (7 rows, 6 columns):
  Columns: الأفق الزمني | # | التوصية | المصدر | الأثر المتوقع | الجهد
  Horizons (emoji-prefixed, Arabic):
    🚨 فوري           — items solvable in weeks with no system changes
    📅 قصير المدى     — items requiring 1–3 months of development
    🔧 متوسط المدى    — items requiring 3–6 months integration work
    🚀 طويل المدى     — items requiring 6+ months or advanced AI/infra

HOW ROWS ARE DERIVED — NO RE-COMPUTATION
─────────────────────────────────────────
Each roadmap row is sourced directly from earlier pipeline stages.
The _build_roadmap_rows() function assembles them; the LLM only writes
prose (التوصية, الأثر المتوقع) using these locked inputs:

  Stage 4 → journey_map
    • cluster / cluster_ar      → friction theme → "فوري" or "قصير المدى" rows
    • case_count                → used in الأثر المتوقع ("إلغاء N+ حالة")
    • root_cause_category       → determines horizon bucket
      - no_proactive_notification → 🚨 فوري   (just needs SMS/notification config)
      - missing_info            → 🚨 فوري   (FAQ/content publish)
      - platform_bug            → 📅 قصير المدى (needs in-app form/flow)
      - inaccessible_info       → 📅 قصير المدى (digital portal / channel fix)
      - policy_complexity       → 🔧 متوسط المدى (cross-agency coordination)

  Stage 5 → gap_table
    • severity = "Critical"     → bumps horizon toward فوري/قصير (urgency signal)
    • proactive_notification_opportunity = True → always 🚨 فوري
    • recommendation_ar         → seed text for التوصية (LLM expands)
    • gap_type_ar               → seed for المصدر column

  Stage 4 → self_service_tags + notification_opportunities
    • notification_opportunities with cases_eliminated → 🚨 فوري rows

  Stage 7 (AI use cases, from report_sections_ar['ai_use_cases'])
    • use_cases_table rows with effort_level:
      - "منخفض"  → 📅 قصير المدى (can be bootstrapped from existing data)
      - "متوسط"  → 🔧 متوسط المدى
      - "مرتفع"  → 🚀 طويل المدى

  المصدر column values:
    - "التحليل"        → derived purely from CRM data patterns (stage 4/5)
    - "كلا المصدرَين" → corroborated by BOTH CRM data AND guidebook gap analysis

LOCKED vs LLM-WRITTEN columns
──────────────────────────────
  LOCKED (pre-computed, LLM copies verbatim):
    • الأفق الزمني   — emoji + Arabic horizon label
    • #              — sequential row number
    • الجهد          — effort label (منخفض / متوسط / مرتفع)
    • المصدر         — source attribution

  LLM-WRITTEN (using locked inputs as seeds):
    • التوصية        — specific, actionable Arabic recommendation (≤ 35 words)
    • الأثر المتوقع  — quantified expected impact grounded in case counts (≤ 25 words)

JSON output schema
──────────────────
{
  "section": "improvement_roadmap",
  "section_body": "...",          ← LLM-written, 2 Arabic sentences
  "roadmap_table": [
    {
      "row_id": "immediate_1",    ← LOCKED internal key
      "الأفق الزمني": "🚨 فوري", ← LOCKED
      "#": "1",                  ← LOCKED
      "التوصية": "...",          ← LLM-written
      "المصدر": "التحليل",      ← LOCKED
      "الأثر المتوقع": "...",   ← LLM-written (grounded in locked case counts)
      "الجهد": "منخفض"         ← LOCKED
    },
    ...  (5–8 rows total)
  ]
}

ERROR POLICY
────────────
No fallbacks. No placeholder returns. Every failure raises so the caller
(_generate_report_sections) sees and logs the real exception.
"""

import json
from typing import Dict, Any, List, Tuple
import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response


# ──────────────────────────────────────────────────────────────────────────────
# Constants — horizon bucketing
# ──────────────────────────────────────────────────────────────────────────────

_ROOT_CAUSE_TO_HORIZON: Dict[str, str] = {
    "no_proactive_notification": "🚨 فوري",
    "missing_info":              "🚨 فوري",
    "inaccessible_info":         "📅 قصير المدى",
    "platform_bug":              "📅 قصير المدى",
    "policy_complexity":         "🔧 متوسط المدى",
}

_EFFORT_TO_HORIZON: Dict[str, str] = {
    "منخفض":  "📅 قصير المدى",
    "متوسط":  "🔧 متوسط المدى",
    "مرتفع":  "🚀 طويل المدى",
}

_HORIZON_ORDER: List[str] = [
    "🚨 فوري",
    "📅 قصير المدى",
    "🔧 متوسط المدى",
    "🚀 طويل المدى",
]

# Source attribution — used in the المصدر column
_SOURCE_ANALYSIS_ONLY = "التحليل"
_SOURCE_BOTH          = "كلا المصدرَين"


# ──────────────────────────────────────────────────────────────────────────────
# Pre-computation helpers
# ──────────────────────────────────────────────────────────────────────────────

def _horizon_rank(label: str) -> int:
    """Return sort key for horizon labels (lower = more urgent)."""
    try:
        return _HORIZON_ORDER.index(label)
    except ValueError:
        return len(_HORIZON_ORDER)


def _source_for_gap(gap) -> str:
    """
    Return المصدر value for a gap row.
    If the guidebook has relevant coverage (status ≠ Missing and match_confidence > 0.4),
    the recommendation is corroborated by BOTH sources; otherwise it's analysis-only.
    """
    if (gap.guidebook_status != "Missing"
            and gap.guidebook_match_confidence is not None
            and gap.guidebook_match_confidence > 0.4):
        return _SOURCE_BOTH
    return _SOURCE_ANALYSIS_ONLY


def _effort_for_root_cause(root_cause: str, case_count: int) -> str:
    """
    Derive effort level from root_cause_category.
    Higher case counts with complex root causes escalate effort slightly.
    """
    if root_cause in ("no_proactive_notification", "missing_info"):
        return "منخفض"
    if root_cause in ("inaccessible_info", "platform_bug"):
        return "متوسط" if case_count < 30 else "متوسط"
    if root_cause == "policy_complexity":
        return "متوسط"
    return "متوسط"


def _extract_keywords(text: str) -> set:
    """Extract Arabic keywords for semantic similarity matching."""
    if not text:
        return set()
    words = text.split()
    # Filter out short words and common prepositions
    return {w for w in words if len(w) > 2 and w not in ['من', 'في', 'على', 'عن', 'إلى', 'هذا', 'أن', 'أو']}


def _are_semantically_similar(text1: str, text2: str, threshold: float = 0.5) -> bool:
    """
    Check if two recommendation texts describe the same action (near-duplicate detection).
    Returns True if they share enough key terms to be considered duplicates.
    """
    keywords1 = _extract_keywords(text1)
    keywords2 = _extract_keywords(text2)

    if not keywords1 or not keywords2:
        return False

    # Calculate Jaccard similarity
    intersection = len(keywords1 & keywords2)
    union = len(keywords1 | keywords2)
    similarity = intersection / union if union > 0 else 0

    return similarity >= threshold


def _build_roadmap_rows(state: PipelineState) -> List[Dict[str, Any]]:
    """
    Build locked roadmap row data from pipeline state — NO LLM invocation.

    Each row contains:
      - row_id:          internal de-duplication key
      - horizon:         one of _HORIZON_ORDER
      - effort:          منخفض / متوسط / مرتفع
      - source:          المصدر attribution string
      - seed_recommendation_ar:  seed text for LLM (from gap recommendation_ar or journey friction)
      - seed_impact_ar:          seed text for LLM (case counts + cluster)
      - case_count:      integer for impact grounding

    Rows are collected from FOUR sources (priority order):
      1. notification_opportunities (stage 4) — 🚨 فوري for distinct items only (semantic dedup)
      2. gap_table Critical rows (stage 5) — horizon from proactive_notification / guidebook status
      3. journey_map distinct friction clusters (stage 4) — horizon from root_cause_category
      4. AI use cases (report_sections_ar['ai_use_cases']) — 🔧 متوسط/🚀 طويل based on effort

    Deduplication:
      - Exact cluster matching (seen_clusters set)
      - Semantic similarity for notifications (shared keywords → skip duplicate)

    Max rows returned: 8 (matches sample output of 7 + one optional long-term).
    """
    rows: List[Dict[str, Any]] = []
    seen_clusters: set = set()
    seen_recommendations: List[str] = []  # Track recommendation text for semantic dedup

    # Diagnostics (logged at end)
    source_counts = {"notification": 0, "critical_gaps": 0, "journey": 0, "ai_use_cases": 0}

    # ── SOURCE 1: Notification opportunities → 🚨 فوري (semantic dedup) ────────────────────────
    for notif in (state.notification_opportunities or []):
        cases_eliminated = notif.get("cases_eliminated", 0)
        notification_type = notif.get("notification_type", "")
        channel = notif.get("channel", "SMS")
        content_summary = notif.get("content_summary", "")
        if not notification_type or cases_eliminated < 1:
            continue

        rec_text = content_summary or notification_type

        # DEDUP: Skip if semantically similar to a row already added
        is_duplicate = any(
            _are_semantically_similar(rec_text, seen_rec, threshold=0.5)
            for seen_rec in seen_recommendations
        )
        if is_duplicate:
            continue

        row_id = f"notif_{notification_type[:30].replace(' ', '_')}"
        if row_id in seen_clusters:
            continue

        seen_clusters.add(row_id)
        seen_recommendations.append(rec_text)
        source_counts["notification"] += 1

        rows.append({
            "row_id":                   row_id,
            "horizon":                  "🚨 فوري",
            "effort":                   "منخفض",
            "source":                   _SOURCE_ANALYSIS_ONLY,
            "seed_recommendation_ar":   rec_text,
            "seed_impact_ar":           f"إلغاء {cases_eliminated}+ حالة تواصل",
            "case_count":               cases_eliminated,
        })

    # ── SOURCE 2: Critical gap_table rows (stage 5) ───────────────────────────
    for gap in (state.gap_table or []):
        if gap.severity != "Critical":
            continue
        cluster_key = (gap.topic or gap.topic_ar or "")[:40]
        if cluster_key in seen_clusters:
            continue

        rec_text = gap.recommendation_ar or gap.recommendation or ""

        # DEDUP: Skip if semantically similar to existing row
        is_duplicate = any(
            _are_semantically_similar(rec_text, seen_rec, threshold=0.5)
            for seen_rec in seen_recommendations
        )
        if is_duplicate:
            continue

        seen_clusters.add(cluster_key)
        seen_recommendations.append(rec_text)
        source_counts["critical_gaps"] += 1

        # Horizon assignment for gaps:
        # - Proactive notification + guidebook missing → "🚨 فوري" (quick notification config)
        # - Proactive notification + guidebook exists → "📅 قصير المدى" (needs minor guidebook updates)
        # - Not proactive + guidebook missing → "📅 قصير المدى" (FAQ/content publishing)
        # - Not proactive + guidebook exists → "🔧 متوسط المدى" (complex guidebook updates)
        if gap.proactive_notification_opportunity and gap.guidebook_status == "Missing":
            horizon = "🚨 فوري"
            effort = "منخفض"
        elif gap.proactive_notification_opportunity or gap.guidebook_status == "Missing":
            horizon = "📅 قصير المدى"
            effort = "متوسط"
        else:
            horizon = "🔧 متوسط المدى"
            effort = "متوسط"

        source = _source_for_gap(gap)
        rows.append({
            "row_id":                 f"gap_{cluster_key.replace(' ', '_')}",
            "horizon":                horizon,
            "effort":                 effort,
            "source":                 source,
            "seed_recommendation_ar": rec_text,
            "seed_impact_ar":         f"معالجة {gap.case_count}+ حالة مرتبطة بـ {gap.topic_ar or gap.topic}",
            "case_count":             gap.case_count,
        })

    # ── SOURCE 3: journey_map friction clusters (stage 4) ────────────────────
    # Sort by case_count descending so high-impact frictions come first
    journey_sorted = sorted(
        state.journey_map or [],
        key=lambda j: j.case_count,
        reverse=True
    )
    for friction in journey_sorted:
        cluster_key = (friction.cluster or friction.cluster_ar or "")[:40]
        if cluster_key in seen_clusters:
            continue

        friction_seed = friction.friction_point_ar or friction.friction_point or cluster_key

        # DEDUP: Skip if semantically similar to existing row
        is_duplicate = any(
            _are_semantically_similar(friction_seed, seen_rec, threshold=0.5)
            for seen_rec in seen_recommendations
        )
        if is_duplicate:
            continue

        seen_clusters.add(cluster_key)
        seen_recommendations.append(friction_seed)
        source_counts["journey"] += 1

        root_cause = friction.root_cause_category or "platform_bug"
        horizon = _ROOT_CAUSE_TO_HORIZON.get(root_cause, "📅 قصير المدى")

        # BUG 4 FIX: Adjust horizon based on gap severity to create varied timelines
        # Don't over-upgrade to immediate just because a gap is critical
        matched_gap = None
        for gap in (state.gap_table or []):
            if (friction.cluster or friction.cluster_ar or "")[:20] in (gap.topic or gap.topic_ar or ""):
                matched_gap = gap
                break

        if matched_gap:
            # For Critical + proactive_notification → can stay immediate
            if matched_gap.severity == "Critical" and matched_gap.proactive_notification_opportunity:
                horizon = "🚨 فوري"
            # For Critical but no proactive → escalate to short-term (requires work)
            elif matched_gap.severity == "Critical":
                horizon = "📅 قصير المدى"
            # For Medium severity → medium-term (integration needed)
            elif matched_gap.severity == "Medium":
                if horizon not in ("🔧 متوسط المدى", "🚀 طويل المدى"):
                    horizon = "🔧 متوسط المدى"

        effort = _effort_for_root_cause(root_cause, friction.case_count)

        # Corroborate with guidebook if a matching gap exists
        source = _SOURCE_ANALYSIS_ONLY
        for gap in (state.gap_table or []):
            if (friction.cluster or friction.cluster_ar or "")[:20] in (gap.topic or gap.topic_ar or ""):
                source = _source_for_gap(gap)
                break

        rows.append({
            "row_id":                 f"journey_{cluster_key.replace(' ', '_')}",
            "horizon":                horizon,
            "effort":                 effort,
            "source":                 source,
            "seed_recommendation_ar": friction_seed,
            "seed_impact_ar":         f"تقليص {friction.case_count}+ حالة — {friction_seed[:60]}",
            "case_count":             friction.case_count,
        })

    # ── SOURCE 4: AI use cases — medium/long term rows ────────────────────────
    ai_section = (state.report_sections_ar or {}).get("ai_use_cases", {})
    ai_raw = ai_section.get("raw_data", {})
    ai_rows_data = ai_raw.get("use_cases_table", [])

    for ai_row in ai_rows_data:
        tool_id     = ai_row.get("tool_id", "")
        tool_name   = ai_row.get("الأداة", "")
        impact      = ai_row.get("الأثر المتوقع", "")
        complexity  = ai_row.get("تقييم التنفيذ", "")

        if not tool_id or not tool_name:
            continue
        if tool_id in seen_clusters:
            continue
        seen_clusters.add(tool_id)
        source_counts["ai_use_cases"] += 1

        # Derive effort level from complexity text
        if "مرتفع" in complexity:
            effort = "مرتفع"
        elif "منخفض" in complexity:
            effort = "منخفض"
        else:
            effort = "متوسط"

        horizon = _EFFORT_TO_HORIZON.get(effort, "🔧 متوسط المدى")

        rows.append({
            "row_id":                 f"ai_{tool_id}",
            "horizon":                horizon,
            "effort":                 effort,
            "source":                 _SOURCE_BOTH,   # AI tools draw on both analyses
            "seed_recommendation_ar": tool_name,
            "seed_impact_ar":         impact,
            "case_count":             0,              # AI tools have estimated, not exact, counts
        })

    # ── Sort, reserve AI slots, and cap ────────────────────────────────────────
    # BUG 2 FIX: Reserve guaranteed slots for AI rows before the cap.
    # Without this, immediate/short-term rows from sources 1-3 dominate and push
    # out the medium/long-term AI rows. Split, sort independently, combine, then resort.

    ai_rows_built = [r for r in rows if r["row_id"].startswith("ai_")]
    other_rows = [r for r in rows if not r["row_id"].startswith("ai_")]

    # Sort each group independently
    other_rows.sort(key=lambda r: (_horizon_rank(r["horizon"]), -r["case_count"]))
    ai_rows_built.sort(key=lambda r: (_horizon_rank(r["horizon"]), -r["case_count"]))

    # Reserve 2 slots for AI rows (medium/long term), fill remaining 6 from other sources
    final_rows = other_rows[:6] + ai_rows_built[:2]

    # Re-sort combined list by horizon for display order
    final_rows.sort(key=lambda r: (_horizon_rank(r["horizon"]), -r["case_count"]))

    # Assign sequential row numbers
    for i, row in enumerate(final_rows, 1):
        row["row_number"] = str(i)

    # Diagnostics: log source distribution
    print(
        f"[ImprovementRoadmap._build_roadmap_rows] Source distribution:\n"
        f"  Notification opportunities: {source_counts['notification']}\n"
        f"  Critical gaps: {source_counts['critical_gaps']}\n"
        f"  Journey friction clusters: {source_counts['journey']}\n"
        f"  AI use cases: {source_counts['ai_use_cases']}\n"
        f"  Total rows built: {len(rows)} (before slot reservation)\n"
        f"  AI rows: {len(ai_rows_built)}, Other rows: {len(other_rows)}\n"
        f"  Final rows: {len(final_rows)} (6 other + up to 2 AI)\n"
        f"  Horizon breakdown:"
    )
    for horizon in _HORIZON_ORDER:
        count = sum(1 for r in final_rows if r["horizon"] == horizon)
        if count > 0:
            print(f"    {horizon}: {count}")

    return final_rows


# ──────────────────────────────────────────────────────────────────────────────
# Public helpers (imported by stage6_json_report.py)
# ──────────────────────────────────────────────────────────────────────────────

def _build_display_roadmap_rows(raw_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Convert LLM raw_data['roadmap_table'] into display-ready dicts for the JSON report.

    Strips internal keys (row_id) and ensures column order matches the sample:
      الأفق الزمني | # | التوصية | المصدر | الأثر المتوقع | الجهد
    """
    display = []
    for row in raw_data.get("roadmap_table", []):
        display.append({
            "الأفق الزمني": row.get("الأفق الزمني", ""),
            "#":            row.get("#", ""),
            "التوصية":      row.get("التوصية", ""),
            "المصدر":       row.get("المصدر", ""),
            "الأثر المتوقع": row.get("الأثر المتوقع", ""),
            "الجهد":        row.get("الجهد", ""),
        })
    return display


# ──────────────────────────────────────────────────────────────────────────────
# Main section generator
# ──────────────────────────────────────────────────────────────────────────────

def generate_improvement_roadmap_section(
    state: PipelineState,
    api_key: str,
) -> Dict[str, Any]:
    """
    Generate Section 8 — Improvement Roadmap (خارطة الطريق التحسينية).

    Pre-computes all structural/locked columns from prior stages (no re-computation),
    then asks the LLM to write:
      • section_body       — 2-sentence Arabic intro tying the 4 analyses together
      • التوصية            — specific, actionable Arabic recommendation per row (≤ 35 words)
      • الأثر المتوقع      — quantified expected impact grounded in locked case counts (≤ 25 words)

    LOCKED columns (copied verbatim, LLM must not alter):
      الأفق الزمني, #, المصدر, الجهد

    Raises on any failure — no fallbacks, no None returns.

    Args:
        state:   Pipeline state (stages 1–7 must be complete)
        api_key: Anthropic API key

    Returns:
        Dict with keys: section, section_body, roadmap_table
    """
    # ── Guards: required upstream outputs ─────────────────────────────────────
    if not state.journey_map:
        raise RuntimeError(
            "[ImprovementRoadmap] state.journey_map is empty — "
            "Stage 4 (stage4_analysis) must complete before this section."
        )
    if not state.gap_table:
        raise RuntimeError(
            "[ImprovementRoadmap] state.gap_table is empty — "
            "Stage 5 (stage5_gap) must complete before this section."
        )
    if not state.month_year:
        raise RuntimeError(
            "[ImprovementRoadmap] state.month_year is not set — Stage 3 must complete first."
        )

    total_cases = len(state.all_classified) or state.total_cases
    if not total_cases:
        raise RuntimeError(
            "[ImprovementRoadmap] total_cases is 0 — no classified cases in state."
        )

    # ── Pre-compute locked row data ───────────────────────────────────────────
    date_range  = convert_month_year_to_arabic(state.month_year)
    roadmap_rows = _build_roadmap_rows(state)

    if not roadmap_rows:
        raise RuntimeError(
            "[ImprovementRoadmap] No roadmap rows could be built from journey_map, "
            "gap_table, notification_opportunities, or ai_use_cases. "
            "Ensure Stage 4, 5, and 7 completed successfully."
        )

    # Summarise horizon distribution for prompt context
    horizon_counts: Dict[str, int] = {}
    for row in roadmap_rows:
        h = row["horizon"]
        horizon_counts[h] = horizon_counts.get(h, 0) + 1

    horizon_summary = "  ".join(
        f"{h}: {c} بند" for h, c in
        sorted(horizon_counts.items(), key=lambda x: _horizon_rank(x[0]))
    )

    # Build locked columns block for prompt (what LLM cannot change)
    locked_rows_for_prompt = [
        {
            "row_id":           r["row_id"],
            "row_number":       r["row_number"],
            "الأفق الزمني":     r["horizon"],
            "#":                r["row_number"],
            "المصدر":           r["source"],
            "الجهد":            r["effort"],
            # Seeds for LLM prose — NOT locked, but grounded
            "seed_recommendation_ar": r["seed_recommendation_ar"],
            "seed_impact_ar":         r["seed_impact_ar"],
            "case_count":             r["case_count"],
        }
        for r in roadmap_rows
    ]

    # ── Prompt ────────────────────────────────────────────────────────────────
    prompt = (
        'You are writing Section 8 of a formal Arabic government report on customer inquiry\n'
        'analysis for Fujairah Police. The section title is:\n'
        '"ثامناً: خارطة الطريق التحسينية المقترحة"\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'INPUTS — use ONLY these numbers, never invent figures\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'total_cases:    {total_cases}\n'
        f'date_range:     "{date_range}"\n'
        f'row_count:      {len(roadmap_rows)}  (number of rows in roadmap table)\n'
        f'horizon_breakdown: {horizon_summary}\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'LOCKED COLUMNS — copy these VERBATIM into roadmap_table.\n'
        'Do NOT rephrase or alter الأفق الزمني, #, المصدر, or الجهد.\n'
        'seed_recommendation_ar and seed_impact_ar are SEEDS — expand them into\n'
        'full Arabic prose for التوصية and الأثر المتوقع respectively.\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'{json.dumps(locked_rows_for_prompt, ensure_ascii=False, indent=2)}\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'YOUR TASK — write ONLY the items listed below\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '\n'
        'A. section_body — 2 sentences, formal Arabic\n'
        '   - State that this roadmap consolidates the four prior analyses into a\n'
        f'     prioritised improvement plan grounded in {date_range} data.\n'
        f'   - Mention that all {len(roadmap_rows)} items are derived from the data\n'
        '     (no generic recommendations) and are ordered by impact and ease of execution.\n'
        '   - Open with: "تجمع هذه الخارطة توصيات التحليلات الأربعة في منظومة أولويات متدرجة"\n'
        '   - Use ONLY numbers from INPUTS above.\n'
        '\n'
        'B. "التوصية" for EVERY row in roadmap_table (row_id order must match locked rows)\n'
        '   - Expand seed_recommendation_ar into a specific, actionable Arabic recommendation.\n'
        '   - Must answer: WHAT to build/activate/publish, WHERE (in-app / SMS / portal),\n'
        '     and HOW (the concrete mechanism).\n'
        '   - Max 35 words. Arabic only (except: MOI, SMS, UAE PASS, CRM, OTP, IVR, OCR, RTA).\n'
        '   - Must be distinct for each row — no repetition across rows.\n'
        '\n'
        'C. "الأثر المتوقع" for EVERY row in roadmap_table\n'
        '   - Ground every impact claim in the case_count from locked rows.\n'
        '   - If case_count > 0: start with "إلغاء/تقليص/تحويل [N]+ حالة"\n'
        '   - If case_count = 0 (AI tools): describe the structural benefit without a count.\n'
        '   - Max 25 words. Arabic only.\n'
        '   - Do NOT repeat التوصية wording — الأثر المتوقع states the measurable OUTCOME.\n'
        '\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'OUTPUT FORMAT — respond with ONLY valid JSON, no markdown fences\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '{\n'
        '  "section": "improvement_roadmap",\n'
        '  "section_body": "...",\n'
        '  "roadmap_table": [\n'
        '    {\n'
        '      "row_id": "<copy from locked rows>",\n'
        '      "الأفق الزمني": "<LOCKED — copy verbatim>",\n'
        '      "#": "<LOCKED — copy verbatim>",\n'
        '      "التوصية": "<YOUR TEXT — ≤35 words>",\n'
        '      "المصدر": "<LOCKED — copy verbatim>",\n'
        '      "الأثر المتوقع": "<YOUR TEXT — ≤25 words, grounded in case_count>",\n'
        '      "الجهد": "<LOCKED — copy verbatim>"\n'
        '    }\n'
        '  ]\n'
        '}\n'
    )

    # ── LLM call ──────────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=(
            "You are a government report writer specialising in formal Arabic public-sector analysis. "
            "Write clear, concise, data-grounded Arabic. "
            "Never invent numbers — use only the figures provided. "
            "Always copy LOCKED columns verbatim. "
            "Return ONLY valid JSON with no markdown fences, no preamble, no postamble."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    # ── Parse LLM response ────────────────────────────────────────────────────
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text += block.text

    if not response_text.strip():
        raise RuntimeError(
            "[ImprovementRoadmap] LLM returned an empty response."
        )

    raw_data = parse_json_response(response_text, tag="ImprovementRoadmap")
    if not raw_data:
        raise RuntimeError(
            f"[ImprovementRoadmap] Could not parse JSON from LLM response.\n"
            f"First 500 chars: {response_text[:500]}"
        )

    # ── Validate required keys ────────────────────────────────────────────────
    if "section_body" not in raw_data or not raw_data["section_body"].strip():
        raise RuntimeError(
            "[ImprovementRoadmap] LLM response missing 'section_body'."
        )
    if "roadmap_table" not in raw_data or not raw_data["roadmap_table"]:
        raise RuntimeError(
            "[ImprovementRoadmap] LLM response missing or empty 'roadmap_table'."
        )

    # ── Reinjection: enforce locked columns from pre-computed rows ────────────
    # Build lookup from locked rows by row_id
    locked_lookup: Dict[str, Dict[str, Any]] = {r["row_id"]: r for r in roadmap_rows}

    for llm_row in raw_data["roadmap_table"]:
        row_id = llm_row.get("row_id", "")
        locked = locked_lookup.get(row_id)
        if locked:
            # Overwrite locked columns regardless of what LLM produced
            llm_row["الأفق الزمني"] = locked["horizon"]
            llm_row["#"]            = locked["row_number"]
            llm_row["المصدر"]       = locked["source"]
            llm_row["الجهد"]        = locked["effort"]
        # Validate LLM-written prose columns
        if not llm_row.get("التوصية", "").strip():
            raise RuntimeError(
                f"[ImprovementRoadmap] Row '{row_id}' has empty 'التوصية'."
            )
        if not llm_row.get("الأثر المتوقع", "").strip():
            raise RuntimeError(
                f"[ImprovementRoadmap] Row '{row_id}' has empty 'الأثر المتوقع'."
            )

    return raw_data
