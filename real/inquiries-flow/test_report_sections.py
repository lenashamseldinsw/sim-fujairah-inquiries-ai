#!/usr/bin/env python3
"""
Test Stages 1-6 + Report Section Generation.

Loads 10 random rows from the inquiries file, runs the pipeline,
and tests stages 1-5 + Stage 6 (Excel generation) + report sections.
"""

import sys
import os
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add real folder to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.orchestrator import PipelineOrchestrator


def main():
    """Run Stages 1-5 + Report Section Generation test."""
    print("=" * 80)
    print("PIPELINE STAGES 1-5 + REPORT SECTIONS TEST")
    print("=" * 80)

    # Input file
    input_file = Path("/Users/lena/Documents/Sword/Fujairah_Inquiries_Docs/Fujairah police Project Inputs/Inputs/Inquiries 2025.xlsx")

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

        # Sample 10 random rows
        if len(df) > 10:
            df = df.sample(n=10, random_state=42)
            print(f"✅ Sampled 10 random rows (seed=42 for reproducibility)")
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
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # Fallback for Python < 3.11

        secrets_path = Path.home() / '.streamlit' / 'secrets.toml'
        if secrets_path.exists():
            with open(secrets_path, 'rb') as f:
                secrets = tomllib.load(f)
                api_key = secrets.get('ANTHROPIC_API_KEY', '')

    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in environment, Streamlit, or ~/.streamlit/secrets.toml")
        return False

    # Initialize orchestrator with output directory
    output_dir = Path(__file__).parent / "pipeline-test-output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🔧 Initializing pipeline...")
    orchestrator = PipelineOrchestrator(api_key=api_key, temp_dir=str(output_dir))
    orchestrator.initialize_state("test_report_sections")
    print(f"✅ Pipeline ready (output: {output_dir})")

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
                excel_path = str(output_dir / f"inquiries_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
                word_path = str(output_dir / f"inquiries_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")
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
            import traceback
            traceback.print_exc()
            results[stage_num] = {'success': False, 'message': str(e)}
            if stage_num < 6:
                break

    # Summary of stages 1-6
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

    # Now test report section generation
    print(f"\n{'=' * 80}")
    print("REPORT SECTION GENERATION TEST")
    print(f"{'=' * 80}")

    try:
        from pipeline.stage6_artifacts import generate_executive_summary_section, generate_methodology_section

        print(f"\n📄 Generating Executive Summary section...")
        exec_summary = generate_executive_summary_section(state, api_key)

        if exec_summary:
            print(f"✅ Executive Summary generated successfully")
            if 'framing_paragraph_ar' in exec_summary:
                print(f"   📋 Framing paragraph: {exec_summary['framing_paragraph_ar'][:100]}...")
            if 'key_findings' in exec_summary:
                print(f"   📊 Key findings: {len(exec_summary['key_findings'])} rows")
        else:
            print(f"❌ Executive Summary generation failed")
            exec_summary = {}

        print(f"\n📄 Generating Methodology section...")
        methodology = generate_methodology_section(state, api_key)

        if methodology:
            print(f"✅ Methodology generated successfully")
            if 'sources_table' in methodology:
                print(f"   📋 Sources table: {len(methodology['sources_table'])} rows")
            if 'classification_method_ar' in methodology:
                print(f"   📋 Classification method: {methodology['classification_method_ar'][:100]}...")
        else:
            print(f"❌ Methodology generation failed")
            methodology = {}

        # Build state.report_sections_ar and report_sections_en using bilingual builder
        from pipeline.stage6_artifacts import build_bilingual_report_sections

        state.report_sections_ar, state.report_sections_en = build_bilingual_report_sections(
            exec_summary if exec_summary else {},
            methodology if methodology else {},
            state=state
        )

        # Generate JSON report for display
        print(f"\n📋 Generating JSON report for display...")
        from pipeline.stage6_json_report import generate_json_report
        state.report_json = generate_json_report(state)
        print(f"✅ JSON report generated")

        # Save to files
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Print Arabic dict before saving
        print(f"\n{'=' * 80}")
        print("ARABIC REPORT SECTIONS DICT (before JSON save):")
        print(f"{'=' * 80}")
        print(json.dumps(state.report_sections_ar, ensure_ascii=False, indent=2))

        # Print English dict before saving
        print(f"\n{'=' * 80}")
        print("ENGLISH REPORT SECTIONS DICT (before JSON save):")
        print(f"{'=' * 80}")
        print(json.dumps(state.report_sections_en, ensure_ascii=False, indent=2))

        # Save full report JSON
        output_file = output_dir / f"report_full_{timestamp}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(state.report_json, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Saved full report JSON to: {output_file}")
        print(f"   File size: {output_file.stat().st_size} bytes")

        # Save report sections (Arabic)
        ar_file = output_dir / f"report_sections_ar_{timestamp}.json"
        with open(ar_file, 'w', encoding='utf-8') as f:
            json.dump(state.report_sections_ar, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved Arabic report sections to: {ar_file}")
        print(f"   File size: {ar_file.stat().st_size} bytes")

        # Save report sections (English)
        en_file = output_dir / f"report_sections_en_{timestamp}.json"
        with open(en_file, 'w', encoding='utf-8') as f:
            json.dump(state.report_sections_en, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved English report sections to: {en_file}")
        print(f"   File size: {en_file.stat().st_size} bytes")

        # Print summary of report_json structure
        if state.report_json:
            print(f"\n📊 Report JSON Structure:")
            print(f"   Sections: {list(state.report_json.keys())}")
            for section_key, section_data in state.report_json.items():
                if isinstance(section_data, dict):
                    print(f"   - {section_key}: {list(section_data.keys())}")

        # Print summary of report_sections
        print(f"\n📊 Report Sections Structure:")
        print(f"   Arabic sections: {list(state.report_sections_ar.keys())}")
        if state.report_sections_ar:
            for section_key, section_data in state.report_sections_ar.items():
                if isinstance(section_data, dict):
                    print(f"   - {section_key}: {list(section_data.keys())}")

        print(f"   English sections: {list(state.report_sections_en.keys())}")
        if state.report_sections_en:
            for section_key, section_data in state.report_sections_en.items():
                if isinstance(section_data, dict):
                    print(f"   - {section_key}: {list(section_data.keys())}")

    except Exception as e:
        print(f"❌ Report generation error: {e}")
        import traceback
        traceback.print_exc()

    # Final status
    all_success = all(r['success'] for r in results.values())
    print(f"\n{'=' * 80}")
    if all_success:
        print("✅ PIPELINE STAGES 1-6 PASSED")
        if state.report_json:
            print("✅ REPORT SECTIONS GENERATED SUCCESSFULLY")
        if results.get(6, {}).get('success'):
            print("✅ EXCEL GENERATION COMPLETED SUCCESSFULLY")
    else:
        failed = [s for s, r in results.items() if not r['success']]
        print(f"❌ FAILED STAGES: {failed}")
    print(f"{'=' * 80}")

    return all_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
