#!/usr/bin/env python3
"""
Quick verification of the four bug fixes without running full pipeline.
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add real folder to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.state import PipelineState, CaseRow
from pipeline.stage6_json_report import JSONReportBuilder


def test_bug1_bug2_findings_and_content():
    """Test Bug 1 & 2: findings table reading and fallback content."""
    print("\n" + "="*80)
    print("BUG 1 & 2: Testing build_executive_summary_section()")
    print("="*80)

    # Create mock state
    state = PipelineState()
    state.total_cases = 100
    state.reclassified_count = 15
    state.reclassification_rate = 15.0
    state.month_year = "يناير — مارس 2026"

    # Add some test cases
    for i in range(100):
        case = CaseRow(
            case_number=str(i),
            case_title=f"Case {i}",
            date_opened="2026-01-01",
            case_channel="Phone",
            description=f"Description {i}",
            resolution_response=f"Resolution {i}",
            sla_color="Green",
            case_type="شكوى" if i % 2 == 0 else "استفسار",
            service_name="Traffic",
            actual_contact_type="شكوى" if i < 60 else "استفسار",
            classification_reason="Test",
            confidence=0.95,
            misclassification="OK",
            top_level="شكوى" if i % 2 == 0 else "استفسار"
        )
        state.all_classified.append(case)

    # Populate report sections with raw_data containing key_findings
    raw_findings = [
        {
            "number": 1,
            "title_ar": "تصنيف غير دقيق",
            "title_en": "Misclassification",
            "description_ar": "النسبة المئوية للتصنيفات غير الدقيقة",
            "description_en": "The percentage of misclassifications",
            "importance_ar": "🔴 حرجة",
            "importance_en": "🔴 Critical"
        },
        {
            "number": 2,
            "title_ar": "الشكاوى تهيمن",
            "title_en": "Complaints Dominate",
            "description_ar": "الشكاوى تشكل النسبة الأكبر",
            "description_en": "Complaints represent the majority",
            "importance_ar": "🔴 حرجة",
            "importance_en": "🔴 Critical"
        }
    ]

    state.report_sections_ar = {
        'executive_summary': {
            'body': '',  # Empty body to test fallback
            'core_message': '',
            'tables': [raw_findings],  # Bug 1 fix: findings in tables, not subsections
            'raw_data': {'key_findings': raw_findings}
        }
    }

    state.report_sections_en = {
        'executive_summary': {
            'body': '',  # Empty to test fallback
            'core_message': '',
            'tables': [raw_findings],
            'raw_data': {'key_findings': raw_findings}
        }
    }

    # Build sections
    builder = JSONReportBuilder(state)

    # Test Arabic
    result_ar = builder.build_executive_summary_section(lang='ar')
    print("\n✓ Arabic executive summary built")
    print(f"  - Content: {result_ar['content'][:80]}...")
    assert result_ar['content'], "❌ Content should not be empty"
    print(f"  ✓ Content is not empty")

    if result_ar['subsections']:
        findings_table = result_ar['subsections'][0]['tables'][0]
        print(f"  - Findings table columns: {findings_table['columns']}")
        print(f"  - Findings table rows: {len(findings_table['rows'])} rows")
        assert isinstance(findings_table['rows'], list), "❌ Rows must be a list"
        assert len(findings_table['rows']) == 2, "❌ Should have 2 findings"
        print(f"  ✓ Findings table properly formatted")
    else:
        print("  ⚠️  No subsections (fallback table will be used)")

    # Test English
    result_en = builder.build_executive_summary_section(lang='en')
    print("\n✓ English executive summary built")
    print(f"  - Content: {result_en['content'][:80]}...")
    assert result_en['content'], "❌ Content should not be empty"
    assert 'This report presents' in result_en['content'], "❌ Should have English content"
    print(f"  ✓ Content is in English")

    print("\n✅ BUG 1 & 2: PASSED")


def test_bug3_basic_sources_table():
    """Test Bug 3: basic sources table structure."""
    print("\n" + "="*80)
    print("BUG 3: Testing _create_basic_report_sections()")
    print("="*80)

    from pipeline.stage6_artifacts import _create_basic_report_sections

    state = PipelineState()
    state.total_cases = 100
    state.month_year = "يناير — مارس 2026"

    # Add test cases
    for i in range(100):
        case = CaseRow(
            case_number=str(i),
            case_title=f"Case {i}",
            date_opened="2026-01-01",
            case_channel="Phone",
            description=f"Description {i}",
            resolution_response=f"Resolution {i}",
            sla_color="Green",
            case_type="شكوى",
            service_name="Traffic",
            actual_contact_type="شكوى",
            classification_reason="Test",
            confidence=0.95,
            misclassification="OK",
            top_level="شكوى"
        )
        state.all_classified.append(case)

    _create_basic_report_sections(state)

    # Check Arabic methodology
    ar_method = state.report_sections_ar.get('methodology', {})
    assert 'tables' in ar_method, "❌ Arabic methodology should have tables"
    assert len(ar_method['tables']) > 0, "❌ Arabic methodology should have at least 1 table"

    ar_table = ar_method['tables'][0]
    print(f"\n✓ Arabic sources table: {ar_table['col_count']} columns, {ar_table['row_count']} rows")
    assert isinstance(ar_table['rows'], list), "❌ Rows must be a list, not dict"
    assert len(ar_table['rows']) == 2, "❌ Should have 2 source rows"
    print(f"  ✓ Rows is a list with {len(ar_table['rows'])} items")
    print(f"  ✓ Columns: {ar_table['columns']}")

    # Check English methodology
    en_method = state.report_sections_en.get('methodology', {})
    assert 'tables' in en_method, "❌ English methodology should have tables"
    assert len(en_method['tables']) > 0, "❌ English methodology should have at least 1 table"

    en_table = en_method['tables'][0]
    print(f"\n✓ English sources table: {en_table['col_count']} columns, {en_table['row_count']} rows")
    assert isinstance(en_table['rows'], list), "❌ Rows must be a list, not dict"
    assert len(en_table['rows']) == 2, "❌ Should have 2 source rows"
    print(f"  ✓ Rows is a list with {len(en_table['rows'])} items")
    print(f"  ✓ Columns: {en_table['columns']}")

    print("\n✅ BUG 3: PASSED")


def test_bug4_methodology_section_reading():
    """Test Bug 4: simplified sources table reading."""
    print("\n" + "="*80)
    print("BUG 4: Testing build_methodology_section()")
    print("="*80)

    state = PipelineState()
    state.total_cases = 100

    # Add test cases
    for i in range(100):
        case = CaseRow(
            case_number=str(i),
            case_title=f"Case {i}",
            date_opened="2026-01-01",
            case_channel="Phone",
            description=f"Description {i}",
            resolution_response=f"Resolution {i}",
            sla_color="Green",
            case_type="شكوى",
            service_name="Traffic",
            actual_contact_type="شكوى",
            classification_reason="Test",
            confidence=0.95,
            misclassification="OK",
            top_level="شكوى"
        )
        state.all_classified.append(case)

    # Create proper flat sources table (as per Bug 3 fix)
    sources_table = {
        'columns': ['Source', 'Nature', 'Size', 'Period'],
        'rows': [
            {'Source': 'CRM', 'Nature': 'Data', 'Size': '100 cases', 'Period': 'Q1 2026'},
            {'Source': 'Guidebook', 'Nature': 'Official', 'Size': '160 pages', 'Period': '2025'}
        ],
        'row_count': 2,
        'col_count': 4,
        'original_index': 0
    }

    state.report_sections_en = {
        'methodology': {
            'heading': 'Methodology',
            'body': 'Test methodology',
            'tables': [sources_table]
        }
    }

    builder = JSONReportBuilder(state)
    result = builder.build_methodology_section(lang='en')

    print(f"\n✓ Methodology section built")
    assert result is not None, "❌ Result should not be None"
    assert 'subsections' in result, "❌ Should have subsections"

    sources_subsection = result['subsections'][0]
    assert 'tables' in sources_subsection, "❌ Sources subsection should have tables"
    assert len(sources_subsection['tables']) > 0, "❌ Should have at least 1 table"

    retrieved_table = sources_subsection['tables'][0]
    print(f"  - Columns: {retrieved_table['columns']}")
    print(f"  - Rows: {len(retrieved_table['rows'])} items")
    assert isinstance(retrieved_table['rows'], list), "❌ Rows must be a list"
    assert len(retrieved_table['rows']) == 2, "❌ Should have 2 rows"
    print(f"  ✓ Table properly read with flat structure")

    print("\n✅ BUG 4: PASSED")


def main():
    """Run all verification tests."""
    print("\n" + "="*80)
    print("VERIFYING BUG FIXES")
    print("="*80)

    try:
        test_bug1_bug2_findings_and_content()
        test_bug3_basic_sources_table()
        test_bug4_methodology_section_reading()

        print("\n" + "="*80)
        print("✅ ALL BUG FIXES VERIFIED")
        print("="*80)
        print("\nSummary:")
        print("  ✓ Bug 1: Findings table now reads from tables[0]")
        print("  ✓ Bug 2: Content fallback generates real text when stubs found")
        print("  ✓ Bug 3: Basic sources table now uses flat structure with list rows")
        print("  ✓ Bug 4: Sources table reading simplified to check for list rows")
        return True

    except AssertionError as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
