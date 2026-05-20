"""
STAGE 6: JSON Report Dictionary Generator

Transforms pipeline outputs (stages 1-5) + report_sections into a dictionary
matching demo cache structure. NO FILE I/O — returns dict for passing through functions.

Structure:
- metadata: Document info (title, author, dates, counts)
- charts: Array of chart definitions
- sections: Array of report sections with subsections, tables, charts

Each section has:
- id: Unique identifier (section_<num>_<slug>)
- title: Section title (language-appropriate for AR/EN versions)
- level: Heading level (1-3)
- content: Narrative text
- tables: Array of data tables
- charts: Array of embedded charts
- subsections: Nested sections
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict
from .state import PipelineState, CaseRow, convert_month_year_to_arabic
from .stage2_rules import SUB_CLASSIFICATIONS as _SUB_CLASSIFICATIONS
from .generate_customer_journey_section import _build_friction_rows
from .generate_digital_gaps_section import _build_gap_rows, _build_root_cause_rows, _ROOT_CAUSE_LABELS
from .generate_digital_transformation_section import (
    _build_faq_rows_for_transform,
    _build_notification_rows,
)
from .generate_ai_use_cases_section import _build_ai_tool_rows
from .generate_improvement_roadmap_section import _build_display_roadmap_rows
from .generate_conclusion_section import build_conclusion_section_for_json
from .utils import calculate_similarity


# ==============================================================================
# Module-level helpers for workload_map section
# ==============================================================================

def _validate_workload_map_data(wm_raw: Dict[str, Any]) -> None:
    """
    Validate that workload_map LLM output contains all required prose fields.
    Raises RuntimeError if any field is missing or empty.
    Allows empty tables (for categories with 0 cases).
    """
    required_prose_fields = {
        "intro_paragraph": "3.1 intro (must open with 'تحليل...' and end with 'التحوّل الجوهري:')",
        "reclassification_insight": "3.2 insight (must open with 'الاكتشاف الحرج:' and include counts/rates)",
        "complaints_intro": "3.3 intro (must identify complaints as dominant category)",
    }

    required_table_fields = {
        "complaints_table": "breakdown table (may be empty if 0 complaints)",
        "requests_table": "breakdown table (may be empty if 0 requests)",
        "inquiries_table": "breakdown table (may be empty if 0 inquiries)",
    }

    # Validate all prose fields exist and are non-empty
    for field, description in required_prose_fields.items():
        if field not in wm_raw:
            raise RuntimeError(
                f"[JSONReportBuilder] Missing required field '{field}' in workload_map LLM output. "
                f"Expected: {description}"
            )

        value = wm_raw[field]
        if isinstance(value, str) and not value.strip():
            raise RuntimeError(
                f"[JSONReportBuilder] Field '{field}' is empty in workload_map LLM output. "
                f"Expected: {description}"
            )

    # Validate all table fields exist (but allow empty lists)
    for field, description in required_table_fields.items():
        if field not in wm_raw:
            raise RuntimeError(
                f"[JSONReportBuilder] Missing required field '{field}' in workload_map LLM output. "
                f"Expected: {description}"
            )

        value = wm_raw[field]
        if not isinstance(value, list):
            raise RuntimeError(
                f"[JSONReportBuilder] Field '{field}' must be a list in workload_map LLM output."
            )

        # Validate الوصف only if table has rows
        for idx, row in enumerate(value):
            if "الوصف" not in row:
                raise RuntimeError(
                    f"[JSONReportBuilder] Row {idx} in {field} missing 'الوصف' field. "
                    f"LLM must add description for each sub-classification."
                )
            if not row["الوصف"].strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] Row {idx} in {field} has empty 'الوصف'. "
                    f"LLM must provide a non-empty description."
                )

def _delta_label(corrected_count: int, original_count: int) -> str:
    """
    Human-readable classification delta string for the distribution table.
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
    digital readiness labels.
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


def _deduplicate_friction_rows(friction_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Detect and flag near-duplicate friction points.

    CRITICAL: This function no longer modifies case counts.
    Case counts must ALWAYS come from state.journey_map (post-reconciliation),
    never from text parsing or deduplication logic.

    This function now:
    - Identifies similar friction points (for logging/debugging)
    - Preserves the LLM row structure unchanged
    - Caller (build_customer_journey_section) must rebuild all case counts from state.journey_map

    Rationale:
    - Text parsing of "الحالات" creates a second source of truth
    - Merging counts without state validation diverges from authoritative data
    - Deduplication should happen in stage 4 when journey_map is built, not stage 6
    """
    if not friction_rows or len(friction_rows) < 2:
        return friction_rows

    def extract_key_terms(text: str) -> set:
        """Extract significant Arabic words for similarity comparison."""
        words = text.split()
        return {w for w in words if len(w) > 2 and w not in ['من', 'في', 'على', 'عن']}

    def is_similar(point1: str, point2: str, threshold: float = 0.5) -> bool:
        """Check if two friction points describe similar issues."""
        terms1 = extract_key_terms(point1)
        terms2 = extract_key_terms(point2)
        if not terms1 or not terms2:
            return False
        overlap = len(terms1 & terms2)
        similarity = overlap / max(len(terms1), len(terms2))
        return similarity >= threshold

    # Log potential duplicates for awareness, but do NOT merge case counts
    for i, row in enumerate(friction_rows):
        current_point = row.get("نقطة الاحتكاك", "")
        for j in range(i + 1, len(friction_rows)):
            other_row = friction_rows[j]
            other_point = other_row.get("نقطة الاحتكاك", "")
            if is_similar(current_point, other_point):
                print(
                    f"[Friction Dedup] INFO: Similar friction points detected "
                    f"(rows {i} & {j}): '{current_point[:50]}...' vs '{other_point[:50]}...'. "
                    f"Real deduplication happens in stage4_analysis, not stage 6."
                )

    # Return rows unchanged — case counts will be rebuilt from state.journey_map by caller
    return friction_rows


def _build_reclassification_samples(state: PipelineState, max_samples: int = 5) -> List[Dict[str, str]]:
    """
    Pick up to max_samples cases where original CRM label != corrected label.
    ISSUE 2 FIX: Use same definition as reclassified_count: actual_contact_type != case_type.
    """
    rows = []
    for case in (state.all_classified or []):
        # ISSUE 2 FIX: Align with reclassified_count definition
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


class JSONReportBuilder:
    """Builds demo-compatible report dictionary from pipeline state."""

    def __init__(self, state: PipelineState):
        self.state = state
        self.section_counter = 0
        self.table_counter = 0

    def next_section_id(self, slug: str) -> str:
        """Generate unique section ID."""
        self.section_counter += 1
        return f"section_{self.section_counter}_{slug}"

    def next_table_index(self) -> int:
        """Get next table index."""
        idx = self.table_counter
        self.table_counter += 1
        return idx

    def _rebuild_friction_rows_from_journey_map(self, friction_rows_with_actions: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Rebuild friction rows from state.journey_map to enforce single source of truth.

        Takes rows with الإجراء التحسيني (from LLM) and rebuilds case counts from state.journey_map.
        This ensures all "الحالات" values are post-reconciliation, not from text parsing.

        Uses similarity-based matching to handle LLM-generated friction point names that may
        differ from state.journey_map names.

        Args:
            friction_rows_with_actions: Rows from LLM with الإجراء التحسيني column

        Returns:
            Rows with case counts sourced from state.journey_map[i].case_count
        """
        if not self.state.journey_map:
            return friction_rows_with_actions

        # Create lookup: friction point name → LLM row with action
        lookup = {}
        for llm_row in friction_rows_with_actions:
            point_ar = llm_row.get("نقطة الاحتكاك", "").strip()
            if point_ar:
                lookup[point_ar] = llm_row

        # Rebuild from state.journey_map to enforce single source of truth
        rebuilt = []
        for friction in sorted(self.state.journey_map, key=lambda f: f.case_count, reverse=True):
            point = friction.friction_point_ar or friction.friction_point or friction.cluster_ar or friction.cluster

            # Get LLM-supplied action and text from the matching row
            action = ""
            root_cause = ""

            if point in lookup:
                # Exact match found
                action = lookup[point].get("الإجراء التحسيني", "")
                root_cause = lookup[point].get("السبب الجذري", "")
            else:
                # Fallback: use similarity-based matching
                best_match = None
                best_score = 0.0

                for llm_point, llm_row in lookup.items():
                    if llm_point:  # Skip empty keys
                        score = calculate_similarity(point, llm_point)
                        if score > best_score:
                            best_score = score
                            best_match = llm_row

                # Apply similarity match only if score exceeds threshold
                if best_score >= 0.5 and best_match:
                    action = best_match.get("الإجراء التحسيني", "")
                    root_cause = best_match.get("السبب الجذري", "")
                    print(
                        f"[JSONReportBuilder] INFO: Friction point '{point[:50]}...' "
                        f"matched via similarity ({best_score:.2f}) to LLM output. "
                        f"الإجراء التحسيني and السبب الجذري updated."
                    )
                else:
                    # No match above threshold; use empty text and warn
                    print(
                        f"[JSONReportBuilder] WARNING: Friction point '{point}' "
                        f"not found in LLM output (best similarity={best_score:.2f}, threshold=0.5). "
                        f"Using state.journey_map values directly without LLM text. "
                        f"This may indicate a mismatch between LLM and state friction definitions."
                    )

            rebuilt.append({
                "نقطة الاحتكاك": point,
                "الحالات": str(friction.case_count),  # SOURCE: state.journey_map — post-reconciliation
                "السبب الجذري": root_cause,
                "الإجراء التحسيني": action,
            })

        return rebuilt

    def build_metadata(self) -> Dict[str, Any]:
        """Build document metadata."""
        return {
            "extraction_version": 1,
            "document_name": f"تقرير تحليل استفسارات المتعاملين — {convert_month_year_to_arabic(self.state.month_year) or 'Q1 2026'}",
            "document_path": "",
            "metadata": {
                "title": f"تقرير تحليل استفسارات المتعاملين — {convert_month_year_to_arabic(self.state.month_year) or 'Q1 2026'}",
                "author": "AI Analysis Pipeline",
                "created": datetime.now().isoformat(),
                "modified": datetime.now().isoformat(),
                "total_paragraphs": len(self.state.all_classified),
                "total_tables": len(self.state.gap_table) + 3,
                "total_cases": self.state.total_cases,
                "closed_cases_count": self.state.closed_cases_count,
            }
        }

    def build_classification_chart(self) -> Optional[Dict[str, Any]]:
        """Build bar chart comparing original vs actual classification."""
        if not self.state.all_classified:
            return None

        # Count classifications
        # FIX 1: Use case.case_type directly — no string parsing needed
        original_counts = defaultdict(int)
        actual_counts = defaultdict(int)

        for case in self.state.all_classified:
            actual_counts[case.actual_contact_type] += 1
            # CONSISTENCY FIX: Filter empty case_type (same as workload_map section)
            if case.case_type and case.case_type.strip():
                original_counts[case.case_type] += 1

        # Categories in order
        categories = ["شكوى", "استفسار", "طلب", "شكر وثناء"]

        return {
            "type": "bar",
            "title": "التصنيف الأصلي مقارنةً بالتصنيف الصحيح",
            "categories": categories,
            "series": [
                {
                    "name": "التصنيف الصحيح",   # series 0 → colors[0] = gold ✓
                    "data": [float(actual_counts.get(c, 0)) for c in categories]
                },
                {
                    "name": "التصنيف الأصلي",   # series 1 → colors[1] = light grey ✓
                    "data": [float(original_counts.get(c, 0)) for c in categories]
                }
            ],
            "colors": ["#B68A35", "#E5E5E5"]
        }

    # ------------------------------------------------------------------
    # Section 3.1 supplementary charts
    # ------------------------------------------------------------------

    _SEVERITY_DISPLAY_MAP: Dict[str, str] = {
        'طلب روتينى': 'طلب عادي',
        'طلب روتيني': 'طلب عادي',
        'طلب حرج': 'طلب عاجل',
        'طلب معقد': 'طلب معقد',
    }
    _SEVERITY_ORDER = ['طلب عادي', 'طلب عاجل', 'طلب معقد']
    _SEVERITY_COLORS = ['#B68A35', '#999999', '#FF0000']

    def build_service_distribution_chart(self) -> Optional[Dict[str, Any]]:
        """Column chart — distribution of requests by service (الخدمة column)."""
        if self.state.raw_df is None:
            return None

        df = self.state.raw_df
        col = next((c for c in ['الخدمة', 'الخدمة '] if c in df.columns), None)
        if col is None:
            return None

        counts = (
            df[col]
            .dropna()
            .astype(str)
            .str.strip()
            .replace('', float('nan'))
            .dropna()
            .value_counts()
        )
        if counts.empty:
            return None

        categories = counts.index.tolist()
        values = [float(v) for v in counts.values.tolist()]

        return {
            "type": "bar",
            "title": "توزيع الطلبات على الخدمات",
            "categories": categories,
            "series": [
                {
                    "name": "توزيع الطلبات على الخدمات",
                    "data": values,
                }
            ],
            "colors": ["#B68A35"],
        }

    def build_sla_compliance_chart(self) -> Optional[Dict[str, Any]]:
        """Pie chart — requests closed within the SLA deadline."""
        if not self.state.all_classified:
            return None

        on_time = sum(
            1 for c in self.state.all_classified
            if str(c.sla_color).strip() == 'نعم'
        )
        total = len(self.state.all_classified)
        if total == 0:
            return None

        off_time = total - on_time

        return {
            "type": "pie",
            "title": "إغلاق الطلب خلال الوقت المحدد",
            "categories": ["ضمن الوقت المحدد", "خارج الوقت المحدد"],
            "series": [
                {
                    "name": "إغلاق الطلب خلال الوقت المحدد",
                    "data": [float(on_time), float(off_time)],
                }
            ],
            "colors": ["#B68A35", "#E5E5E5"],
        }

    def build_severity_chart(self) -> Optional[Dict[str, Any]]:
        """Pie chart — severity distribution of requests (شدة الطلب column)."""
        if self.state.raw_df is None:
            return None

        df = self.state.raw_df
        col = next(
            (c for c in ['شدة الطلب', 'شدة_الطلب'] if c in df.columns),
            None,
        )
        if col is None:
            return None

        counts: Dict[str, int] = defaultdict(int)
        for val in df[col].dropna().astype(str):
            val = val.strip()
            if not val:
                continue
            mapped = self._SEVERITY_DISPLAY_MAP.get(val, val)
            counts[mapped] += 1

        if not counts:
            return None

        categories = [s for s in self._SEVERITY_ORDER if counts.get(s, 0) > 0]
        values = [float(counts[s]) for s in categories]
        colors = [
            self._SEVERITY_COLORS[self._SEVERITY_ORDER.index(s)]
            for s in categories
        ]

        return {
            "type": "pie",
            "title": "شدة الطلب",
            "categories": categories,
            "series": [
                {
                    "name": "شدة الطلب",
                    "data": values,
                }
            ],
            "colors": colors,
        }

    def build_executive_summary_section(self, lang: str = "ar") -> Dict[str, Any]:
        """BUG 3: Build executive summary section by reading from language-specific dict."""
        # Read from correct language dict
        report_sections = (
            self.state.report_sections_ar if lang == "ar"
            else self.state.report_sections_en
        )
        exec_data = report_sections.get('executive_summary', {})

        # Use language-appropriate content from state
        body = exec_data.get('body', '')
        # Don't show Arabic stub in English output
        if lang == 'en' and body and not any(c.isascii() for c in body[:20]):
            body = ''
        # Fall back to computed summary if body is empty or stub
        if not body or body.startswith('جاري') or body.startswith('Generating'):
            # Use total_cases (all cases, open or closed) for cover/intro reporting
            total = self.state.total_cases if self.state.total_cases > 0 else len(self.state.all_classified)
            complaint_count = sum(
                1 for c in self.state.all_classified
                if c.actual_contact_type == 'شكوى'
            )
            complaint_rate = (complaint_count / total * 100) if total > 0 else 0
            if lang == 'ar':
                body = (
                    f"يُقدّم هذا التقرير تحليلاً ذكياً مُندمجاً لـ {total} حالة "
                    f"من بيانات CRM لشرطة الفجيرة "
                    f"{convert_month_year_to_arabic(self.state.month_year) or 'الربع الأول 2026'}. "
                    f"الهدف ليس عرض الأرقام، بل تحويل البيانات إلى قرارات ورؤى قابلة للتنفيذ. "
                    f"المُستجد الجوهري: بعد تطبيق معايير التصنيف الدقيقة، "
                    f"الشكاوى باتت تُمثّل {complaint_rate:.1f}% من عبء العمل الفعلي."
                )
            else:
                body = (
                    f"This report presents an intelligent analysis of {total} cases "
                    f"from Fujairah Police CRM "
                    f"({self.state.month_year or 'Q1 2026'}). "
                    f"After applying precise classification criteria, complaints represent "
                    f"{complaint_rate:.1f}% of the actual workload."
                )
        content = body

        core_message = (
            exec_data.get('core_message')
            or exec_data.get('raw_data', {}).get('core_message_ar', '')
        )

        # Read key_findings from tables[0] (stored as raw list by artifacts)
        # or from raw_data if available
        raw_findings = []
        raw_data = exec_data.get('raw_data', {})
        if raw_data and raw_data.get('key_findings'):
            raw_findings = raw_data['key_findings']
        elif exec_data.get('tables') and exec_data['tables']:
            candidate = exec_data['tables'][0]
            if isinstance(candidate, list):
                raw_findings = candidate

        # Build language-appropriate findings table from raw_findings
        findings_table = None
        if raw_findings and isinstance(raw_findings, list) and len(raw_findings) > 0:
            if lang == 'ar':
                rows = [{
                    '#': str(f.get('number', i+1)),
                    'الاكتشاف': f.get('title', ''),
                    'الوصف': f.get('description', ''),
                    'مستوى الأهمية': f.get('importance', '🔴 حرجة')
                } for i, f in enumerate(raw_findings)]
                columns = ['#', 'الاكتشاف', 'الوصف', 'مستوى الأهمية']
            else:
                rows = [{
                    '#': str(f.get('number', i+1)),
                    'Discovery': f.get('title', ''),
                    'Description': f.get('description', ''),
                    'Importance': f.get('importance', '🔴 Critical')
                } for i, f in enumerate(raw_findings)]
                columns = ['#', 'Discovery', 'Description', 'Importance']

            findings_table = {
                'columns': columns,
                'rows': rows,
                'row_count': len(rows),
                'col_count': 4,
                'original_index': self.next_table_index()
            }

        # Fall back to computed findings table if LLM data unavailable
        if not findings_table:
            findings_table = self._build_key_findings_table()

        # Build section structure
        result = {
            "id": self.next_section_id(
                "أولا_الملخص_التنفيذي" if lang == "ar" else "executive_summary"
            ),
            "title": (
                "أولاً: الملخص التنفيذي — التحليلات الرئيسية"
                if lang == "ar" else "Executive Summary — Key Analyses"
            ),
            "level": 2,
            "content": content,
            "tables": [],
            "charts": [],
            "subsections": []
        }

        if findings_table:
            result["subsections"] = [{
                "id": self.next_section_id(
                    "النتائج_الرئيسية" if lang == "ar" else "key_findings"
                ),
                "title": "النتائج الرئيسية" if lang == "ar" else "Key Findings",
                "level": 2,
                "content": core_message,
                "tables": [findings_table],
                "charts": []
            }]

        return result

    def _build_key_findings_table(self) -> Optional[Dict[str, Any]]:
        """Build key findings table."""
        if not self.state.all_classified:
            return None

        total = len(self.state.all_classified)
        # FIX 1: Use centralized reclassification count from state
        misclassified = self.state.reclassified_count
        misclassification_rate = self.state.reclassification_rate
        complaint_count = sum(1 for c in self.state.all_classified if c.actual_contact_type == "شكوى")

        rows = [
            {
                "#": "1",
                "الاكتشاف": f"تصنيف غير دقيق بنسبة {misclassification_rate:.1f}%",
                "الوصف": f"{misclassified} من {total} حالة كانت مُصنَّفة أصلاً بشكل غير صحيح.",
                "مستوى الأهمية": "🔴 حرجة"
            },
            {
                "#": "2",
                "الاكتشاف": f"الشكاوى تهيمن بـ {(complaint_count/total*100):.1f}% على عبء العمل",
                "الوصف": f"الشكاوى تُمثّل {complaint_count} حالة ({(complaint_count/total*100):.1f}%) من العبء الفعلي.",
                "مستوى الأهمية": "🔴 حرجة"
            }
        ]

        return {
            "columns": ["#", "الاكتشاف", "الوصف", "مستوى الأهمية"],
            "rows": rows,
            "row_count": len(rows),
            "col_count": 4,
            "original_index": self.next_table_index()
        }

    def build_workload_map_section(self, lang: str = "ar") -> Dict[str, Any]:
        """
        Build Section 3 - workload map.

        Reuses existing JSONReportBuilder infrastructure:
          - self.build_classification_chart()  (bar chart, already defined)
          - self.next_section_id() / self.next_table_index()

        Module-level helpers required:
          _delta_label, _digital_readiness, _build_rich_distribution_rows,
          _build_reclassification_samples, _sub_classification_breakdown
        """
        report_sections = (
            self.state.report_sections_ar if lang == "ar"
            else self.state.report_sections_en
        )
        wm_raw = (report_sections.get("workload_map") or {}).get("raw_data") or {}
        if not wm_raw:
            raise RuntimeError(
                "[JSONReportBuilder] workload_map raw_data not found in state.report_sections_ar. "
                "Ensure stage6_artifacts.py called generate_workload_map_section() successfully."
            )

        # Validate all required fields are present and non-empty
        _validate_workload_map_data(wm_raw)
        print(f"[JSONReportBuilder] ✓ workload_map validation passed")

        all_classified = self.state.all_classified or []
        total_cases = len(all_classified)  # ISSUE 3 FIX: Use len(all_classified), not state.total_cases

        # Same two-pass counting loop used by build_classification_chart()
        corrected_dist = defaultdict(int)
        original_dist = defaultdict(int)
        for case in all_classified:
            corrected_dist[case.actual_contact_type] += 1
            # ISSUE 1 FIX: Filter empty case_type to prevent empty-string bucket
            if case.case_type and case.case_type.strip():
                original_dist[case.case_type] += 1

        # Bar chart — reuse existing method, no duplication
        classification_chart = self.build_classification_chart()

        # Additional 3.1 charts
        service_chart = self.build_service_distribution_chart()
        sla_chart = self.build_sla_compliance_chart()
        severity_chart = self.build_severity_chart()
        charts_31 = [
            c for c in [classification_chart, service_chart, sla_chart, severity_chart]
            if c is not None
        ]

        # 3.1 actual distribution
        intro_paragraph = wm_raw["intro_paragraph"]

        dist_rows = wm_raw.get("distribution_table") or _build_rich_distribution_rows(
            corrected_dist, original_dist, total_cases
        )
        dist_table = {
            "columns": ["نوع التواصل", "العدد", "النسبة", "تغيُّر التصنيف", "قابلية التحويل الرقمي"],
            "rows": dist_rows,
            "row_count": len(dist_rows),
            "col_count": 5,
            "original_index": self.next_table_index(),
        }
        subsection_31 = {
            "id": self.next_section_id("31_التوزيع_الفعلي" if lang == "ar" else "31_actual_distribution"),
            "title": "3.1  التوزيع الفعلي لأنواع التواصل" if lang == "ar" else "3.1  Actual Contact Type Distribution",
            "title_en": "3.1  Actual Contact Type Distribution",
            "level": 2,
            "content": intro_paragraph,
            "tables": [dist_table],
            "charts": charts_31,
        }

        # 3.2 classification accuracy
        reclass_count = self.state.reclassified_count
        reclass_rate = self.state.reclassification_rate

        reclassification_insight = wm_raw["reclassification_insight"]

        sample_rows = wm_raw.get("reclassification_sample") or _build_reclassification_samples(self.state)
        sample_table = {
            "columns": ["رقم الطلب", "مسجَّلة كـ", "التصنيف الصحيح", "الدليل من تفاصيل الطلب"],
            "rows": sample_rows,
            "row_count": len(sample_rows),
            "col_count": 4,
            "original_index": self.next_table_index(),
        }
        subsection_32 = {
            "id": self.next_section_id("32_دقة_التصنيف" if lang == "ar" else "32_classification_accuracy"),
            "title": (
                f"3.2  دقة التصنيف — {reclass_rate:.1f}% من الحالات تم إعادة تصنيفها"
                if lang == "ar"
                else f"3.2  Classification Accuracy — {reclass_rate:.1f}% Reclassified"
            ),
            "title_en": f"3.2  Classification Accuracy — {reclass_rate:.1f}% Reclassified",
            "level": 2,
            "content": reclassification_insight,
            "tables": [sample_table] if sample_rows else [],
            "charts": [],
        }

        # 3.3 complaints breakdown
        complaint_count = corrected_dist.get("شكوى", 0)
        complaint_pct = complaint_count / total_cases * 100 if total_cases else 0

        complaints_intro = wm_raw["complaints_intro"]

        complaint_rows = wm_raw["complaints_table"]
        # Normalize: ensure complaints table uses "النسبة من الشكاوى" not "النسبة"
        for row in complaint_rows:
            if "النسبة" in row and "النسبة من الشكاوى" not in row:
                row["النسبة من الشكاوى"] = row.pop("النسبة")
        complaint_table = {
            "columns": ["الفئة الفرعية", "العدد", "النسبة من الشكاوى", "الوصف"],
            "rows": complaint_rows,
            "row_count": len(complaint_rows),
            "col_count": 4,
            "original_index": self.next_table_index(),
        }
        subsection_33 = {
            "id": self.next_section_id("33_تفصيل_الشكاوى" if lang == "ar" else "33_complaints_breakdown"),
            "title": (
                f"3.3  تفصيل الشكاوى ({complaint_count} حالة — {complaint_pct:.1f}%)"
                if lang == "ar"
                else f"3.3  Complaints Breakdown ({complaint_count} cases — {complaint_pct:.1f}%)"
            ),
            "title_en": f"3.3  Complaints Breakdown ({complaint_count} cases — {complaint_pct:.1f}%)",
            "level": 2,
            "content": complaints_intro,
            "tables": [complaint_table] if complaint_rows else [],
            "charts": [],
        }

        # 3.4 requests breakdown
        request_count = corrected_dist.get("طلب", 0)
        request_pct = request_count / total_cases * 100 if total_cases else 0

        request_rows = wm_raw["requests_table"]
        # Task 8 Fix: Include ALL طلب cases regardless of sub-classification name.
        # Case 2025278919 has sub_type "استفسار عن الأسلحة والتراخيص" but top_level "طلب" —
        # the previous startswith("استفسار") filter incorrectly dropped it.
        # Classification inconsistencies are surfaced in Excel, not silently suppressed here.

        def _sub_table(rows, columns):
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "col_count": len(columns),
                "original_index": self.next_table_index(),
            }

        # 3.4 requests breakdown — with explanatory message when empty
        subsection_34 = {
            "id": self.next_section_id("34_تفصيل_الطلبات" if lang == "ar" else "34_requests"),
            "title": "3.4  تفصيل الطلبات والاستفسارات",
            "title_en": "3.4  Service Requests and Inquiries",
            "level": 2,
            "content": (
                f"أبرز الطلبات المقدَّمة ({request_count} حالات — {request_pct:.1f}%):"
                if request_rows
                else "لم تُسجَّل أي طلبات خدمة مباشرة في هذه الفترة — اقتصر العبء على الشكاوى والاستفسارات."
            ),
            "tables": [_sub_table(
                request_rows,
                ["الفئة الفرعية", "العدد", "النسبة", "الوصف"],
            )] if request_rows else [],
            "charts": [],
        }

        # 3.5 inquiries breakdown — with explanatory message when empty
        inquiry_count = corrected_dist.get("استفسار", 0)
        inquiry_pct = inquiry_count / total_cases * 100 if total_cases else 0

        _inquiry_subs = set(_SUB_CLASSIFICATIONS.get('استفسار', []))
        _request_subs = set(_SUB_CLASSIFICATIONS.get('طلب', []))
        # Task 7 Fix: Symmetric filter — inquiries_table must only contain استفسار sub-types
        inquiry_rows = [
            row for row in wm_raw["inquiries_table"]
            if row.get("الفئة الفرعية", "") not in _request_subs
        ]

        subsection_35 = {
            "id": self.next_section_id("35_أبرز_الاستفسارات" if lang == "ar" else "35_inquiries"),
            "title": (
                f"3.5  أبرز الاستفسارات المتكررة ({inquiry_count} حالات — {inquiry_pct:.1f}%) — وهي الفئة الأكثر قابليةً للتحويل إلى خدمة ذاتية رقمية كاملة"
                if inquiry_rows
                else "3.5  الاستفسارات المتكررة"
            ),
            "title_en": (
                f"3.5  Recurring Inquiries ({inquiry_count} cases — {inquiry_pct:.1f}%) — highest digital-deflection potential"
                if inquiry_rows
                else "3.5  Recurring Inquiries"
            ),
            "level": 2,
            "content": (
                ""
                if inquiry_rows
                else "لم تُسجَّل استفسارات متكررة واضحة في هذه الفترة — كان التوزيع موزعاً على عدد من الحالات الفردية."
            ),
            "tables": [_sub_table(
                inquiry_rows,
                ["الفئة الفرعية", "العدد", "النسبة", "الوصف"],
            )] if inquiry_rows else [],
            "charts": [],
        }

        # Build subsections list (always include 3.4 and 3.5 with explanatory messages when empty)
        subsections = [subsection_31, subsection_32, subsection_33, subsection_34, subsection_35]

        return {
            "id": self.next_section_id("ثالثا_التحليل_الأول" if lang == "ar" else "workload_map"),
            "title": "ثالثاً: التحليل الأول — خريطة تصنيف الطلبات" if lang == "ar" else "Analysis One — Contact Type Classification Map",
            "title_en": "Analysis One — Contact Type Classification Map",
            "level": 2,
            "content": "",
            "tables": [],
            "charts": [],
            "subsections": subsections,
        }

    def build_customer_journey_section(
        self,
        lang: str = "ar",
    ) -> Dict[str, Any]:
        """
        Build Section 4 — Customer Journey Challenges — for the JSON report dict.

        Reads pre-generated prose from state.report_sections_ar['customer_journey']['raw_data']
        and pre-computed table rows from state.journey_map (via _build_friction_rows).

        Validates that all required LLM fields are present before building.
        Raises RuntimeError if validation fails.
        """
        cj_section = (self.state.report_sections_ar or {}).get("customer_journey", {})
        cj_raw = cj_section.get("raw_data")

        if not cj_raw:
            raise RuntimeError(
                "[JSONReportBuilder] customer_journey raw_data not found in state.report_sections_ar. "
                "Ensure stage6_artifacts.py called generate_customer_journey_section() successfully."
            )

        # ── Validate required LLM fields ─────────────────────────────────────────
        required_fields = {
            "section_body":    "opening narrative paragraph (must open with 'يكشف التحليل...')",
            "friction_table":  "friction rows with الإجراء التحسيني column",
        }
        for field, description in required_fields.items():
            if field not in cj_raw:
                raise RuntimeError(
                    f"[JSONReportBuilder] Missing required field '{field}' in customer_journey LLM output. "
                    f"Expected: {description}"
                )
            value = cj_raw[field]
            if isinstance(value, str) and not value.strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] Field '{field}' is empty in customer_journey LLM output."
                )
            if isinstance(value, list) and not value:
                raise RuntimeError(
                    f"[JSONReportBuilder] Field '{field}' is an empty list in customer_journey LLM output."
                )

        # Validate الإجراء التحسيني is present in every friction row
        for idx, row in enumerate(cj_raw["friction_table"]):
            if "الإجراء التحسيني" not in row or not row["الإجراء التحسيني"].strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] friction_table row {idx} missing 'الإجراء التحسيني'. "
                    f"LLM must provide a corrective action for each friction point."
                )

        print("[JSONReportBuilder] ✓ customer_journey validation passed")

        # ── Build table dict ──────────────────────────────────────────────────────
        friction_rows  = cj_raw["friction_table"]
        # Deduplicate near-duplicate friction points (detection only, no count changes)
        friction_rows  = _deduplicate_friction_rows(friction_rows)

        # SOURCE: state.journey_map — post-reconciliation
        # Rebuild all case counts from state.journey_map to enforce single source of truth.
        # The LLM output may have pre-reconciliation counts; we replace them here.
        friction_rows = self._rebuild_friction_rows_from_journey_map(friction_rows)
        section_body   = cj_raw["section_body"]

        # Guard assertion: verify reconciled counts don't exceed actual sub_classification counts
        from collections import defaultdict
        actual_sub_counts = defaultdict(int)
        for case in (self.state.all_classified or []):
            actual_sub_counts[case.sub_classification] += 1

        for friction in self.state.journey_map or []:
            actual_count = actual_sub_counts.get(friction.sub_classification, 0)
            if friction.case_count > actual_count:
                print(
                    f"[JSONReportBuilder] WARNING: friction '{friction.friction_point_ar}' "
                    f"case_count={friction.case_count} exceeds actual count={actual_count} "
                    f"for sub_classification='{friction.sub_classification}'. "
                    f"Reconciliation may not have completed successfully."
                )

        friction_table_dict = {
            "columns": ["نقطة الاحتكاك", "الحالات", "السبب الجذري", "الإجراء التحسيني"],
            "rows":    friction_rows,
            "row_count": len(friction_rows),
            "col_count": 4,
            "original_index": self.next_table_index(),
        }

        # ── Section dict (matches sample output section_28 structure) ─────────────
        section_title = (
            "رابعاً: التحليل الثاني — التحديات في رحلة المتعامل"
            if lang == "ar"
            else "Section 4: Customer Journey Challenges"
        )

        return {
            "id":       self.next_section_id("رابعا_التحليل_الثاني" if lang == "ar" else "customer_journey"),
            "title":    section_title,
            "title_en": "Section 4: Customer Journey Challenges",
            "level":    2,
            "content":  section_body,
            "tables":   [friction_table_dict],
            "charts":   [],
            "subsections": [],
        }

    def build_digital_gaps_section(
        self,
        lang: str = "ar",
    ) -> Dict[str, Any]:
        """
        Build Section 5 — Digital Gaps Analysis — for the JSON report dict.

        Reads pre-generated LLM output from state.report_sections_ar['digital_gaps']['raw_data']
        and builds two tables: gap_table (5.1) and root_cause_table (5.2).

        Validates that all required LLM fields are present before building.
        Raises RuntimeError if validation fails.
        """
        dg_section = (self.state.report_sections_ar or {}).get("digital_gaps", {})
        dg_raw = dg_section.get("raw_data")

        if not dg_raw:
            raise RuntimeError(
                "[JSONReportBuilder] digital_gaps raw_data not found in state.report_sections_ar. "
                "Ensure stage6_artifacts.py called generate_digital_gaps_section() successfully."
            )

        # ── Validate required LLM fields ─────────────────────────────────────────
        required_fields = {
            "section_body":      "opening narrative paragraph",
            "gap_table":         "table with وضع التطبيق and التوصية columns",
            "root_cause_table":  "root cause rows with الحل column",
        }
        for field, description in required_fields.items():
            if field not in dg_raw:
                raise RuntimeError(
                    f"[JSONReportBuilder] Missing required field '{field}' in digital_gaps LLM output. "
                    f"Expected: {description}"
                )
            value = dg_raw[field]
            if isinstance(value, str) and not value.strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] Field '{field}' is empty in digital_gaps LLM output."
                )
            if isinstance(value, list) and not value:
                raise RuntimeError(
                    f"[JSONReportBuilder] Field '{field}' is an empty list in digital_gaps LLM output."
                )

        # Validate required columns in gap_table
        for idx, row in enumerate(dg_raw["gap_table"]):
            if "الشدّة" not in row or not row["الشدّة"].strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] gap_table row {idx} missing 'الشدّة'. "
                    f"LLM must copy severity emoji from pre_computed_gap_table."
                )
            if "وضع التطبيق / الموقع الحالي" not in row or not row["وضع التطبيق / الموقع الحالي"].strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] gap_table row {idx} missing 'وضع التطبيق / الموقع الحالي'. "
                    f"LLM must provide this column."
                )
            if "التوصية" not in row or not row["التوصية"].strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] gap_table row {idx} missing 'التوصية'. "
                    f"LLM must provide a recommendation for each gap."
                )

        # Validate required columns in root_cause_table
        for idx, row in enumerate(dg_raw["root_cause_table"]):
            if "الحل" not in row or not row["الحل"].strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] root_cause_table row {idx} missing 'الحل'. "
                    f"LLM must provide a solution for each root cause."
                )

        print("[JSONReportBuilder] ✓ digital_gaps validation passed")

        # ── Build table dicts ────────────────────────────────────────────────────
        gap_table_rows = dg_raw["gap_table"]

        # SOURCE: state.gap_table — post-reconciliation
        # Override case counts from LLM with authoritative values from state.gap_table.
        # The LLM was called with pre-reconciliation counts; we sync them here.
        if self.state.gap_table:
            gap_lookup = {(g.topic_ar or g.topic or "").strip(): g for g in self.state.gap_table}
            for row in gap_table_rows:
                topic = (row.get("الموضوع", "") or "").strip()
                if topic in gap_lookup:
                    # Exact match found
                    gap = gap_lookup[topic]
                    row["الحالات"] = str(gap.case_count)
                else:
                    # Fallback: use similarity-based matching
                    # Find the gap_lookup entry with highest similarity score
                    best_match = None
                    best_score = 0.0

                    for gap_key, gap in gap_lookup.items():
                        if gap_key:  # Skip empty keys
                            score = calculate_similarity(topic, gap_key)
                            if score > best_score:
                                best_score = score
                                best_match = gap

                    # Apply similarity match only if score exceeds threshold
                    if best_score >= 0.5 and best_match:
                        row["الحالات"] = str(best_match.case_count)
                        print(
                            f"[JSONReportBuilder] INFO: Gap topic '{topic[:50]}...' "
                            f"matched via similarity ({best_score:.2f}) to state.gap_table. "
                            f"Case count updated."
                        )
                    else:
                        # No match above threshold; keep LLM-supplied count and warn
                        print(
                            f"[JSONReportBuilder] WARNING: Gap topic '{topic}' "
                            f"not found in state.gap_table (best similarity={best_score:.2f}, threshold=0.5). "
                            f"Using LLM-supplied case count. "
                            f"This may indicate a mismatch between LLM and state gap definitions."
                        )

        root_cause_table_rows = dg_raw["root_cause_table"]

        # SOURCE: state.journey_map (post-reconciliation) — same source as _build_root_cause_rows().
        # Override LLM-supplied counts in root_cause_table with the authoritative grouped totals.
        # The LLM may hallucinate or reuse stale pre-reconciliation counts.
        if self.state.journey_map:
            rc_totals_auth: dict = defaultdict(int)
            for f in self.state.journey_map:
                rc_totals_auth[f.root_cause_category] += f.case_count

            # Combined label→category mapping covering both label sets:
            # _ROOT_CAUSE_LABELS (what LLM is given via _build_root_cause_rows) AND
            # _root_cause_label() aliases (what the LLM sometimes returns instead).
            label_to_category: dict = {v: k for k, v in _ROOT_CAUSE_LABELS.items()}
            label_to_category.update({
                'غياب معلومات من الدليل':             'missing_info',
                'معلومات موجودة لكنها صعبة الوصول':   'inaccessible_info',
                'غياب الإشعار الاستباقي':              'no_proactive_notification',
                'خلل تقني في المنصة':                 'platform_bug',
                'تعقيد إجراءات السياسة':              'policy_complexity',
            })

            for row in root_cause_table_rows:
                label = (row.get("السبب الجذري", "") or "").strip()
                cat = label_to_category.get(label)
                if cat and cat in rc_totals_auth:
                    auth_total = rc_totals_auth[cat]
                    row["الحالات"] = str(auth_total)
                    example = row.get("مثال على التحدي", "")
                    if example and " حالة — " in example:
                        suffix = example.split(" حالة — ", 1)[1]
                        row["مثال على التحدي"] = f"{auth_total} حالة — {suffix}"

        section_body = dg_raw["section_body"]

        gap_table_dict = {
            "columns": ["الموضوع", "الحالات", "الشدّة", "وضع التطبيق / الموقع الحالي", "نوع الفجوة", "التوصية"],
            "rows":    gap_table_rows,
            "row_count": len(gap_table_rows),
            "col_count": 6,
            "original_index": self.next_table_index(),
        }

        root_cause_table_dict = {
            "columns": ["#", "السبب الجذري", "مثال على التحدي", "الحل"],
            "rows":    root_cause_table_rows,
            "row_count": len(root_cause_table_rows),
            "col_count": 4,
            "original_index": self.next_table_index(),
        }

        # ── Subsection 5.1: Gaps Table ─────────────────────────────────────────────
        subsection_51 = {
            "id":       self.next_section_id("51_جدول_الفجوات" if lang == "ar" else "51_gaps_table"),
            "title":    "5.1  جدول الفجوات المُدمج" if lang == "ar" else "5.1  Merged Gaps Table",
            "title_en": "5.1  Merged Gaps Table",
            "level":    3,
            "content":  "",
            "tables":   [gap_table_dict],
            "charts":   [],
        }

        # ── Subsection 5.2: Root Causes Table ──────────────────────────────────────
        subsection_52 = {
            "id":       self.next_section_id("52_الأسباب_الجذرية" if lang == "ar" else "52_root_causes"),
            "title":    "5.2  الأسباب الجذرية لاستمرار المشكلات" if lang == "ar" else "5.2  Root Causes of Continued Issues",
            "title_en": "5.2  Root Causes of Continued Issues",
            "level":    3,
            "content":  "",
            "tables":   [root_cause_table_dict],
            "charts":   [],
        }

        # ── Section dict (matches sample output section_29 structure) ──────────────
        section_title = (
            "خامساً: التحليل الثالث — تحليل الفجوات الرقمية"
            if lang == "ar"
            else "Section 5: Digital Gaps Analysis"
        )

        return {
            "id":       self.next_section_id("خامسا_التحليل_الثالث" if lang == "ar" else "digital_gaps"),
            "title":    section_title,
            "title_en": "Section 5: Digital Gaps Analysis",
            "level":    2,
            "content":  section_body,
            "tables":   [],
            "charts":   [],
            "subsections": [subsection_51, subsection_52],
        }

    def build_digital_transformation_section(
        self,
        lang: str = "ar",
        section_number: int = 6,
    ) -> Optional[Dict[str, Any]]:
        """
        Build Section 6 — Digital Transformation Plan — for the JSON report dict.

        Reads pre-generated LLM output from state.report_sections_ar['digital_transformation']['raw_data']
        and builds two tables: FAQ table (6.1) and notification table (6.2).

        Args:
            lang: 'ar' or 'en'
            section_number: ordinal position in report (default 6 → سادساً)

        Returns:
            Section dict matching JSON cache structure, or None if raw_data unavailable.
        """
        dt_section = (self.state.report_sections_ar or {}).get("digital_transformation", {})
        dt_raw = dt_section.get("raw_data")

        if not dt_raw:
            return None

        section_body  = dt_raw.get("section_body", "")
        faq_rows      = dt_raw.get("faq_table", [])
        notif_rows    = dt_raw.get("notification_table", [])
        faq_table_intro = dt_raw.get("faq_table_intro", "")  # Optional: separate intro for FAQ subsection

        if not section_body or not faq_rows or not notif_rows:
            return None

        # Use LLM-provided faq_table_intro if available; otherwise derive from section_body
        if not faq_table_intro:
            faq_intro = (
                section_body.split("—")[0].strip()
                if "—" in section_body and len(section_body.split("—")[0].strip()) > 10
                else "هذه الأسئلة مستخرجة من الأنماط الأكثر تكراراً في البيانات النصية."
            )
        else:
            faq_intro = faq_table_intro

        # SOURCE: state.notification_opportunities — post-reconciliation
        # Compute notification impact count directly from state, not from LLM rows.
        # The LLM rows may have pre-reconciliation data; we replace with authoritative values.
        notif_intro_count = sum(
            n.get('cases_eliminated', n.get('case_count', 0))
            for n in (self.state.notification_opportunities or [])
        )

        # Recompute percentage from reconciled total_cases
        total_for_notif_pct = len(self.state.all_classified) or self.state.total_cases or 1
        notif_pct = round(notif_intro_count / total_for_notif_pct * 100, 0) if notif_intro_count > 0 else 0

        notif_intro = (
            f"تحليل البيانات يكشف أن {notif_intro_count}+ حالة تواصل "
            f"({notif_pct:.0f}% "
            "من الإجمالي) كان يمكن إلغاؤها كلياً بمنظومة إشعارات بسيطة — "
            "دون أي تغيير هيكلي في الأنظمة أو الإجراءات:"
            if notif_intro_count > 0
            else "تحليل البيانات يكشف فرصة إلغاء عدد من حالات التواصل بمنظومة إشعارات بسيطة:"
        )

        # ── FAQ table dict ────────────────────────────────────────────────────
        faq_table_dict = {
            "columns":        ["#", "السؤال", "الإجابة المقترحة", "التكرار"],
            "rows":           faq_rows,
            "row_count":      len(faq_rows),
            "col_count":      4,
            "original_index": self.next_table_index(),
            "caption":        faq_intro,
        }

        # ── Notification table dict ───────────────────────────────────────────
        notif_table_dict = {
            "columns":        ["نوع الإشعار", "الحالات المُلغاة", "محتوى الإشعار (مثال)", "القناة", "الأثر المتوقع"],
            "rows":           notif_rows,
            "row_count":      len(notif_rows),
            "col_count":      5,
            "original_index": self.next_table_index(),
            "caption":        notif_intro,
        }

        # ── Subsection 6.1: FAQ Table ─────────────────────────────────────────
        subsection_61_title = (
            "6.1  الأسئلة الشائعة ذات الأولوية"
            if lang == "ar"
            else "6.1  Priority FAQs"
        )
        # BUG FIX: Don't duplicate section_body in subsection content if they're identical
        subsection_61_content = faq_intro if faq_intro != section_body else ""
        subsection_61 = {
            "id":       self.next_section_id(
                "61_الأسئلة_الشائعة" if lang == "ar" else "61_faq_table"
            ),
            "title":    subsection_61_title,
            "title_en": "6.1  Priority FAQs",
            "level":    3,
            "content":  subsection_61_content,
            "tables":   [faq_table_dict],
            "charts":   [],
        }

        # ── Subsection 6.2: Notification Pathway ─────────────────────────────
        notif_count_label = (
            str(notif_intro_count) + "+" if notif_intro_count > 0 else "30+"
        )
        subsection_62_title = (
            f"6.2  مسار إلغاء {notif_count_label} حالة تواصل بالإشعار الاستباقي"
            if lang == "ar"
            else "6.2  Proactive Notification Elimination Pathway"
        )
        # BUG FIX: Don't duplicate section_body in subsection content if they're identical
        subsection_62_content = notif_intro if notif_intro != section_body else ""
        subsection_62 = {
            "id":       self.next_section_id(
                "62_مسار_إلغاء_الإشعار" if lang == "ar" else "62_notification_pathway"
            ),
            "title":    subsection_62_title,
            "title_en": "6.2  Proactive Notification Elimination Pathway",
            "level":    3,
            "content":  subsection_62_content,
            "tables":   [notif_table_dict],
            "charts":   [],
        }

        # ── Section dict ──────────────────────────────────────────────────────
        ordinals = ["", "أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً"]
        analysis_labels = ["", "التحليل الأول", "التحليل الثاني", "التحليل الثالث", "التحليل الرابع", "التحليل الخامس"]
        ordinal = ordinals[section_number] if section_number < len(ordinals) else f"القسم {section_number}"
        analysis_num = section_number - 2
        analysis_label = (
            analysis_labels[analysis_num]
            if 0 < analysis_num < len(analysis_labels)
            else f"التحليل {analysis_num}"
        )

        section_title = (
            f"{ordinal}: {analysis_label} — خطة التحويل الرقمي"
            if lang == "ar"
            else "Section 6: Digital Transformation Plan"
        )

        return {
            "id":       self.next_section_id(
                "سادسا_التحليل_الرابع" if lang == "ar" else "digital_transformation"
            ),
            "title":    section_title,
            "title_en": "Section 6: Digital Transformation Plan",
            "level":    2,
            "content":  section_body,
            "tables":   [],
            "charts":   [],
            "subsections": [subsection_61, subsection_62],
        }

    def build_ai_use_cases_section(
        self,
        lang: str = "ar",
        section_number: int = 7,
    ) -> Optional[Dict[str, Any]]:
        """
        Build Section 7 — AI-Powered Use Cases — for the JSON report dict.

        Reads pre-generated LLM output from state.report_sections_ar['ai_use_cases']['raw_data']
        and builds a use-cases table with 4 AI tool rows.

        Args:
            lang: 'ar' or 'en'
            section_number: ordinal position in report (default 7 → سابعاً)

        Returns:
            Section dict matching JSON cache structure, or None if raw_data unavailable.
        """
        uc_section = (self.state.report_sections_ar or {}).get("ai_use_cases", {})
        uc_raw = uc_section.get("raw_data")

        if not uc_raw:
            return None

        section_body   = uc_raw.get("section_body", "")
        use_cases_rows = uc_raw.get("use_cases_table", [])
        closing_note   = uc_raw.get("closing_note", "")

        if not section_body or not use_cases_rows or not closing_note:
            return None

        # Strip tool_id from display (internal use only)
        display_rows = []
        for row in use_cases_rows:
            display_row = {k: v for k, v in row.items() if k != "tool_id"}
            display_rows.append(display_row)

        # ── Use Cases table dict ──────────────────────────────────────────────
        use_cases_table_dict = {
            "columns":        ["الأداة", "الوظيفة", "الأثر المتوقع على بيانات " + (convert_month_year_to_arabic(self.state.month_year) or "الفترة الحالية"), "تقييم التنفيذ"],
            "rows":           display_rows,
            "row_count":      len(display_rows),
            "col_count":      4,
            "original_index": self.next_table_index(),
            "caption":        section_body,
        }

        # ── Section dict ──────────────────────────────────────────────────────
        ordinals = ["", "أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً"]
        ordinal = ordinals[section_number] if section_number < len(ordinals) else f"القسم {section_number}"

        section_title = (
            f"{ordinal}: حالات الاستخدام المدعومة بالذكاء الاصطناعي"
            if lang == "ar"
            else "Section 7: AI-Powered Use Cases"
        )

        # Build full content: section_body + table + closing_note
        full_content = f"{section_body}\n\n{closing_note}"

        return {
            "id":       self.next_section_id(
                "سابعا_حالات_الاستخدام_الذكاء_الاصطناعي" if lang == "ar" else "ai_use_cases"
            ),
            "title":    section_title,
            "title_en": "Section 7: AI-Powered Use Cases",
            "level":    2,
            "content":  full_content,
            "tables":   [use_cases_table_dict],
            "charts":   [],
        }

    def build_improvement_roadmap_section(
        self,
        lang: str = "ar",
        section_number: int = 8,
    ) -> Optional[Dict[str, Any]]:
        """
        Build Section 8 — Improvement Roadmap — for the JSON report dict.

        Reads pre-generated LLM output from
        state.report_sections_ar['improvement_roadmap']['raw_data']
        and assembles a 6-column prioritised roadmap table.

        Args:
            lang:           'ar' or 'en'
            section_number: ordinal position in report (default 8 → ثامناً)

        Returns:
            Section dict matching JSON cache structure, or None if raw_data unavailable.
        """
        roadmap_section = (self.state.report_sections_ar or {}).get("improvement_roadmap", {})
        roadmap_raw = roadmap_section.get("raw_data")

        if not roadmap_raw:
            return None

        section_body = roadmap_raw.get("section_body", "")
        if not section_body or not roadmap_raw.get("roadmap_table"):
            return None

        # Build display rows (strips internal keys)
        display_rows = _build_display_roadmap_rows(roadmap_raw)

        # Roadmap table dict
        roadmap_table_dict = {
            "columns":        ["الأفق الزمني", "#", "التوصية", "المصدر", "الأثر المتوقع", "الجهد"],
            "rows":           display_rows,
            "row_count":      len(display_rows),
            "col_count":      6,
            "original_index": self.next_table_index(),
            "caption":        section_body,
        }

        ordinals = ["", "أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً", "ثامناً"]
        ordinal = ordinals[section_number] if section_number < len(ordinals) else f"القسم {section_number}"

        section_title = (
            f"{ordinal}: خارطة الطريق التحسينية المقترحة"
            if lang == "ar"
            else "Section 8: Improvement Roadmap"
        )

        return {
            "id":       self.next_section_id(
                "ثامنا_خارطة_الطريق_التحسينية" if lang == "ar" else "improvement_roadmap"
            ),
            "title":    section_title,
            "title_en": "Section 8: Improvement Roadmap",
            "level":    2,
            "content":  section_body,
            "tables":   [roadmap_table_dict],
            "charts":   [],
            "subsections": [],
        }

    def build_conclusion_section(self, lang: str = "ar", section_number: int = 9) -> Optional[Dict[str, Any]]:
        """Build Conclusion section (Section 9) from state.report_sections_ar['conclusion']."""
        return build_conclusion_section_for_json(self.state, lang, section_number)

    def build_faq_section(self, section_number: int = 8) -> Optional[Dict[str, Any]]:
        """Build FAQ section from validated FAQs. ISSUE 2 FIX: Accept positional section_number."""
        if not self.state.validated_faqs:
            return None

        faq_rows = []
        for i, faq in enumerate(self.state.validated_faqs[:7], 1):
            # FIX 2: Use Arabic fields with fallback to English
            faq_rows.append({
                "#": str(i),
                "السؤال": faq.question_ar or faq.question,
                "الإجابة المقترحة": faq.answer_ar or faq.answer,
                "التكرار": str(faq.frequency)
            })

        faq_table = {
            "columns": ["#", "السؤال", "الإجابة المقترحة", "التكرار"],
            "rows": faq_rows,
            "row_count": len(faq_rows),
            "col_count": 4,
            "original_index": self.next_table_index()
        }

        # ISSUE 2 FIX: Use positional numbering
        # Sections 1-2 are not analyses (Executive, Methodology)
        # Sections 3+ are analyses (Workload, Journey, Patterns, Gap, FAQ)
        ordinals = ["", "أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً"]
        analysis_labels = ["", "التحليل الأول", "التحليل الثاني", "التحليل الثالث", "التحليل الرابع", "التحليل الخامس"]
        ordinal = ordinals[section_number] if section_number < len(ordinals) else f"القسم {section_number}"
        analysis_num = section_number - 2  # Section 3 = analysis 1, Section 7 = analysis 5, etc.
        analysis_label = analysis_labels[analysis_num] if 0 < analysis_num < len(analysis_labels) else f"التحليل {analysis_num}"

        return {
            "id": self.next_section_id("سابعا_التحليل_الخامس"),
            "title": f"{ordinal}: {analysis_label} — الأسئلة الشائعة",
            "level": 2,
            "content": "الأسئلة الشائعة المستخرجة من بيانات المتعاملين.",
            "tables": [faq_table],
            "charts": [],
            "subsections": []
        }

    def build_methodology_section(self, lang: str = "ar") -> Optional[Dict[str, Any]]:
        """Build methodology section from stage6 report generation with language support."""
        report_sections = self.state.report_sections_en if lang == "en" else self.state.report_sections_ar
        if not report_sections or 'methodology' not in report_sections:
            return None

        method_data = report_sections['methodology']
        subsections = []

        # 2.1 Sources table — read from flat structure with list rows
        sources_table = None
        if method_data.get('tables') and len(method_data['tables']) > 0:
            candidate = method_data['tables'][0]
            # Validate it's a proper table dict with a list for rows
            if (isinstance(candidate, dict)
                    and isinstance(candidate.get('rows'), list)
                    and len(candidate.get('rows', [])) > 0):
                # ISSUE 3 FIX: Ensure row_count is always present (fallback to len(rows) if missing)
                if 'row_count' not in candidate and candidate.get('rows'):
                    candidate['row_count'] = len(candidate['rows'])
                sources_table = candidate

        if sources_table:
            subsections.append({
                "id": self.next_section_id("21_المصادر_المحللة" if lang == "ar" else "21_sources_analyzed"),
                "title": "2.1  المصادر المُحلَّلة" if lang == "ar" else "2.1  Sources Analyzed",
                "level": 2,
                "content": "",
                "tables": [sources_table],
                "charts": []
            })

        # 2.2 Classification methodology — read from language-appropriate dict
        classification_content = (
            method_data.get('classification_method') or
            method_data.get('body', '')
        )
        subsections.append({
            "id": self.next_section_id("22_منهجية_التصنيف" if lang == "ar" else "22_classification_methodology"),
            "title": "2.2  منهجية التصنيف" if lang == "ar" else "2.2  Classification Methodology",
            "level": 2,
            "content": classification_content,
            "tables": [],
            "charts": []
        })

        # 2.3 Analyzed fields — read from language-appropriate dict
        fields_content = (
            method_data.get('analyzed_fields') or
            method_data.get('body', '')
        )
        subsections.append({
            "id": self.next_section_id("23_الحقول_المحللة" if lang == "ar" else "23_analyzed_fields"),
            "title": "2.3  الحقول المُحلَّلة" if lang == "ar" else "2.3  Analyzed Fields",
            "level": 2,
            "content": fields_content,
            "tables": [],
            "charts": []
        })

        return {
            "id": self.next_section_id("ثانيا_المنهجية_وطبيعة" if lang == "ar" else "methodology"),
            "title": "ثانياً: المنهجية وطبيعة المصادر" if lang == "ar" else "Methodology and Data Sources",
            "level": 2,
            "content": "",
            "tables": [],
            "charts": [],
            "subsections": subsections
        }

    def build_patterns_section(self, section_number: int = 5) -> Optional[Dict[str, Any]]:
        """ISSUE 1 FIX: Build patterns section split by top_level type. ISSUE 2 FIX: Accept positional section_number."""
        if not self.state.patterns:
            return None

        # Group patterns by top_level
        patterns_by_type = {}
        for pattern in self.state.patterns:
            top_level = pattern.top_level or pattern.cluster  # Use top_level field with fallback to cluster
            if top_level not in patterns_by_type:
                patterns_by_type[top_level] = []
            patterns_by_type[top_level].append(pattern)

        # Build separate tables per type — skip only if empty, not if < 3
        subsections = []
        all_tables = []

        for top_level, patterns_list in sorted(patterns_by_type.items()):
            if not patterns_list:
                continue  # ISSUE 1 FIX: Skip only empty groups, not groups with < 3 patterns

            # Calculate total for this type
            type_total = sum(p.case_count for p in patterns_list)

            # Build table for this type
            pattern_rows = []
            for pattern in patterns_list[:10]:  # Limit to 10 per type
                pattern_rows.append({
                    "الفئة الفرعية": pattern.cluster_ar or pattern.cluster,
                    "العدد": str(pattern.case_count),
                    "النسبة": f"{(pattern.case_count / type_total * 100):.1f}%",  # ISSUE 2: Fixed percentage calculation
                    "الوصف": pattern.sub_theme_ar or pattern.sub_theme
                })

            pattern_table = {
                "columns": ["الفئة الفرعية", "العدد", "النسبة", "الوصف"],
                "rows": pattern_rows,
                "row_count": len(pattern_rows),
                "col_count": 4,
                "original_index": self.next_table_index()
            }

            # Map top_level to Arabic title
            type_titles = {
                "شكوى": "أنماط الشكاوى",
                "طلب": "أنماط الطلبات",
                "استفسار": "أنماط الاستفسارات",
            }
            type_title = type_titles.get(top_level, f"أنماط {top_level}")

            subsections.append({
                "id": f"section_{section_number}_{len(subsections)+1}_أنماط_{top_level}",
                "title": f"{section_number}.{len(subsections)+1} {type_title}",
                "level": 2,
                "content": f"أنماط {type_title} الرئيسية ({type_total} حالة إجمالية)",
                "tables": [pattern_table],
                "charts": [],
                "subsections": []
            })
            all_tables.append(pattern_table)

        if not subsections:
            return None

        # Use ordinal numbering based on section_number
        ordinals = ["", "أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً"]
        analysis_labels = ["", "التحليل الأول", "التحليل الثاني", "التحليل الثالث", "التحليل الرابع", "التحليل الخامس"]
        ordinal = ordinals[section_number] if section_number < len(ordinals) else f"القسم {section_number}"
        analysis_num = section_number - 2  # Section 3 = analysis 1, Section 5 = analysis 3, etc.
        analysis_label = analysis_labels[analysis_num] if 0 < analysis_num < len(analysis_labels) else f"التحليل {analysis_num}"

        # Explain clustering threshold to clarify case count differences
        clustering_note = (
            "الأنماط الرئيسية المكتشفة في البيانات، مجمعة حسب نوع التصنيف (شكوى، طلب، استفسار). "
            "ملاحظة: تتضمن الجداول أدناه الأنماط التي تجمع حالات متشابهة بقدر كاف (مجموعة من حالتين فأكثر). "
            "قد لا تظهر جميع الحالات من القسم 3 في هذه الأنماط إذا كانت تشكل مجموعات منفردة دون تشابه واضح مع حالات أخرى."
        )

        return {
            "id": f"section_{section_number}_تحليل_الأنماط",
            "title": f"{ordinal}: {analysis_label} — تفصيل الأنماط حسب نوع التصنيف",
            "level": 2,
            "content": clustering_note,
            "tables": [],
            "charts": [],
            "subsections": subsections
        }

    def build_report(self, lang: str = "ar") -> Dict[str, Any]:
        """BUG 1: Build complete report JSON for specified language. ISSUE 2 FIX: Positional section numbering."""
        report = self.build_metadata()

        # Sections — build all, then determine numbering based on actual inclusions
        sections = []

        # 1. Executive Summary (always included)
        sections.append(self.build_executive_summary_section(lang=lang))

        # 2. Methodology (inserted after Executive Summary)
        methodology_section = self.build_methodology_section(lang=lang)
        if methodology_section:
            sections.append(methodology_section)

        # 3. Workload Map
        sections.append(self.build_workload_map_section(lang=lang))

        # 4. Customer Journey Challenges
        sections.append(self.build_customer_journey_section(lang=lang))

        # 5. Digital Gaps Analysis
        sections.append(self.build_digital_gaps_section(lang=lang))

        # 6. Digital Transformation Plan
        digital_transform_section = self.build_digital_transformation_section(lang=lang, section_number=6)
        if digital_transform_section:
            sections.append(digital_transform_section)

        # 7. AI Use Cases
        ai_use_cases_section = self.build_ai_use_cases_section(lang=lang, section_number=7)
        if ai_use_cases_section:
            sections.append(ai_use_cases_section)

        # 8. Improvement Roadmap
        improvement_roadmap_section = self.build_improvement_roadmap_section(lang=lang, section_number=8)
        if improvement_roadmap_section:
            sections.append(improvement_roadmap_section)

        # 9. Conclusion
        conclusion_section = self.build_conclusion_section(lang=lang, section_number=9)
        if conclusion_section:
            sections.append(conclusion_section)

        # NOTE: Patterns section (S10) removed — patterns are internal clustering and don't add value to the
        # executive report. The patterns are already surfaced via journey_map clusters in the customer journey
        # section (S4) and gap analysis (S5). Separate patterns enumeration was causing denominator confusion
        # with the workload map section totals.

        # NOTE: FAQ section removed (Issue 1) — FAQs now embedded in Section 6.1 (Digital Transformation)
        # The old build_faq_section() was a duplicate with lower-quality content. Digital transformation
        # section provides FAQs with better operational guidance and contextual information.

        # Charts
        charts = []
        chart = self.build_classification_chart()
        if chart:
            charts.append(chart)

        report["charts"] = charts
        report["sections"] = sections

        # Issue 3 Fix: Recalculate total_tables at the end by walking all sections
        total_tables_count = 0
        for section in sections:
            if section and section.get('tables'):
                total_tables_count += len(section['tables'])
            if section and section.get('subsections'):
                for subsection in section['subsections']:
                    if subsection and subsection.get('tables'):
                        total_tables_count += len(subsection['tables'])

        if 'metadata' in report:
            report['metadata']['total_tables'] = total_tables_count

        return report


def generate_json_report(state: PipelineState) -> Dict[str, Any]:
    """
    Generate report dictionary for Arabic only from pipeline state.

    Combines pipeline outputs (stages 1-5) with report_sections to build
    report JSON structure for Arabic.

    Args:
        state: PipelineState from stages 1-5 with populated report_sections_ar

    Returns:
        Dict with structure: {...report structure for Arabic...}
        with "sections" key at top level for build_report_ar
    """
    builder = JSONReportBuilder(state)
    return builder.build_report(lang='ar')
