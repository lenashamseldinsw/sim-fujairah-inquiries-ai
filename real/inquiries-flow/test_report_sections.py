#!/usr/bin/env python3
"""
Test Stages 1-6 + Report Section Generation.

Loads 10 random rows from the inquiries file, runs the pipeline,
and tests stages 1-5 + Stage 6 (Excel generation) + report sections.
"""

import sys
import os
import json
import traceback
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add real folder to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.orchestrator import PipelineOrchestrator  # type: ignore[import-untyped]


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
    print("REPORT SECTION GENERATION TEST (Executive Summary → Methodology → Workload Map → Customer Journey)")
    print(f"{'=' * 80}")

    try:
        from pipeline.stage6_artifacts import generate_executive_summary_section, generate_methodology_section  # type: ignore[import-untyped]
        from pipeline.stage6_json_report import JSONReportBuilder  # type: ignore[import-untyped]

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

        # Build Arabic report sections only (LLM now outputs Arabic-only)
        state.report_sections_ar = {
            'executive_summary': {
                'heading': 'أولاً: الملخص التنفيذي — التحليلات الرئيسية',
                'body': exec_summary.get('framing_paragraph_ar', '') if exec_summary else '',
                'core_message': exec_summary.get('core_message_ar', '') if exec_summary else '',
                'tables': [exec_summary.get('key_findings', [])] if exec_summary and exec_summary.get('key_findings') else [],
                'raw_data': exec_summary,
            },
            'methodology': {
                'heading': 'ثانياً: المنهجية وطبيعة المصادر',
                'classification_method': methodology.get('classification_method', '') if methodology else '',
                'analyzed_fields': methodology.get('analyzed_fields', '') if methodology else '',
                'tables': [{'columns': ['المصدر', 'الطبيعة', 'الحجم', 'الفترة'], 'rows': methodology.get('sources_table', [])}] if methodology else [],
                'raw_data': methodology,
            }
        }

        # Generate Workload Map section
        print(f"\n📄 Generating Workload Map section...")
        from pipeline.generate_workload_map_section import generate_workload_map_section  # type: ignore[import-untyped]

        workload_map_raw = generate_workload_map_section(state, api_key)
        if workload_map_raw:
            # Store as JSONReportBuilder expects it
            state.report_sections_ar['workload_map'] = {
                'heading': 'ثالثاً: التحليل الأول — خريطة تصنيف الطلبات',
                'raw_data': workload_map_raw,
            }
            print(f"✅ Workload Map raw data generated successfully")
        else:
            print(f"❌ Workload Map generation failed")

        # Generate Customer Journey Challenges section
        print(f"\n📄 Generating Customer Journey Challenges section...")
        from pipeline.generate_customer_journey_section import generate_customer_journey_section  # type: ignore[import-untyped]

        customer_journey = generate_customer_journey_section(state, api_key)
        if customer_journey:
            state.report_sections_ar['customer_journey'] = {
                'heading': 'رابعاً: التحليل الثاني — التحديات في رحلة المتعامل',
                'raw_data': customer_journey,
            }
            print(f"✅ Customer Journey generated successfully")
            print(f"   📊 Friction table rows: {len(customer_journey.get('friction_table', []))}")
        else:
            print(f"⚠️  Customer Journey generation failed (will be skipped in report)")

        # Generate Digital Gaps section
        print(f"\n📄 Generating Digital Gaps section...")
        from pipeline.generate_digital_gaps_section import generate_digital_gaps_section  # type: ignore[import-untyped]

        digital_gaps = generate_digital_gaps_section(state, api_key)
        if digital_gaps:
            state.report_sections_ar['digital_gaps'] = {
                'heading': 'خامساً: التحليل الثالث — تحليل الفجوات الرقمية',
                'raw_data': digital_gaps,
            }
            print(f"✅ Digital Gaps generated successfully")
        else:
            print(f"⚠️  Digital Gaps generation failed (will be skipped in report)")

        # No English sections (Arabic-only output per new prompts)
        state.report_sections_en = None

        # Generate complete report JSON using JSONReportBuilder
        print(f"\n📄 Assembling complete report structure via JSONReportBuilder...")
        from pipeline.stage6_json_report import generate_json_report  # type: ignore[import-untyped]
        state.report_json = generate_json_report(state)

        if state.report_json:
            print(f"✅ Report JSON assembled successfully")
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
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if state.report_json and 'ar' in state.report_json:
            ar_report = state.report_json['ar']

            # Print summary before save
            print(f"\n{'=' * 80}")
            print("FINAL REPORT STRUCTURE (from JSONReportBuilder):")
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
            print(f"\n⚠️  No final report JSON to save")

    except Exception as e:
        print(f"❌ Report generation error: {e}")
        import traceback
        traceback.print_exc()

    # Final status
    all_success = all(r['success'] for r in results.values())
    print(f"\n{'=' * 80}")
    if all_success:
        print("✅ PIPELINE STAGES 1-6 PASSED")
        print("✅ REPORT SECTIONS GENERATED (Executive Summary + Methodology + Workload Map + Customer Journey)")
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
