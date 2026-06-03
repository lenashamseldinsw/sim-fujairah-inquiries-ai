#!/usr/bin/env python3
"""
Test script to diagnose the closure rate bug (80% vs 40 closed).
Creates 50 test complaint cases and runs through Stage 2 to check date_closed processing.
"""

import os
import sys
import pandas as pd
from pathlib import Path

# Add pipeline directory to path for imports
pipeline_dir = Path(__file__).parent / "pipeline"
sys.path.insert(0, str(pipeline_dir))
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import ComplaintsPipelineOrchestrator
from state import PipelineState


def create_test_excel():
    """Create a test Excel file with 50 complaint cases."""
    print("[TEST] Creating test Excel with 50 cases...")

    # Create test data: 50 cases, mix of closed and open
    data = []

    # 46 closed cases (should be ~92% closure rate)
    for i in range(1, 47):
        data.append({
            'رقم الطلب': f'211{i:03d}',
            'تفاصيل الطلب': f'Test complaint {i}',
            'الحل': f'Resolved on time {i}',
            'الخدمة': 'فتح البلاغات المرورية',
            'الخدمة الرئيسية': 'خدمات مرورية',
            'شدة الطلب': 'عالية',
            'نوع المكالمة': 'شكاوى',
            'قناة تقديم الخدمة': 'هاتف',
            'الحالة': 'مغلق',
            'تاريخ الإنشاء': '2026-01-01',
            'تاريخ الإغلاق': f'2026-01-{(i % 28) + 1:02d}',  # Mix of dates throughout Jan
            'إغلاق الطلب خلال الوقت المحدد': 'نعم',
            'تم الحل بواسطة': 'Team A',
            'الإدارة العامة': 'الفجيرة - شرطة المرور',
            'المالك': 'Officer 1',
            'اسم مقدم الطلب': f'Customer {i}',
            'الجنسية': 'Emirati',
            'رقم الهوية': f'784{i:06d}',
            'الهاتف الجوال': '971501234567',
            'الرقم الوظيفي': f'{i}',
        })

    # 4 open cases (should be ~8% open rate)
    for i in range(47, 51):
        data.append({
            'رقم الطلب': f'211{i:03d}',
            'تفاصيل الطلب': f'Test complaint {i} - still open',
            'الحل': f'Pending resolution {i}',
            'الخدمة': 'فتح البلاغات المرورية',
            'الخدمة الرئيسية': 'خدمات مرورية',
            'شدة الطلب': 'متوسطة',
            'نوع المكالمة': 'شكاوى',
            'قناة تقديم الخدمة': 'تطبيق',
            'الحالة': 'مفتوح',
            'تاريخ الإنشاء': '2026-02-01',
            'تاريخ الإغلاق': '',  # No closing date
            'إغلاق الطلب خلال الوقت المحدد': '',
            'تم الحل بواسطة': 'Pending',
            'الإدارة العامة': 'الفجيرة - شرطة مرور أخرى',
            'المالك': 'Officer 2',
            'اسم مقدم الطلب': f'Customer {i}',
            'الجنسية': 'Emirati',
            'رقم الهوية': f'784{i:06d}',
            'الهاتف الجوال': '971509876543',
            'الرقم الوظيفي': f'{i}',
        })

    df = pd.DataFrame(data)
    test_file = Path(__file__).parent.parent / "test_complaints_input.xlsx"
    df.to_excel(test_file, sheet_name='Sheet1', index=False, header=True)

    print(f"[TEST] ✓ Created test file: {test_file}")
    print(f"[TEST]   50 cases total: 46 closed (should be 92%), 4 open (should be 8%)")

    return test_file


def run_test():
    """Run the pipeline with diagnostics."""
    print("\n" + "="*80)
    print("CLOSURE RATE BUG DIAGNOSTIC TEST")
    print("="*80)

    # Create test data
    test_file = create_test_excel()

    try:
        # Initialize orchestrator
        print("\n[TEST] Initializing pipeline orchestrator...")
        orchest = ComplaintsPipelineOrchestrator()

        # Run Stage 1
        print("\n[TEST] ▶ Running Stage 1: Validation...")
        success, msg, _ = orchest.run_stage1_validator(str(test_file))
        if not success:
            print(f"[TEST] ✗ Stage 1 failed: {msg}")
            return False
        print(f"[TEST] ✓ Stage 1 passed: {orchest.state.total_cases} cases")

        # Run Stage 2 — THIS IS WHERE WE'LL SEE THE DIAGNOSTICS
        print("\n[TEST] ▶ Running Stage 2: Rule Classifier (DIAGNOSTIC OUTPUT BELOW)...")
        print("\n" + "-"*80)
        success, msg = orchest.run_stage2_classifier()
        print("-"*80 + "\n")

        if not success:
            print(f"[TEST] ✗ Stage 2 failed: {msg}")
            return False

        # Analyze results
        print("[TEST] ▶ Analyzing closure rate from all_classified...")
        if orchest.state.all_classified:
            closed = sum(1 for c in orchest.state.all_classified if c.date_closed and str(c.date_closed).strip())
            open_cases = len(orchest.state.all_classified) - closed
            closure_rate = 100 * closed / len(orchest.state.all_classified) if orchest.state.all_classified else 0

            print(f"\n[TEST] RESULTS:")
            print(f"  Total cases: {len(orchest.state.all_classified)}")
            print(f"  Closed: {closed} ({closure_rate:.1f}%)")
            print(f"  Open: {open_cases}")
            print(f"\n[TEST] EXPECTED: 46 closed (92%), 4 open")
            print(f"[TEST] ACTUAL:   {closed} closed ({closure_rate:.1f}%), {open_cases} open")

            if closed == 46 and open_cases == 4:
                print("\n✅ [TEST] PASSED: Closure rate is correct!")
                return True
            else:
                print(f"\n❌ [TEST] FAILED: Closure rate is wrong!")
                print(f"   Missing {46 - closed} closed cases")
                return False
        else:
            print("[TEST] ✗ No all_classified data")
            return False

    except Exception as e:
        print(f"[TEST] ✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up
        test_file.unlink(missing_ok=True)
        print(f"\n[TEST] Cleaned up test file")


if __name__ == '__main__':
    success = run_test()
    sys.exit(0 if success else 1)
