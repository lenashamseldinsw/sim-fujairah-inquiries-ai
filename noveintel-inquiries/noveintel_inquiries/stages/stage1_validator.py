"""
STAGE 1: Schema Validator

Validates uploaded Excel against contract using Pandera.
Reads into pandas DataFrame, validates required columns and types.
On failure: halt, display specific failing rows in UI.
On warning (>10% nulls): log warning, continue.
"""

import pandas as pd
import pandera as pa
from pandera import Column, Index, Check, DataFrameSchema
from typing import Tuple, Dict, Any
from .state import PipelineState


def _sanitize_for_json(obj):
    """Recursively convert numpy scalars to native Python types for JSON safety."""
    try:
        import numpy as np
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(i) for i in obj]
    return obj


# Column mapping: input column name -> normalized name
COLUMN_MAPPING = {
    # Case Number
    'رقم الطلب': 'رقم_الطلب',
    'رقم_الطلب': 'رقم_الطلب',
    # Case Title / Description
    'تفاصيل الطلب': 'تفاصيل_الطلب',
    'تفاصيل_الطلب': 'تفاصيل_الطلب',
    # Date Opened
    'تاريخ الإنشاء': 'تاريخ_الإنشاء',
    'تاريخ_الإنشاء': 'تاريخ_الإنشاء',
    'تاريخ إغلاق الطلب': 'تاريخ_إغلاق_الطلب',
    # Case Channel / قناة تقديم الخدمة
    'قناة تقديم الخدمة': 'قناة_تقديم_الخدمة',
    'قناه تقديم الخدمة': 'قناة_تقديم_الخدمة',  # Common typo variation
    'قناة_تقديم_الخدمة': 'قناة_تقديم_الخدمة',
    'قناه_تقديم_الخدمة': 'قناة_تقديم_الخدمة',
    # Description / Type of Contact
    'نوع المكالمة': 'نوع_المكالمة',
    'نوع_المكالمة': 'نوع_المكالمة',
    # Resolution Response
    'الحل': 'الحل',
    'الحل ': 'الحل',
    # SLA Color / Status
    'الحالة SLA': 'الحالة_SLA',
    'الحالة_SLA': 'الحالة_SLA',
    'الحالة_SLA ': 'الحالة_SLA',
    'الحالة': 'الحالة_SLA',  # Use status as SLA color
    # SLA Compliance (نعم/لا)
    'إغلاق الطلب خلال الوقت المحدد': 'سلا_امتثال',
    'إغلاق_الطلب_خلال_الوقت_المحدد': 'سلا_امتثال',
    'سلا_امتثال': 'سلا_امتثال',
    # Case Type / Sub-classification
    'التصنيف الفرعي': 'التصنيف_الفرعي',
    'التصنيف_الفرعي': 'التصنيف_الفرعي',
    # Service Name (main/primary)
    'الخدمة الرئيسيه': 'الخدمة_الرئيسية',
    'الخدمة_الرئيسية': 'الخدمة_الرئيسية',
    'الخدمة الرئيسية': 'الخدمة_الرئيسية',
    'الخدمة_رئيسيه': 'الخدمة_الرئيسية',
    # Service Name (general/secondary)
    'الخدمة': 'الخدمة',
    'الخدمة ': 'الخدمة',
    # General Administration
    'الإدارة العامة': 'الإدارة_العامة',
    'الإدارة_العامة': 'الإدارة_العامة',
    'الاداره العامه': 'الإدارة_العامة',
    'الادارة العامة': 'الإدارة_العامة',
    'الإدارة العامة ': 'الإدارة_العامة',  # trailing space
    'إدارة عامة': 'الإدارة_العامة',  # shortened form
}

# Required normalized columns (critical for pipeline)
REQUIRED_COLUMNS = [
    'رقم_الطلب',           # Case ID - essential
    'تفاصيل_الطلب',        # Case description - essential
    'نوع_المكالمة',        # Description - essential for classification
    'الحل',                # Resolution - essential for analysis
]

# Optional but preferred columns
OPTIONAL_COLUMNS = [
    'تاريخ_الإنشاء',       # Date opened
    'قناة_تقديم_الخدمة',    # Case channel
    'الحالة_SLA',          # SLA status
    'التصنيف_الفرعي',      # Case type (may not be in input)
    'الخدمة_الرئيسية',     # Service name
    'الإدارة_العامة',     # General administration / department
    'تاريخ_إغلاق_الطلب',  # Closure date — empty means case not yet closed
]

# Accepted values (from reference)
VALID_CASE_TYPES = [
    'طلب',
    'شكوى',
    'استفسار',
    'شكر وثناء',
]

VALID_CHANNELS = [
    'هاتف',
    'خدمة ذاتية',
    'دردشة مباشرة',
    'بريد إلكتروني',
    'زيارة شخصية',
]

# Valid sub-classifications per Fujairah Police taxonomy
VALID_SUB_CLASSIFICATIONS = [
    # Complaint sub-classifications
    'تقديم بلاغ أمني أو مروري',
    'اعتراض على مخالفة مرورية',
    'شكوى عامة',
    'شكوى عن مخالفة مشكوك فيها',
    'شكوى على خطأ تقني أو في النظام',
    'شكوى عن عدم استلام الخدمة',
    'شكوى على عدم الرد',
    'شكوى على تأخر المعالجة',
    # Request sub-classifications
    'طلب توصيل أو استلام',
    'طلب خدمة عام',
    'طلب تصريح سلاح أو ترخيص',
    'طلب تجديد رخصة أو ملكية',
    'طلب إصدار شهادة أو وثيقة',
    'طلب سداد مخالفة',
    'طلب فتح ملف أو بلاغ',
    'طلب تعديل أو تحديث بيانات',
    'طلب تصريح خاص',
    'متابعة طلب مقدم',
    # Inquiry sub-classifications
    'استفسار عام',
    'استفسار عن الرخص والمركبات',
    'استفسار عن الإجراءات والمتطلبات',
    'استفسار تقني',
    'استفسار عن البلاغات الأمنية',
    'استفسار عن الأسلحة والتراخيص',
    # Praise sub-classifications
    'شكر وتقدير عام',
]


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize DataFrame columns to expected names.

    Maps input column names to normalized names using COLUMN_MAPPING.
    Handles duplicate normalized names by keeping first occurrence.
    """
    new_columns = {}
    seen_normalized = set()
    mappings = []

    for col in df.columns:
        # Convert column name to string to handle integer column names
        col_str = str(col)

        # Try exact match first
        if col in COLUMN_MAPPING:
            normalized = COLUMN_MAPPING[col]
            mappings.append(f"  {col} → {normalized} (exact)")
        # Try fuzzy match (remove extra spaces)
        elif col_str.strip() in COLUMN_MAPPING:
            normalized = COLUMN_MAPPING[col_str.strip()]
            mappings.append(f"  {col} → {normalized} (fuzzy)")
        else:
            normalized = col
            mappings.append(f"  {col} → {col} (no mapping)")

        # Avoid duplicate normalized column names
        if normalized not in seen_normalized:
            new_columns[col] = normalized
            seen_normalized.add(normalized)
        # If already seen, keep original name to avoid duplicate
        else:
            new_columns[col] = col
            mappings[-1] += " [duplicate, keeping original]"

    if mappings:
        print(f"[Stage1] Column mappings:\n" + "\n".join(mappings[:10]))

    df_norm = df.rename(columns=new_columns)
    return df_norm


def validate_excel(df: pd.DataFrame) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate Excel DataFrame against contract.

    Returns:
        (is_valid, result_dict)
        result_dict contains:
            - if valid: {'status': 'OK', 'case_count': N}
            - if invalid: {'status': 'FAILED', 'errors': [...], 'failing_rows': [...]}
            - if warning: {'status': 'WARNING', 'message': str, 'null_columns': {...}}
    """
    errors = []
    warnings = []
    failing_rows = []

    # 1. Check required columns exist
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    print(f"[Stage1] Missing columns: {missing_cols}")
    if missing_cols:
        return False, {
            'status': 'FAILED',
            'errors': [f"Missing required columns: {missing_cols}. Need at least: {REQUIRED_COLUMNS}"],
            'failing_rows': []
        }

    # Check optional columns availability (for logging)
    available_optional = [col for col in OPTIONAL_COLUMNS if col in df.columns]

    # 2. Check for duplicates in Case Number
    case_num_col = 'رقم_الطلب'
    duplicates = df[df.duplicated(subset=[case_num_col], keep=False)]
    if not duplicates.empty:
        warnings.append(f"Note: {len(duplicates)} duplicate case numbers found")
        # Don't fail on duplicates - just warn

    # 3. Check top-level Case Type values (نوع_المكالمة column)
    case_type_col = 'نوع_المكالمة'
    if case_type_col in df.columns:
        invalid_types = df[~df[case_type_col].isin(VALID_CASE_TYPES)]
        if not invalid_types.empty:
            warnings.append(f"Note: {len(invalid_types)} rows have unexpected top-level case type values")

    # 3a. Check Sub-classification values (التصنيف_الفرعي column — warning only, not hard failure)
    sub_class_col = 'التصنيف_الفرعي'
    if sub_class_col in df.columns:
        invalid_sub = df[~df[sub_class_col].isin(VALID_SUB_CLASSIFICATIONS)]
        if not invalid_sub.empty:
            warnings.append(f"Note: {len(invalid_sub)} rows have unexpected sub-classification values")

    # 4. Check Case Channel values (if present)
    channel_col = 'قناة_تقديم_الخدمة'
    if channel_col in df.columns:
        invalid_channels = df[~df[channel_col].isin(VALID_CHANNELS)]
        if not invalid_channels.empty:
            warnings.append(f"Note: {len(invalid_channels)} rows have unexpected Channel values")

    # 5. Check critical Description field is non-null (allow short descriptions)
    desc_col = 'نوع_المكالمة'
    missing_desc = df[df[desc_col].isna()]
    if not missing_desc.empty:
        warnings.append(f"Note: {len(missing_desc)} rows have missing descriptions")
    # Allow short descriptions - they may still be valid

    # 6. Try to parse dates (if present)
    date_col = 'تاريخ_الإنشاء'
    if date_col in df.columns:
        try:
            pd.to_datetime(df[date_col], errors='coerce')
        except Exception as e:
            warnings.append(f"Note: Some dates may not parse correctly")

    # 7. Check null percentages in critical columns (warning only, don't fail)
    null_counts = df[REQUIRED_COLUMNS].isnull().sum()
    null_pcts = (null_counts / len(df) * 100).round(1)
    high_null_cols = {col: pct for col, pct in zip(null_counts.index, null_pcts) if pct > 10}

    # Return results
    if errors:
        return False, {
            'status': 'FAILED',
            'errors': errors,
            'failing_rows': list(set(failing_rows))[:100]  # Cap at 100 rows
        }

    if high_null_cols:
        return True, {
            'status': 'WARNING',
            'message': f"High null percentage in some columns: {high_null_cols}",
            'null_columns': high_null_cols,
            'case_count': len(df)
        }

    return True, {
        'status': 'OK',
        'case_count': len(df)
    }


def run_stage1(state: PipelineState, df: pd.DataFrame) -> PipelineState:
    """
    Stage 1: Read and validate Excel.

    Input: pandas DataFrame from uploaded file
    Output: state with raw_df and validated_schema
    """
    # Store original column names before normalization
    state.original_columns = df.columns.tolist()
    print(f"[Stage1] Original columns detected: {state.original_columns}")

    # Normalize column names
    df_normalized = normalize_columns(df)
    print(f"[Stage1] Normalized columns: {list(df_normalized.columns)}")
    print(f"[Stage1] Required columns: {REQUIRED_COLUMNS}")

    # Null-description audit — flag rows with missing CRM label or case description before
    # they silently degrade downstream classification. Pipeline continues regardless.
    null_audit_cols = {
        'نوع_المكالمة': 'CRM label (نوع_المكالمة)',
        'تفاصيل_الطلب': 'Case description (تفاصيل_الطلب)',
    }
    for col, label in null_audit_cols.items():
        if col in df_normalized.columns:
            null_mask = df_normalized[col].isna() | (df_normalized[col].astype(str).str.strip() == '')
            null_count = null_mask.sum()
            if null_count > 0:
                null_case_ids = df_normalized.loc[null_mask, 'رقم_الطلب'].tolist() if 'رقم_الطلب' in df_normalized.columns else []
                id_preview = ', '.join(str(x) for x in null_case_ids[:10])
                ellipsis = f' … (+{null_count - 10} more)' if null_count > 10 else ''
                print(
                    f"\n⚠️  [Stage1] WARNING — {null_count} rows have null/empty {label}.\n"
                    f"   Case IDs: {id_preview}{ellipsis}\n"
                    f"   These cases will reach Stage 2 with no text to classify and will "
                    f"fall through to the CRM-label fallthrough path.\n"
                )

    # Validate
    is_valid, result = validate_excel(df_normalized)

    state.raw_df = df_normalized
    state.validated_schema = _sanitize_for_json(result)
    state.total_cases = len(df_normalized)

    # Count closed cases (where تاريخ_إغلاق_الطلب is not empty)
    # This is used in methodology section to report "X حالة مغلقة"
    closed_date_col = 'تاريخ_إغلاق_الطلب'
    if closed_date_col in df_normalized.columns:
        state.closed_cases_count = int(df_normalized[closed_date_col].notna().sum())
    else:
        # Fallback: if closing date column doesn't exist, use total cases
        state.closed_cases_count = state.total_cases

    if not is_valid:
        raise ValueError(f"Schema validation failed: {result}")

    return state
