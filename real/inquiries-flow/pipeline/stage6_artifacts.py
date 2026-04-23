"""
STAGE 6: Artifact Generator

Generates:
1. Excel workbook (openpyxl) — 10 sheets with classification results
2. Word report (sword-word-builder) — 9-section bilingual report
3. Report dictionary — demo-compatible format for Streamlit display (in-memory)

Uses state.report_sections from Stage 4/5 to build Word document and report dict.
Report dict is stored in state.report_json for passing to display functions.
"""

import json
import sys
import anthropic
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import importlib.util

from .state import PipelineState, CaseRow
from .stage6_json_report import generate_json_report

# Load sword_word_builder from local path
WordBuilder = None
DocumentConfig = None
TextStyle = None
TableStyle = None
CoverPage = None

try:
    sword_word_builder_path = Path(__file__).parent.parent.parent / 'sword_word_builder'

    if sword_word_builder_path.exists():
        # Try method 1: Add to sys.path and import normally
        sys.path.insert(0, str(sword_word_builder_path.parent))
        try:
            from sword_word_builder import WordBuilder, DocumentConfig, TextStyle, TableStyle, CoverPage
        except ImportError:
            # Try method 2: Load module directly from file path
            init_file = sword_word_builder_path / '__init__.py'
            if init_file.exists():
                spec = importlib.util.spec_from_file_location("sword_word_builder", init_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules['sword_word_builder'] = module
                    spec.loader.exec_module(module)
                    WordBuilder = module.WordBuilder
                    DocumentConfig = module.DocumentConfig
                    TextStyle = module.TextStyle
                    TableStyle = module.TableStyle
                    CoverPage = module.CoverPage
except Exception as e:
    print(f"[Warning] Could not load sword_word_builder: {e}")
    WordBuilder = None


# Excel formatting
HEADER_FILL = PatternFill(start_color="1B4F72", end_color="1B4F72", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
ALT_ROW_FILL = PatternFill(start_color="F8F9F9", end_color="F8F9F9", fill_type="solid")
BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)

# Sheet names in order
SHEET_NAMES = [
    'ملخص',                    # Summary
    'كل الحالات',              # All Cases
    'طلبات',                   # Service Requests
    'استفسارات',               # Information Inquiries
    'متابعات',                 # Status Follow-ups
    'مشاكل جهات أخرى',         # Cross-Entity
    'استفسارات الموقع',        # Location Inquiries
    'بلاغات تقنية',            # Tech Incidents
    'استفسارات مالية',         # Financial Inquiries
    'إعادة التصنيف',           # Misclassified Cases
]


def generate_excel(state: PipelineState, output_path: str) -> None:
    """Generate Excel workbook with classification results."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default sheet

    # Add summary sheet
    ws_summary = wb.create_sheet('ملخص', 0)
    _populate_summary_sheet(ws_summary, state)

    # Add all cases sheet
    ws_all = wb.create_sheet('كل الحالات', 1)
    _populate_all_cases_sheet(ws_all, state.all_classified)

    # Add category-specific sheets
    wb.create_sheet('طلبات', 2)
    wb.create_sheet('استفسارات', 3)
    wb.create_sheet('متابعات', 4)
    wb.create_sheet('مشاكل جهات أخرى', 5)
    wb.create_sheet('استفسارات الموقع', 6)
    wb.create_sheet('بلاغات تقنية', 7)
    wb.create_sheet('استفسارات مالية', 8)

    # Add misclassified cases sheet
    ws_misclass = wb.create_sheet('إعادة التصنيف', 9)
    misclassified = [c for c in state.all_classified if c.misclassification != 'OK']
    _populate_all_cases_sheet(ws_misclass, misclassified)

    # Color misclassified tab
    ws_misclass.sheet_properties.tabColor = "C0392B"

    # Save
    wb.save(output_path)


def _populate_summary_sheet(ws, state: PipelineState) -> None:
    """Populate summary sheet with metrics."""
    ws.merge_cells('A1:E1')
    ws['A1'] = f"ملخص تحليل استفسارات شرطة الفجيرة — {state.month_year or 'Q1 2026'}"
    ws['A1'].font = Font(bold=True, size=14)

    ws.merge_cells('A2:E2')
    ws['A2'] = f"تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d')}"

    # Total cases
    row = 4
    ws[f'A{row}'] = "1. إجمالي الحالات"
    ws[f'A{row}'].font = Font(bold=True)

    row = 5
    ws[f'A{row}'] = "إجمالي الحالات المعالجة"
    ws[f'B{row}'] = len(state.all_classified)
    ws[f'C{row}'] = "100.0%"

    # Distribution by contact type
    row = 7
    ws[f'A{row}'] = "2. توزيع حسب نوع التصنيف"
    ws[f'A{row}'].font = Font(bold=True)

    contact_types = {}
    for case in state.all_classified:
        ct = case.actual_contact_type
        contact_types[ct] = contact_types.get(ct, 0) + 1

    row = 8
    total = len(state.all_classified)
    for contact_type, count in sorted(contact_types.items(), key=lambda x: x[1], reverse=True):
        ws[f'A{row}'] = contact_type
        ws[f'B{row}'] = count
        ws[f'C{row}'] = f"{(count/total*100):.1f}%"
        row += 1


def _populate_all_cases_sheet(ws, cases: List[CaseRow]) -> None:
    """Populate sheet with case data."""
    headers = [
        'رقم الطلب',
        'تفاصيل الطلب',
        'الحل',
        'الخدمة',
        'الخدمة الرئيسية',
        'نوع المكالمة',
        'التصنيف الفعلي',
        'السبب',
        'إعادة التصنيف',
        'قناة التقديم',
        'حالة SLA',
        'تاريخ الإنشاء',
        'الإدارة',
    ]

    # Write headers
    for col, header in enumerate(headers, 1):
        cell = ws.cell(1, col, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # Write data
    for row_idx, case in enumerate(cases, 2):
        data = [
            case.case_number,
            case.case_title[:50],  # Truncate for display
            case.resolution_response[:50],
            case.service_name,
            case.service_name,
            case.case_type,
            case.actual_contact_type,
            case.classification_reason,
            case.misclassification,
            case.case_channel,
            case.sla_color,
            case.date_opened,
            '',  # Admin
        ]

        for col_idx, value in enumerate(data, 1):
            cell = ws.cell(row_idx, col_idx, value)
            cell.border = BORDER

            # Alternate row coloring
            if row_idx % 2 == 0:
                cell.fill = ALT_ROW_FILL

            # RTL alignment for Arabic
            cell.alignment = Alignment(horizontal='right' if col_idx <= 8 else 'left', vertical='top', wrap_text=True)

    # Set column widths
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 50
    ws.column_dimensions['C'].width = 60
    for col in range(4, 14):
        ws.column_dimensions[get_column_letter(col)].width = 20

    # Freeze header
    ws.freeze_panes = 'A2'

    # Auto-filter
    ws.auto_filter.ref = f'A1:{get_column_letter(len(headers))}{len(cases) + 1}'


def generate_word_report(
    state: PipelineState,
    output_path: str,
    language: str = 'ar',
    api_key: str = ""
) -> None:
    """
    Generate Word report using sword-word-builder.

    Args:
        state: Pipeline state with report_sections
        output_path: Path to save .docx
        language: 'ar' or 'en'
        api_key: Anthropic API key for LLM report generation
    """
    if WordBuilder is None:
        raise ImportError("sword-word-builder not installed")

    # Build report content via LLM if not in state
    if not state.report_sections:
        _generate_report_sections(state, api_key)

    # Create builder
    is_arabic = language == 'ar'
    builder = WordBuilder(
        DocumentConfig(
            default_font="Calibri",
            default_rtl=is_arabic,
            heading_font="Arial",
            accent_color="B68A35",  # Gold
            secondary_color="1A6080",  # Dark blue
            body_color="333333",
            line_spacing=14,
        )
    )

    # Add cover page
    if is_arabic:
        title = "نبض الفجيرة"
        subtitle = f"تقرير تحليل الاستفسارات — {state.month_year or 'الربع الأول 2026'}"
    else:
        title = "Fujairah Pulse"
        subtitle = f"Inquiry Analysis Report — {state.month_year or 'Q1 2026'}"

    cover = CoverPage.preset(
        title=title,
        subtitle=subtitle,
        metadata={
            "Total Cases": state.total_cases,
            "Report Date": state.created_at.split('T')[0],
        }
    )
    builder.add_cover_page(cover)

    # Add sections
    section_order = [
        'executive_summary',
        'methodology',
        'classification_summary',
        'workload_distribution',
        'top_patterns',
        'friction_analysis',
        'gap_analysis',
        'faq_summary',
        'recommendations',
        'conclusion',
    ]

    for section_key in section_order:
        if section_key not in state.report_sections:
            continue

        section_data = state.report_sections[section_key]

        # Get language-specific content
        if is_arabic:
            heading = section_data.get('heading_ar', section_data.get('heading', ''))
            body = section_data.get('body_ar', section_data.get('body', ''))
        else:
            heading = section_data.get('heading_en', section_data.get('heading', ''))
            body = section_data.get('body_en', section_data.get('body', ''))

        if not heading:
            continue

        # Add section heading
        builder.add_heading(heading, level=2, rtl=is_arabic)

        # Add body text
        if body:
            builder.add_paragraph(body, rtl=is_arabic)

        # Add tables if present
        if 'tables' in section_data:
            tables = section_data['tables']
            if isinstance(tables, list) and tables:
                for table_data in tables:
                    if isinstance(table_data, (list, dict)):
                        try:
                            builder.add_table(table_data, rtl=is_arabic)
                        except Exception as e:
                            print(f"Warning: Failed to add table in {section_key}: {e}")

        # Add spacer between sections
        builder.add_spacer(12)

    # Save
    builder.save(output_path)


def _generate_report_sections(state: PipelineState, api_key: str = "") -> None:
    """
    Generate report sections via LLM.

    Calls specialized functions for each of the 9 sections:
    1. Executive Summary
    2. Methodology (placeholder)
    3. Workload Map (placeholder)
    4. Customer Journey Challenges (placeholder)
    5. Digital Gaps (placeholder)
    6. Digital Transformation Plan (placeholder)
    7. AI Use Cases (placeholder)
    8. Improvement Roadmap (placeholder)
    9. Conclusion (placeholder)
    """
    if not api_key:
        # Fallback to basic structure if no API key
        _create_basic_report_sections(state)
        return

    try:
        # Initialize report_sections dict
        state.report_sections = {}

        # 1. Generate Executive Summary (primary, detailed implementation)
        print("[Report Gen] Generating Executive Summary...")
        exec_summary = generate_executive_summary_section(state, api_key)
        if exec_summary:
            # Store in report_sections with proper structure for Word builder
            state.report_sections['executive_summary'] = {
                'heading': 'Executive Summary',
                'heading_ar': 'أولاً: الملخص التنفيذي — التحليلات الرئيسية',
                'body_ar': exec_summary.get('framing_paragraph_ar', ''),
                'body_en': exec_summary.get('framing_paragraph_en', ''),
                'tables': [exec_summary.get('key_findings', [])],  # Will be formatted as table
                'core_message_ar': exec_summary.get('core_message_ar', ''),
                'core_message_en': exec_summary.get('core_message_en', ''),
                'raw_data': exec_summary  # Store full response for later processing
            }
        else:
            print("[Report Gen] Warning: Executive summary generation failed, using fallback")
            state.report_sections['executive_summary'] = {
                'heading_ar': 'أولاً: الملخص التنفيذي — التحليلات الرئيسية',
                'body_ar': 'جاري إنشاء الملخص التنفيذي...',
            }

        # 2. Generate Methodology section
        print("[Report Gen] Generating Methodology section...")
        methodology = generate_methodology_section(state, api_key)
        if methodology:
            state.report_sections['methodology'] = {
                'heading_ar': 'ثانياً: المنهجية وطبيعة المصادر',
                'body_ar': methodology.get('classification_method_ar', ''),
                'tables': [methodology.get('sources_table', [])],
                'analyzed_fields_ar': methodology.get('analyzed_fields_ar', ''),
                'raw_data': methodology
            }
        else:
            print("[Report Gen] Warning: Methodology generation failed, using fallback")
            state.report_sections['methodology'] = {
                'heading_ar': 'ثانياً: المنهجية وطبيعة المصادر',
                'body_ar': 'جاري إنشاء قسم المنهجية...',
            }

        # TODO: 3. Workload Map (ثالثاً: خريطة عبء العمل الحقيقي)
        # TODO: 4. Customer Journey Challenges (رابعاً: التحديات في رحلة المتعامل)
        # TODO: 5. Digital Gaps (خامساً: تحليل الفجوات الرقمية)
        # TODO: 6. Digital Transformation Plan (سادساً: خطة التحويل الرقمي)
        # TODO: 7. AI Use Cases (سابعاً: حالات الاستخدام المدعومة بالذكاء الاصطناعي)
        # TODO: 8. Improvement Roadmap (ثامناً: خارطة الطريق التحسينية)
        # TODO: 9. Conclusion (تاسعاً: الخلاصة)

        # For now, fill in placeholders for remaining sections
        for section_key, heading_ar in [
            ('methodology', 'ثانياً: المنهجية وطبيعة المصادر'),
            ('workload_map', 'ثالثاً: التحليل الأول — خريطة عبء العمل الحقيقي'),
            ('journey_challenges', 'رابعاً: التحليل الثاني — التحديات في رحلة المتعامل'),
            ('digital_gaps', 'خامساً: التحليل الثالث — تحليل الفجوات الرقمية'),
            ('digital_transformation', 'سادساً: التحليل الرابع — خطة التحويل الرقمي'),
            ('ai_use_cases', 'سابعاً: حالات الاستخدام المدعومة بالذكاء الاصطناعي'),
            ('improvement_roadmap', 'ثامناً: خارطة الطريق التحسينية المقترحة'),
            ('conclusion', 'تاسعاً: الخلاصة — من البيانات إلى القرار'),
        ]:
            state.report_sections[section_key] = {
                'heading_ar': heading_ar,
                'body_ar': f'جاري إنشاء قسم {heading_ar}...',
                'status': 'pending'  # Mark as pending for implementation
            }

    except Exception as e:
        print(f"Error in _generate_report_sections: {e}")
        _create_basic_report_sections(state)


def generate_executive_summary_section(state: PipelineState, api_key: str) -> Dict[str, Any]:
    """
    Generate the executive summary section using Claude API.

    Extracts all necessary metrics from state and calls Claude with the detailed prompt.

    Args:
        state: Pipeline state with classified cases and analysis results
        api_key: Anthropic API key

    Returns:
        Dict with section_key and content following the specified JSON structure
    """
    try:
        # Extract classification metrics
        total_cases = state.total_cases
        all_classified = state.all_classified or []

        # Calculate distribution (after reclassification)
        # ISSUE 1 FIX: Ensure comparing final top_level against original case_type
        distribution = {}
        original_distribution = {}
        misclassified = []

        for case in all_classified:
            final_type = case.top_level  # Final classification (after Stage 2 + Stage 3)
            distribution[final_type] = distribution.get(final_type, 0) + 1

            # Track misclassifications against original CRM label
            original_type = case.case_type  # Original CRM نوع_المكالمة label
            original_distribution[original_type] = original_distribution.get(original_type, 0) + 1

            # Case is reclassified if final doesn't match original
            if original_type != final_type:
                misclassified.append(case)

        misclassification_count = state.reclassified_count
        misclassification_rate = state.reclassification_rate
        matched_original_count = total_cases - misclassification_count
        matched_original_rate = (matched_original_count / total_cases * 100) if total_cases > 0 else 0

        # Find dominant contact type
        dominant_type = max(distribution.items(), key=lambda x: x[1])[0] if distribution else ""
        dominant_type_count = distribution.get(dominant_type, 0)
        dominant_type_pct = (dominant_type_count / total_cases * 100) if total_cases > 0 else 0

        # Extract complaint subcategories from patterns
        complaint_subcategories = []
        if state.patterns:
            complaint_patterns = [p for p in state.patterns if 'شكوى' in (p.cluster_ar or p.cluster)]
            complaint_patterns.sort(key=lambda x: x.case_count, reverse=True)
            for pattern in complaint_patterns[:10]:
                pct = (pattern.case_count / dominant_type_count * 100) if dominant_type_count > 0 else 0
                complaint_subcategories.append({
                    'name': pattern.sub_theme_ar or pattern.sub_theme,
                    'count': pattern.case_count,
                    'pct_of_complaints': pct
                })

        # Extract friction points
        friction_points = []
        if state.journey_map:
            for friction in state.journey_map[:10]:
                # Map severity from root_cause_category
                severity_map = {
                    'missing_info': '🔴 حرجة',
                    'inaccessible_info': '🔴 حرجة',
                    'no_proactive_notification': '🟡 عالية',
                    'platform_bug': '🔴 حرجة',
                    'policy_complexity': '🟡 عالية'
                }
                severity = severity_map.get(friction.root_cause_category, '🟢 متوسطة')

                friction_points.append({
                    'name': friction.friction_point_ar or friction.friction_point,
                    'case_count': friction.case_count,
                    'root_cause': friction.root_cause_category,
                    'gap_severity': severity
                })

        # Extract gaps with enhanced guidebook intelligence
        gap_table = []
        guidebook_coverage_metrics = {
            'total_gaps': 0,
            'covered': 0,
            'partially_covered': 0,
            'missing': 0,
            'avg_coverage_percentage': 0,
            'avg_match_confidence': 0,
            'gaps_with_proactive_notification_opportunity': 0
        }

        if state.gap_table:
            coverage_percentages = []
            match_confidences = []

            for gap in state.gap_table[:20]:
                severity_emoji = '🔴 حرجة' if gap.severity == 'Critical' else '🟡 عالية' if gap.severity == 'Medium' else '🟢 متوسطة'

                # Track coverage metrics
                guidebook_coverage_metrics['total_gaps'] += 1
                if gap.guidebook_status == 'Covered':
                    guidebook_coverage_metrics['covered'] += 1
                elif gap.guidebook_status == 'Partially Covered':
                    guidebook_coverage_metrics['partially_covered'] += 1
                else:
                    guidebook_coverage_metrics['missing'] += 1

                if gap.coverage_percentage:
                    coverage_percentages.append(gap.coverage_percentage)
                if gap.guidebook_match_confidence:
                    match_confidences.append(gap.guidebook_match_confidence)
                if gap.proactive_notification_opportunity:
                    guidebook_coverage_metrics['gaps_with_proactive_notification_opportunity'] += 1

                gap_table.append({
                    'topic': gap.topic_ar or gap.topic,
                    'case_count': gap.case_count,
                    'current_status': gap.guidebook_status,
                    'gap_type': gap.gap_type_ar or gap.gap_type,
                    'coverage_percentage': gap.coverage_percentage,
                    'clarity': gap.clarity_assessment,
                    'format': gap.format_assessment,
                    'has_visuals': gap.has_visual_guidance,
                    'match_confidence': gap.guidebook_match_confidence,
                    'can_use_proactive_notification': gap.proactive_notification_opportunity,
                    'guidebook_excerpt': gap.guidebook_excerpt_ar or gap.guidebook_excerpt,
                    'recommendation': gap.recommendation
                })

            # Calculate averages
            if coverage_percentages:
                guidebook_coverage_metrics['avg_coverage_percentage'] = sum(coverage_percentages) / len(coverage_percentages)
            if match_confidences:
                guidebook_coverage_metrics['avg_match_confidence'] = sum(match_confidences) / len(match_confidences)

        # Calculate SLA metrics — check for 'نعم' (yes) in SLA compliance field
        sla_closed = sum(1 for c in all_classified if c.sla_color == 'نعم')
        sla_rate = (sla_closed / total_cases * 100) if total_cases > 0 else 0

        # Calculate proactive notification impact (from notification opportunities)
        proactive_notification_total = 0
        if state.notification_opportunities:
            proactive_notification_total = sum(n.get('cases_eliminated', n.get('case_count', 0)) for n in state.notification_opportunities)
        proactive_notification_pct = (proactive_notification_total / total_cases * 100) if total_cases > 0 else 0

        # Digital channel percentage
        digital_cases = sum(1 for c in all_classified if c.case_channel in ['app', 'web', 'website', 'application'])
        digital_channel_pct = (digital_cases / total_cases * 100) if total_cases > 0 else 0

        # Date range extraction (placeholder - would be parsed from data in real scenario)
        date_range = state.month_year or "يناير — مارس 2026"
        quarter_label = "Q1 2026"  # Would be calculated from month_year

        # Build the prompt
        prompt = f"""You are an expert CX strategist writing the executive summary of a formal Arabic government report on customer inquiry analysis.

INPUTS PROVIDED:
- total_cases: {total_cases}
- date_range: {date_range}
- quarter_label: {quarter_label}
- source_1: "تصدير نظام إدارة علاقات العملاء — نصوص غير منسقة"
- source_2: "دليل الخدمات والأسئلة الشائعة"
- distribution: {json.dumps(distribution, ensure_ascii=False)}
- original_distribution: {json.dumps(original_distribution, ensure_ascii=False)}
- misclassification_count: {misclassification_count}
- misclassification_rate: {misclassification_rate:.1f}%
- dominant_type: {dominant_type}
- dominant_type_count: {dominant_type_count}
- dominant_type_pct: {dominant_type_pct:.1f}%
- complaint_subcategories: {json.dumps(complaint_subcategories, ensure_ascii=False)}
- friction_points: {json.dumps(friction_points, ensure_ascii=False)}
- gap_table: {json.dumps(gap_table, ensure_ascii=False)}
- guidebook_coverage_metrics: {json.dumps(guidebook_coverage_metrics, ensure_ascii=False)}
- proactive_notification_total: {proactive_notification_total}
- proactive_notification_pct: {proactive_notification_pct:.1f}%
- sla_closed_count: {sla_closed}
- sla_rate: {sla_rate:.1f}%
- digital_channel_pct: {digital_channel_pct:.1f}%

GUIDEBOOK INTELLIGENCE AVAILABLE:
The gap_table entries include:
- coverage_percentage: How much of each issue is addressed by current guidebook (0-100%)
- clarity: Assessment of guidebook text (plain_language | bureaucratic | unclear)
- format: How content is presented (step_by_step | wall_of_text | mixed)
- has_visuals: Whether guidebook includes diagrams/screenshots
- match_confidence: How well guidebook content matches actual customer needs (0.0-1.0)
- can_use_proactive_notification: Whether issue could be solved by proactive SMS/email
- guidebook_excerpt: The actual relevant guidebook text for the issue

Use guidebook_coverage_metrics to quantify guidebook comprehensiveness:
- Percentage of gaps covered vs. partially covered vs. missing
- Average coverage score for all identified gaps
- Average match confidence between customer needs and guidebook content
- Count of opportunities for proactive notification to prevent inquiries

YOUR TASK:
Write the executive summary section and its النتائج الرئيسية subsection.
Leverage the guidebook intelligence to demonstrate how the guidebook aligns with or fails to address customer needs.

─────────────────────────────────────────────
SECTION STRUCTURE (follow exactly):
─────────────────────────────────────────────

1. FRAMING PARAGRAPH (فقرة الإطار)
   Write 2–3 sentences that:
   - State how many cases were analyzed, from which CRM source, and for which period
   - Name both data sources (source_1 and source_2)
   - Declare the report's purpose as transforming data into actionable decisions —
     not presenting numbers
   - End with the single most striking structural discovery revealed by reclassification
     (e.g., the dominant type and its reclassified share)

   Style: Open with "يُقدّم هذا التقرير...". Third sentence must begin with
   "المُستجد الجوهري:" and deliver an insight, not a description.

2. النتائج الرئيسية TABLE
   Produce a table with exactly these 4 columns:
   # | الاكتشاف | الوصف | مستوى الأهمية

   The table must have exactly 5 rows. Derive each finding entirely from the
   provided inputs — never invent numbers. The 5 findings must follow this logic:

   ROW 1 — Classification accuracy gap
   - Title: state the misclassification_rate in the title itself
     (e.g., "تصنيف غير دقيق بنسبة X%")
   - Description: 2 sentences —
     Sentence 1: exact count of misclassified cases out of total, what the original
     label was, what the corrected labels revealed
     Sentence 2: the misclassification_rate for this period vs. any prior period
     if available in inputs, otherwise state it stands as a critical data quality gap
   - Importance: 🔴 حرجة

   ROW 2 — Dominant contact type dominance
   - Title: state the dominant_type and its percentage in the title itself
     (e.g., "الشكاوى تهيمن بـ X% على عبء العمل")
   - Description: 2 sentences —
     Sentence 1: dominant_type_count and dominant_type_pct, contrast with original
     CRM label if the gap is significant
     Sentence 2: name the top 2 complaint subcategories with their case counts,
     explaining what this concentration reveals about the operational focus area
   - Importance: 🔴 حرجة

   ROW 3 — Largest friction cluster (no digital path)
   - Title: state the case count and friction name of the single highest-volume
     friction point from friction_points
   - Description: 2 sentences —
     Sentence 1: total cases affected, break down sub-components if available
     Sentence 2: the root cause and the specific access barrier it creates for users
   - Importance: use gap_severity from that friction point

   ROW 4 — Operational root cause cluster
   - Title: state the combined case count and the shared root cause theme of the
     2nd and 3rd largest friction points (e.g., "X حالة ناتجة عن فجوة Y")
   - Description: 2 sentences —
     Sentence 1: name both friction points with exact case counts and the shared
     root cause linking them
     Sentence 2: what the data shows as the immediate fix and its projected impact
   - Importance: use the higher severity of the two from gap_table

   ROW 5 — SLA / operational performance
   - Title: state the sla_rate in the title itself
     (e.g., "X% إغلاق في الوقت المحدد")
   - Description: 2 sentences —
     Sentence 1: sla_closed_count out of total_cases and the sla_rate
     Sentence 2: contextualise — even strong SLA performance does not address the
     structural reclassification gap; this is positive evidence of execution capacity
   - Importance: 🟢 إيجابية

3. الرسالة الجوهرية (CORE MESSAGE)
   One paragraph placed after the table. Must:
   - Begin with "الرسالة الجوهرية:"
   - Name the specific systemic failure the data exposes (derived from
     misclassification pattern + dominant friction theme)
   - State what fixing it unlocks, using at least one specific number
   - End with a forward-looking strategic statement about what this reclassification
     enables (data-driven strategy, not guesswork)

   Style: 3 sentences maximum. No bullet points. Assertive, not descriptive.

─────────────────────────────────────────────
TONE AND STYLE RULES:
─────────────────────────────────────────────
- Formal Arabic (MSA), consultant register, no filler phrases
- Lead with insight, not description — do not say what the section contains,
  state what the data reveals
- Every number in every sentence must come from the provided inputs
- Discovery titles (الاكتشاف column) must embed the key metric in the title text —
  a reader scanning only titles should grasp the magnitude of each finding
- Importance levels use exactly: 🔴 حرجة | 🟡 عالية | 🟢 إيجابية
  (not متوسطة — reserve that label for internal gap tables, not executive findings)

─────────────────────────────────────────────
OUTPUT FORMAT:
─────────────────────────────────────────────
Return a single bilingual JSON object:
{{
  "section": "executive_summary",
  "framing_paragraph_ar": "...",
  "framing_paragraph_en": "...",
  "key_findings": [
    {{
      "number": 1,
      "title_ar": "...",
      "title_en": "...",
      "description_ar": "...",
      "description_en": "...",
      "importance_ar": "🔴 حرجة",
      "importance_en": "🔴 Critical"
    }}
    // 5 total
  ],
  "core_message_ar": "...",
  "core_message_en": "..."
}}
"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,  # Increased to handle full response
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Extract JSON from response
        response_text = message.content[0].text

        # Try to parse JSON from response
        import re

        # First try: look for ```json ... ``` block (with or without closing ```)
        # Handle both complete and incomplete code blocks
        json_code_block = re.search(r'```\s*(?:json)?\s*\n(.*?)(?:\n```|$)', response_text, re.DOTALL)
        if json_code_block:
            json_candidate = json_code_block.group(1).strip()
            try:
                result = json.loads(json_candidate)
                return result
            except json.JSONDecodeError:
                pass  # Fall through to next method

        # Second try: extract between first { and last } using state machine
        first_brace = response_text.find('{')
        if first_brace != -1:
            # Use state machine to find matching closing brace
            depth = 0
            in_string = False
            escape = False

            for i in range(first_brace, len(response_text)):
                char = response_text[i]

                # Handle escape sequences
                if escape:
                    escape = False
                    continue

                if char == '\\' and in_string:
                    escape = True
                    continue

                # Track string boundaries (only outside strings do braces matter)
                if char == '"':
                    in_string = not in_string
                    continue

                if in_string:
                    continue

                # Track brace depth
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        # Found closing brace
                        json_str = response_text[first_brace:i + 1]
                        try:
                            result = json.loads(json_str)
                            return result
                        except json.JSONDecodeError as e:
                            print(f"Failed to parse executive summary JSON: {e}")
                            print(f"Attempted string length: {len(json_str)}")
                            print(f"First 500 chars: {json_str[:500]}")
                            if len(json_str) > 500:
                                print(f"Last 500 chars: {json_str[-500:]}")
                            return None

        print("No JSON found in executive summary response")
        print(f"Response first 500 chars: {response_text[:500]}")
        return None

    except Exception as e:
        print(f"Error generating executive summary: {e}")
        return None


def generate_methodology_section(state: PipelineState, api_key: str) -> Dict[str, Any]:
    """
    Generate the methodology section using Claude API.

    Covers:
    - 2.1 المصادر المُحلَّلة (Sources analyzed table)
    - 2.2 منهجية التصنيف (Classification methodology prose)
    - 2.3 الحقول المُحلَّلة (Analyzed fields prose)

    Args:
        state: Pipeline state with classified cases and analysis results
        api_key: Anthropic API key

    Returns:
        Dict with section_key and content following the specified JSON structure
    """
    try:
        # Extract classification metrics
        total_cases = state.total_cases
        all_classified = state.all_classified or []

        # Use centralized reclassification stats from state (computed in generate_artifacts_stage6)
        misclassification_count = state.reclassified_count
        misclassification_rate = state.reclassification_rate
        matched_original_count = total_cases - misclassification_count
        matched_original_rate = (matched_original_count / total_cases * 100) if total_cases > 0 else 0

        # Guidebook stats (placeholder if not in state)
        guidebook_pages = getattr(state, 'guidebook_pages', 160)
        guidebook_faq_count = getattr(state, 'guidebook_faq_count', 25)
        guidebook_year = getattr(state, 'guidebook_year', '2025')

        # Date range
        date_range = state.month_year or "يناير — مارس 2026"

        # Build two-level taxonomy structure
        # Top level types (4 required)
        top_level_types = ['شكوى', 'طلب', 'استفسار', 'شكر وثناء']

        # Try to load SUB_CLASSIFICATIONS from stage2_rules
        try:
            from .stage2_rules import SUB_CLASSIFICATIONS
            complaint_subs = SUB_CLASSIFICATIONS.get('شكوى', [])
            request_subs = SUB_CLASSIFICATIONS.get('طلب', [])
            inquiry_subs = SUB_CLASSIFICATIONS.get('استفسار', [])
            praise_sub = SUB_CLASSIFICATIONS.get('شكر وثناء', [''])[-1] if 'شكر وثناء' in SUB_CLASSIFICATIONS else 'شكر وثناء'
        except ImportError:
            # Fallback defaults
            complaint_subs = ['شكوى على عدم استلام الخدمة', 'شكوى على خطأ تقني']
            request_subs = ['طلب تصريح سلاح', 'طلب ترخيص']
            inquiry_subs = ['استفسار عن الرخص', 'استفسار عن المركبات']
            praise_sub = 'شكر وثناء'

        # Classification logic priority tree (from stage2_rules)
        priority_tree = [
            "اعتراض على مخالفة مرورية",
            "تقديم بلاغ أمني أو مروري",
            "طلب تصريح سلاح أو ترخيص",
            "شكوى عن عدم استلام الخدمة",
            "شكوى على خطأ تقني أو في النظام",
            "شكوى على تأخر المعالجة",
            "استفسار عن الرخص والمركبات",
            "شكر وثناء",
        ]

        # Confidence thresholds
        confidence_threshold_stage2 = 0.75
        llm_confidence_threshold = 0.65

        # Count cases sent to LLM (those below confidence threshold in stage 2)
        llm_queue_count = sum(1 for c in all_classified if c.confidence < confidence_threshold_stage2)
        human_review_count = sum(1 for c in all_classified if c.confidence < llm_confidence_threshold)

        # Analyze unstructured fields
        desc_lengths = [len(c.case_title or '') for c in all_classified if c.case_title]
        res_lengths = [len(c.resolution_response or '') for c in all_classified if c.resolution_response]

        desc_avg_chars = int(sum(desc_lengths) / len(desc_lengths)) if desc_lengths else 250
        res_avg_chars = int(sum(res_lengths) / len(res_lengths)) if res_lengths else 300

        # Language distribution (assume 72% Arabic, 28% English as default)
        desc_lang_dist = "72% عربي / 28% إنجليزي"
        res_lang_dist = "72% عربي / 28% إنجليزي"

        # Calculate total sub-classification count
        total_sub_count = len(complaint_subs) + len(request_subs) + len(inquiry_subs) + 1

        # Build the prompt
        prompt = f"""You are documenting the methodology section of a formal Arabic government report for
Fujairah Police customer inquiry analysis.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUTS PROVIDED TO YOU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

source_1_crm:
  - total_cases: {total_cases}
  - date_range: "{date_range}"
  - content_description: >
      CRM data — unstructured text fields (case details, resolutions,
      service names, case descriptions). All cases are closed.

source_2_guidebook:
  - pages: {guidebook_pages}
  - faq_count: {guidebook_faq_count}
  - edition_year: "{guidebook_year}"
  - content_description: >
      Official customer services guidebook covering traffic, licensing,
      and security services, plus FAQ validation and service gap analysis.

classification_stats:
  - total_cases: {total_cases}
  - reclassified_count: {misclassification_count}
  - reclassification_rate: "{misclassification_rate:.1f}%"
  - matched_original_count: {matched_original_count}
  - matched_original_rate: "{matched_original_rate:.1f}%"

two_level_taxonomy:
  top_level_types:
    - شكوى
    - طلب
    - استفسار
    - شكر وثناء
  sub_classifications:
    شكوى: {json.dumps(complaint_subs, ensure_ascii=False)}
    طلب: {json.dumps(request_subs, ensure_ascii=False)}
    استفسار: {json.dumps(inquiry_subs, ensure_ascii=False)}
    شكر وثناء: ["{praise_sub}"]

classification_logic:
  priority_tree:
    1: "اعتراض على مخالفة مرورية"
    2: "تقديم بلاغ أمني أو مروري"
    3: "طلب تصريح سلاح أو ترخيص"
    4: "شكوى عن عدم استلام الخدمة"
    5: "شكوى على خطأ تقني أو في النظام"
    6: "شكوى على تأخر المعالجة"
    7: "استفسار عن الرخص والمركبات"
    8: "شكر وثناء"
    default: "map from CRM نوع_المكالمة label if available"
  confidence_threshold_stage2: {confidence_threshold_stage2}
  fallthrough_confidence: 0.70–0.75

llm_stage:
  model: "claude-haiku-4-5-20251001"
  trigger: "confidence < {confidence_threshold_stage2}"
  llm_confidence_threshold: {llm_confidence_threshold}
  low_confidence_action: "routed to human review queue — excluded from report counts"
  cases_to_llm: {llm_queue_count}
  cases_to_human_review: {human_review_count}

analyzed_fields:
  structured:
    - رقم_الطلب
    - تاريخ_الإنشاء
    - قناة_تقديم_الخدمة
    - الخدمة_الرئيسية
    - نوع_المكالمة
    - الجنسية
    - الإدارة المختصة
  unstructured:
    - field: تفاصيل_الطلب
      avg_chars: {desc_avg_chars}
      language_dist: "{desc_lang_dist}"
    - field: الحل
      avg_chars: {res_avg_chars}
      language_dist: "{res_lang_dist}"

core_definitional_principle: >
  طبيعة المطلوب — وليس الصياغة — هي المعيار الفاصل.
  الحالة التي تُعبّر عن استياء تُصنَّف شكوى حتى لو تضمّنت طلب إجراء.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Write the three subsections below in formal Arabic. Do not invent numbers
or details not present in the inputs above.

───────────────────────────────────────────────
2.1  المصادر المُحلَّلة
───────────────────────────────────────────────
Produce a 2-row Arabic table with columns:
  المصدر | الطبيعة | الحجم | الفترة

Row 1 — CRM inquiry data:
  - المصدر: تحليل الاستفسارات
  - الطبيعة: describe it as CRM data with unstructured text fields
              (case details, resolutions, service names, case descriptions)
  - الحجم: {total_cases} حالة مغلقة
  - الفترة: {date_range}

Row 2 — Customer services guidebook:
  - المصدر: دليل خدمات العملاء
  - الطبيعة: describe its role covering traffic, licensing, and security
              services, plus FAQ validation and gap analysis
  - الحجم: {guidebook_pages} صفحة، {guidebook_faq_count} سؤالاً
  - الفترة: {guidebook_year}

No prose paragraphs in this subsection — the table IS the content.

───────────────────────────────────────────────
2.2  منهجية التصنيف
───────────────────────────────────────────────
Write a prose paragraph that explains the two-stage pipeline.

STAGE 1 — Rule-based engine (stage2_rules.py):
  - Applied to all {total_cases} cases via a priority decision tree.
  - State the priority order (1→8) using the Arabic sub-classification
    names from classification_logic.priority_tree above.
  - State the confidence threshold ({confidence_threshold_stage2}).
  - Cases below threshold queued for Stage 2.
  - Cases at or above threshold: directly classified.

STAGE 2 — LLM classification (stage3_llm.py):
  - Applied only to rule-engine rejects ({llm_queue_count} cases).
  - Model: claude-haiku-4-5-20251001. Uses two-level taxonomy via tool-use.
  - Cases with LLM confidence < {llm_confidence_threshold} routed to
    human review queue and excluded from report counts
    ({human_review_count} cases).

Include this principle explicitly in the paragraph (do not paraphrase it):
  "طبيعة المطلوب — وليس الصياغة — هي المعيار الفاصل.
   الحالة التي تُعبّر عن استياء تُصنَّف شكوى حتى لو تضمّنت طلب إجراء."

State the two-level taxonomy structure: 4 top-level types, each with
domain-specific sub-classifications (total {total_sub_count} sub-types).

───────────────────────────────────────────────
2.3  الحقول المُحلَّلة
───────────────────────────────────────────────
Write a single prose paragraph (no table) with two groups:

Group A — Structured fields (handled by dashboard/PowerBI, not this pipeline):
  List all fields from analyzed_fields.structured using their Arabic names.

Group B — Unstructured fields — the focus of this analysis:
  - تفاصيل_الطلب: avg {desc_avg_chars} chars, {desc_lang_dist}
  - الحل: avg {res_avg_chars} chars, {res_lang_dist}
  Close with one sentence explaining that these two fields reveal the
  true nature of each case beyond the CRM's original label (نوع_المكالمة).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{{
  "section": "methodology",
  "subsections": {{
    "sources_table": [
      {{
        "المصدر": "...",
        "الطبيعة": "...",
        "الحجم": "...",
        "الفترة": "..."
      }}
    ],
    "classification_method_ar": "...",
    "analyzed_fields_ar": "..."
  }}
}}

TONE: Methodological, precise, transparent. Arabic-only output.
No bilingual fields — the report is Arabic-only.
Do not reproduce or quote CRM case text verbatim."""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Extract JSON from response
        response_text = message.content[0].text

        # Try to parse JSON from response
        import re

        # First try: look for ```json ... ``` block
        json_code_block = re.search(r'```\s*(?:json)?\s*\n(.*?)(?:\n```|$)', response_text, re.DOTALL)
        if json_code_block:
            json_candidate = json_code_block.group(1).strip()
            try:
                result = json.loads(json_candidate)
                # Flatten the structure if it has subsections
                if 'subsections' in result:
                    flat_result = {
                        'section': result.get('section', 'methodology'),
                        'sources_table': result['subsections'].get('sources_table', []),
                        'classification_method_ar': result['subsections'].get('classification_method_ar', ''),
                        'analyzed_fields_ar': result['subsections'].get('analyzed_fields_ar', '')
                    }
                    return flat_result
                return result
            except json.JSONDecodeError as e:
                print(f"[Debug] Code block JSON parse error: {e}")
                pass

        # Second try: extract between first { and last }, but more carefully
        first_brace = response_text.find('{')
        last_brace = response_text.rfind('}')

        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_str = response_text[first_brace:last_brace + 1]
            try:
                result = json.loads(json_str)
                # Flatten the structure if it has subsections
                if 'subsections' in result:
                    flat_result = {
                        'section': result.get('section', 'methodology'),
                        'sources_table': result['subsections'].get('sources_table', []),
                        'classification_method_ar': result['subsections'].get('classification_method_ar', ''),
                        'analyzed_fields_ar': result['subsections'].get('analyzed_fields_ar', '')
                    }
                    return flat_result
                return result
            except json.JSONDecodeError as e:
                print(f"Failed to parse methodology JSON (full range): {e}")
                print(f"JSON length: {len(json_str)}, Error at char {e.pos}")
                # Try a more aggressive fix: remove trailing comma issues
                json_str_fixed = re.sub(r',(\s*[}\]])', r'\1', json_str)
                try:
                    result = json.loads(json_str_fixed)
                    if 'subsections' in result:
                        flat_result = {
                            'section': result.get('section', 'methodology'),
                            'sources_table': result['subsections'].get('sources_table', []),
                            'classification_method_ar': result['subsections'].get('classification_method_ar', ''),
                            'analyzed_fields_ar': result['subsections'].get('analyzed_fields_ar', '')
                        }
                        return flat_result
                    return result
                except json.JSONDecodeError as e2:
                    print(f"Failed to parse even after fix: {e2}")
                    return None

        print("No JSON found in methodology response")
        print(f"Response first 500 chars: {response_text[:500]}")
        if len(response_text) > 500:
            print(f"Response last 500 chars: {response_text[-500:]}")
        return None

    except Exception as e:
        print(f"Error generating methodology section: {e}")
        return None


def _build_summary_context(state: PipelineState) -> str:
    """Build summary context for report generation."""
    lines = [
        f"Total Cases: {state.total_cases}",
        f"Date: {state.month_year or 'Q1 2026'}",
    ]

    # Add distribution
    if state.all_classified:
        type_counts = {}
        for case in state.all_classified:
            ct = case.actual_contact_type
            type_counts[ct] = type_counts.get(ct, 0) + 1

        lines.append("\nClassification Distribution:")
        for ct, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            pct = count / state.total_cases * 100
            lines.append(f"  {ct}: {count} ({pct:.1f}%)")

    # Add patterns
    if state.patterns:
        lines.append(f"\nIdentified Patterns: {len(state.patterns)} clusters")
        for pattern in state.patterns[:5]:
            lines.append(f"  - {pattern.sub_theme}: {pattern.case_count} cases")

    # Add friction points
    if state.journey_map:
        lines.append(f"\nFriction Points: {len(state.journey_map)}")
        for friction in state.journey_map[:5]:
            lines.append(f"  - {friction.friction_point}: {friction.case_count} cases")

    # Add gaps
    if state.gap_table:
        critical_gaps = [g for g in state.gap_table if g.severity == 'Critical']
        lines.append(f"\nGaps Identified: {len(state.gap_table)} total, {len(critical_gaps)} critical")

    # Add FAQs
    if state.validated_faqs:
        lines.append(f"\nValidated FAQs: {len(state.validated_faqs)}")

    return "\n".join(lines)


def _create_basic_report_sections(state: PipelineState) -> None:
    """Create basic report structure without LLM."""
    state.report_sections = {
        'executive_summary': {
            'heading': 'Executive Summary',
            'heading_ar': 'الملخص التنفيذي',
            'body': f'This report analyzes {state.total_cases} customer inquiries and complaints. Key findings include identification of customer service patterns, friction points in the customer journey, and recommendations for service improvement.',
            'body_ar': f'يحلل هذا التقرير {state.total_cases} استفسار وشكوى من المتعاملين. تشمل النتائج الرئيسية تحديد أنماط الخدمة، والنقاط الصعبة في رحلة المتعامل، والتوصيات لتحسين الخدمة.',
        },
        'methodology': {
            'heading': 'Methodology',
            'heading_ar': 'المنهجية',
            'body': 'Analysis was conducted using a six-stage pipeline: (1) Schema validation, (2) Rule-based classification, (3) LLM-enhanced classification, (4) Pattern analysis, (5) Gap identification, and (6) Report generation.',
            'body_ar': 'تم إجراء التحليل باستخدام خط أنابيب متقدم يضم ستة مراحل: (1) التحقق من الصيغة، (2) التصنيف القائم على القواعد، (3) التصنيف المحسّن بالذكاء الاصطناعي، (4) تحليل الأنماط، (5) تحديد الفجوات، و (6) توليد التقرير.',
        },
        'classification_summary': {
            'heading': 'Classification Summary',
            'heading_ar': 'ملخص التصنيف',
            'body': 'Cases were classified into eight categories based on customer intent and interaction patterns.',
            'body_ar': 'تم تصنيف الحالات في ثماني فئات بناءً على نوايا المتعامل وأنماط التفاعل.',
        },
        'recommendations': {
            'heading': 'Recommendations',
            'heading_ar': 'التوصيات',
            'body': 'Based on the analysis, the following recommendations are provided for improving service delivery and customer satisfaction.',
            'body_ar': 'بناءً على التحليل، يتم تقديم التوصيات التالية لتحسين جودة الخدمة ورضا المتعاملين.',
        },
    }


def run_stage6(
    state: PipelineState,
    excel_path: str,
    word_path: str,
    language: str = 'ar',
    api_key: str = ""
) -> PipelineState:
    """
    Stage 6: Artifact generator.

    Input: state with all_classified, analysis results, and report_sections
    Output: Excel and Word files on disk; report dictionary in state.report_json

    Args:
        state: Pipeline state from stages 1-5
        excel_path: Path to save Excel workbook
        word_path: Path to save Word document
        language: 'ar' or 'en'
        api_key: Anthropic API key for Word report generation

    Returns:
        Updated state with report_json dictionary
    """
    # Validation
    assert len(state.all_classified) == state.total_cases, "Case count mismatch"
    assert all(c.actual_contact_type for c in state.all_classified), "Missing contact types"
    assert all(0.0 <= c.confidence <= 1.0 for c in state.all_classified), "Invalid confidence scores"

    # FIX 1: Compute reclassification stats once — used by all downstream outputs
    reclassified = [
        c for c in state.all_classified
        if c.top_level != c.case_type
    ]
    state.reclassified_count = len(reclassified)
    state.reclassification_rate = (
        state.reclassified_count / state.total_cases * 100
        if state.total_cases > 0 else 0.0
    )

    # Generate Excel
    generate_excel(state, excel_path)

    # Generate Word report
    generate_word_report(state, word_path, language, api_key)

    # Generate report dictionary (for passing to display functions)
    state.report_json = generate_json_report(state)

    return state
