#!/usr/bin/env python3
"""
Test Stages 1-2 of the pipeline against reference data.

Validates:
1. Stage 1: Schema validation
2. Stage 2: Rule-based classification

Measures classification agreement with reference outputs.
"""

import sys
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple

# Add real folder to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.state import PipelineState


def load_reference_data() -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Load sample input and reference output."""
    # Load sample input
    input_path = Path("inquiries-flow/sample-input/Inquiries 2025.xlsx")
    if not input_path.exists():
        raise FileNotFoundError(f"Sample input not found: {input_path}")

    # Read with correct header (row 4, 0-indexed)
    df = pd.read_excel(input_path, header=4)

    # Load reference classification
    ref_path = Path("inquiries-flow/reference-inquiries-outputs/تصنيف استفسارات المتعاملين — الربع الأول 2026.xlsx")
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference output not found: {ref_path}")

    ref_df = pd.read_excel(ref_path, sheet_name="كل الحالات")

    # Build reference mapping: case_number -> actual_contact_type
    reference_classifications = {}
    for _, row in ref_df.iterrows():
        case_num = str(row.get('رقم_الطلب', ''))
        contact_type = str(row.get('التصنيف_الفعلي', ''))
        if case_num and contact_type:
            reference_classifications[case_num] = contact_type

    return df, reference_classifications


def run_test():
    """Run Stages 1-2 test."""
    print("=" * 70)
    print("PIPELINE STAGE 1-2 TEST")
    print("=" * 70)

    # Load data
    print("\n📥 Loading reference data...")
    try:
        df, reference_classifications = load_reference_data()
        print(f"✅ Loaded {len(df)} cases from sample input")
        print(f"✅ Loaded {len(reference_classifications)} reference classifications")
    except Exception as e:
        print(f"❌ Failed to load data: {e}")
        return False

    # Run Stage 1
    print("\n" + "=" * 70)
    print("STAGE 1: SCHEMA VALIDATION")
    print("=" * 70)

    orchestrator = PipelineOrchestrator(api_key="test-key")
    orchestrator.initialize_state("test_run")

    try:
        success, msg, validation = orchestrator.run_stage1_validator(df)
        if success:
            print(f"✅ {msg}")
            if validation.get('case_count'):
                print(f"   Cases processed: {validation['case_count']}")
        else:
            print(f"❌ Validation failed: {msg}")
            if validation.get('errors'):
                for error in validation['errors']:
                    print(f"   - {error}")
            return False
    except Exception as e:
        print(f"❌ Stage 1 error: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Run Stage 2
    print("\n" + "=" * 70)
    print("STAGE 2: RULE-BASED CLASSIFICATION")
    print("=" * 70)

    try:
        success, msg = orchestrator.run_stage2_classifier()
        if success:
            print(f"✅ {msg}")
        else:
            print(f"❌ Classification failed: {msg}")
            return False
    except Exception as e:
        print(f"❌ Stage 2 error: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Measure agreement with reference
    print("\n" + "=" * 70)
    print("AGREEMENT ANALYSIS")
    print("=" * 70)

    classified = orchestrator.state.rule_classified
    print(f"Total classified by rules: {len(classified)}")
    print(f"Total queued for LLM: {len(orchestrator.state.llm_queue)}")

    # Build agreement statistics
    agreement_by_type = {}
    mismatches = []
    matched = 0
    total_compared = 0

    for case in classified:
        case_num = case.case_number
        predicted_type = case.actual_contact_type
        reference_type = reference_classifications.get(case_num)

        if reference_type:
            total_compared += 1

            # Normalize for comparison
            pred_norm = predicted_type.lower().strip()
            ref_norm = reference_type.lower().strip()

            if pred_norm == ref_norm:
                matched += 1
            else:
                mismatches.append({
                    'case_number': case_num,
                    'predicted': predicted_type,
                    'reference': reference_type,
                    'confidence': case.confidence
                })

            # Track by type
            if reference_type not in agreement_by_type:
                agreement_by_type[reference_type] = {'matched': 0, 'total': 0}
            agreement_by_type[reference_type]['total'] += 1
            if pred_norm == ref_norm:
                agreement_by_type[reference_type]['matched'] += 1

    if total_compared > 0:
        overall_agreement = matched / total_compared * 100
        print(f"\nOverall Agreement Rate: {overall_agreement:.1f}% ({matched}/{total_compared})")

        print("\nAgreement by Reference Type:")
        for ref_type in sorted(agreement_by_type.keys()):
            stats = agreement_by_type[ref_type]
            pct = stats['matched'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"  {ref_type:40s} {stats['matched']:3d}/{stats['total']:3d} ({pct:5.1f}%)")

        # Show top mismatches
        if mismatches:
            print(f"\nTop Mismatches (showing first 10 of {len(mismatches)}):")
            for i, mm in enumerate(mismatches[:10], 1):
                print(f"  {i}. Case {mm['case_number']}")
                print(f"     Predicted: {mm['predicted']} (conf: {mm['confidence']:.2f})")
                print(f"     Reference: {mm['reference']}")

        # Recommendations
        print("\n" + "=" * 70)
        print("RECOMMENDATIONS")
        print("=" * 70)

        if overall_agreement >= 85:
            print("✅ Agreement rate ≥85% — rules are well-tuned")
            print("   Next: Test Stage 3 (LLM classifier) on low-confidence cases")
        elif overall_agreement >= 75:
            print("⚠️  Agreement rate 75-85% — may need fine-tuning")
            print("   Consider adjusting:")
            print("   - Confidence thresholds in stage2_rules.py")
            print("   - Pattern matching rules for problematic categories")
        else:
            print("❌ Agreement rate <75% — significant tuning needed")
            print("   Review mismatches above and adjust rule patterns")

        return overall_agreement >= 75  # Consider success if ≥75%

    else:
        print("⚠️  No reference data available for comparison")
        print("   Make sure reference case numbers match the input file")
        return True  # Don't fail if can't compare


def main():
    """Main entry point."""
    try:
        success = run_test()
        print("\n" + "=" * 70)
        if success:
            print("✅ TEST PASSED")
        else:
            print("❌ TEST FAILED")
        print("=" * 70)
        return success
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
