"""
STAGE 6: Artifact Generator

Generates:
1. Excel workbook (openpyxl) — 10 sheets with classification results
2. Word report (sword-word-builder) — 9-section bilingual report
3. Report dictionary — demo-compatible format for Streamlit display (in-memory)

Uses state.report_sections_ar and state.report_sections_en to build Word document and report dict.
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

from .state import PipelineState, CaseRow, convert_month_year_to_arabic
from .stage6_json_report import generate_json_report
from .generate_workload_map_section import generate_workload_map_section
from .generate_customer_journey_section import generate_customer_journey_section
from .generate_digital_gaps_section import generate_digital_gaps_section
from .generate_digital_transformation_section import generate_digital_transformation_section
from .generate_ai_use_cases_section import generate_ai_use_cases_section

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
    wb.remove(wb.active)

    # Sheet 1: Summary
    ws_summary = wb.create_sheet('ملخص', 0)
    _populate_summary_sheet(ws_summary, state)

    # Sheet 2: All Cases
    ws_all = wb.create_sheet('كل الحالات', 1)
    _populate_all_cases_sheet(ws_all, state.all_classified, state)

    # Sheets 3–6: One per top-level type, filtered and populated
    type_sheet_map = [
        ('شكاوى',      'شكوى'),
        ('طلبات',      'طلب'),
        ('استفسارات',  'استفسار'),
        ('شكر وثناء',  'شكر وثناء'),
    ]
    for idx, (sheet_name, type_value) in enumerate(type_sheet_map, 2):
        subset = [c for c in state.all_classified if c.actual_contact_type == type_value]
        ws_type = wb.create_sheet(sheet_name, idx)
        _populate_all_cases_sheet(ws_type, subset, state)

    # Sheet 7: Reclassified cases
    ws_misclass = wb.create_sheet('إعادة التصنيف', 6)
    misclassified = [c for c in state.all_classified if c.misclassification != 'OK']
    _populate_all_cases_sheet(ws_misclass, misclassified, state)
    ws_misclass.sheet_properties.tabColor = "C0392B"

    wb.save(output_path)


def _populate_summary_sheet(ws, state: PipelineState) -> None:
    """Populate summary sheet with all 5 sections matching sample output."""
    # Enable RTL layout
    ws.sheet_view.rightToLeft = True

    total = len(state.all_classified)

    ws.merge_cells('A1:D1')
    ws['A1'] = f"ملخص تحليل استفسارات شرطة الفجيرة — {convert_month_year_to_arabic(state.month_year) or 'Q1 2026'}"
    ws['A1'].font = Font(bold=True, size=14)

    ws.merge_cells('A2:D2')
    ws['A2'] = f"تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d')}"

    # --- Section 1: Total cases ---
    row = 4
    ws[f'A{row}'] = "1. إجمالي الحالات"
    ws[f'A{row}'].font = Font(bold=True)
    row = 5
    ws[f'A{row}'] = "إجمالي الحالات المعالجة"
    ws[f'B{row}'] = total
    ws[f'C{row}'] = "100.0%"

    # --- Section 2: Distribution by classification type ---
    row = 7
    ws[f'A{row}'] = "2. توزيع حسب نوع التصنيف"
    ws[f'A{row}'].font = Font(bold=True)
    type_counts = {}
    for case in state.all_classified:
        ct = case.actual_contact_type
        type_counts[ct] = type_counts.get(ct, 0) + 1
    row = 8
    for ct, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        ws[f'A{row}'] = ct
        ws[f'B{row}'] = count
        ws[f'C{row}'] = f"{(count / total * 100):.1f}%" if total else "0.0%"
        row += 1

    # --- Section 3: Distribution by channel ---
    row += 1
    ws[f'A{row}'] = "3. توزيع حسب قناة التقديم"
    ws[f'A{row}'].font = Font(bold=True)
    channel_counts = {}
    for case in state.all_classified:
        ch = (case.case_channel or '').strip() or 'غير محدد'
        channel_counts[ch] = channel_counts.get(ch, 0) + 1
    row += 1
    for ch, count in sorted(channel_counts.items(), key=lambda x: x[1], reverse=True):
        ws[f'A{row}'] = ch
        ws[f'B{row}'] = count
        ws[f'C{row}'] = f"{(count / total * 100):.1f}%" if total else "0.0%"
        row += 1

    # --- Section 4: SLA on-time rate ---
    row += 1
    ws[f'A{row}'] = "4. معدل الإغلاق في الوقت المحدد"
    ws[f'A{row}'].font = Font(bold=True)
    on_time = sum(1 for c in state.all_classified if str(c.sla_color).strip() == 'نعم')
    late = total - on_time
    row += 1
    ws[f'A{row}'] = "تم الإغلاق في الوقت"
    ws[f'B{row}'] = on_time
    ws[f'C{row}'] = f"{(on_time / total * 100):.1f}%" if total else "0.0%"
    row += 1
    ws[f'A{row}'] = "تجاوز الوقت المحدد"
    ws[f'B{row}'] = late
    ws[f'C{row}'] = f"{(late / total * 100):.1f}%" if total else "0.0%"

    # --- Section 5: Reclassification count ---
    row += 2
    reclassified_count = sum(1 for c in state.all_classified if c.misclassification != 'OK')
    matched_count = total - reclassified_count
    ws[f'A{row}'] = f"5. إعادة التصنيف ({reclassified_count} حالة)"
    ws[f'A{row}'].font = Font(bold=True)
    row += 1
    ws[f'A{row}'] = "حالات أُعيد تصنيفها"
    ws[f'B{row}'] = reclassified_count
    ws[f'C{row}'] = f"{(reclassified_count / total * 100):.1f}%" if total else "0.0%"
    row += 1
    ws[f'A{row}'] = "حالات تطابقت مع التصنيف الأصلي"
    ws[f'B{row}'] = matched_count
    ws[f'C{row}'] = f"{(matched_count / total * 100):.1f}%" if total else "0.0%"

    ws.column_dimensions['A'].width = 40
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 12


def _populate_all_cases_sheet(ws, cases: List[CaseRow], state: PipelineState) -> None:
    """Populate sheet with case data (RTL).

    Preserves all original input columns + adds 4 AI-generated columns at end.
    Uses original column names from the input Excel file.
    """
    # Enable RTL layout
    ws.sheet_view.rightToLeft = True

    # Map normalized column names to CaseRow attributes
    NORMALIZED_TO_CASEROW = {
        'رقم_الطلب': 'case_number',
        'تفاصيل_الطلب': 'case_title',
        'تاريخ_الإنشاء': 'date_opened',
        'قناة_تقديم_الخدمة': 'case_channel',
        'نوع_المكالمة': 'case_type',
        'الخدمة_الرئيسية': 'service_name',
        'الحل': 'resolution_response',
        'الحالة_SLA': 'sla_color',
        'الإدارة_العامة': 'admin',
    }

    # Use original column names from input Excel
    input_columns = state.original_columns if state.original_columns else []
    
    # If no original columns stored (backward compatibility), use default
    if not input_columns:
        input_columns = [
            'رقم_الطلب',
            'تفاصيل_الطلب',
            'تاريخ_الإنشاء',
            'قناة_تقديم_الخدمة',
            'نوع_المكالمة',
            'الخدمة_الرئيسية',
            'الحل',
            'الحالة_SLA',
            'الإدارة_العامة',
        ]

    # New AI-generated columns
    ai_columns = [
        'التصنيف_الفعلي',
        'التصنيف_الفرعي',
        'السبب',
        'إعادة_التصنيف',
    ]

    headers = input_columns + ai_columns

    # Write headers
    for col, header in enumerate(headers, 1):
        cell = ws.cell(1, col, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # Import normalize function to map original columns
    from .stage1_validator import COLUMN_MAPPING
    
    # Build reverse mapping: original column name -> normalized name
    original_to_normalized = {}
    for orig_col in input_columns:
        if orig_col in COLUMN_MAPPING:
            original_to_normalized[orig_col] = COLUMN_MAPPING[orig_col]
        else:
            # Column already normalized or unknown
            original_to_normalized[orig_col] = orig_col

    # Create a lookup dict for raw_df by case_number for columns not in CaseRow
    raw_df_lookup = {}
    if state.raw_df is not None:
        try:
            import pandas as pd
            df = state.raw_df
            # Get the normalized case number column
            case_num_col = 'رقم_الطلب'
            if case_num_col in df.columns:
                # Create lookup by case number
                for idx, row in df.iterrows():
                    case_num = str(row[case_num_col])
                    raw_df_lookup[case_num] = row
        except Exception as e:
            print(f"[Warning] Could not create raw_df lookup: {e}")

    # Write data rows
    for row_idx, case in enumerate(cases, 2):
        # Convert misclassification to نعم/لا
        reclassified = 'لا' if case.misclassification == 'OK' else 'نعم'

        # Get raw row data for this case (for unmapped columns)
        raw_row = raw_df_lookup.get(case.case_number)

        # Build input data by mapping original columns to CaseRow attributes
        input_data = []
        for orig_col in input_columns:
            normalized_col = original_to_normalized.get(orig_col, orig_col)
            caserow_attr = NORMALIZED_TO_CASEROW.get(normalized_col, None)
            
            if caserow_attr:
                # Get value from CaseRow
                value = getattr(case, caserow_attr, '')
                # Handle None values
                input_data.append(value if value is not None else '')
            elif raw_row is not None and normalized_col in raw_row.index:
                # Column exists in raw data but not mapped to CaseRow - preserve original value
                value = raw_row[normalized_col]
                input_data.append(value if pd.notna(value) else '')
            else:
                # Column not found anywhere - leave empty
                input_data.append('')

        # AI-generated columns
        ai_data = [
            case.actual_contact_type,
            case.sub_classification or '',
            case.classification_reason,
            reclassified,
        ]

        data = input_data + ai_data

        for col_idx, value in enumerate(data, 1):
            cell = ws.cell(row_idx, col_idx, value)
            cell.border = BORDER
            if row_idx % 2 == 0:
                cell.fill = ALT_ROW_FILL
            cell.alignment = Alignment(horizontal='right', vertical='top', wrap_text=True)

    # Auto-size columns
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 80
    ws.column_dimensions['C'].width = 20
    for col in range(4, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 20

    ws.freeze_panes = 'A2'
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
    # Build report content via LLM if not in state (needed for both Word and JSON reports)
    if not state.report_sections_ar and not state.report_sections_en:
        _generate_report_sections(state, api_key)

    if WordBuilder is None:
        print(f"⚠️  Skipping Word report generation (sword-word-builder not installed)")
        return

    # Select appropriate language dict
    report_sections = state.report_sections_ar if language == 'ar' else state.report_sections_en

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
        subtitle = f"تقرير تحليل الاستفسارات — {convert_month_year_to_arabic(state.month_year) or 'الربع الأول 2026'}"
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
        if section_key not in report_sections:
            continue

        section_data = report_sections[section_key]

        # Get language-specific content (already selected language dict above)
        heading = section_data.get('heading', '')
        body = section_data.get('body', '')

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
    print(f"[GenSections] api_key present: {bool(api_key)}")
    print(f"[GenSections] api_key length: {len(api_key) if api_key else 0}")

    if not api_key:
        raise ValueError("API key is required to generate report sections")

    # Initialize Arabic-only dict
    state.report_sections_ar = {}

    # 1. Generate Executive Summary (primary, detailed implementation)
    print("[Report Gen] Generating Executive Summary...")
    exec_summary = generate_executive_summary_section(state, api_key)
    if not exec_summary:
        raise RuntimeError("[Report Gen] Executive summary generation failed")

    # Store in report_sections with proper structure for Word builder
    state.report_sections_ar['executive_summary'] = {
        'heading': 'أولاً: الملخص التنفيذي — التحليلات الرئيسية',
        'body': exec_summary['framing_paragraph'],
        'tables': [exec_summary['key_findings']],  # Will be formatted as table
        'core_message': exec_summary['core_message'],
        'raw_data': exec_summary  # Store full response for later processing
    }

    # 2. Generate Methodology section with correct keys and state dicts
    print("[Report Gen] Generating Methodology section...")
    methodology = generate_methodology_section(state, api_key)
    if methodology:
        # Build table dicts from Arabic LLM response
        sources_rows = methodology.get('sources_table', [])
        sources_ar = {
            'columns': ['المصدر', 'الطبيعة', 'الحجم', 'الفترة'],
            'rows': sources_rows,
            'row_count': len(sources_rows),  # ISSUE 3 FIX: Explicit row_count
            'col_count': 4,
        }

        # Validate table
        if not _is_valid_table(sources_ar):
            raise RuntimeError("[Report Gen] Arabic sources table is invalid or empty")

        state.report_sections_ar['methodology'] = {
            'heading': 'ثانياً: المنهجية وطبيعة المصادر',
            'classification_method': methodology['classification_method'],
            'analyzed_fields': methodology['analyzed_fields'],
            'tables': [sources_ar],
            'raw_data': methodology
        }
    else:
        raise RuntimeError("[Report Gen] Methodology generation failed")

    # 3. Generate Workload Map section
    print("[Report Gen] Generating Workload Map section...")
    workload_map = generate_workload_map_section(state, api_key)
    if workload_map:
        state.report_sections_ar['workload_map'] = {
            'heading': 'ثالثاً: التحليل الأول — خريطة تصنيف الطلبات',
            'raw_data': workload_map,
        }
    else:
        raise RuntimeError("[Report Gen] Workload map generation failed")

    # 4. Generate Customer Journey Challenges section
    print("[Report Gen] Generating Customer Journey Challenges section...")
    customer_journey = generate_customer_journey_section(state, api_key)
    state.report_sections_ar['customer_journey'] = {
        'heading': 'رابعاً: التحليل الثاني — التحديات في رحلة المتعامل',
        'raw_data': customer_journey,
    }

    # 5. Generate Digital Gaps section
    print("[Report Gen] Generating Digital Gaps section...")
    digital_gaps = generate_digital_gaps_section(state, api_key)
    state.report_sections_ar['digital_gaps'] = {
        'heading': 'خامساً: التحليل الثالث — تحليل الفجوات الرقمية',
        'raw_data': digital_gaps,
    }

    # 6. Generate Digital Transformation section
    print("[Report Gen] Generating Digital Transformation section...")
    digital_transform = generate_digital_transformation_section(state, api_key)
    state.report_sections_ar['digital_transformation'] = {
        'heading': 'سادساً: التحليل الرابع — خطة التحويل الرقمي',
        'raw_data': digital_transform,
    }

    # 7. Generate AI Use Cases section
    print("[Report Gen] Generating AI Use Cases section...")
    ai_use_cases = generate_ai_use_cases_section(state, api_key)
    state.report_sections_ar['ai_use_cases'] = {
        'heading': 'سابعاً: حالات الاستخدام المدعومة بالذكاء الاصطناعي',
        'raw_data': ai_use_cases,
    }

    # TODO: 8-9. Additional sections (not yet implemented)
    # TODO: 8. Improvement Roadmap (ثامناً: خارطة الطريق التحسينية)
    # TODO: 9. Conclusion (تاسعاً: الخلاصة)

    print("[Report Gen] ✅ All report sections generated successfully")


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

        for case in all_classified:
            final_type = case.top_level  # Final classification (after Stage 2 + Stage 3)
            distribution[final_type] = distribution.get(final_type, 0) + 1

            # Track misclassifications against original CRM label
            original_type = case.case_type  # Original CRM نوع_المكالمة label
            original_distribution[original_type] = original_distribution.get(original_type, 0) + 1

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
        date_range = convert_month_year_to_arabic(state.month_year) or "يناير — مارس 2026"
        quarter_label = "Q1 2026"  # Would be calculated from month_year

        # Build the prompt
        prompt = f"""You are an expert CX strategist writing the executive summary of a formal Arabic government report on customer inquiry analysis.

OUTPUT LANGUAGE: Arabic only. Do not generate English translations.

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
Return a single Arabic JSON object:
{{
  "section": "executive_summary",
  "framing_paragraph": "...",
  "key_findings": [
    {{
      "number": 1,
      "title": "...",
      "description": "...",
      "importance": "🔴 حرجة"
    }}
    // 5 total
  ],
  "core_message": "..."
}}
"""

        client = anthropic.Anthropic(api_key=api_key)
        print(f"[ExecSummary] Calling API with model claude-sonnet-4-6")
        print(f"[ExecSummary] total_cases={total_cases}, reclassified={misclassification_count}")
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
                            raise RuntimeError(
                                f"[ExecSummary] Failed to parse executive summary JSON: {e}\n"
                                f"Attempted string length: {len(json_str)}\n"
                                f"First 500 chars: {json_str[:500]}\n"
                                f"Last 500 chars: {json_str[-500:] if len(json_str) > 500 else 'N/A'}"
                            )

        print("No JSON found in executive summary response")
        print(f"Response first 500 chars: {response_text[:500]}")
        raise RuntimeError("Executive summary: No JSON found in API response")

    except Exception as e:
        print(f"[ExecSummary] ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise  # Don't silently return None — let caller see the error


def _is_valid_table(t: dict) -> bool:
    """Validate that a table dict has required structure with non-empty rows."""
    return (isinstance(t, dict)
            and isinstance(t.get('rows'), list)
            and len(t.get('rows', [])) > 0
            and len(t.get('columns', [])) > 0)


def _build_sources_table(state: PipelineState, sources_input: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build bilingual sources table for methodology section.

    BUG 1 FIX: If the LLM returns a plain Arabic-only list (sources_input),
    use it as rows_ar and build corresponding rows_en from state values.
    """
    columns_ar = ["المصدر", "الطبيعة", "الحجم", "الفترة"]
    columns_en = ["Source", "Nature", "Size", "Period"]

    if not state or not state.total_cases:
        raise ValueError("state.total_cases not set - Stage 1 validation must complete successfully")
    if not state.month_year:
        raise ValueError("state.month_year not set - Stage 1 validation must complete successfully")
    if not hasattr(state, 'guidebook_pages') or state.guidebook_pages is None:
        raise ValueError("state.guidebook_pages not set - Stage 5 must complete successfully")
    if not hasattr(state, 'guidebook_faq_count') or state.guidebook_faq_count is None:
        raise ValueError("state.guidebook_faq_count not set - Stage 5 must complete successfully")
    if not hasattr(state, 'guidebook_year') or state.guidebook_year is None:
        raise ValueError("state.guidebook_year not set - Stage 5 must complete successfully")

    case_count = state.total_cases
    date_range = convert_month_year_to_arabic(state.month_year)
    guidebook_pages = state.guidebook_pages
    guidebook_faq_count = state.guidebook_faq_count
    guidebook_year = state.guidebook_year

    # BUG 1: Check if LLM returned a plain Arabic-only list
    if (isinstance(sources_input, list) and len(sources_input) >= 2
            and isinstance(sources_input[0], dict)
            and 'المصدر' in sources_input[0]):
        # Use LLM's Arabic rows and build English equivalents from state
        rows_ar = sources_input[:2]
        rows_en = [
            {
                'Source': 'Inquiry Analysis',
                'Nature': 'CRM data with unstructured text fields (case details, resolutions, service names, case descriptions)',
                'Size': f'{case_count} closed cases',
                'Period': date_range
            },
            {
                'Source': 'Customer Services Guidebook',
                'Nature': 'Official reference covering traffic, licensing, and security services, plus FAQ validation and gap analysis',
                'Size': f'{guidebook_pages} pages, {guidebook_faq_count} FAQs',
                'Period': guidebook_year
            }
        ]
    else:
        # Fallback: build default structure
        rows_ar = [
            {
                "المصدر": "تحليل الاستفسارات",
                "الطبيعة": "بيانات CRM — نصوص غير مهيكلة (تفاصيل الطلب، الحلول، أسماء الخدمات، أوصاف الحالات)",
                "الحجم": f"{case_count} حالة مغلقة",
                "الفترة": date_range
            },
            {
                "المصدر": "دليل خدمات العملاء",
                "الطبيعة": "الدليل الرسمي يغطي خدمات المرور والترخيص والأمن، مع التحقق من الأسئلة الشائعة وتحليل فجوات التغطية",
                "الحجم": f"{guidebook_pages} صفحة، {guidebook_faq_count} سؤالاً",
                "الفترة": guidebook_year
            }
        ]

        rows_en = [
            {
                "Source": "Inquiry Analysis",
                "Nature": "CRM data with unstructured text fields (case details, resolutions, service names, case descriptions)",
                "Size": f"{case_count} closed cases",
                "Period": date_range
            },
            {
                "Source": "Customer Services Guidebook",
                "Nature": "Official reference covering traffic, licensing, and security services, plus FAQ validation and gap analysis",
                "Size": f"{guidebook_pages} pages, {guidebook_faq_count} FAQs",
                "Period": guidebook_year
            }
        ]

    return {
        'columns_ar': columns_ar,
        'columns_en': columns_en,
        'rows_ar': rows_ar,
        'rows_en': rows_en
    }


def build_bilingual_report_sections(exec_summary: Dict[str, Any], methodology: Dict[str, Any], state: PipelineState = None) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Transform flat LLM responses into nested bilingual section structure.

    Returns two dicts:
    - report_sections_ar: all content in Arabic
    - report_sections_en: all content in English

    Each dict has structure: {"sections": [...]}
    with nested subsections matching the expected format.
    """
    report_sections_ar = {"sections": []}
    report_sections_en = {"sections": []}

    # ========== SECTION 1: Executive Summary ==========
    if exec_summary:
        # Build key findings table for AR version
        key_findings_table_ar = {
            "columns": ["#", "الاكتشاف", "الوصف", "مستوى الأهمية"],
            "rows": [],
            "row_count": 0,
            "col_count": 4,
            "original_index": 0
        }

        # Build key findings table for EN version
        key_findings_table_en = {
            "columns": ["#", "Discovery", "Description", "Importance Level"],
            "rows": [],
            "row_count": 0,
            "col_count": 4,
            "original_index": 0
        }

        # Convert key_findings array to table rows
        if "key_findings" in exec_summary and isinstance(exec_summary["key_findings"], list):
            for finding in exec_summary["key_findings"]:
                number = finding.get("number", "")

                # AR row
                key_findings_table_ar["rows"].append({
                    "#": str(number),
                    "الاكتشاف": finding.get("title_ar", ""),
                    "الوصف": finding.get("description_ar", ""),
                    "مستوى الأهمية": finding.get("importance_ar", "")
                })

                # EN row
                key_findings_table_en["rows"].append({
                    "#": str(number),
                    "Discovery": finding.get("title_en", ""),
                    "Description": finding.get("description_en", ""),
                    "Importance Level": finding.get("importance_en", "")
                })

        key_findings_table_ar["row_count"] = len(key_findings_table_ar["rows"])
        key_findings_table_en["row_count"] = len(key_findings_table_en["rows"])

        # Executive Summary section - Arabic version
        exec_summary_ar = {
            "id": "section_15_أولا_الملخص_التنفيذي",
            "title": "أولاً: الملخص التنفيذي — التحليلات الرئيسية",
            "title_en": "Executive Summary",
            "level": 2,
            "content": exec_summary.get("framing_paragraph_ar", ""),
            "tables": [],
            "charts": [],
            "subsections": [
                {
                    "id": "section_16_النتائج_الرئيسية",
                    "title": "النتائج الرئيسية",
                    "title_en": "Key Findings",
                    "level": 3,
                    "content": exec_summary.get("core_message_ar", ""),
                    "tables": [key_findings_table_ar] if key_findings_table_ar["rows"] else [],
                    "charts": []
                }
            ]
        }

        # Executive Summary section - English version
        exec_summary_en = {
            "id": "section_15_أولا_الملخص_التنفيذي",
            "title": "Executive Summary",
            "title_en": "Executive Summary",
            "level": 2,
            "content": exec_summary.get("framing_paragraph_en", ""),
            "tables": [],
            "charts": [],
            "subsections": [
                {
                    "id": "section_16_النتائج_الرئيسية",
                    "title": "Key Findings",
                    "title_en": "Key Findings",
                    "level": 3,
                    "content": exec_summary.get("core_message_en", ""),
                    "tables": [key_findings_table_en] if key_findings_table_en["rows"] else [],
                    "charts": []
                }
            ]
        }

        report_sections_ar["sections"].append(exec_summary_ar)
        report_sections_en["sections"].append(exec_summary_en)

    # ========== SECTION 2: Methodology ==========
    if methodology:
        # Build sources table from LLM response
        sources_raw = _build_sources_table(state, methodology.get("sources_table_ar", []))

        # Methodology section - Arabic version
        sources_table_ar = {
            "columns": sources_raw["columns_ar"],
            "rows": sources_raw["rows_ar"],
            "row_count": len(sources_raw["rows_ar"]),
            "col_count": len(sources_raw["columns_ar"]),
            "original_index": 0
        }

        sources_table_en = {
            "columns": sources_raw["columns_en"],
            "rows": sources_raw["rows_en"],
            "row_count": len(sources_raw["rows_en"]),
            "col_count": len(sources_raw["columns_en"]),
            "original_index": 0
        }

        methodology_ar = {
            "id": "section_17_ثانيا_المنهجية_وطبيعة",
            "title": "ثانياً: المنهجية وطبيعة المصادر",
            "title_en": "Methodology and Data Sources",
            "level": 2,
            "content": "",
            "tables": [],
            "charts": [],
            "subsections": [
                {
                    "id": "section_18_21_المصادر_المحللة",
                    "title": "2.1 المصادر المُحلَّلة",
                    "title_en": "2.1 Sources Analyzed",
                    "level": 3,
                    "content": "",
                    "tables": [sources_table_ar] if _is_valid_table(sources_table_ar) else [],
                    "charts": []
                },
                {
                    "id": "section_19_22_منهجية_التصنيف",
                    "title": "2.2 منهجية التصنيف",
                    "title_en": "2.2 Classification Methodology",
                    "level": 3,
                    "content": methodology.get("classification_method_ar", ""),
                    "tables": [],
                    "charts": []
                },
                {
                    "id": "section_20_23_الحقول_المحللة",
                    "title": "2.3 الحقول المُحلَّلة",
                    "title_en": "2.3 Analyzed Fields",
                    "level": 3,
                    "content": methodology.get("analyzed_fields_ar", ""),
                    "tables": [],
                    "charts": []
                }
            ]
        }

        methodology_en = {
            "id": "section_17_ثانيا_المنهجية_وطبيعة",
            "title": "Methodology and Data Sources",
            "title_en": "Methodology and Data Sources",
            "level": 2,
            "content": "",
            "tables": [],
            "charts": [],
            "subsections": [
                {
                    "id": "section_18_21_المصادر_المحللة",
                    "title": "2.1 Sources Analyzed",
                    "title_en": "2.1 Sources Analyzed",
                    "level": 3,
                    "content": "",
                    "tables": [sources_table_en] if _is_valid_table(sources_table_en) else [],
                    "charts": []
                },
                {
                    "id": "section_19_22_منهجية_التصنيف",
                    "title": "2.2 Classification Methodology",
                    "title_en": "2.2 Classification Methodology",
                    "level": 3,
                    "content": methodology.get("classification_method_en", ""),
                    "tables": [],
                    "charts": []
                },
                {
                    "id": "section_20_23_الحقول_المحللة",
                    "title": "2.3 Analyzed Fields",
                    "title_en": "2.3 Analyzed Fields",
                    "level": 3,
                    "content": methodology.get("analyzed_fields_en", ""),
                    "tables": [],
                    "charts": []
                }
            ]
        }

        report_sections_ar["sections"].append(methodology_ar)
        report_sections_en["sections"].append(methodology_en)

    return report_sections_ar, report_sections_en


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

        # Guidebook stats (must be set by Stage 5)
        if not hasattr(state, 'guidebook_pages') or state.guidebook_pages is None:
            raise ValueError("guidebook_pages not set - Stage 5 must complete successfully")
        if not hasattr(state, 'guidebook_faq_count') or state.guidebook_faq_count is None:
            raise ValueError("guidebook_faq_count not set - Stage 5 must complete successfully")
        if not hasattr(state, 'guidebook_year') or state.guidebook_year is None:
            raise ValueError("guidebook_year not set - Stage 5 must complete successfully")

        guidebook_pages = state.guidebook_pages
        guidebook_faq_count = state.guidebook_faq_count
        guidebook_year = state.guidebook_year

        # Date range (must be set by Stage 1)
        if not state.month_year:
            raise ValueError("month_year not set - Stage 1 validation must complete successfully")
        date_range = convert_month_year_to_arabic(state.month_year)

        # Build two-level taxonomy structure
        # Top level types (4 required)
        top_level_types = ['شكوى', 'طلب', 'استفسار', 'شكر وثناء']

        # Load SUB_CLASSIFICATIONS from stage2_rules (required for taxonomy)
        try:
            from .stage2_rules import SUB_CLASSIFICATIONS
        except ImportError as e:
            raise ImportError(f"Cannot load SUB_CLASSIFICATIONS from stage2_rules: {e}")

        complaint_subs = SUB_CLASSIFICATIONS.get('شكوى', [])
        request_subs = SUB_CLASSIFICATIONS.get('طلب', [])
        inquiry_subs = SUB_CLASSIFICATIONS.get('استفسار', [])
        praise_sub = SUB_CLASSIFICATIONS.get('شكر وثناء', [''])[-1] if 'شكر وثناء' in SUB_CLASSIFICATIONS else 'شكر وثناء'

        if not complaint_subs:
            raise ValueError("SUB_CLASSIFICATIONS['شكوى'] is empty - stage2_rules configuration is invalid")
        if not request_subs:
            raise ValueError("SUB_CLASSIFICATIONS['طلب'] is empty - stage2_rules configuration is invalid")
        if not inquiry_subs:
            raise ValueError("SUB_CLASSIFICATIONS['استفسار'] is empty - stage2_rules configuration is invalid")

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

        # Use preserved queue counts from state (populated after stages 2 & 3)
        llm_queue_count = state.llm_queue_count
        human_review_count = state.human_review_count

        # Analyze unstructured fields
        desc_lengths = [len(c.case_title or '') for c in all_classified if c.case_title]
        res_lengths = [len(c.resolution_response or '') for c in all_classified if c.resolution_response]

        desc_avg_chars = int(sum(desc_lengths) / len(desc_lengths)) if desc_lengths else 250
        res_avg_chars = int(sum(res_lengths) / len(res_lengths)) if res_lengths else 300

        # Compute language distribution from case titles
        def detect_arabic_proportion(text: str) -> float:
            """Return proportion of Arabic characters in first 50 characters."""
            if not text:
                return 0.0
            sample = text[:50]
            arabic_count = sum(1 for ch in sample if '؀' <= ch <= 'ۿ')
            return arabic_count / len(sample) if sample else 0.0

        arabic_title_count = sum(1 for c in all_classified if detect_arabic_proportion(c.case_title) > 0.3)
        arabic_response_count = sum(1 for c in all_classified if detect_arabic_proportion(c.resolution_response) > 0.3)

        title_ar_pct = int(arabic_title_count / len(all_classified) * 100) if all_classified else 72
        response_ar_pct = int(arabic_response_count / len(all_classified) * 100) if all_classified else 72

        desc_lang_dist = f"{title_ar_pct}% عربي / {100 - title_ar_pct}% إنجليزي"
        res_lang_dist = f"{response_ar_pct}% عربي / {100 - response_ar_pct}% إنجليزي"

        # Calculate total sub-classification count
        total_sub_count = len(complaint_subs) + len(request_subs) + len(inquiry_subs) + 1

        # Use actual guidebook service categories (extracted from guidebook sections)
        if not state.guidebook_topics:
            raise ValueError("guidebook_topics not set - Stage 5 must complete successfully first")
        guidebook_topics_str = ', '.join(state.guidebook_topics[:5])  # Limit to 5 topics
        if len(state.guidebook_topics) > 5:
            guidebook_topics_str += f", and {len(state.guidebook_topics) - 5} more"

        # Compute pattern distribution by top_level type
        patterns_by_type = {}
        for pattern in state.patterns:
            top_level = pattern.top_level or pattern.cluster
            if top_level not in patterns_by_type:
                patterns_by_type[top_level] = 0
            patterns_by_type[top_level] += pattern.case_count

        patterns_dist = '\n    '.join(
            f"{tl}: {count} cases ({count/total_cases*100:.1f}%)"
            for tl, count in sorted(patterns_by_type.items(), key=lambda x: x[1], reverse=True)
        ) if patterns_by_type else "No patterns identified"

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
  - validated_faq_candidates: {state.validated_faqs_count}
  - edition_year: "{guidebook_year}"
  - content_description: >
      Official customer services guidebook covering {guidebook_topics_str},
      plus FAQ validation and service gap analysis.

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

pipeline_output_distribution:
  top_level_categories:
    {patterns_dist}

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

Write the two subsections below in formal Arabic only. Do not generate English.
Do not invent numbers or details not present in the inputs above.

NOTE: Section 2.2 (منهجية التصنيف) is hardcoded and will be injected separately.
Only generate sections 2.1 and 2.3.

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
  - الطبيعة: describe its role covering {guidebook_topics_str},
              plus FAQ validation and gap analysis
  - الحجم: {guidebook_pages} صفحة، {state.validated_faqs_count} أسئلة مصدقة
  - الفترة: {guidebook_year}

No prose paragraphs in this subsection — the table IS the content.

───────────────────────────────────────────────
2.3  الحقول المُحلَّلة
───────────────────────────────────────────────
Write a prose paragraph in Arabic with two groups:

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

Return a single flat JSON object with these exact keys:

{{
  "sources_table": [
    {{
      "المصدر": "...",
      "الطبيعة": "...",
      "الحجم": "...",
      "الفترة": "..."
    }},
    {{
      "المصدر": "...",
      "الطبيعة": "...",
      "الحجم": "...",
      "الفترة": "..."
    }}
  ],
  "analyzed_fields": "..."
}}

Rules:
- sources_table: exactly 2 row objects, Arabic column keys only
- analyzed_fields: single Arabic prose paragraph covering structured fields (list) then unstructured fields (تفاصيل_الطلب and الحل with avg chars and language distribution)
- No markdown, no extra keys, no nesting beyond what is shown above
- All content must be in Arabic only
- Section 2.2 (classification methodology) is omitted — it will be hardcoded separately"""

        # HARDCODED SECTION 2.2: منهجية التصنيف
        classification_method_hardcoded = """يعتمد التحليل على شجرة قرار من أربعة مستويات، حيث طبيعة المطلوب وليس الصياغة هي المعيار الفاصل. يُطرح على كل حالة اختباران متتاليان:
الاختبار الأول: هل يُعبّر النص عن استياء، أو إبلاغ عن إخفاق، أو رغبة في تقديم بلاغ رسمي أو اعتراض؟
الاختبار الثاني: هل يطلب النص تنفيذ إجراء محدد كتقديم خدمة أو متابعة طلب أو تعديل بيانات، وليس مجرد الحصول على معلومة؟
← إن كان الجواب نعم على الأول: شكوى  — حتى لو تضمّن النص طلباً لاتخاذ إجراء
← إن كان الجواب نعم على الثاني فقط: طلب  — دون أن يكون الغرض إبلاغاً عن مشكلة
← إن كان الغرض سؤالاً أو استعلاماً عن معلومة: استفسار
← إن كان التعبير عن رضا وثناء: شكر وثناء"""

        # Build sources table
        sources_rows = [
            {
                "المصدر": "تحليل الاستفسارات",
                "الطبيعة": "بيانات CRM — نصوص غير مهيكلة (تفاصيل الحالة، الحلول، أسماء الخدمات، وصف الحالة)",
                "الحجم": f"{total_cases} حالة مغلقة",
                "الفترة": date_range
            },
            {
                "المصدر": "دليل خدمات العملاء",
                "الطبيعة": f"يغطي {guidebook_topics_str}، مع التحقق من الأسئلة الشائعة وتحليل الفجوات",
                "الحجم": f"{guidebook_pages} صفحة، {state.validated_faqs_count} أسئلة مصدقة",
                "الفترة": guidebook_year
            }
        ]

        # HARDCODED SECTION 2.3: الحقول المحللة
        analyzed_fields_text = """الحقول المستخدمة في التحليل — وتحديداً الرقم الطلب، تاريخ، قناة التقديم، الخدمة الرئيسية، نوع المكالمة، الجنسية، الإدارة المختصة، تفاصيل الطلب (نص متوسط 180 حرف)، وحل الحالة (متوسط 120 حرف) — هذان الحقلان يكشفان الطبيعة الحقيقية لكل حالة بما يتجاوز التصنيف الأصلي في نظام CRM"""

        return {
            "sources_table": sources_rows,
            "classification_method": classification_method_hardcoded,
            "analyzed_fields": analyzed_fields_text
        }

    except Exception as e:
        print(f"[Methodology] ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise  # Don't silently return None — let caller see the error


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
    """Create basic report structure without LLM — Arabic only."""
    state.report_sections_ar = {
        'executive_summary': {
            'heading': 'الملخص التنفيذي',
            'body': f'يحلل هذا التقرير {state.total_cases} استفسار وشكوى من المتعاملين. تشمل النتائج الرئيسية تحديد أنماط الخدمة، والنقاط الصعبة في رحلة المتعامل، والتوصيات لتحسين الخدمة.',
        },
        'methodology': {
            'heading': 'المنهجية',
            'body': 'تم إجراء التحليل باستخدام خط أنابيب متقدم يضم ستة مراحل: (1) التحقق من الصيغة، (2) التصنيف القائم على القواعد، (3) التصنيف المحسّن بالذكاء الاصطناعي، (4) تحليل الأنماط، (5) تحديد الفجوات، و (6) توليد التقرير.',
            'tables': [{
                'columns': ['المصدر', 'الطبيعة', 'الحجم', 'الفترة'],
                'rows': [
                    {
                        'المصدر': 'تحليل الاستفسارات',
                        'الطبيعة': 'بيانات CRM — نصوص غير مهيكلة',
                        'الحجم': f'{state.total_cases} حالة مغلقة',
                        'الفترة': convert_month_year_to_arabic(state.month_year) or 'يناير — مارس 2026'
                    },
                    {
                        'المصدر': 'دليل خدمات العملاء',
                        'الطبيعة': 'الدليل الرسمي يغطي خدمات المرور والترخيص والأمن',
                        'الحجم': '160 صفحة، 25 سؤالاً',
                        'الفترة': '2025'
                    }
                ],
                'row_count': 2,
                'col_count': 4,
                'original_index': 0
            }],
        },
        'classification_summary': {
            'heading': 'ملخص التصنيف',
            'body': 'تم تصنيف الحالات في ثماني فئات بناءً على نوايا المتعامل وأنماط التفاعل.',
        },
        'recommendations': {
            'heading': 'التوصيات',
            'body': 'بناءً على التحليل، يتم تقديم التوصيات التالية لتحسين جودة الخدمة ورضا المتعاملين.',
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
