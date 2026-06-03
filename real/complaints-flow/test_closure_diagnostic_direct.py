#!/usr/bin/env python3
"""
Direct test of date_closed processing in stage2_rules.py
Tests the diagnostic output without needing full orchestrator.
"""

import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path

# Change to pipeline directory for imports to work properly
os.chdir(Path(__file__).parent / "pipeline")
sys.path.insert(0, os.getcwd())

import stage2_rules
from state import PipelineState, CaseRow

# Create test data with 50 cases
print("="*80)
print("CLOSURE RATE DIAGNOSTIC - Direct Stage 2 Test")
print("="*80)

# Create test DataFrame
test_data = []

# 46 closed cases with dates (should be 92%)
for i in range(1, 47):
    test_data.append({
        'رقم الطلب': f'211{i:03d}',
        'تفاصيل الطلب': f'Complaint {i}',
        'الحل': f'Resolved {i}',
        'الخدمة': 'فتح البلاغات المرورية',
        'الخدمة الرئيسية': 'خدمات مرورية',
        'شدة الطلب': 'عالية',
        'نوع المكالمة': 'شكاوى',
        'قناة تقديم الخدمة': 'هاتف',
        'الحالة': 'مغلق',
        'تاريخ الإنشاء': pd.Timestamp('2026-01-01'),
        'تاريخ الإغلاق': pd.Timestamp(2026, 1, (i % 28) + 1),  # Dates as Timestamp objects
        'إغلاق الطلب خلال الوقت المحدد': 'نعم',
        'تم_الحل_بواسطة': 'Team A',
        'الإدارة_العامة': 'شرطة المرور',
        'المالك': f'Officer{i}',
        'اسم_مقدم_الطلب': f'Customer{i}',
        'الجنسية': 'Emirati',
        'رقم_الهوية': f'784{i:06d}',
        'الهاتف_الجوال': '971501234567',
        'الرقم_الوظيفي': str(i),
        'نوع_المكالمة': 'شكاوى',
    })

# 4 open cases (no date_closed)
for i in range(47, 51):
    test_data.append({
        'رقم الطلب': f'211{i:03d}',
        'تفاصيل الطلب': f'Complaint {i} - open',
        'الحل': f'Pending {i}',
        'الخدمة': 'فتح البلاغات المرورية',
        'الخدمة الرئيسية': 'خدمات مرورية',
        'شدة الطلب': 'متوسطة',
        'نوع المكالمة': 'شكاوى',
        'قناة تقديم الخدمة': 'تطبيق',
        'الحالة': 'مفتوح',
        'تاريخ الإنشاء': pd.Timestamp('2026-02-01'),
        'تاريخ الإغلاق': pd.NaT,  # Explicitly None
        'إغلاق الطلب خلال الوقت المحدد': '',
        'تم_الحل_بواسطة': '',
        'الإدارة_العامة': 'شرطة أخرى',
        'المالك': f'Officer{i}',
        'اسم_مقدم_الطلب': f'Customer{i}',
        'الجنسية': 'Emirati',
        'رقم_الهوية': f'784{i:06d}',
        'الهاتف_الجوال': '971509876543',
        'الرقم_الوظيفي': str(i),
        'نوع_المكالمة': 'شكاوى',
    })

df = pd.DataFrame(test_data)

print(f"\n[TEST] Created DataFrame with {len(df)} rows")
print(f"[TEST] Expected: 46 closed (with Timestamp dates), 4 open (NaT)")

print("\n" + "-"*80)
print("STAGE 2 DIAGNOSTIC OUTPUT:")
print("-"*80)

# Create minimal state
state = PipelineState()
state.raw_df = df
state.total_cases = len(df)
state.complaints_methodology = None

# Run stage 2 — this will print all the diagnostics
try:
    state = stage2_rules.run_stage2(state)

    print("-"*80)
    print("\nRESULTS FROM all_classified:")
    print("-"*80)

    closed_count = 0
    open_count = 0

    for c in state.all_classified:
        is_closed = c.date_closed and str(c.date_closed).strip()
        if is_closed:
            closed_count += 1
        else:
            open_count += 1

    closure_rate = 100 * closed_count / len(state.all_classified) if state.all_classified else 0

    print(f"\nTotal in all_classified: {len(state.all_classified)}")
    print(f"Closed (date_closed != ''): {closed_count} ({closure_rate:.1f}%)")
    print(f"Open (date_closed == ''): {open_count}")

    print(f"\nEXPECTED: 46 closed (92%), 4 open (8%)")
    print(f"ACTUAL:   {closed_count} closed ({closure_rate:.1f}%), {open_count} open")

    if closed_count == 46 and open_count == 4:
        print("\n✅ TEST PASSED")
    else:
        print(f"\n❌ TEST FAILED: Missing {46 - closed_count} closed cases")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
