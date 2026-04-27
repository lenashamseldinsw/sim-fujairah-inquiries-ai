#!/usr/bin/env python3
"""Verify that report JSON structure matches expected format."""

import json
from pathlib import Path


def verify_section_structure(section, section_num, lang='ar'):
    """Verify a section has all required fields."""
    required_fields = ['id', 'title', 'title_en', 'level', 'content', 'tables', 'charts', 'subsections']

    for field in required_fields:
        if field not in section:
            print(f"❌ Section {section_num} missing field: {field}")
            return False

    # Verify tables structure
    for i, table in enumerate(section.get('tables', [])):
        if not isinstance(table, dict):
            print(f"❌ Section {section_num}, Table {i}: not a dict")
            return False

        required_table_fields = ['columns', 'rows', 'row_count', 'col_count', 'original_index']
        for field in required_table_fields:
            if field not in table:
                print(f"⚠️  Section {section_num}, Table {i} missing field: {field}")

    # Verify subsections recursively
    for sub_num, subsection in enumerate(section.get('subsections', [])):
        if not verify_section_structure(subsection, f"{section_num}.{sub_num+1}", lang):
            return False

    return True


def main():
    """Check latest report JSON file."""
    test_output_dir = Path('pipeline-test-output')

    # Find most recent report_full JSON
    report_files = list(test_output_dir.glob('report_full_*.json'))
    if not report_files:
        print("❌ No report_full_*.json files found")
        return False

    latest_report = sorted(report_files)[-1]
    print(f"📄 Checking: {latest_report.name}")

    with open(latest_report) as f:
        report = json.load(f)

    # Check both languages
    for lang in ['ar', 'en']:
        if lang not in report:
            print(f"❌ Missing language: {lang}")
            return False

        lang_report = report[lang]
        print(f"\n🔍 Verifying {lang.upper()} structure:")

        # Check sections array
        if 'sections' not in lang_report:
            print(f"❌ Missing 'sections' array")
            return False

        sections = lang_report['sections']
        if not isinstance(sections, list):
            print(f"❌ 'sections' is not a list")
            return False

        print(f"   ✅ Found {len(sections)} sections")

        # Verify each section
        for i, section in enumerate(sections, 1):
            if not verify_section_structure(section, i, lang):
                return False

            print(f"   ✅ Section {i}: {section.get('title', '?')}")

    print("\n✅ All structure checks passed!")
    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
