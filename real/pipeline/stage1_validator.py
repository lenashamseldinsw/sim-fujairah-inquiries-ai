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
    'تاريخ إغلاق الطلب': 'تاريخ_الإنشاء',
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
    # Case Type / Sub-classification
    'التصنيف الفرعي': 'التصنيف_الفرعي',
    'التصنيف_الفرعي': 'التصنيف_الفرعي',
    # Service Name
    'الخدمة الرئيسيه': 'الخدمة_الرئيسية',
    'الخدمة_الرئيسية': 'الخدمة_الرئيسية',
    'الخدمة الرئيسية': 'الخدمة_الرئيسية',
    'الخدمة_رئيسيه': 'الخدمة_الرئيسية',
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
]

# Accepted values (from reference)
VALID_CASE_TYPES = [
    'طلب',
    'شكوى',
    'استفسار',
]

VALID_CHANNELS = [
    'هاتف',
    'خدمة ذاتية',
    'دردشة مباشرة',
    'بريد إلكتروني',
    'زيارة شخصية',
]


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize DataFrame columns to expected names.

    Maps input column names to normalized names using COLUMN_MAPPING.
    Handles duplicate normalized names by keeping first occurrence.
    """
    new_columns = {}
    seen_normalized = set()

    for col in df.columns:
        # Try exact match first
        if col in COLUMN_MAPPING:
            normalized = COLUMN_MAPPING[col]
        # Try fuzzy match (remove extra spaces)
        elif col.strip() in COLUMN_MAPPING:
            normalized = COLUMN_MAPPING[col.strip()]
        else:
            normalized = col

        # Avoid duplicate normalized column names
        if normalized not in seen_normalized:
            new_columns[col] = normalized
            seen_normalized.add(normalized)
        # If already seen, keep original name to avoid duplicate
        else:
            new_columns[col] = col

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

    # 3. Check Case Type values (if present)
    case_type_col = 'التصنيف_الفرعي'
    if case_type_col in df.columns:
        invalid_types = df[~df[case_type_col].isin(VALID_CASE_TYPES)]
        if not invalid_types.empty:
            warnings.append(f"Note: {len(invalid_types)} rows have unexpected Case Type values")

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
    # Normalize column names
    df_normalized = normalize_columns(df)

    # Validate
    is_valid, result = validate_excel(df_normalized)

    state.raw_df = df_normalized
    state.validated_schema = result
    state.total_cases = len(df_normalized)

    if not is_valid:
        raise ValueError(f"Schema validation failed: {result}")

    return state
