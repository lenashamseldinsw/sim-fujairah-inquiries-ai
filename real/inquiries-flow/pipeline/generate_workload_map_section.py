"""
generate_workload_map_section — stage6_artifacts.py companion
See integration notes at bottom of this docstring.

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

    a) Paste _delta_label, _digital_readiness, _build_rich_distribution_rows,
       _build_reclassification_samples, _sub_classification_breakdown at module level.

    b) Paste build_workload_map_section as a method on JSONReportBuilder.

    c) In build_report(), REPLACE build_classification_analysis_section():

        # REMOVE:
        sections.append(self.build_classification_analysis_section())

        # ADD:
        workload_section = self.build_workload_map_section(lang=lang)
        if workload_section:
            sections.append(workload_section)

    d) Optionally upgrade _build_distribution_table() to delegate to
       _build_rich_distribution_rows() for consistency in any legacy calls.
"""

import json
import re
from typing import Dict, Any, List, Optional
from collections import defaultdict
import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response


# ==============================================================================
# Module-level helpers
# Paste these at module level in stage6_json_report.py as well.
# ==============================================================================

def _delta_label(corrected_count: int, original_count: int) -> str:
    """
    Human-readable classification delta string for the distribution table.
    Replaces the placeholder "تم إعادة تصنيف N حالة" in _build_distribution_table.
    """
    delta = corrected_count - original_count
    if delta == 0:
        return "بلا تغيير"
    if original_count == 0:
        return f"+{corrected_count} (كانت صفراً في الملف الأصلي)"
    sign = "+" if delta > 0 else "−"
    return f"{sign}{abs(delta)} عن الأصلي"


def _digital_readiness(top_level: str) -> str:
    """
    Digital deflection potential label for a top-level contact type (Arabic).
    Replaces the placeholder "مسار رقمي" / "خدمة ذاتية" in _build_distribution_table.
    """
    mapping = {
        "شكوى":      "مسار رقمي مختص — بوابة شكاوى / تتبع بلاغ في التطبيق",
        "طلب":       "يتطلب موظفاً بصلاحية النظام",
        "استفسار":   "تحويل كامل — روبوت محادثة / أسئلة شائعة / IVR / الموقع الإلكتروني",
        "شكر وثناء": "توثيق تلقائي — لا يتطلب إجراءً",
    }
    return mapping.get(top_level, "—")


def _build_rich_distribution_rows(
    corrected_dist: Dict[str, int],
    original_dist: Dict[str, int],
    total_cases: int,
) -> List[Dict[str, str]]:
    """
    Build the 5-column distribution table rows with proper delta strings and
    digital readiness labels. Upgraded replacement for _build_distribution_table()'s
    placeholder values ("تم إعادة تصنيف N حالة" / "مسار رقمي" / "خدمة ذاتية").
    """
    TYPE_ORDER = ["شكوى", "طلب", "استفسار", "شكر وثناء"]
    rows = []
    for t in TYPE_ORDER:
        corrected = corrected_dist.get(t, 0)
        original = original_dist.get(t, 0)
        pct = f"{corrected / total_cases * 100:.1f}%" if total_cases else "0%"
        rows.append({
            "نوع التواصل": t,
            "العدد": str(corrected),
            "النسبة": pct,
            "تغيُّر التصنيف": _delta_label(corrected, original),
            "قابلية التحويل الرقمي": _digital_readiness(t),
        })
    return rows


def _build_reclassification_samples(state: PipelineState, max_samples: int = 5) -> List[Dict[str, str]]:
    """
    Pick up to max_samples cases where original CRM label != corrected label.
    Uses state.all_classified — same source as the Excel 'إعادة التصنيف' sheet.
    Matches the same definition as state.reclassified_count: actual_contact_type != case_type.

    Row schema: رقم الطلب | مسجَّلة كـ | التصنيف الصحيح | الدليل من تفاصيل الطلب
    """
    rows = []
    for case in (state.all_classified or []):
        # ISSUE 2 FIX: Use same definition as reclassified_count: actual_contact_type != case_type
        if case.actual_contact_type == case.case_type:
            continue
        sub_label = (
            f"{case.actual_contact_type} — {case.sub_classification}"
            if case.sub_classification
            else case.actual_contact_type
        )
        excerpt = (case.description or case.case_title or "").strip()
        rows.append({
            "رقم الطلب": case.case_number,
            "مسجَّلة كـ": case.case_type or "استفسار",
            "التصنيف الصحيح": sub_label,
            "الدليل من تفاصيل الطلب": f'"{excerpt}"',
        })
        if len(rows) >= max_samples:
            break
    return rows


def _sub_classification_breakdown(
    state: PipelineState,
    top_level_filter: str,
) -> List[Dict[str, str]]:
    """
    Count cases per sub_classification within a top_level type, sorted descending.
    Uses state.all_classified — same source as the per-type Excel sheets.
    Returns rows without الوصف; the LLM adds that field.
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
    Generate Section 3 via Claude API.

    All numeric data is pre-computed from state before the call.
    The LLM writes ONLY prose fields and the 'الوصف' column entries.
    Pre-computed tables are safety-reinjected after parsing.
    """
    try:
        all_classified = state.all_classified or []
        total_cases = len(all_classified)  # ISSUE 3 FIX: Use len(all_classified), not state.total_cases
        date_range = convert_month_year_to_arabic(state.month_year) or "Q1 2026"
        reclass_count = state.reclassified_count
        reclass_rate = state.reclassification_rate

        # Same counting logic as build_classification_chart() and _populate_summary_sheet()
        corrected_dist: Dict[str, int] = defaultdict(int)
        original_dist: Dict[str, int] = defaultdict(int)
        for case in all_classified:
            corrected_dist[case.actual_contact_type] += 1
            # ISSUE 1 FIX: Filter empty case_type to prevent empty-string bucket
            if case.case_type and case.case_type.strip():
                original_dist[case.case_type] += 1

        dominant_type = max(corrected_dist, key=corrected_dist.get) if corrected_dist else "شكوى"
        dominant_count = corrected_dist.get(dominant_type, 0)
        dominant_pct = dominant_count / total_cases * 100 if total_cases else 0
        # ISSUE 1 FIX: Fallback to "استفسار" if original_dist is empty or has only empty keys
        original_dominant = max(original_dist, key=original_dist.get) if original_dist else "استفسار"
        if not original_dominant or not original_dominant.strip():
            original_dominant = "استفسار"
        original_dominant_n = original_dist.get(original_dominant, 0)

        distribution_rows = _build_rich_distribution_rows(corrected_dist, original_dist, total_cases)
        reclass_samples = _build_reclassification_samples(state, max_samples=5)
        complaint_subs = _sub_classification_breakdown(state, "شكوى")
        request_subs = _sub_classification_breakdown(state, "طلب")
        inquiry_subs = _sub_classification_breakdown(state, "استفسار")

        dist_json = json.dumps(distribution_rows, ensure_ascii=False)
        samples_json = json.dumps(reclass_samples, ensure_ascii=False)
        complaint_subs_json = json.dumps(complaint_subs, ensure_ascii=False, indent=2)
        request_subs_json = json.dumps(request_subs, ensure_ascii=False, indent=2)
        inquiry_subs_json = json.dumps(inquiry_subs, ensure_ascii=False, indent=2)

        prompt = (
            'You are writing Section 3 of a formal Arabic government report on customer inquiry analysis\n'
            'for Fujairah Police. The section title is "ثالثاً: خريطة عبء العمل الحقيقي".\n'
            '\n'
            'INPUTS — use ONLY these numbers, never invent figures\n'
            f'total_cases: {total_cases}\n'
            f'date_range: "{date_range}"\n'
            f'reclassified_count: {reclass_count}\n'
            f'reclassification_rate: "{reclass_rate:.1f}%"\n'
            f'dominant_type: "{dominant_type}"\n'
            f'dominant_count: {dominant_count}\n'
            f'dominant_pct: "{dominant_pct:.1f}%"\n'
            f'original_dominant: "{original_dominant}"\n'
            f'original_dominant_n: {original_dominant_n}\n'
            f'complaint_total: {corrected_dist.get("شكوى", 0)}\n'
            f'request_total: {corrected_dist.get("طلب", 0)}\n'
            f'inquiry_total: {corrected_dist.get("استفسار", 0)}\n'
            '\n'
            'pre_computed_distribution_table (copy verbatim — do NOT change any value):\n'
            f'{dist_json}\n'
            '\n'
            'pre_computed_reclassification_samples (real case data — do NOT alter):\n'
            f'{samples_json}\n'
            '\n'
            'pre_computed_complaint_sub_classifications (sorted descending by count):\n'
            f'{complaint_subs_json}\n'
            '\n'
            'pre_computed_request_sub_classifications:\n'
            f'{request_subs_json}\n'
            '\n'
            'pre_computed_inquiry_sub_classifications:\n'
            f'{inquiry_subs_json}\n'
            '\n'
            'YOUR TASK — write ONLY the four items below; everything else is pre-computed\n'
            '\n'
            'A. intro_paragraph (subsection 3.1)\n'
            '2-3 sentences, formal Arabic. Must:\n'
            f'  - Open: "تحليل {total_cases} حالة مغلقة في {date_range}..."\n'
            '  - Declare precision classification reveals a radically different picture.\n'
            f'  - Final sentence starts "التحوّل الجوهري:" and names dominant_type ({dominant_type}),\n'
            f'    dominant_count ({dominant_count}), dominant_pct ({dominant_pct:.1f}%) — contrasting\n'
            f'    with original_dominant ({original_dominant}, {original_dominant_n} cases) before correction.\n'
            '\n'
            'B. reclassification_insight (subsection 3.2)\n'
            '2-3 sentences, formal Arabic. Must:\n'
            f'  - Open "الاكتشاف الحرج:" — state that {original_dominant_n} of {total_cases} cases\n'
            f'    were originally labelled "{original_dominant}" in CRM.\n'
            f'  - State reclassified_count ({reclass_count}) and reclassification_rate ({reclass_rate:.1f}%).\n'
            '  - Clarify this does NOT indicate human error — CRM label reflects intake channel/intent.\n'
            f'  - Final sentence: "القائمة الكاملة لـ {reclass_count} حالة مع الأدلة متاحة في الملحق الرقمي (ملف Excel المرفق)."\n'
            '\n'
            'C. complaints_intro (lead-in for 3.3 table)\n'
            '1-2 sentences, formal Arabic. Must:\n'
            '  - Identify complaints as the hidden dominant category now revealed.\n'
            '  - Note concentration in the traffic and licensing ecosystem.\n'
            '  - End with a colon (":") — the table follows immediately.\n'
            '\n'
            'D. "الوصف" column for all three breakdown tables\n'
            'For EACH row in the three pre_computed tables, add a "الوصف" field:\n'
            '  1 concise Arabic sentence (20–35 words) describing the SPECIFIC customer\n'
            '  situation that falls under that sub-classification. Write from the\n'
            '  customer\'s perspective, describing what actually happened to them —\n'
            '  NOT a definition of the category. Use concrete operational language:\n'
            '  what the customer experienced, what they reported, what triggered the contact.\n'
            '  Examples of the required style:\n'
            '    WRONG: "حالات يُبدي فيها المتعامل اعتراضه على مخالفة يرى أنها صدرت بصورة غير مستحقة"\n'
            '    RIGHT:  "متعاملون يعترضون على مخالفات مرورية ثبت خطؤها أو أن مركباتهم لم تكن في الإمارة وقت الرصد"\n'
            '  Do NOT add or change any numbers.\n'
            'For complaints_table: rename "النسبة" -> "النسبة من الشكاوى" and add "الوصف".\n'
            'For requests_table / inquiries_table: keep "النسبة" as-is and add "الوصف".\n'
            '\n'
            'OUTPUT — single JSON object, no markdown, no extra keys\n'
            '\n'
            '{\n'
            '  "section": "workload_map",\n'
            '  "intro_paragraph": "...",\n'
            f'  "distribution_table": {dist_json},\n'
            '  "reclassification_insight": "...",\n'
            f'  "reclassification_sample": {samples_json},\n'
            '  "complaints_intro": "...",\n'
            '  "complaints_table": [\n'
            '    {"الفئة الفرعية": "...", "العدد": "...", "النسبة من الشكاوى": "...", "الوصف": "..."}\n'
            '  ],\n'
            '  "requests_table":  [{"الفئة الفرعية": "...", "العدد": "...", "النسبة": "...", "الوصف": "..."}],\n'
            '  "inquiries_table": [{"الفئة الفرعية": "...", "العدد": "...", "النسبة": "...", "الوصف": "..."}]\n'
            '}\n'
            '\n'
            'RULES:\n'
            '- distribution_table and reclassification_sample: copy verbatim — do NOT change any value.\n'
            '- complaints_table: rename "النسبة" -> "النسبة من الشكاوى", add "الوصف".\n'
            '- requests_table / inquiries_table: keep column names, add "الوصف".\n'
            '- All prose keys must be Arabic only.\n'
            '- Every number in prose must match a pre-computed input above.\n'
            '- No markdown, no extra keys, no extra nesting.\n'
        )

        client = anthropic.Anthropic(api_key=api_key)
        print(
            f"[WorkloadMap] Calling API — total_cases={total_cases}, "
            f"reclass={reclass_count} ({reclass_rate:.1f}%), "
            f"dominant={dominant_type} ({dominant_pct:.1f}%)"
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

        # Safety-reinject: these two tables must always be exact state data
        result["distribution_table"] = distribution_rows
        result["reclassification_sample"] = reclass_samples

        # VALIDATION: Verify all sub-classifications are present in returned tables
        # Bug 2 Fix: LLM sometimes only returns partial breakdown tables
        def validate_and_fix_table(table_name, table_rows, expected_rows):
            """Ensure all expected rows are present in table; add missing ones."""
            if not expected_rows:
                return table_rows

            returned_count = len(table_rows)
            expected_count = len(expected_rows)

            if returned_count < expected_count:
                print(f"[WorkloadMap] WARNING: {table_name} has {returned_count} rows, expected {expected_count}")

                # Add missing rows from expected_rows
                returned_subs = {row.get('الفئة الفرعية', '') for row in table_rows}
                for expected_row in expected_rows:
                    sub = expected_row.get('الفئة الفرعية', '')
                    if sub not in returned_subs:
                        # Preserve LLM-written description if it was provided
                        table_rows.append(expected_row)
                        print(f"[WorkloadMap] FIX: Added missing row for '{sub}'")

            return table_rows

        # Validate complaints, requests, inquiries tables against pre-computed data
        result["complaints_table"] = validate_and_fix_table(
            "complaints_table",
            result.get("complaints_table", []),
            complaint_subs
        )
        result["requests_table"] = validate_and_fix_table(
            "requests_table",
            result.get("requests_table", []),
            request_subs
        )
        result["inquiries_table"] = validate_and_fix_table(
            "inquiries_table",
            result.get("inquiries_table", []),
            inquiry_subs
        )

        print(
            f"[WorkloadMap] OK — "
            f"complaints={len(result.get('complaints_table', []))} rows, "
            f"requests={len(result.get('requests_table', []))} rows, "
            f"inquiries={len(result.get('inquiries_table', []))} rows"
        )
        return result

    except Exception as e:
        print(f"[WorkloadMap] ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise  # Don't silently return None — let caller see the error
