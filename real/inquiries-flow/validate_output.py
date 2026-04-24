#!/usr/bin/env python3
"""
Validate the generated report sections JSON files.
Checks structure, data presence, and table formats.
"""

import json
from pathlib import Path


def validate_file(filepath, lang):
    """Validate a report sections JSON file."""
    print(f"\n{'='*80}")
    print(f"VALIDATING {lang.upper()} REPORT SECTIONS")
    print(f"{'='*80}")

    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        return False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False

    print(f"✅ File loaded: {filepath.name}")

    # Check sections
    sections = list(data.keys())
    print(f"\n📋 Sections found: {sections}")

    all_valid = True

    # Check executive summary
    if 'executive_summary' in data:
        exec_summary = data['executive_summary']
        print(f"\n🔹 Executive Summary:")
        print(f"   - Title: {exec_summary.get('title', '(missing)')[:50]}...")
        print(f"   - Content length: {len(exec_summary.get('content', ''))} chars")

        content = exec_summary.get('content', '')
        if content and len(content) > 20:
            print(f"   ✓ Content is present")
        else:
            print(f"   ✗ Content is missing or too short")
            all_valid = False

        subsections = exec_summary.get('subsections', [])
        if subsections:
            print(f"   - Subsections: {len(subsections)}")
            for i, sub in enumerate(subsections):
                tables = sub.get('tables', [])
                if tables:
                    table = tables[0]
                    rows = table.get('rows', [])
                    print(f"     {i+1}. {sub.get('title', '(untitled)')} - {len(rows)} rows")
                    if isinstance(rows, list):
                        print(f"        ✓ Rows is a list")
                    else:
                        print(f"        ✗ Rows is {type(rows).__name__}, not list")
                        all_valid = False
    else:
        print(f"✗ Executive Summary section missing")
        all_valid = False

    # Check methodology
    if 'methodology' in data:
        methodology = data['methodology']
        print(f"\n🔹 Methodology:")
        print(f"   - Title: {methodology.get('title', '(missing)')[:50]}...")

        subsections = methodology.get('subsections', [])
        print(f"   - Subsections: {len(subsections)}")

        for i, sub in enumerate(subsections):
            print(f"     {i+1}. {sub.get('title', '(untitled)')}")

            tables = sub.get('tables', [])
            if tables:
                table = tables[0]
                columns = table.get('columns', [])
                rows = table.get('rows', [])

                print(f"        - Columns: {columns}")
                print(f"        - Row count: {len(rows)}")

                if isinstance(rows, list):
                    print(f"        ✓ Rows is a list")
                    if rows:
                        first_row = rows[0]
                        print(f"        - First row keys: {list(first_row.keys())}")
                else:
                    print(f"        ✗ Rows is {type(rows).__name__}, not list")
                    all_valid = False
    else:
        print(f"✗ Methodology section missing")
        all_valid = False

    return all_valid


def main():
    """Validate all report sections files."""
    output_dir = Path(__file__).parent / 'pipeline-test-output'

    print(f"\n{'='*80}")
    print("REPORT SECTIONS VALIDATION")
    print(f"{'='*80}")

    # Find latest timestamped files
    ar_files = sorted(output_dir.glob('report_sections_ar_*.json'), reverse=True)
    en_files = sorted(output_dir.glob('report_sections_en_*.json'), reverse=True)

    if not ar_files and not en_files:
        # Fall back to non-timestamped files
        ar_files = sorted(output_dir.glob('report_sections_ar.json'), reverse=True)
        en_files = sorted(output_dir.glob('report_sections_en.json'), reverse=True)

    if not ar_files or not en_files:
        print(f"❌ No report sections files found in {output_dir}")
        return False

    ar_valid = validate_file(ar_files[0], 'arabic')
    en_valid = validate_file(en_files[0], 'english')

    print(f"\n{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}")

    if ar_valid and en_valid:
        print("✅ ALL VALIDATIONS PASSED")
        print(f"\n📁 Arabic: {ar_files[0].name}")
        print(f"📁 English: {en_files[0].name}")
        return True
    else:
        if not ar_valid:
            print("❌ Arabic sections validation failed")
        if not en_valid:
            print("❌ English sections validation failed")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
