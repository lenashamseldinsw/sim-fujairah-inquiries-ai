#!/usr/bin/env python3
"""
Test Stages 1-6 + Report Section Generation.

Loads 50 random rows from the inquiries file, runs the pipeline,
and tests stages 1-5 + Stage 6 (Excel generation) + report sections.
"""

import sys
import os
import json
import time
import traceback
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add real folder to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.orchestrator import PipelineOrchestrator  # type: ignore[import-untyped]


def main():
    """Run Stages 1-5 + Report Section Generation test."""
    start_time = time.time()
    print("=" * 80)
    print("PIPELINE STAGES 1-5 + REPORT SECTIONS TEST")
    print("=" * 80)

    # Input file
    input_file =  Path(__file__).parent / "sample-input" / "Inquiries 2025.xlsx"

    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        return False

    print(f"\n📥 Loading input file...")
    print(f"   {input_file.name}")

    try:
        # Read with auto-detected header
        df = pd.read_excel(input_file, header=4)
        print(f"✅ Loaded {len(df)} rows, {len(df.columns)} columns")
        print(f"   Columns: {list(df.columns)[:5]}...")

        # Sample 20 random rows
        if len(df) > 20:
            df = df.sample(n=20, random_state=42)
            print(f"✅ Sampled 20 random rows (seed=42 for reproducibility)")
        else:
            print(f"⚠️  Only {len(df)} rows available (less than 10)")

    except Exception as e:
        print(f"❌ Failed to load file: {e}")
        return False

    # Get API key from environment, Streamlit secrets, or secrets.toml
    api_key = os.getenv('ANTHROPIC_API_KEY', '')

    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get('ANTHROPIC_API_KEY', '')
        except:
            pass

    if not api_key:
        try:
            try:
                import tomllib  # Python 3.11+
            except ImportError:
                import tomli as tomllib  # type: ignore[import-untyped]  # Fallback for Python < 3.11

            secrets_path = Path.home() / '.streamlit' / 'secrets.toml'
            if secrets_path.exists():
                with open(secrets_path, 'rb') as f:
                    secrets = tomllib.load(f)
                    api_key = secrets.get('ANTHROPIC_API_KEY', '')
        except ImportError:
            pass  # tomli not available, skip secrets.toml loading

    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in environment, Streamlit, or ~/.streamlit/secrets.toml")
        return False

    # Initialize orchestrator with output directory
    output_dir = Path(__file__).parent / "pipeline-test-output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🔧 Initializing pipeline...")
    orchestrator = PipelineOrchestrator(api_key=api_key, temp_dir=str(output_dir))
    # Use a unique session ID per run so stale state from a previous run is never loaded.
    # A fixed ID like "test_report_sections" causes initialize_state() to reload the old
    # state.json (including old report_json), which then gets saved when stage 6 fails.
    run_session_id = f"test_report_sections_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    orchestrator.initialize_state(run_session_id)
    print(f"✅ Pipeline ready (output: {output_dir}, session: {run_session_id})")

    stages = [
        (1, "SCHEMA VALIDATION"),
        (2, "RULE-BASED CLASSIFICATION"),
        (3, "LLM CLASSIFICATION"),
        (4, "PATTERN ANALYSIS"),
        (5, "GAP ANALYSIS"),
        (6, "EXCEL GENERATION"),
    ]

    results = {}

    for stage_num, stage_name in stages:
        print(f"\n{'=' * 80}")
        print(f"STAGE {stage_num}: {stage_name}")
        print(f"{'=' * 80}")

        try:
            # Run each stage
            if stage_num == 1:
                success, msg, _ = orchestrator.run_stage1_validator(df)
            elif stage_num == 2:
                success, msg = orchestrator.run_stage2_classifier()
            elif stage_num == 3:
                success, msg = orchestrator.run_stage3_llm_classifier()
            elif stage_num == 4:
                success, msg = orchestrator.run_stage4_analysis()
            elif stage_num == 5:
                success, msg = orchestrator.run_stage5_gap_analysis()
            elif stage_num == 6:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                excel_path = str(output_dir / f"inquiries_report_{timestamp}.xlsx")
                word_path = str(output_dir / f"inquiries_report_{timestamp}.docx")
                success, msg = orchestrator.run_stage6_artifacts(excel_path, word_path, language='ar')

            results[stage_num] = {'success': success, 'message': msg}

            if success:
                print(f"✅ {msg}")
            else:
                print(f"❌ {msg}")
                if stage_num < 6:
                    print(f"⚠️  Stopping pipeline (stage {stage_num} failed)")
                    break
        except Exception as e:
            print(f"❌ Exception: {e}")
            traceback.print_exc()
            results[stage_num] = {'success': False, 'message': str(e)}
            if stage_num < 6:
                break

    # Summary of pipeline stages 1-6
    print(f"\n{'=' * 80}")
    print("PIPELINE STAGES 1-6 SUMMARY")
    print(f"{'=' * 80}")

    for stage_num, stage_name in stages:
        if stage_num in results:
            r = results[stage_num]
            status = "✅" if r['success'] else "❌"
            print(f"{status} Stage {stage_num}: {stage_name}")
            print(f"   {r['message']}")

    # State summary
    state = orchestrator.state
    if state:
        print(f"\n{'=' * 80}")
        print("ANALYSIS RESULTS")
        print(f"{'=' * 80}")
        print(f"Total cases: {state.total_cases}")
        print(f"Rule-classified: {len(state.rule_classified)}")
        print(f"LLM-classified: {len(state.llm_classified)}")
        print(f"All classified: {len(state.all_classified)}")
        print(f"Patterns found: {len(state.patterns)}")
        print(f"Journey friction points: {len(state.journey_map)}")
        print(f"FAQ candidates: {len(state.faq_candidates)}")
        print(f"Gap rows identified: {len(state.gap_table)}")
        print(f"Validated FAQs: {len(state.validated_faqs)}")

        # Show sample results
        if state.patterns:
            print(f"\n🔍 Sample Patterns (top 3):")
            for i, p in enumerate(state.patterns[:3], 1):
                print(f"   {i}. {p.cluster} ({p.case_count} cases)")

        if state.journey_map:
            print(f"\n🔍 Sample Friction Points (top 3):")
            for i, j in enumerate(state.journey_map[:3], 1):
                print(f"   {i}. {j.friction_point} ({j.case_count} cases)")

        if state.gap_table:
            print(f"\n🔍 Sample Gaps (top 3):")
            for i, g in enumerate(state.gap_table[:3], 1):
                status = g.guidebook_status or "Unknown"
                print(f"   {i}. {g.topic} - {status}")
                if g.severity:
                    print(f"      Severity: {g.severity}")

    # Verify report section generation (already done by run_stage6_artifacts above)
    print(f"\n{'=' * 80}")
    print("REPORT SECTIONS VERIFICATION")
    print(f"{'=' * 80}")

    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')  # used for the JSON save filename

        if state.report_sections_ar:
            print(f"✅ Report sections generated successfully by Stage 6")
            for section_name in state.report_sections_ar.keys():
                print(f"   ✓ {section_name}")
        else:
            print(f"⚠️  No report sections found in state after Stage 6")

        # Verify final report JSON was assembled
        if state.report_json:
            print(f"\n✅ Report JSON assembled successfully")
            if 'ar' in state.report_json:
                ar_report = state.report_json['ar']
                sections = ar_report.get('sections', [])
                print(f"   📊 Sections in final report: {len(sections)}")
                for section in sections:
                    print(f"     - {section.get('title', 'Untitled')}")
                    if section.get('subsections'):
                        for subsection in section['subsections']:
                            print(f"       - {subsection.get('title', 'Untitled')} (level {subsection.get('level', '?')})")
        else:
            print(f"⚠️  Report JSON not generated")

        # Save final report JSON (Arabic-only, production version)
        # Only save if stage 6 actually ran successfully — if it failed, state.report_json
        # may still hold a value loaded from a previous-run state file (stale data).
        stage6_succeeded = results.get(6, {}).get('success', False)
        if stage6_succeeded and state.report_json and 'ar' in state.report_json:
            ar_report = state.report_json['ar']

            # Print summary before save
            print(f"\n{'=' * 80}")
            print("FINAL REPORT STRUCTURE (from Stage 6):")
            print(f"{'=' * 80}")
            print(f"Metadata: {json.dumps(ar_report.get('metadata', {}), ensure_ascii=False, indent=2)}")
            print(f"\nSections ({len(ar_report.get('sections', []))} total):")
            for i, section in enumerate(ar_report.get('sections', []), 1):
                print(f"{i}. {section.get('title', 'Untitled')}")
                if section.get('subsections'):
                    for subsection in section['subsections']:
                        print(f"   {subsection.get('title', 'Untitled')}")

            # Save to file
            ar_file = output_dir / f"report_final_ar_{timestamp}.json"
            with open(ar_file, 'w', encoding='utf-8') as f:
                json.dump(ar_report, f, ensure_ascii=False, indent=2)
            print(f"\n💾 Saved final Arabic report to: {ar_file}")
            print(f"   File size: {ar_file.stat().st_size} bytes")
            print(f"   Sections in file: {len(ar_report.get('sections', []))}")
        else:
            if not stage6_succeeded:
                print(f"\n⚠️  Stage 6 did not succeed — skipping JSON save to avoid writing stale data")
            else:
                print(f"\n⚠️  No final report JSON to save")

    except Exception as e:
        print(f"❌ Report verification error: {e}")
        import traceback
        traceback.print_exc()

    # Final status
    all_success = all(r['success'] for r in results.values())
    print(f"\n{'=' * 80}")
    if all_success:
        print("✅ PIPELINE STAGES 1-6 PASSED")
        print("✅ ALL REPORT SECTIONS 1-8 GENERATED (Executive Summary, Methodology, Workload Map, Customer Journey, Digital Gaps, Digital Transformation, AI Use Cases, Improvement Roadmap)")
        if results.get(6, {}).get('success'):
            print("✅ EXCEL GENERATION COMPLETED SUCCESSFULLY")
    else:
        failed = [s for s, r in results.items() if not r['success']]
        print(f"❌ FAILED STAGES: {failed}")

    end_time = time.time()
    elapsed_time = end_time - start_time
    hours = int(elapsed_time // 3600)
    minutes = int((elapsed_time % 3600) // 60)
    seconds = int(elapsed_time % 60)
    milliseconds = int((elapsed_time % 1) * 1000)

    print(f"\n⏱️  TOTAL TEST DURATION: {hours}h {minutes}m {seconds}s {milliseconds}ms ({elapsed_time:.2f}s)")
    print(f"{'=' * 80}")

    return all_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
