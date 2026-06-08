"""
STAGE 6: JSON Report Dictionary Generator (Complaints Version)

Transforms pipeline outputs (stages 1-5) + report_sections into a dictionary
matching demo cache structure. NO FILE I/O — returns dict for passing through functions.

COMPLAINTS-SPECIFIC CHANGES:
- Single top-level type (شكوى) instead of 4
- Sections 3.1-3.4 structure (vs inquiry 3.1-3.5):
  - 3.1: Distribution of 6 complaint sub-categories
  - 3.2: Channel analysis
  - 3.3: Resolution analysis (NEW — built from state.all_classified)
  - 3.4: Department distribution (NEW — built from state.department_distribution)

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
from collections import defaultdict, Counter
from .state import PipelineState, CaseRow, convert_month_year_to_arabic
from .stage2_rules import ALL_COMPLAINT_SUB_CATEGORIES as _SUB_CLASSIFICATIONS
from .generate_customer_journey_section import _build_friction_rows
from .generate_digital_gaps_section import _build_gap_rows, _build_root_cause_rows
from .generate_digital_transformation_section import (
    _build_faq_rows_for_transform,
    _build_notification_rows,
)
from .generate_ai_use_cases_section import _build_ai_tool_rows
from .generate_improvement_roadmap_section import _build_display_roadmap_rows
from .generate_conclusion_section import build_conclusion_section_for_json
from .utils import calculate_similarity, normalize_arabic


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
        "intro_paragraph": "3.1 intro (must open with 'تحليل...' and describe complaint sub-categories)",
        "channel_insight": "3.2 insight (must describe channel distribution)",
        "resolution_intro": "3.3 intro (must analyze resolution status distribution)",
    }

    required_table_fields = {
        "complaints_table": "breakdown table for 6 sub-categories",
        "channel_table": "breakdown table for communication channels",
        "resolution_table": "breakdown table for resolution status",
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
                    f"LLM must add description for each row."
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


def _digital_readiness(complaint_subcategory: str) -> str:
    """
    Digital deflection potential label for a complaint sub-category (Arabic).
    Maps 6 complaint sub-categories to digitization feasibility.
    """
    mapping = {
        "شكوى خدمة": "مسار رقمي كامل — بوابة شكاوى / تطبيق شامل للتتبع",
        "شكوى عن السلوك": "معالجة شبه رقمية — موثقة في النظام مع تنبيهات فورية",
        "شكوى بشأن العملية": "تحويل لموقع — عرض الخطوات المعتمدة والمواعيد المتوقعة",
        "شكوى بشأن الجودة": "مسار رقمي — لتقييم الخدمات وتقديم الملاحظات",
        "شكوى إدارية": "معالجة متخصصة — قد تتطلب موظفاً",
        "شكاوى أخرى": "تقييم حالة بحالة — قد تتطلب إجراءات يدوية",
    }
    return mapping.get(complaint_subcategory, "—")


def _validate_complaints_table(
    rows: List[Dict[str, str]],
    table_name: str = "complaints_table",
    expected_subs: Optional[set] = None
) -> None:
    """
    Strictly validate that complaints_table has correct structure and all required columns.
    Raises RuntimeError with detailed message if validation fails.

    Args:
        rows: Table rows to validate
        table_name: Name of table for error messages
        expected_subs: Set of expected sub-classifications. If provided, validates all are present.

    Raises:
        RuntimeError: If any validation check fails
    """
    if not rows:
        raise RuntimeError(
            f"[JSONReportBuilder] VALIDATION FAILED: {table_name} is empty. "
            f"Expected at least 6 complaint sub-categories."
        )

    required_columns = {"نوع الشكوى", "العدد", "النسبة", "الوصف", "قابلية التحويل الرقمي"}

    for idx, row in enumerate(rows):
        row_keys = set(row.keys())
        if not required_columns.issubset(row_keys):
            missing = required_columns - row_keys
            extra = row_keys - required_columns
            raise RuntimeError(
                f"[JSONReportBuilder] VALIDATION FAILED: Row {idx} in {table_name} has wrong columns. "
                f"Missing: {missing}. Extra/unexpected: {extra}. "
                f"Required exactly: {required_columns}. Got: {row_keys}"
            )

        # Verify non-empty values
        for col in required_columns:
            if not str(row[col]).strip():
                raise RuntimeError(
                    f"[JSONReportBuilder] VALIDATION FAILED: Row {idx}, column '{col}' is empty. "
                    f"All columns must have non-empty values."
                )

    # Verify we have all expected sub-classifications (if expected_subs provided)
    if expected_subs is not None:
        sub_classifications = {row.get("نوع الشكوى") for row in rows}
        missing_subs = expected_subs - sub_classifications
        if missing_subs:
            raise RuntimeError(
                f"[JSONReportBuilder] VALIDATION FAILED: {table_name} is missing sub-classifications: {missing_subs}. "
                f"All {len(expected_subs)} complaint types must be present, even with zero count."
            )

    print(f"[JSONReportBuilder] ✓ {table_name} validation passed — all {len(rows)} rows valid")


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
            "مسجَّلة كـ": case.case_type or "شكوى",
            "التصنيف الصحيح": sub_label,
            "الدليل من تفاصيل الطلب": f'"{excerpt}"',
        })
        if len(rows) >= max_samples:
            break
    return rows


class JSONReportBuilder:
    """Builds demo-compatible report dictionary from pipeline state (complaints version)."""

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
        """Build document metadata (complaints version).
        ISSUE 2 FIX: Include total_complaints, digital_channel_rate, zero_rejection_rate
        for build_report_ar._extract_cover_stats() to read.
        """
        all_classified = self.state.all_classified or []
        total = len(all_classified)

        # Calculate digital channel rate from case_channel (phone app + website)
        # Use normalized matching to handle diacritic variants
        DIGITAL_KEYWORDS = {normalize_arabic(kw) for kw in ['تطبيق', 'موقع']}
        digital_count = sum(
            1 for c in all_classified
            if c.case_channel and any(
                kw in normalize_arabic(str(c.case_channel))
                for kw in DIGITAL_KEYWORDS
            )
        )
        digital_channel_rate = f"{digital_count / total * 100:.1f}%" if total > 0 else "0%"

        # Check formal rejection rate (cases with status='طلب مرفوض')
        rejected_count = sum(1 for c in all_classified if c.case_status and c.case_status.strip() == 'طلب مرفوض')
        rejection_rate = (rejected_count / total * 100) if total > 0 else 0.0

        # Compute closure rate from total_cases and closed_cases_count
        closure_rate = 0.0
        if self.state.total_cases and self.state.closed_cases_count:
            closure_rate = round(self.state.closed_cases_count / self.state.total_cases * 100, 1)

        return {
            "extraction_version": 1,
            "document_name": f"تقرير تحليل شكاوى المتعاملين — {convert_month_year_to_arabic(self.state.month_year) or 'Q1 2026'}",
            "document_path": "",
            "metadata": {
                "title": f"تقرير تحليل شكاوى المتعاملين — {convert_month_year_to_arabic(self.state.month_year) or 'Q1 2026'}",
                "author": "AI Analysis Pipeline",
                "created": datetime.now().isoformat(),
                "modified": datetime.now().isoformat(),
                "total_paragraphs": len(all_classified),
                "total_tables": len(self.state.gap_table) + 3,
                "total_cases": self.state.total_cases,
                "closed_cases_count": self.state.closed_cases_count,
                "closure_rate": closure_rate,
                "total_complaints": total,
                "digital_channel_rate": digital_channel_rate,
                "rejection_rate": round(rejection_rate, 1),
            }
        }

    def build_classification_chart(self) -> Optional[Dict[str, Any]]:
        """Build bar chart showing complaint sub-category distribution (no original vs actual for complaints)."""
        if not self.state.all_classified:
            return None

        # For complaints, count by sub-classification (the 6 sub-categories)
        subcategory_counts = defaultdict(int)
        unclassified_count = 0
        for case in self.state.all_classified:
            # BUG 2 FIX: Skip cases without sub_classification (don't map to fake category)
            if case.sub_classification:
                subcategory_counts[case.sub_classification] += 1
            else:
                unclassified_count += 1

        if unclassified_count > 0:
            print(f"[JSONChart] WARNING: {unclassified_count} cases lack sub_classification — excluded from chart")

        # TASK 5 FIX: Filter categories to ONLY include those with actual cases
        # Do NOT include zero-count categories in chart (avoids confusion about missing categories)
        all_categories = _SUB_CLASSIFICATIONS
        categories = [c for c in all_categories if subcategory_counts.get(c, 0) > 0]

        if not categories:
            # Fallback: if no matches, use all categories (shouldn't happen with real data)
            categories = all_categories

        return {
            "type": "column",
            "title": "تصنيف أنواع الشكاوى",
            "categories": categories,
            "series": [
                {
                    "name": "عدد الشكاوى",
                    "data": [float(subcategory_counts.get(c, 0)) for c in categories]
                }
            ],
            "colors": ["#B68A35"],
            "orientation": "vertical"
        }

    # ------------------------------------------------------------------
    # Section 3.1 supplementary charts
    # ------------------------------------------------------------------

    _SEVERITY_VARIANTS: Dict[str, str] = {
        # Normalize diacritic variants to canonical form
        'طلب روتينى': 'طلب روتينى',
        'طلب روتيني': 'طلب روتينى',
        'روتينى': 'طلب روتينى',
        'روتيني': 'طلب روتينى',
        'شكوى روتينية': 'طلب روتينى',
        'شكوى روتيني': 'طلب روتينى',
        'طلب حرج': 'طلب حرج',
        'حرج': 'طلب حرج',
        'شكوى حرجة': 'طلب حرج',
        'طلب معقد': 'طلب معقد',
        'معقد': 'طلب معقد',
        'شكوى معقدة': 'طلب معقد',
    }
    _SEVERITY_ORDER = ['طلب روتينى', 'طلب حرج', 'طلب معقد']
    _SEVERITY_COLORS = ['#B68A35', '#999999', '#FF0000']

    def build_service_distribution_chart(self) -> Optional[Dict[str, Any]]:
        """Column chart — distribution of complaints by service (الخدمة column)."""
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
            "type": "column",
            "title": "توزيع الشكاوى على الخدمات",
            "categories": categories,
            "series": [
                {
                    "name": "توزيع الشكاوى على الخدمات",
                    "data": values,
                }
            ],
            "colors": ["#B68A35"],
            "orientation": "vertical"
        }

    def build_resolution_status_chart(self) -> Optional[Dict[str, Any]]:
        """Pie chart — complaints accepted vs rejected (based on case_status)."""
        if not self.state.all_classified:
            return None

        rejected = sum(
            1 for c in self.state.all_classified
            if c.case_status and c.case_status.strip() == 'طلب مرفوض'
        )
        total = len(self.state.all_classified)
        if total == 0:
            return None

        accepted = total - rejected

        return {
            "type": "pie",
            "title": "حالة معالجة الشكاوى",
            "categories": ["مقبولة", "مرفوضة"],
            "series": [
                {
                    "name": "حالة المعالجة",
                    "data": [float(accepted), float(rejected)],
                }
            ],
            "colors": ["#B68A35", "#FF0000"],
        }

    def build_severity_chart(self) -> Optional[Dict[str, Any]]:
        """Pie chart — severity distribution of complaints (شدة الطلب column)."""
        if self.state.raw_df is None:
            print("[build_severity_chart] raw_df is None, skipping")
            return None

        df = self.state.raw_df
        col = next(
            (c for c in ['شدة الطلب', 'شدة_الطلب', 'Severity'] if c in df.columns),
            None,
        )
        if col is None:
            print(f"[build_severity_chart] No severity column found. Available columns: {df.columns.tolist()}")
            return None

        counts: Dict[str, int] = defaultdict(int)
        non_empty_count = 0
        for val in df[col].dropna().astype(str):
            val = val.strip()
            if not val:
                continue
            non_empty_count += 1
            # Normalize diacritic variants to canonical form
            normalized = self._SEVERITY_VARIANTS.get(val, val)
            counts[normalized] += 1

        if not counts:
            print(f"[build_severity_chart] No valid severity data found. Total non-empty: {non_empty_count}")
            return None

        categories = [s for s in self._SEVERITY_ORDER if counts.get(s, 0) > 0]
        if not categories:
            print(f"[build_severity_chart] No severity categories matched. Raw counts: {dict(counts)}")
            return None

        values = [float(counts[s]) for s in categories]
        colors = [
            self._SEVERITY_COLORS[self._SEVERITY_ORDER.index(s)]
            for s in categories
        ]

        print(f"[build_severity_chart] Built pie chart with categories: {categories}, counts: {[counts[s] for s in categories]}")
        return {
            "type": "pie",
            "title": "شدة الشكوى",
            "categories": categories,
            "series": [
                {
                    "name": "شدة الشكوى",
                    "data": values,
                }
            ],
            "colors": colors,
        }

    def build_sla_closure_chart(self) -> Optional[Dict[str, Any]]:
        """Pie chart — SLA closure on time (whether case closed within specified SLA time)."""
        if not self.state.all_classified:
            return None

        on_time = 0
        late = 0
        unknown = 0
        for c in self.state.all_classified:
            raw = c.sla_closed_on_time
            val = str(raw).strip() if raw is not None else ''
            if val == 'نعم':
                on_time += 1
            elif val == 'لا':
                late += 1
            else:
                # Empty, 'nan', 'None', or any other unexpected value
                unknown += 1

        total = on_time + late + unknown
        if total == 0:
            return None

        # Build slices, omitting empty categories
        categories: List[str] = []
        values: List[float] = []
        colors: List[str] = []

        if on_time > 0:
            categories.append("ضمن الوقت المحدد")
            values.append(float(on_time))
            colors.append("#B68A35")
        if late > 0:
            categories.append("خارج الوقت المحدد")
            values.append(float(late))
            colors.append("#999999")
        if unknown > 0:
            categories.append("غير محدد")
            values.append(float(unknown))
            colors.append("#D9D9D9")

        return {
            "type": "pie",
            "title": "إغلاق الطلب خلال الوقت المحدد",
            "categories": categories,
            "series": [
                {
                    "name": "إغلاق الطلب",
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
                    f"يُقدّم هذا التقرير تحليلاً ذكياً مُندمجاً لـ {total} شكوى "
                    f"من بيانات CRM لشرطة الفجيرة "
                    f"{convert_month_year_to_arabic(self.state.month_year) or 'الربع الأول 2026'}. "
                    f"الهدف ليس عرض الأرقام، بل تحويل البيانات إلى قرارات ورؤى قابلة للتنفيذ. "
                    f"المُستجد الجوهري: الشكاوى تُوزّع على ست فئات فرعية متميزة، "
                    f"كل منها يتطلب معالجة متخصصة."
                )
            else:
                body = (
                    f"This report presents an intelligent analysis of {total} complaints "
                    f"from Fujairah Police CRM "
                    f"({self.state.month_year or 'Q1 2026'}). "
                    f"Complaints distribute across six distinct sub-categories, each requiring "
                    f"specialized handling."
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
                "الاكتشاف": f"الشكاوى تغطي {(complaint_count/total*100):.1f}% من العبء",
                "الوصف": f"الشكاوى تُمثّل {complaint_count} حالة ({(complaint_count/total*100):.1f}%) من الإجمالي.",
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

    def _extract_rejection_reason(self, case: CaseRow) -> str:
        """
        Extract rejection reason from case data.
        Maps sub_classification and case details to human-readable rejection reasons.
        Returns the reason category for table grouping. Called only on rejected cases.
        """
        sub = case.sub_classification or ""
        res = case.resolution_response or ""
        res_lower = res.lower()

        # Check sub_classification for explicit rejection reasons
        if "مكررة" in sub or "مكرر" in res:
            return "شكوى مكررة"

        if "بلا تصنيف" in sub or "أخرى" in sub:
            if "قناة" in res or "channel" in res_lower:
                return "بلاغ في قناة خاطئة"
            return "أخرى"

        if "خارج الاختصاص" in sub:
            return "خارج اختصاص شرطة الفجيرة"

        # Fallback: analyze resolution_response for rejection clues
        # (all rejected cases should have a reason in their metadata)
        if "مكرر" in res or "مكررة" in res:
            return "شكوى مكررة"
        if "قناة" in res or "channel" in res_lower:
            return "بلاغ في قناة خاطئة"
        if "اختصاص" in res:
            return "خارج اختصاص شرطة الفجيرة"
        if "انسحب" in res or "تعذر" in res:
            return "انسحب المشتكي / تعذر التواصل"
        if "نظام" in res or "عطل" in res or "خلل" in res:
            return "عطل في النظام"
        if "تنظيم" in res or "إداري" in res or "داخلي" in res:
            return "تنظيم وظيفي داخلي"

        return "أخرى"

    def _build_rejection_reasons_table(self) -> Dict[str, Any]:
        """
        Build rejection reasons breakdown table for Section 3.3.
        Analyzes only FORMALLY REJECTED cases (case_status == 'طلب مرفوض') and counts rejection reasons dynamically.
        Returns table dict with columns: سبب الرفض, العدد, % من المرفوضات, التشخيص
        """
        all_classified = self.state.all_classified or []

        # Filter for formally rejected cases only (case_status == 'طلب مرفوض')
        # Note: This is different from SLA compliance — formal rejection is an explicit status in the input data
        rejected_cases = [
            c for c in all_classified
            if c.case_status and c.case_status.strip() == 'طلب مرفوض'
        ]

        # Count rejection reasons
        rejection_counts = defaultdict(int)
        rejection_descriptions = {
            "شكوى مكررة": "طلبات متطابقة أو متشابهة جداً سبق استقبالها ومعالجتها",
            "بلاغ في قناة خاطئة": "بلاغات مقدمة عبر قنوات غير معتمدة أو غير صحيحة",
            "تنظيم وظيفي داخلي": "شكاوى تتعلق بتنظيم داخلي لا تندرج تحت شكاوى المتعاملين",
            "خارج اختصاص شرطة الفجيرة": "شكاوى خارج نطاق اختصاص شرطة الفجيرة",
            "عطل في النظام": "شكاوى لم تُستقبل بسبب خلل تقني في النظام",
            "انسحب المشتكي / تعذر التواصل": "انسحب المشتكي أو تعذر التواصل معه",
            "أخرى": "أسباب أخرى غير محددة",
        }

        for case in rejected_cases:
            reason = self._extract_rejection_reason(case)
            if reason:  # Only count non-empty reasons
                rejection_counts[reason] += 1

        # Build table rows sorted by count (descending)
        total_rejections = sum(rejection_counts.values()) or 1
        rows = []

        for reason in sorted(rejection_counts.keys(), key=lambda r: rejection_counts[r], reverse=True):
            count = rejection_counts[reason]
            pct = f"{count/total_rejections*100:.1f}%"
            diagnosis = rejection_descriptions.get(reason, "—")

            rows.append({
                "سبب الرفض": reason,
                "العدد": str(count),
                "% من المرفوضات": pct,
                "التشخيص": diagnosis,
            })

        return {
            "columns": ["سبب الرفض", "العدد", "% من المرفوضات", "التشخيص"],
            "rows": rows,
            "row_count": len(rows),
            "col_count": 4,
            "original_index": self.next_table_index(),
        }

    def _build_resolution_analysis_subsection(self, wm_raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build Section 3.3 — Resolution Analysis with rejection reasons table.

        Changed from: Single bold paragraph (spec requirement)
        To: Intro paragraph + rejection reasons breakdown table
        """
        # Section 3.3 — intro paragraph + rejection reasons table
        resolution_data = wm_raw.get("resolution_paragraph") or ""

        # Build the rejection reasons table
        rejection_table = self._build_rejection_reasons_table()

        return {
            "id": self.next_section_id("33_تحليل_المعالجة"),
            "title": "3.3  تحليل معالجة الشكاوى — الموافقة والرفض والإنجاز",
            "level": 2,
            "content": resolution_data,
            "tables": [rejection_table] if rejection_table.get("rows") else [],
            "charts": [],
        }

    def _build_department_distribution_subsection(self) -> Dict[str, Any]:
        """
        Build Section 3.4 — Department Distribution.
        Built from state.department_distribution (computed in stage1).
        Shows dominant complaint type for each department.
        """
        all_classified = self.state.all_classified or []
        total = len(all_classified) or 1

        # Build lookup: department → list of cases in that department
        dept_cases = defaultdict(list)
        for case in all_classified:
            if case.admin:
                dept_cases[case.admin].append(case)

        rows = []
        if self.state.department_distribution:
            for dept, count in sorted(
                self.state.department_distribution.items(),
                key=lambda x: x[1],
                reverse=True
            ):
                pct = f'{count/total*100:.1f}%'

                # Find dominant complaint type for this department
                # BUG 2 FIX: Skip cases without sub_classification (don't map to fallback "أخرى")
                cases_in_dept = dept_cases.get(dept, [])
                dominant_complaint = "—"
                if cases_in_dept:
                    complaint_counts = Counter(
                        case.sub_classification
                        for case in cases_in_dept
                        if case.sub_classification  # Skip None/empty
                    )
                    if complaint_counts:
                        dominant_complaint = complaint_counts.most_common(1)[0][0]

                rows.append({
                    'الإدارة': dept,
                    'العدد': str(count),
                    'النسبة': pct,
                    'نوع الشكاوى الغالب': dominant_complaint
                })

        department_table = {
            'columns': ['الإدارة', 'العدد', 'النسبة', 'نوع الشكاوى الغالب'],
            'rows': rows,
            'row_count': len(rows),
            'col_count': 4,
            'original_index': self.next_table_index(),
        }

        return {
            "id": self.next_section_id("34_توزيع_الإدارات"),
            "title": "3.4  توزيع الشكاوى الواردة حسب الإدارات",
            "level": 2,
            "content": "توزيع الشكاوى على الإدارات المسؤولة:",
            "tables": [department_table] if rows else [],
            "charts": [],
        }

    def build_workload_map_section(self, lang: str = "ar") -> Dict[str, Any]:
        """
        Build Section 3 - workload map (complaints version).

        Complaints version has 4 subsections:
        - 3.1: Distribution of 6 complaint sub-categories
        - 3.2: Channel analysis
        - 3.3: Resolution analysis (NEW — built from state.all_classified)
        - 3.4: Department distribution (NEW — built from state.department_distribution)
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
        total_cases = len(all_classified)  # Use len(all_classified), not state.total_cases

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
        sla_closure_chart = self.build_sla_closure_chart()
        severity_chart = self.build_severity_chart()
        charts_31 = [
            c for c in [classification_chart, service_chart, severity_chart, sla_closure_chart]
            if c is not None
        ]

        # 3.1 sub-category distribution
        # ISSUE 1 FIX: Build subcategory counts from all_classified
        sub_category_counts = defaultdict(int)
        unclassified_cases = []  # Track cases that lack sub_classification
        for case in all_classified:
            if case.sub_classification:
                sub_category_counts[case.sub_classification] += 1
            else:
                # BUG 2: Do NOT assign unclassified cases to "بلا تصنيف"
                # Mark them as "غير محدد" internally for tracking, but exclude from output
                unclassified_cases.append(case.case_number)

        # BUG 2 FIX: If there are unclassified cases, log a warning
        # but do NOT assign them to "بلا تصنيف" — that's a fallback, not a real classification
        if unclassified_cases:
            print(
                f"[JSONReportBuilder] WARNING: {len(unclassified_cases)} cases have no sub_classification: "
                f"{unclassified_cases[:5]}{'...' if len(unclassified_cases) > 5 else ''}. "
                f"These will be skipped from the complaints table."
            )

        intro_paragraph = wm_raw["intro_paragraph"]

        # Require LLM to provide complaints_table — no fallback, fail loudly if missing
        if "complaints_table" not in wm_raw:
            raise RuntimeError(
                "[JSONReportBuilder] VALIDATION FAILED: workload_map LLM output missing 'complaints_table'. "
                "LLM must provide a complete complaints_table with all 6 complaint sub-categories."
            )

        dist_rows = wm_raw["complaints_table"]

        # Compute expected sub-classifications dynamically from state
        # Only include subs that actually have cases (filter out zero-count categories)
        expected_complaint_subs = set(k for k, v in sub_category_counts.items() if v > 0)

        # Strictly validate the complaints_table with dynamic expected categories
        _validate_complaints_table(
            dist_rows,
            table_name="workload_map complaints_table",
            expected_subs=expected_complaint_subs
        )

        dist_table = {
            "columns": ["نوع الشكوى", "العدد", "النسبة", "الوصف", "قابلية التحويل الرقمي"],
            "rows": dist_rows,
            "row_count": len(dist_rows),
            "col_count": 5,
            "original_index": self.next_table_index(),
        }
        subsection_31 = {
            "id": self.next_section_id("31_التوزيع_الفعلي"),
            "title": "3.1  التوزيع الفعلي للشكاوى",
            "title_en": "3.1  Actual Complaint Distribution",
            "level": 2,
            "content": intro_paragraph,
            "tables": [dist_table],
            "charts": charts_31,
        }

        # 3.2 channel analysis
        channel_insight = wm_raw.get("channel_insight", "")
        channel_rows = wm_raw.get("channel_table", [])

        channel_table = {
            "columns": ["قناة التواصل", "العدد", "النسبة", "الوصف"],
            "rows": channel_rows,
            "row_count": len(channel_rows),
            "col_count": 4,
            "original_index": self.next_table_index(),
        }
        subsection_32 = {
            "id": self.next_section_id("32_تحليل_القنوات"),
            "title": "3.2  تحليل قنوات التواصل",
            "title_en": "3.2  Communication Channel Analysis",
            "level": 2,
            "content": channel_insight,
            "tables": [channel_table] if channel_rows else [],
            "charts": [],
        }

        # 3.3 resolution analysis (built from wm_raw, spec: single bold paragraph)
        subsection_33 = self._build_resolution_analysis_subsection(wm_raw)

        # 3.4 department distribution (built from state, not LLM)
        subsection_34 = self._build_department_distribution_subsection()

        # Build subsections list
        subsections = [subsection_31, subsection_32, subsection_33, subsection_34]

        return {
            "id": self.next_section_id("ثالثا_التحليل_الأول"),
            "title": "ثالثاً: التحليل الأول — خريطة تصنيف الشكاوى",
            "title_en": "Analysis One — Complaint Classification Map",
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
            "id":       self.next_section_id("رابعا_التحليل_الثاني"),
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
            required_cols = ["الخدمة", "الشكاوى", "القناة الرسمية في دليل الخدمات", "نوع الفجوة", "التوصية"]
            for col in required_cols:
                if col not in row or not str(row[col]).strip():
                    raise RuntimeError(
                        f"[JSONReportBuilder] gap_table row {idx} missing '{col}'. "
                        f"Expected all columns: {required_cols}"
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

        # NOTE: Case counts in gap_table_rows are already pre-computed from state.gap_table
        # and locked (not modified by LLM). This sync logic is a safety check only.
        if self.state.gap_table:
            gap_lookup = {(g.topic_ar or g.topic or "").strip(): g for g in self.state.gap_table}
            for row in gap_table_rows:
                topic = (row.get("الخدمة", "") or "").strip()
                if topic in gap_lookup:
                    # Exact match found — verify case count is correct
                    gap = gap_lookup[topic]
                    row["الشكاوى"] = str(gap.case_count)
                else:
                    # Fallback: use similarity-based matching
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
                        row["الشكاوى"] = str(best_match.case_count)
                        print(
                            f"[JSONReportBuilder] INFO: Gap topic '{topic[:50]}...' "
                            f"matched via similarity ({best_score:.2f}) to state.gap_table."
                        )
                    else:
                        # No match above threshold; keep pre-computed count
                        print(
                            f"[JSONReportBuilder] INFO: Gap topic '{topic}' "
                            f"not found in state.gap_table (best similarity={best_score:.2f}). "
                            f"Using pre-computed case count."
                        )

        root_cause_table_rows = dg_raw["root_cause_table"]
        section_body = dg_raw["section_body"]

        gap_table_dict = {
            "columns": ["الخدمة", "الشكاوى", "القناة الرسمية في دليل الخدمات", "نوع الفجوة", "التوصية"],
            "rows":    gap_table_rows,
            "row_count": len(gap_table_rows),
            "col_count": 5,
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
            "id":       self.next_section_id("51_جدول_الفجوات"),
            "title":    "5.1  جدول الفجوات المُدمج",
            "title_en": "5.1  Merged Gaps Table",
            "level":    3,
            "content":  "",
            "tables":   [gap_table_dict],
            "charts":   [],
        }

        # ── Subsection 5.2: Root Causes Table ──────────────────────────────────────
        subsection_52 = {
            "id":       self.next_section_id("52_الأسباب_الجذرية"),
            "title":    "5.2  الأسباب الجذرية لاستمرار المشكلات",
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
            "id":       self.next_section_id("خامسا_التحليل_الثالث"),
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
                else "هذه الأسئلة مستخرجة من الأنماط الأكثر تكراراً في بيانات الشكاوى النصية."
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
            f"تحليل البيانات يكشف أن {notif_intro_count} حالة تواصل "
            f"({notif_pct:.0f}% "
            "من الإجمالي) كان يمكن إلغاؤها كلياً بمنظومة إشعارات بسيطة — "
            "دون أي تغيير هيكلي في الأنظمة أو الإجراءات:"
            if notif_intro_count > 0
            else "تحليل البيانات يكشف فرصة إلغاء عدد من حالات التواصل بمنظومة إشعارات بسيطة:"
        )

        # ── FAQ table dict ────────────────────────────────────────────────────
        # COLUMNS (matching Section 6.1 screenshot):
        # #, السؤال, الفئة الرسمية, الإجابة الصحيحة, التكرار
        faq_table_dict = {
            "columns":        ["#", "السؤال", "الفئة الرسمية", "الإجابة الصحيحة", "التكرار"],
            "rows":           faq_rows,
            "row_count":      len(faq_rows),
            "col_count":      5,
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
            str(notif_intro_count) if notif_intro_count > 0 else "عدة"
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
            "columns":        ["الأداة", "الوظيفة", "الأثر المتوقع", "تقييم التنفيذ"],
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
                "id": self.next_section_id("21_المصادر_المحللة"),
                "title": "2.1  المصادر المُحلَّلة",
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
            "id": self.next_section_id("22_منهجية_التصنيف"),
            "title": "2.2  منهجية التصنيف",
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
            "id": self.next_section_id("23_الحقول_المحللة"),
            "title": "2.3  الحقول المُحلَّلة",
            "level": 2,
            "content": fields_content,
            "tables": [],
            "charts": []
        })

        return {
            "id": self.next_section_id("ثانيا_المنهجية_وطبيعة"),
            "title": "ثانياً: المنهجية وطبيعة المصادر",
            "level": 2,
            "content": "",
            "tables": [],
            "charts": [],
            "subsections": subsections
        }

    def build_report(self, lang: str = "ar") -> Dict[str, Any]:
        """Build complete report JSON for specified language (complaints version)."""
        report = self.build_metadata()

        # Sections — build all, then determine numbering based on actual inclusions
        sections = []

        # 1. Executive Summary (always included)
        sections.append(self.build_executive_summary_section(lang=lang))

        # 2. Methodology (inserted after Executive Summary)
        methodology_section = self.build_methodology_section(lang=lang)
        if methodology_section:
            sections.append(methodology_section)

        # 3. Workload Map (complaints version with 4 subsections)
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

        report["charts"] = []
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
    Generate report dictionary for Arabic only from pipeline state (complaints version).

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
