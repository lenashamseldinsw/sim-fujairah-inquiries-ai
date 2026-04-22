#!/usr/bin/env python3
"""
Test Stages 1-5 of the pipeline.

Runs: Schema validation → Rule classification → LLM classification →
      Pattern analysis → Gap analysis (NO artifact generation)
"""

import sys
import os
import pandas as pd
from pathlib import Path

# Add real folder to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.orchestrator import PipelineOrchestrator


def main():
    """Run Stages 1-5 test."""
    print("=" * 80)
    print("PIPELINE STAGES 1-5 TEST (NO ARTIFACTS)")
    print("=" * 80)

    # Input file
    input_file = Path("/Users/lena/Documents/Sword/Fujairah_Inquiries_Docs/Fujairah police Project Inputs/Inputs/Inquiries2025_short.xlsx")

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
    except Exception as e:
        print(f"❌ Failed to load file: {e}")
        return False

    # Get API key
    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get('ANTHROPIC_API_KEY', '')
        except:
            pass

    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in environment or secrets")
        return False

    # Initialize orchestrator with output directory
    output_dir = Path("/Users/lena/Documents/Sword/sim-fujairah-inquiries-ai/real/pipeline-test-output")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🔧 Initializing pipeline...")
    orchestrator = PipelineOrchestrator(api_key=api_key, temp_dir=str(output_dir))
    orchestrator.initialize_state("test_run_1_to_5")
    print(f"✅ Pipeline ready (output: {output_dir})")

    stages = [
        (1, "SCHEMA VALIDATION"),
        (2, "RULE-BASED CLASSIFICATION"),
        (3, "LLM CLASSIFICATION"),
        (4, "PATTERN ANALYSIS"),
        (5, "GAP ANALYSIS"),
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

            results[stage_num] = {'success': success, 'message': msg}

            if success:
                print(f"✅ {msg}")
            else:
                print(f"❌ {msg}")
                if stage_num < 5:
                    print(f"⚠️  Stopping pipeline (stage {stage_num} failed)")
                    break
        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
            results[stage_num] = {'success': False, 'message': str(e)}
            if stage_num < 5:
                break

    # Summary
    print(f"\n{'=' * 80}")
    print("PIPELINE SUMMARY")
    print(f"{'=' * 80}")

    for stage_num, stage_name in stages:
        if stage_num in results:
            r = results[stage_num]
            status = "✅" if r['success'] else "❌"
            print(f"{status} Stage {stage_num}: {stage_name}")
            print(f"   {r['message']}")

    # State summary
    if orchestrator.state:
        state = orchestrator.state
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

    # Final status
    all_success = all(r['success'] for r in results.values())
    print(f"\n{'=' * 80}")
    if all_success:
        print("✅ ALL STAGES PASSED")
    else:
        failed = [s for s, r in results.items() if not r['success']]
        print(f"❌ FAILED STAGES: {failed}")
    print(f"{'=' * 80}")

    return all_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
