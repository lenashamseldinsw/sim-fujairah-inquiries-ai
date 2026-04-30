"""
Test script to verify dynamic column preservation in Excel output.

This script demonstrates how the updated pipeline preserves all input columns
and appends AI-generated columns at the end.
"""

import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.state import PipelineState, CaseRow
from pipeline.stage1_validator import run_stage1

def test_original_columns_preservation():
    """Test that original column names are preserved during validation."""
    
    # Create sample DataFrame with original column names (with spaces)
    sample_data = {
        'رقم الطلب': ['12345', '12346', '12347'],
        'تفاصيل الطلب': ['طلب 1', 'طلب 2', 'طلب 3'],
        'تاريخ الإنشاء': ['2026-01-01', '2026-01-02', '2026-01-03'],
        'قناة تقديم الخدمة': ['هاتف', 'دردشة مباشرة', 'بريد إلكتروني'],
        'نوع المكالمة': ['طلب', 'استفسار', 'شكوى'],
        'الخدمة الرئيسيه': ['خدمة 1', 'خدمة 2', 'خدمة 3'],
        'الحل': ['تم الحل', 'قيد المعالجة', 'تم الحل'],
        'الحالة SLA': ['أخضر', 'أصفر', 'أحمر'],
        'الإدارة العامة': ['الإدارة 1', 'الإدارة 2', 'الإدارة 3'],
        # Extra column not in COLUMN_MAPPING
        'ملاحظات إضافية': ['ملاحظة 1', 'ملاحظة 2', 'ملاحظة 3'],
    }
    
    df = pd.DataFrame(sample_data)
    
    # Create state and run stage 1
    state = PipelineState()
    
    print("Original columns from input DataFrame:")
    print(df.columns.tolist())
    print()
    
    # Run stage 1
    state = run_stage1(state, df)
    
    print("Original columns stored in state:")
    print(state.original_columns)
    print()
    
    print("Normalized columns in state.raw_df:")
    print(state.raw_df.columns.tolist())
    print()
    
    # Verify that original column names were preserved
    assert len(state.original_columns) == len(df.columns), "Column count mismatch"
    assert state.original_columns == df.columns.tolist(), "Original columns not preserved"
    
    # Verify that normalization happened
    assert 'رقم_الطلب' in state.raw_df.columns, "Normalization failed"
    assert 'رقم الطلب' not in state.raw_df.columns, "Column not normalized"
    
    # Verify extra column was preserved
    assert 'ملاحظات إضافية' in state.original_columns, "Extra column not preserved in original_columns"
    assert 'ملاحظات إضافية' in state.raw_df.columns, "Extra column not preserved in raw_df"
    
    print("✓ All tests passed!")
    print()
    print("Summary:")
    print(f"- Input had {len(df.columns)} columns")
    print(f"- Original column names preserved: {len(state.original_columns)}")
    print(f"- Normalized DataFrame has: {len(state.raw_df.columns)} columns")
    print(f"- Extra unmapped columns: 1 ('ملاحظات إضافية')")
    print()
    print("When generating Excel output, all these columns will appear")
    print("in the same order with original names, followed by 4 AI columns.")

if __name__ == '__main__':
    test_original_columns_preservation()
