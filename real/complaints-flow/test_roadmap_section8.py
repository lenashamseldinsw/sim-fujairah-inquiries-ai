#!/usr/bin/env python3
"""
Test script to diagnose Section 8 (Improvement Roadmap) hardcoding issue.

Runs the complaints pipeline up to stage 6 and checks:
1. Which sources contribute rows to the roadmap (notifications, gaps, journey, AI)
2. Whether المصدر and الجهد values actually vary
3. Identifies if all rows come from notifications (hardcoded values)
"""

import sys
import os
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.state import PipelineState
from pipeline.generate_improvement_roadmap_section import _build_roadmap_rows
import os

def test_roadmap_sources():
    """Test which sources contribute to roadmap section 8."""

    # Find a sample complaints file
    sample_file = Path(__file__).parent.parent / "complaints-output" / "Q1-2026" / "تصنيف شكاوى المتعاملين — حسب النوعQ1 2026.xlsx"

    if not sample_file.exists():
        print(f"❌ Sample file not found: {sample_file}")
        return False

    print(f"📋 Using sample file: {sample_file}")
    print("=" * 80)

    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY environment variable not set")
        return False

    # Run pipeline through stage 5 to populate state
    print("\n🔄 Running pipeline (stages 1-6)...")
    try:
        orchestrator = PipelineOrchestrator(api_key=api_key)
        results = orchestrator.run_full_pipeline(
            file_path=str(sample_file),
            language='ar',
            progress_callback=lambda pct, msg_ar, msg_en: print(f"  {pct}%: {msg_ar}")
        )

        if not results.get('success'):
            print(f"❌ Pipeline failed: {results.get('errors')}")
            return False

        state = orchestrator.state
        print(f"✅ Pipeline completed")
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Check state before roadmap generation
    print("\n" + "=" * 80)
    print("STATE CHECK (before roadmap generation):")
    print("=" * 80)
    print(f"  all_classified: {len(state.all_classified or [])} cases")
    print(f"  journey_map: {len(state.journey_map or [])} friction points")
    print(f"  gap_table: {len(state.gap_table or [])} gaps")
    print(f"    - Critical severity: {sum(1 for g in (state.gap_table or []) if g.severity == 'Critical')}")
    print(f"    - High severity: {sum(1 for g in (state.gap_table or []) if g.severity == 'High')}")
    print(f"  notification_opportunities: {len(state.notification_opportunities or [])} items")
    print(f"  report_sections_ar['ai_use_cases']: {bool(state.report_sections_ar.get('ai_use_cases'))}")

    if state.report_sections_ar.get('ai_use_cases', {}).get('raw_data', {}).get('use_cases_table'):
        ai_rows = state.report_sections_ar['ai_use_cases']['raw_data']['use_cases_table']
        print(f"    - AI use cases rows: {len(ai_rows)}")

    # Build roadmap rows and capture diagnostics
    print("\n" + "=" * 80)
    print("ROADMAP ROW GENERATION (with diagnostics):")
    print("=" * 80)

    try:
        roadmap_rows = _build_roadmap_rows(state)
    except Exception as e:
        print(f"❌ Roadmap generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Analyze the resulting rows
    print("\n" + "=" * 80)
    print("ROADMAP ROWS ANALYSIS:")
    print("=" * 80)
    print(f"\nTotal rows: {len(roadmap_rows)}")

    # Extract source attribution
    source_patterns = {
        'notif_': 0,
        'gap_': 0,
        'journey_': 0,
        'ai_': 0,
        'consolidated_': 0,
    }

    for row in roadmap_rows:
        row_id = row.get('row_id', '')
        for pattern in source_patterns:
            if row_id.startswith(pattern):
                source_patterns[pattern] += 1
                break

    print("\nRow distribution by source:")
    for pattern, count in source_patterns.items():
        if count > 0:
            print(f"  {pattern}: {count} rows")

    # Check المصدر values
    source_values = [row.get('source', '') for row in roadmap_rows]
    unique_sources = set(source_values)
    print(f"\nUnique المصدر values: {unique_sources}")
    print(f"  Source value counts:")
    for val in unique_sources:
        count = source_values.count(val)
        print(f"    '{val}': {count} rows")

    # Check الجهد values
    effort_values = [row.get('effort', '') for row in roadmap_rows]
    unique_efforts = set(effort_values)
    print(f"\nUnique الجهد values: {unique_efforts}")
    print(f"  Effort value counts:")
    for val in unique_efforts:
        count = effort_values.count(val)
        print(f"    '{val}': {count} rows")

    # Detailed row breakdown
    print("\n" + "=" * 80)
    print("DETAILED ROW BREAKDOWN:")
    print("=" * 80)
    for i, row in enumerate(roadmap_rows, 1):
        print(f"\nRow {i}:")
        print(f"  row_id: {row.get('row_id')}")
        print(f"  horizon: {row.get('horizon')}")
        print(f"  effort: {row.get('effort')}")
        print(f"  source: {row.get('source')}")
        print(f"  case_count: {row.get('case_count')}")
        print(f"  seed_recommendation: {row.get('seed_recommendation_ar', '')[:60]}...")

    # Final diagnosis
    print("\n" + "=" * 80)
    print("DIAGNOSIS:")
    print("=" * 80)

    if len(unique_sources) == 1 and unique_sources == {'التحليل'}:
        print("⚠️  ALL rows have المصدر='التحليل' — data variation is missing!")
        print(f"   Notification rows: {source_patterns['notif_']}")
        print(f"   Critical gaps rows: {source_patterns['gap_']}")
        print(f"   Journey rows: {source_patterns['journey_']}")
        print(f"   AI rows: {source_patterns['ai_']}")

        if source_patterns['gap_'] == 0:
            print("\n   → ROOT CAUSE: No critical gaps made it to roadmap")
            print("     Fix: Change gap severity filter in line 456 to include 'High'")
        if source_patterns['journey_'] == 0:
            print("\n   → ROOT CAUSE: No journey friction made it to roadmap")
            print("     Check: Is state.journey_map populated?")
        if source_patterns['ai_'] == 0:
            print("\n   → ROOT CAUSE: No AI use cases made it to roadmap")
            print("     Check: Did stage 7 (ai_use_cases) complete successfully?")
    else:
        print("✅ Source values vary as expected!")
        print(f"   Unique values: {unique_sources}")

    if len(unique_efforts) == 1:
        print(f"\n⚠️  ALL rows have الجهد='{list(unique_efforts)[0]}' — effort is not varying!")
        print("   This typically means all rows come from one source (likely notifications)")
    else:
        print(f"\n✅ Effort values vary as expected!")
        print(f"   Unique values: {unique_efforts}")

    return True

if __name__ == "__main__":
    success = test_roadmap_sources()
    sys.exit(0 if success else 1)
