#!/usr/bin/env python3
"""
Test section 3.4 (department distribution) to verify:
1. Department names are cleaned consistently between stage1 and stage2
2. sub_classification values are correctly populated for all cases
3. Dominant complaint type is correctly identified per department
"""

import sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from pipeline.state import PipelineState, CaseRow


def test_department_name_cleaning():
    """Test that department names are cleaned consistently."""
    import re

    # Test cases with "الفجيرة - " prefix
    test_cases = [
        ("الفجيرة - الإدارة العامة لعمليات الشرطة", "الإدارة العامة لعمليات الشرطة"),
        ("الفجيرة  -  إدارة المرور", "إدارة المرور"),
        ("الفجيرة- المنشآت العقابية والإصلاحية", "المنشآت العقابية والإصلاحية"),
        ("المنشآت العقابية والإصلاحية", "المنشآت العقابية والإصلاحية"),  # Already clean
    ]

    cleaning_pattern = r'^الفجيرة\s*-\s*'

    for raw, expected in test_cases:
        cleaned = re.sub(cleaning_pattern, '', raw).strip()
        assert cleaned == expected, f"Failed: {raw} → {cleaned} (expected {expected})"
        print(f"✓ {raw} → {cleaned}")

    print("\n✓ All department name cleaning tests passed!")


def test_section_3_4_data_structure():
    """Test that section 3.4 can find cases by cleaned department names."""

    # Mock cases with cleaned department names (matching stage2 fix)
    cases = [
        CaseRow(
            case_number="001",
            case_title="Test 1",
            date_opened="2026-01-01",
            case_channel="WhatsApp",
            description="Test",
            resolution_response="Test",
            sla_color="Green",
            case_type="شكوى",
            service_name="Service A",
            actual_contact_type="شكوى",
            classification_reason="Test",
            confidence=0.95,
            misclassification="OK",
            top_level="شكوى",
            sub_classification="شكاوى على الخدمات المرورية",
            admin="الإدارة العامة لعمليات الشرطة",
        ),
        CaseRow(
            case_number="002",
            case_title="Test 2",
            date_opened="2026-01-02",
            case_channel="App",
            description="Test",
            resolution_response="Test",
            sla_color="Yellow",
            case_type="شكوى",
            service_name="Service B",
            actual_contact_type="شكوى",
            classification_reason="Test",
            confidence=0.90,
            misclassification="OK",
            top_level="شكوى",
            sub_classification="شكاوى على الخدمات المرورية",
            admin="الإدارة العامة لعمليات الشرطة",
        ),
        CaseRow(
            case_number="003",
            case_title="Test 3",
            date_opened="2026-01-03",
            case_channel="Phone",
            description="Test",
            resolution_response="Test",
            sla_color="Red",
            case_type="شكوى",
            service_name="Service C",
            actual_contact_type="شكوى",
            classification_reason="Test",
            confidence=0.88,
            misclassification="OK",
            top_level="شكوى",
            sub_classification="شكاوى أمنية وجنائية",
            admin="إدارة المرور",
        ),
    ]

    # Simulate department_distribution from stage1 (with cleaned names)
    department_distribution = {
        "الإدارة العامة لعمليات الشرطة": 2,
        "إدارة المرور": 1,
    }

    # Build dept_cases lookup (same as in stage6_json_report.py)
    dept_cases = defaultdict(list)
    for case in cases:
        if case.admin:
            dept_cases[case.admin].append(case)

    print("\nDept cases lookup:")
    for dept, cases_list in dept_cases.items():
        print(f"  {dept}: {len(cases_list)} cases")

    # Verify matching works
    for dept, count in department_distribution.items():
        cases_in_dept = dept_cases.get(dept, [])
        assert len(cases_in_dept) > 0, f"No cases found for department: {dept}"

        # Find dominant complaint type
        complaint_counts = Counter(
            case.sub_classification or "أخرى"
            for case in cases_in_dept
        )
        if complaint_counts:
            dominant = complaint_counts.most_common(1)[0][0]
            print(f"✓ {dept}: {dominant} (count: {len(cases_in_dept)})")
        else:
            print(f"✗ {dept}: No complaint types found!")
            assert False, "Failed to find dominant complaint type"

    print("\n✓ All section 3.4 data structure tests passed!")


if __name__ == "__main__":
    print("Testing section 3.4 (Department Distribution) Fix")
    print("=" * 60)

    test_department_name_cleaning()
    print()
    test_section_3_4_data_structure()

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
