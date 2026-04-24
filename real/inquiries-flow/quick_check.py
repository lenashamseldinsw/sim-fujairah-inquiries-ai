#!/usr/bin/env python3
"""Quick check of report sections JSON structure."""

import json
from pathlib import Path

output_dir = Path("pipeline-test-output")

# Find latest report sections files
ar_files = sorted(output_dir.glob("report_sections_ar_*.json"), reverse=True)
en_files = sorted(output_dir.glob("report_sections_en_*.json"), reverse=True)

if not ar_files or not en_files:
    print("❌ Report sections files not found yet")
    exit(1)

ar_file = ar_files[0]
en_file = en_files[0]

print(f"\n{'='*60}")
print(f"QUICK CHECK: {ar_file.name}")
print(f"{'='*60}")

with open(ar_file) as f:
    ar_data = json.load(f)

exec_summary = ar_data.get("executive_summary", {})
methodology = ar_data.get("methodology", {})

print(f"\n✓ Executive Summary:")
content = exec_summary.get("content", "")
print(f"  Content: {content[:60]}..." if content else "  Content: EMPTY ❌")

print(f"\n✓ Methodology Sources Table:")
subsections = methodology.get("subsections", [])
if subsections:
    sources_sub = subsections[0]
    tables = sources_sub.get("tables", [])
    if tables:
        table = tables[0]
        rows = table.get("rows", [])
        print(f"  Rows type: {type(rows).__name__} {'✓' if isinstance(rows, list) else '❌'}")
        print(f"  Row count: {len(rows)}")
        if rows and isinstance(rows, dict):
            print(f"  ❌ ERROR: Rows is dict with keys: {list(rows.keys())}")
            print(f"     Should be list of dicts!")
    else:
        print(f"  ❌ No tables found")
else:
    print(f"  ❌ No subsections found")

print(f"\n{'='*60}")
print(f"QUICK CHECK: {en_file.name}")
print(f"{'='*60}")

with open(en_file) as f:
    en_data = json.load(f)

exec_summary = en_data.get("executive_summary", {})
methodology = en_data.get("methodology", {})

print(f"\n✓ Executive Summary:")
content = exec_summary.get("content", "")
print(f"  Content: {content[:60]}..." if content else "  Content: EMPTY ❌")

print(f"\n✓ Methodology Sources Table:")
subsections = methodology.get("subsections", [])
if subsections:
    sources_sub = subsections[0]
    tables = sources_sub.get("tables", [])
    if tables:
        table = tables[0]
        rows = table.get("rows", [])
        print(f"  Rows type: {type(rows).__name__} {'✓' if isinstance(rows, list) else '❌'}")
        print(f"  Row count: {len(rows)}")
        if rows and isinstance(rows, dict):
            print(f"  ❌ ERROR: Rows is dict with keys: {list(rows.keys())}")
            print(f"     Should be list of dicts!")
    else:
        print(f"  ❌ No tables found")
else:
    print(f"  ❌ No subsections found")

print(f"\n{'='*60}")
print("✅ STRUCTURE OK" if isinstance(ar_data.get("methodology", {}).get("subsections", [{}])[0].get("tables", [{}])[0].get("rows", []), list) else "❌ STRUCTURE ERROR")
print(f"{'='*60}\n")
