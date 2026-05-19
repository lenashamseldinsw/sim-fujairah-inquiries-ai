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


# ==============================================================================
# Module-level helpers
# Paste these at module level in stage6_json_report.py as well.
# ==============================================================================

def _digital_readiness_complaint(complaint_subtype: str) -> str:
    """
    Digital deflection potential label for a complaint sub-type (Arabic).
    Complaints version — only one top-level category (شكوى).
    """
    mapping = {
        "مخالفة مرورية": "بوابة شكاوى — تتبع بلاغ في التطبيق",
        "مشكلة في ترخيص": "بوابة شكاوى — طلب استفسار في التطبيق",
        "شكوى عن الخدمة": "بوابة شكاوى — نموذج تقييم في التطبيق",
        "بلاغ أمني": "بوابة الأمن العام — تطبيق التبليغ الموحد",
        "طلب معلومات": "روبوت محادثة / أسئلة شائعة / الموقع الإلكتروني",
        "أخرى": "حالة حسب النوع الفرعي المحدد",
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
    # Define digital channels (use official channels if provided, otherwise use defaults)
    # Channels like "تطبيق", "موقع الكتروني", "بريد إلكتروني" are considered digital
    if official_channels:
        digital_keywords = {"تطبيق", "موقع", "إلكترون", "ويتس", "تطبيق ذكي"}
        digital_channels = {ch for ch in official_channels if any(kw in ch for kw in digital_keywords)}
    else:
        digital_channels = {"تطبيق", "بريد إلكتروني", "بوابة إلكترونية", "موقع", "ويتس آب"}

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
    resolution_response_data: List[str],
    total_cases: int,
) -> List[Dict[str, str]]:
    """
    Build resolution analysis table from resolution_response field.
    Counts by الحالة value: تم الموافقة على الحل, طلب منجز, طلب مرفوض
    Also counts duplicates from "مكرر" mentions.

    Row schema: نوع الإغلاق | العدد | النسبة | الوصف
    """
    resolution_counts = defaultdict(int)
    duplicate_count = 0

    for response in (resolution_response_data or []):
        if not response or not isinstance(response, str):
            continue

        response_lower = response.strip()

        # Count by status
        if "تم الموافقة على الحل" in response_lower:
            resolution_counts["تم الموافقة على الحل"] += 1
        elif "طلب منجز" in response_lower:
            resolution_counts["طلب منجز"] += 1
        elif "طلب مرفوض" in response_lower:
            resolution_counts["طلب مرفوض"] += 1
        else:
            resolution_counts["قيد المعالجة"] += 1

        # Count duplicates
        if "مكرر" in response_lower:
            duplicate_count += 1

    # Calculate rejection rate
    total_resolved = sum(resolution_counts.values()) or 1
    rejection_count = resolution_counts.get("طلب مرفوض", 0)
    rejection_rate = rejection_count / total_resolved * 100 if total_resolved else 0

    # Description mapping for resolution statuses
    status_descriptions = {
        "تم الموافقة على الحل": "الشكاوى التي تمت الموافقة على حلها من قبل الجهات المختصة",
        "طلب منجز": "الشكاوى المنجزة والمغلقة بنجاح بعد معالجة كاملة",
        "طلب مرفوض": "الشكاوى المرفوضة لأسباب إجرائية أو لعدم استيفاء الشروط",
        "قيد المعالجة": "الشكاوى التي لا تزال قيد المعالجة والفحص",
    }

    # Build rows
    rows = []
    row_order = ["تم الموافقة على الحل", "طلب منجز", "طلب مرفوض", "قيد المعالجة"]
    for status in row_order:
        count = resolution_counts.get(status, 0)
        if count == 0:
            continue
        pct = f"{count / total_resolved * 100:.1f}%" if total_resolved else "0%"

        # Use predefined description
        description = status_descriptions.get(
            status,
            f"الشكاوى ذات حالة المعالجة: {status}"
        )

        rows.append({
            "نوع الإغلاق": status,
            "العدد": str(count),
            "النسبة": pct,
            "الوصف": description,
        })

    return rows


def _build_resolution_paragraph(resolution_rows: list, total_cases: int) -> str:
    """
    Convert resolution analysis rows into the single bold paragraph required by
    report_structure.md section 3.3.

    The spec says: "ENTIRE SECTION IS ONE BOLD PARAGRAPH. Not a table."
    Format: counts and percentages embedded in flowing Arabic prose.
    """
    # Index rows by نوع الإغلاق value for reliable lookup
    row_map = {r["نوع الإغلاق"]: r for r in resolution_rows}

    approved   = row_map.get("تم الموافقة على الحل", {})
    completed  = row_map.get("طلب منجز",              {})
    rejected   = row_map.get("طلب مرفوض",             {})
    duplicate  = row_map.get("مكرر (غير رسمي)",       {})  # informal duplicates row

    approved_count  = approved.get("العدد",  "0")
    approved_pct    = approved.get("النسبة", "0%")
    completed_count = completed.get("العدد",  "0")
    completed_pct   = completed.get("النسبة", "0%")
    rejected_count  = rejected.get("العدد",  "0")
    rejected_pct    = rejected.get("النسبة", "0%")
    dup_count       = duplicate.get("العدد", "0")

    para = (
        f"أُغلقت {approved_count} شكوى ({approved_pct}) بـ«تم الموافقة على الحل»، "
        f"و{completed_count} شكوى ({completed_pct}) بـ«طلب منجز» — "
        f"في مقابل معدل رفض بلغ {rejected_count} حالة ({rejected_pct}). "
        f"ورُصدت {dup_count} حالة تحمل كلمة «مكرر» في نص الحل دون أن تُصنَّف رسمياً كمرفوضة، "
        f"مما يُشير إلى أن التكرار الفعلي أعلى من المُسجَّل رسمياً."
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

        # Extract resolution data from all_classified
        resolution_responses = [case.resolution_response for case in all_classified if case.resolution_response]
        resolution_rows = _build_resolution_analysis_rows(resolution_responses, total_cases)

        # Department distribution
        dept_dist = state.department_distribution or {}
        department_rows = _build_department_distribution_rows(dept_dist, total_cases)

        # Calculate channel stats for LLM context
        if official_channels:
            digital_keywords = {"تطبيق", "موقع", "إلكترون", "ويتس", "تطبيق ذكي"}
            official_digital = {ch for ch in official_channels if any(kw in ch for kw in digital_keywords)}
            digital_channel_count = sum(
                count for channel, count in channel_dist.items()
                if channel in official_digital
            )
        else:
            digital_channel_count = sum(
                count for channel, count in channel_dist.items()
                if channel in {"تطبيق", "بريد إلكتروني", "بوابة إلكترونية", "موقع", "ويتس آب"}
            )
        digital_channel_rate = digital_channel_count / total_cases * 100 if total_cases else 0

        # Rejection rate for context
        rejection_count = len([c for c in all_classified if "طلب مرفوض" in (c.resolution_response or "")])
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
            'pre_computed_complaint_sub_classifications (6 complaint types, sorted descending by count):\n'
            f'{complaint_subs_json}\n'
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
            f'  - Note that {digital_channel_rate:.1f}% of complaints arrived via digital channels.\n'
            '  - Highlight the shift toward self-service and app-based submissions.\n'
            '  - End with a colon (":") — the table follows immediately.\n'
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
            '\n'
            'OUTPUT — single JSON object, no markdown, no extra keys\n'
            '\n'
            '{\n'
            '  "section": "workload_map",\n'
            '  "intro_paragraph": "...",\n'
            '  "channel_insight": "...",\n'
            '  "resolution_intro": "...",\n'
            '  "complaints_table": [\n'
            '    {"الفئة الفرعية": "...", "العدد": "...", "النسبة من الشكاوى": "...", "الوصف": "..."}\n'
            '  ]\n'
            '}\n'
            '\n'
            'RULES:\n'
            '- resolution_table and department_table: pre-computed, will be injected after parsing.\n'
            '  Do NOT include them in your JSON output.\n'
            '- CRITICAL: complaints_table must include EVERY sub-classification from\n'
            '  pre_computed_complaint_sub_classifications, even those with count = 1.\n'
            '  Do NOT omit low-count rows. All sub-classifications must appear.\n'
            '- complaints_table: rename "النسبة" -> "النسبة من الشكاوى", add "الوصف".\n'
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

        # VALIDATION: Verify all sub-classifications are present in returned complaints_table
        def validate_and_fix_complaints_table(table_rows, expected_rows):
            """Ensure all expected rows are present in table; add missing ones."""
            if not expected_rows:
                return table_rows

            returned_count = len(table_rows)
            expected_count = len(expected_rows)

            if returned_count < expected_count:
                print(f"[WorkloadMap] WARNING: complaints_table has {returned_count} rows, expected {expected_count}")

                # Add missing rows from expected_rows
                returned_subs = {row.get('الفئة الفرعية', '') for row in table_rows}
                for expected_row in expected_rows:
                    sub = expected_row.get('الفئة الفرعية', '')
                    if sub not in returned_subs:
                        # Add missing row with placeholder description
                        completed_row = {
                            **expected_row,
                            "النسبة من الشكاوى": expected_row.get('النسبة'),  # Copy النسبة to النسبة من الشكاوى
                            "الوصف": f"حالات {sub} المُسجَّلة خلال الفترة.",
                        }
                        # Remove the original النسبة key if it exists
                        if "النسبة" in completed_row:
                            del completed_row["النسبة"]
                        table_rows.append(completed_row)
                        print(f"[WorkloadMap] FIX: Added missing row for '{sub}'")

            return table_rows

        # Validate complaints table against pre-computed data
        result["complaints_table"] = validate_and_fix_complaints_table(
            result.get("complaints_table", []),
            complaint_subs
        )

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
