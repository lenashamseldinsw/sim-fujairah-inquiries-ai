"""
generate_workload_map_section — stage6_artifacts.py companion (Complaints Version)

See integration notes at bottom of this docstring.

COMPLAINTS VARIANT
──────────────────
Complaints have only 1 top-level type (شكوى), so the structure changes:
- No "distribution_table" for 4 types (inquiry version concept)
- Instead: 4 subsections with pre-computed tables from state
  * 3.1: Complaint sub-categories breakdown (LLM-written intro + table)
  * 3.2: Channel analysis (LLM-written intro + table)
  * 3.3: Resolution analysis (computed from state, NO LLM)
  * 3.4: Department distribution (computed from state, NO LLM)

INTEGRATION
───────────
1. stage6_artifacts.py — _generate_report_sections(), after methodology block:

    from .generate_workload_map_section import generate_workload_map_section

    print("[Report Gen] Generating Workload Map section...")
    workload_map = generate_workload_map_section(state, api_key)
    if workload_map:
        state.report_sections_ar['workload_map'] = {
            'heading': 'ثالثاً: خريطة عبء العمل الحقيقي',
            'raw_data': workload_map,
        }
    else:
        raise RuntimeError("[Report Gen] Workload map generation failed")

2. stage6_json_report.py — JSONReportBuilder:

    a) Paste _digital_readiness_complaint (complaints-specific version),
       _build_channel_rows, _build_resolution_analysis_rows,
       _build_department_distribution_rows, _sub_classification_breakdown
       at module level.

    b) Paste build_workload_map_section as a method on JSONReportBuilder.

    c) In build_report(), add:

        workload_section = self.build_workload_map_section(lang=lang)
        if workload_section:
            sections.append(workload_section)
"""

import json
import re
from typing import Dict, Any, List, Optional
from collections import defaultdict
import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response, extract_methodology_context
from .utils import normalize_arabic


# ==============================================================================
# Module-level helpers
# Paste these at module level in stage6_json_report.py as well.
# ==============================================================================

def _digital_readiness_complaint(complaint_subtype: str) -> str:
    """
    Digital deflection potential label for a complaint sub-type (Arabic).
    Complaints version — maps from complaint sub-categories to transformation readiness.
    """
    mapping = {
        'شكاوى مكررة (مرفوضة)': 'نظام تصفية آلي — لتجنب الازدواجية',
        'شكاوى بلا تصنيف خدمي ("أخرى")': 'إعادة تصنيف ذكي — بتحليل النصوص',
        'شكاوى على الخدمات المرورية': 'بوابة مرورية متكاملة — تقديم وتتبع أونلاين',
        'شكاوى أمنية وجنائية': 'نموذج إبلاغ آمن — مع التشفير والخصوصية',
        'شكاوى شهادات وتصاريح': 'نظام طلبات موحد — متكامل مع قاعدة البيانات',
        'شكاوى خارج الاختصاص والأخرى': 'نموذج تحويل ذكي — مع إعادة التوجيه التلقائية',
    }
    return mapping.get(complaint_subtype, "—")


def _build_channel_rows(
    channel_dist: Dict[str, int],
    total_cases: int,
    official_channels: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    Build channel analysis table rows with descriptions.
    Counts channel usage and provides a description for each channel type.

    Args:
        channel_dist: Distribution of channels from state
        total_cases: Total number of cases
        official_channels: Optional list of official channel names from methodology
    """
    # Use normalize_arabic() so matches don't fail because of hamza variants
    # (إلكتروني vs الكترونى) or ى vs ي. The raw data in this dataset uses
    # "موقع الكترونى" — without normalization, substring matches against "إلكترون" fail.
    digital_keywords_normalized = {normalize_arabic(k) for k in
                                   ("تطبيق", "موقع", "إلكتروني", "ويتس", "بريد إلكتروني", "بوابة إلكترونية")}
    if official_channels:
        digital_channels = {ch for ch in official_channels
                            if any(kw in normalize_arabic(ch) for kw in digital_keywords_normalized)}
    else:
        digital_channels = {ch for ch in channel_dist.keys()
                            if any(kw in normalize_arabic(ch) for kw in digital_keywords_normalized)}

    # Channel description mapping
    channel_descriptions = {
        "تطبيق": "تقديم الشكاوى من خلال التطبيق الرسمي — طريقة موثقة وسريعة",
        "بريد إلكتروني": "تقديم الشكاوى عبر البريد الإلكتروني — توثيق رسمي للمخاطبات",
        "بوابة إلكترونية": "تقديم الشكاوى عبر البوابة الإلكترونية — وصول مباشر للنظام",
        "موقع": "تقديم الشكاوى عبر الموقع الإلكتروني — واجهة سهلة الاستخدام",
        "ويتس آب": "تقديم الشكاوى عبر تطبيق المراسلة — تواصل فوري وسهل",
        "هاتف": "تقديم الشكاوى عبر المكالمة الهاتفية — تواصل مباشر مع الموظفين",
        "شخصي": "تقديم الشكاوى بشكل مباشر في المكاتب — حضور شخصي للتقرير",
    }

    rows = []
    for channel, count in sorted(channel_dist.items(), key=lambda x: x[1], reverse=True):
        if not channel or channel.strip() == "":
            continue
        pct = f"{count / total_cases * 100:.1f}%" if total_cases else "0%"
        # Use predefined description or generate generic one
        description = channel_descriptions.get(
            channel.strip(),
            f"تقديم الشكاوى عبر {channel} — إحدى قنوات التواصل المتاحة"
        )
        rows.append({
            "قناة التواصل": channel,
            "العدد": str(count),
            "النسبة": pct,
            "الوصف": description,
        })
    return rows


def _build_resolution_analysis_rows(
    all_classified: List,
    total_cases: int,
) -> List[Dict[str, str]]:
    """
    Build resolution analysis table from real fields on each CaseRow.

    Our dataset has no closure-status column. We bucket on:
      - date_closed presence    → "مغلقة" vs "قيد المعالجة"
      - sub_classification      → officially-rejected count (duplicates)
      - "مكرر" in resolution_response → data-quality observation

    Row schema: نوع الإغلاق | العدد | النسبة | الوصف
    """
    closed_count = 0
    open_count = 0
    rejected_count = 0
    mukarrar_mentions = 0

    for case in (all_classified or []):
        # Closure status from date_closed
        date_closed = getattr(case, 'date_closed', None)
        if date_closed and str(date_closed).strip():
            closed_count += 1
        else:
            open_count += 1

        # Officially rejected = classified as duplicate
        sub = getattr(case, 'sub_classification', None) or ''
        if 'مكررة' in sub or 'مرفوضة' in sub:
            rejected_count += 1

        # "مكرر" in resolution text — for data-quality observation only
        resp = getattr(case, 'resolution_response', None) or ''
        if 'مكرر' in resp:
            mukarrar_mentions += 1

    def pct(n: int) -> str:
        return f"{n / total_cases * 100:.1f}%" if total_cases else "0%"

    rows = []
    if closed_count:
        rows.append({
            "نوع الإغلاق": "مغلقة (لها تاريخ إغلاق)",
            "العدد": str(closed_count),
            "النسبة": pct(closed_count),
            "الوصف": "الشكاوى التي تم إغلاقها وتسجيل تاريخ إغلاق لها في النظام",
        })
    if open_count:
        rows.append({
            "نوع الإغلاق": "قيد المعالجة (بدون تاريخ إغلاق)",
            "العدد": str(open_count),
            "النسبة": pct(open_count),
            "الوصف": "الشكاوى التي لا تزال مفتوحة ولم يُسجَّل لها تاريخ إغلاق بعد",
        })
    if rejected_count:
        rows.append({
            "نوع الإغلاق": "مُصنَّفة كمكررة/مرفوضة",
            "العدد": str(rejected_count),
            "النسبة": pct(rejected_count),
            "الوصف": "الشكاوى المُصنَّفة رسمياً كمكررة في حقل نوع_الشكوى",
        })
    # Always include the mukarrar observation row (even if 0) so the paragraph
    # builder can read it via row_map without a KeyError.
    rows.append({
        "نوع الإغلاق": "مكرر (في نص الحل)",
        "العدد": str(mukarrar_mentions),
        "النسبة": pct(mukarrar_mentions),
        "الوصف": "عدد الحالات التي ورد فيها لفظ «مكرر» داخل نص الحل (مؤشر جودة بيانات)",
    })

    return rows


def _build_resolution_paragraph(resolution_rows: list, total_cases: int) -> str:
    """
    One bold paragraph for section 3.3, grounded in fields we actually have:
    closure (from date_closed) + official rejection (from sub_classification)
    + a separate data-quality observation about "مكرر" mentions in resolution text.
    """
    row_map = {r["نوع الإغلاق"]: r for r in resolution_rows}

    closed   = row_map.get("مغلقة (لها تاريخ إغلاق)",          {})
    opened   = row_map.get("قيد المعالجة (بدون تاريخ إغلاق)", {})
    rejected = row_map.get("مُصنَّفة كمكررة/مرفوضة",            {})
    mukarrar = row_map.get("مكرر (في نص الحل)",                {})

    closed_count   = closed.get("العدد",   "0")
    closed_pct     = closed.get("النسبة", "0%")
    open_count     = opened.get("العدد",   "0")
    open_pct       = opened.get("النسبة", "0%")
    rejected_count = rejected.get("العدد", "0")
    rejected_pct   = rejected.get("النسبة", "0%")
    mukarrar_count = mukarrar.get("العدد", "0")

    # Frame "مكرر" mentions as data-quality observation, not as "hidden duplicates"
    # beyond what's classified. In practice these usually overlap with the
    # already-rejected set; the value is signal-redundancy, not hidden volume.
    para = (
        f"أُغلقت {closed_count} شكوى ({closed_pct}) — بتاريخ إغلاق مُسجَّل — "
        f"بينما لا تزال {open_count} شكوى ({open_pct}) قيد المعالجة دون تاريخ إغلاق. "
        f"من إجمالي الحالات، صُنِّفت {rejected_count} حالة ({rejected_pct}) رسمياً "
        f"ضمن فئة «شكاوى مكررة (مرفوضة)». "
        f"كما ورد لفظ «مكرر» داخل نص الحل في {mukarrar_count} حالة، "
        f"وهو مؤشر جودة بيانات يُؤكد التصنيف الرسمي للتكرار."
    )
    return para


def _build_department_distribution_rows(
    department_dist: Dict[str, int],
    total_cases: int,
) -> List[Dict[str, str]]:
    """
    Build department distribution table from state.department_distribution.

    Row schema: الإدارة العامة | العدد | النسبة | الدلالة
    """
    rows = []
    for dept, count in sorted(department_dist.items(), key=lambda x: x[1], reverse=True):
        if not dept or dept.strip() == "":
            continue
        pct = f"{count / total_cases * 100:.1f}%" if total_cases else "0%"

        # Significance note: high concentration in a single department
        significance = ""
        if count / total_cases > 0.3:
            significance = "تركيز عالي — يتطلب انتباهاً خاصاً"
        elif count / total_cases > 0.1:
            significance = "حصة ملحوظة"
        else:
            significance = "توزيع طبيعي"

        rows.append({
            "الإدارة العامة": dept,
            "العدد": str(count),
            "النسبة": pct,
            "الدلالة": significance,
        })
    return rows


def _sub_classification_breakdown(
    state: PipelineState,
    top_level_filter: str,
) -> List[Dict[str, str]]:
    """
    Count cases per sub_classification within a top_level type, sorted descending.
    Uses state.all_classified — same source as per-type analysis.
    Returns rows without الوصف; the LLM adds that field.

    For complaints pipeline, top_level_filter is always "شكوى".
    """
    counts: Dict[str, int] = defaultdict(int)
    for case in state.all_classified:
        if case.actual_contact_type == top_level_filter:
            sub = case.sub_classification or "غير محدد"
            counts[sub] += 1

    type_total = sum(counts.values()) or 1
    return [
        {
            "الفئة الفرعية": sub,
            "العدد": str(cnt),
            "النسبة": f"{cnt / type_total * 100:.1f}%",
        }
        for sub, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)
    ]


# ==============================================================================
# Prompt + API call  —  goes in stage6_artifacts.py
# ==============================================================================

def generate_workload_map_section(state: PipelineState, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Generate Section 3 (Workload Map) for complaints pipeline via Claude API.

    Complaints variant:
    - Pre-computes 4 subsections (3.1 complaint subs, 3.2 channels, 3.3 resolution, 3.4 departments)
    - LLM writes only prose intros for 3.1 and 3.2
    - 3.3 and 3.4 tables are built directly from state, no LLM writes them

    All numeric data is pre-computed from state before the call.
    The LLM writes ONLY prose fields and the 'الوصف' column entries.
    Pre-computed tables are safety-reinjected after parsing.
    """
    try:
        all_classified = state.all_classified or []
        total_cases = state.total_cases if state.total_cases > 0 else len(all_classified)
        date_range = convert_month_year_to_arabic(state.month_year) or "Q1 2026"

        # Extract official channels from methodology if present
        official_channels = None
        if state.complaints_methodology:
            methodology_context = extract_methodology_context(
                state.complaints_methodology,
                ["5_procedures.5_1_receiving_channels"]
            )
            official_channels = methodology_context.get("5_1_receiving_channels", {}).get("channels")
            if official_channels:
                print(f"[WorkloadMap] Using {len(official_channels)} official channels from methodology")

        # Build all four subsection tables upfront
        complaint_subs = _sub_classification_breakdown(state, "شكوى")
        channel_dist = state.channel_distribution or {}
        channel_rows = _build_channel_rows(channel_dist, total_cases, official_channels)

        # Pass the full CaseRow objects — we now bucket on date_closed and
        # sub_classification, not just on resolution-text matching.
        resolution_rows = _build_resolution_analysis_rows(all_classified, total_cases)

        # Department distribution
        dept_dist = state.department_distribution or {}
        department_rows = _build_department_distribution_rows(dept_dist, total_cases)

        # Use the digital-channel rate pre-computed in stage1_validator (the canonical source).
        # The previous local recomputation matched against "إلكترون" (with hamza), but the
        # raw data uses "الكترونى" (no hamza, ى not ي) — so the local match was always 0%.
        digital_channel_rate = state.digital_channel_rate

        # "Rejection" in this dataset = officially classified as duplicate/rejected.
        # The previous version searched resolution_response for "طلب مرفوض" which is
        # never present (الحل is free-text narrative, not a status code) → always 0%.
        rejection_count = len([
            c for c in all_classified
            if 'مكررة' in (getattr(c, 'sub_classification', '') or '')
            or 'مرفوضة' in (getattr(c, 'sub_classification', '') or '')
        ])
        rejection_rate = rejection_count / total_cases * 100 if total_cases else 0

        # Serialize pre-computed tables
        complaint_subs_json = json.dumps(complaint_subs, ensure_ascii=False, indent=2)
        channel_rows_json = json.dumps(channel_rows, ensure_ascii=False, indent=2)
        resolution_rows_json = json.dumps(resolution_rows, ensure_ascii=False, indent=2)
        department_rows_json = json.dumps(department_rows, ensure_ascii=False, indent=2)

        prompt = (
            'You are writing Section 3 of a formal Arabic government report on complaint analysis\n'
            'for Fujairah Police. The section title is "ثالثاً: خريطة عبء العمل الحقيقي".\n'
            '\n'
            'NOTE: This is the complaints pipeline variant. All cases are classified as شكوى (complaint).\n'
            'There are 4 subsections (3.1-3.4), not 3 tables.\n'
            '\n'
            'INPUTS — use ONLY these numbers, never invent figures\n'
            f'total_cases: {total_cases}\n'
            f'date_range: "{date_range}"\n'
            f'complaint_total: {total_cases}\n'
            f'digital_channel_rate: "{digital_channel_rate:.1f}%"\n'
            f'rejection_rate: "{rejection_rate:.1f}%"\n'
            '\n'
            f'pre_computed_complaint_sub_classifications ({len(complaint_subs)} complaint types, sorted descending by count):\n'
            f'{complaint_subs_json}\n'
            '\n'
            'CRITICAL — TASK 5 INSTRUCTION:\n'
            '  Do NOT invent rows for sub-classifications with zero cases.\n'
            '  Do NOT add categories not in the pre_computed list above.\n'
            '  Your complaints_table MUST contain ONLY the sub-categories shown above.\n'
            '  Each row must come directly from the pre_computed data — do not create new rows.\n'
            '\n'
            'pre_computed_channel_distribution (all channels, sorted descending by count):\n'
            f'{channel_rows_json}\n'
            '\n'
            'pre_computed_resolution_analysis (status breakdown — copy verbatim):\n'
            f'{resolution_rows_json}\n'
            '\n'
            'pre_computed_department_distribution (admin departments — copy verbatim):\n'
            f'{department_rows_json}\n'
            '\n'
            'YOUR TASK — write ONLY the four prose/table items below; tables are pre-computed\n'
            '\n'
            'A. intro_paragraph (subsection 3.1 lead-in)\n'
            '2-3 sentences, formal Arabic. Must:\n'
            f'  - Open: "تحليل {total_cases} شكوى في {date_range}..."\n'
            '  - Identify complaint sub-categories as the core of workload distribution.\n'
            '  - Note the concentration in specific complaint types (from the pre_computed table).\n'
            '\n'
            'B. channel_insight (subsection 3.2 lead-in) — KEY: use this exact field name\n'
            '1-2 sentences, formal Arabic. Must:\n'
            f'  - Reference that {digital_channel_rate:.1f}% of complaints arrived via digital channels (تطبيق الهاتف and موقع إلكتروني).\n'
            '  - Reference individual percentages ONLY from the pre_computed_channel_distribution table below.\n'
            '  - Do NOT invent percentages. Do NOT contradict the {digital_channel_rate:.1f}% figure.\n'
            '  - The detailed breakdown table shows all channels — reference those exact numbers only.\n'
            '  - End with a colon (":") — the channel distribution table follows immediately.\n'
            '\n'
            'C. resolution_intro (subsection 3.3 lead-in) — KEY: use this exact field name\n'
            '1-2 sentences, formal Arabic describing how complaints are resolved:\n'
            f'  - Reference the resolution status distribution from pre_computed_resolution_analysis.\n'
            '  - Comment on approval vs. rejection patterns.\n'
            '  - End with a period — the resolution analysis paragraph follows.\n'
            '\n'
            'D. "الوصف" column for complaint sub-classifications ONLY\n'
            'For EACH row in pre_computed_complaint_sub_classifications, add a "الوصف" field:\n'
            '  1 concise Arabic sentence (20–35 words) describing what this complaint type represents\n'
            '  from the customer\'s perspective. Write from the citizen/driver perspective.\n'
            '  What issue did they experience? What triggered them to file this complaint?\n'
            '  Examples of the required style:\n'
            '    WRONG: "شكاوى تتعلق بالمخالفات المرورية"\n'
            '    RIGHT: "مواطنون وسائقون يعترضون على مخالفات مرورية يرون أنها غير مستحقة أو صدرت بالخطأ"\n'
            '  Do NOT add or change any numbers.\n'
            'For complaints_table: rename "النسبة" -> "النسبة من الشكاوى" and add "الوصف".\n'
            'NOTE: قابلية التحويل الرقمي will be added automatically after parsing.\n'
            '\n'
            'OUTPUT — single JSON object, no markdown, no extra keys\n'
            '\n'
            '{\n'
            '  "section": "workload_map",\n'
            '  "intro_paragraph": "...",\n'
            '  "channel_insight": "...",\n'
            '  "resolution_intro": "...",\n'
            '  "complaints_table": [\n'
            '    {"نوع الشكوى": "...", "العدد": "...", "النسبة": "...", "الوصف": "..."}\n'
            '  ]\n'
            '}\n'
            '\n'
            'RULES — CRITICAL (must be followed exactly):\n'
            '- resolution_table and department_table: pre-computed, will be injected after parsing.\n'
            '  Do NOT include them in your JSON output.\n'
            '- CRITICAL: complaints_table MUST use EXACTLY these column names:\n'
            '  * "نوع الشكوى" (NOT "الفئة الفرعية")\n'
            '  * "العدد"\n'
            '  * "النسبة" (NOT "النسبة من الشكاوى")\n'
            '  * "الوصف"\n'
            '  These exact names are required. Any variation will cause the report to fail.\n'
            '- CRITICAL — MANDATORY: complaints_table MUST include EVERY row from the\n'
            '  pre_computed_complaint_sub_classifications list above — ALL of them, without exception.\n'
            '  This includes rows with count = 1, 2, or 3 (low-count categories) and all special categories\n'
            '  like شكاوى بلا تصنيف خدمي, شكاوى خارج الاختصاص, etc.\n'
            '  If you omit even ONE category, the validation will FAIL.\n'
            '  REQUIRED: Copy the "الفئة الفرعية" value from input as "نوع الشكوى" in your output.\n'
            '  Then add "العدد", "النسبة", and "الوصف" for that row.\n'
            '  Sort your output rows by count descending (same order as the input).\n'
            '- All prose keys must be Arabic only.\n'
            '- Every number in prose must match a pre-computed input above.\n'
            '- No markdown, no extra keys, no extra nesting.\n'
            '- CRITICAL: Do NOT use double-quote characters (") inside any string value. '
            'Use angle brackets « » instead of double quotes when citing names.\n'
        )

        client = anthropic.Anthropic(api_key=api_key)
        print(
            f"[WorkloadMap] Calling API — total_cases={total_cases}, "
            f"complaint_subs={len(complaint_subs)}, "
            f"channels={len(channel_rows)}, "
            f"digital_rate={digital_channel_rate:.1f}%"
        )

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )

        result = parse_json_response(message.content[0].text, tag="WorkloadMap")
        if result is None:
            print("[WorkloadMap] ERROR: Could not parse JSON from API response")
            return None

        # Safety-reinject: these tables are always exact state data
        # Resolution rendered as bold paragraph (spec 3.3), not a table.
        # The raw rows are kept for any downstream consumers that need the numbers.
        result["resolution_paragraph"] = _build_resolution_paragraph(resolution_rows, total_cases)
        result["resolution_table"] = resolution_rows  # kept for audit/downstream use only
        result["department_table"] = department_rows
        result["channel_table"] = channel_rows

        # STRICT VALIDATION: Verify complaints_table has correct structure and all required rows
        complaints_table = result.get("complaints_table", [])

        if not complaints_table:
            raise RuntimeError(
                "[WorkloadMap] VALIDATION FAILED: complaints_table is missing or empty in LLM output. "
                "LLM must return a non-empty complaints_table with all 6 complaint sub-categories."
            )

        # Check column names are exactly as required
        required_columns = {"نوع الشكوى", "العدد", "النسبة", "الوصف"}
        for idx, row in enumerate(complaints_table):
            row_keys = set(row.keys())
            if not required_columns.issubset(row_keys):
                missing = required_columns - row_keys
                extra = row_keys - required_columns
                raise RuntimeError(
                    f"[WorkloadMap] VALIDATION FAILED: Row {idx} has wrong column names. "
                    f"Missing: {missing}. "
                    f"Extra/wrong: {extra}. "
                    f"Required exactly: {required_columns}. "
                    f"Row keys: {row_keys}"
                )

        # Check all sub-classifications are present
        # complaint_subs uses 'الفئة الفرعية'; complaints_table (from LLM) uses 'نوع الشكوى'
        expected_subs = {row.get('الفئة الفرعية', '') for row in complaint_subs}
        returned_subs = {row.get('نوع الشكوى', '') for row in complaints_table}
        missing_subs = expected_subs - returned_subs

        if missing_subs:
            print(
                f"[WorkloadMap] WARNING: LLM omitted {len(missing_subs)} complaint sub-categories: {missing_subs}. "
                f"Injecting missing rows from pre-computed data..."
            )

            # Inject missing rows from complaint_subs (pre-computed ground truth)
            injected_count = 0
            for missing_sub in missing_subs:
                source_row = next(
                    (row for row in complaint_subs if row.get('الفئة الفرعية') == missing_sub),
                    None
                )
                if source_row:
                    # TASK 1 FIX: Skip injection if العدد == 0 (no cases in dataset for this sub-classification)
                    count_str = source_row.get('العدد', '0')
                    try:
                        count_val = int(count_str) if count_str else 0
                    except (ValueError, TypeError):
                        count_val = 0

                    if count_val == 0:
                        print(f"[WorkloadMap] SKIPPED injection for '{missing_sub}' (no cases in data, العدد = 0)")
                        continue

                    # Build row with LLM-style column names, using ground truth data
                    # Use _digital_readiness_complaint for proper description (no [Injected] marker)
                    description = _digital_readiness_complaint(missing_sub)
                    injected_row = {
                        "نوع الشكوى": missing_sub,
                        "العدد": source_row.get('العدد', ''),
                        "النسبة": source_row.get('النسبة', ''),
                        "الوصف": description
                    }
                    complaints_table.append(injected_row)
                    injected_count += 1
                    print(f"[WorkloadMap] Injected missing row: {missing_sub} (العدد={count_val})")

            # Re-sort by العدد descending (numeric sort)
            try:
                complaints_table = sorted(
                    complaints_table,
                    key=lambda x: int(x.get('العدد', '0')),
                    reverse=True
                )
                result["complaints_table"] = complaints_table
            except (ValueError, TypeError):
                print("[WorkloadMap] WARNING: Could not re-sort complaints_table by العدد")
                result["complaints_table"] = complaints_table

            # TASK 1 FIX: Assert case count consistency (never exceed 100%)
            try:
                table_total = sum(int(row.get('العدد', '0')) for row in complaints_table)
                if table_total != total_cases:
                    raise RuntimeError(
                        f"[WorkloadMap] VALIDATION FAILED: complaint sub-classification table total {table_total} "
                        f"does not match total_cases {total_cases}. "
                        f"This indicates injected rows with incorrect counts or missing data reconciliation."
                    )
            except (ValueError, TypeError) as e:
                print(f"[WorkloadMap] WARNING: Could not validate case count totals: {e}")

            # Verify again
            returned_subs = {row.get('نوع الشكوى', '') for row in complaints_table}
            still_missing = expected_subs - returned_subs
            if still_missing:
                raise RuntimeError(
                    f"[WorkloadMap] VALIDATION FAILED: After injection, still missing sub-classifications: {still_missing}. "
                    f"Could not recover from LLM omission."
                )

        # Add digital transformation capability to each row
        for row in complaints_table:
            complaint_type = row.get("نوع الشكوى", "أخرى")
            row["قابلية التحويل الرقمي"] = _digital_readiness_complaint(complaint_type)

        result["complaints_table"] = complaints_table

        print(
            f"[WorkloadMap] OK — "
            f"complaints={len(result.get('complaints_table', []))} rows, "
            f"channels={len(result.get('channel_table', []))} rows, "
            f"resolution={len(result.get('resolution_table', []))} rows, "
            f"departments={len(result.get('department_table', []))} rows"
        )
        return result

    except Exception as e:
        print(f"[WorkloadMap] ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise  # Don't silently return None — let caller see the error
