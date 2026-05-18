"""
STAGE 1: Schema Validator (Complaints Pipeline)

Validates uploaded Excel against contract using Pandera.
Reads into pandas DataFrame, validates required columns and types.
On failure: halt, display specific failing rows in UI.
On warning (>10% nulls): log warning, continue.

CRITICAL: Input Excel has header on row 5, not row 1 (orchestrator passes header=4).
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
# Covers all 27 columns from Complaints_2025.xlsx input file
COLUMN_MAPPING = {
    # Case Number
    'رقم الطلب': 'رقم_الطلب',
    'رقم_الطلب': 'رقم_الطلب',

    # Case Title / Description
    'تفاصيل الطلب': 'تفاصيل_الطلب',
    'تفاصيل_الطلب': 'تفاصيل_الطلب',

    # Resolution Response
    'الحل': 'الحل',
    'الحل ': 'الحل',

    # Service Name (PRIMARY classification signal for complaints)
    'الخدمة': 'الخدمة',
    'الخدمة ': 'الخدمة',

    # Service Name (secondary)
    'الخدمة الرئيسية': 'الخدمة_الرئيسية',
    'الخدمة_الرئيسية': 'الخدمة_الرئيسية',
    'الخدمة الرئيسيه': 'الخدمة_الرئيسية',
    'الخدمة_رئيسيه': 'الخدمة_الرئيسية',

    # Severity Level (شدة_الطلب)
    'شدة الطلب': 'شدة_الطلب',
    'شدة_الطلب': 'شدة_الطلب',
    'شدة الطلب ': 'شدة_الطلب',

    # Case Type / Contact Type
    'نوع المكالمة': 'نوع_المكالمة',
    'نوع_المكالمة': 'نوع_المكالمة',

    # Pipeline OUTPUT: classification (never read from input)
    'نوع_الشكوى': 'نوع_الشكوى',
    'نوع الشكوى': 'نوع_الشكوى',

    # Case Channel
    'قناة تقديم الخدمة': 'قناة_تقديم_الخدمة',
    'قناه تقديم الخدمة': 'قناة_تقديم_الخدمة',  # Common typo
    'قناة_تقديم_الخدمة': 'قناة_تقديم_الخدمة',
    'قناه_تقديم_الخدمة': 'قناة_تقديم_الخدمة',

    # Case Status
    'الحالة': 'الحالة',
    'الحالة ': 'الحالة',

    # Date Opened
    'تاريخ الإنشاء': 'تاريخ_الإنشاء',
    'تاريخ_الإنشاء': 'تاريخ_الإنشاء',

    # Date Closed
    'تاريخ إغلاق الطلب': 'تاريخ_الإغلاق',
    'تاريخ_إغلاق_الطلب': 'تاريخ_الإغلاق',
    'تاريخ الإغلاق': 'تاريخ_الإغلاق',

    # SLA Closure (Yes/No)
    'إغلاق الطلب خلال الوقت المحدد': 'إغلاق_الطلب_خلال_الوقت_المحدد',
    'إغلاق_الطلب_خلال_الوقت_المحدد': 'إغلاق_الطلب_خلال_الوقت_المحدد',

    # Resolved By
    'تم الحل بواسطة': 'تم_الحل_بواسطة',
    'تم_الحل_بواسطة': 'تم_الحل_بواسطة',

    # General Administration
    'الإدارة العامة': 'الإدارة_العامة',
    'الإدارة_العامة': 'الإدارة_العامة',
    'الاداره عامه': 'الإدارة_العامة',
    'الاداره العامه': 'الإدارة_العامة',  # lowercase ه variant
    'الادارة العامة': 'الإدارة_العامة',
    'الإداره_العامة': 'الإدارة_العامة',
    'الإداره العامة': 'الإدارة_العامة',  # CRITICAL: actual input (Complaints_2025.xlsx col 12)

    # Owner / Creator
    'انشاء بواسطة': 'انشاء_بواسطة',
    'المالك': 'المالك',

    # Applicant Name
    'اسم مقدم الطلب': 'اسم_مقدم_الطلب',
    'اسم_مقدم_الطلب': 'اسم_مقدم_الطلب',

    # Nationality
    'الجنسية': 'الجنسية',

    # ID Number
    'رقم الهوية': 'رقم_الهوية',
    'رقم_الهوية': 'رقم_الهوية',

    # Mobile
    'الهاتف الجوال': 'الهاتف_الجوال',
    'الهاتف_الجوال': 'الهاتف_الجوال',

    # Employee Number
    'الرقم الوظيفى': 'الرقم_الوظيفي',  # Input has ى not ي
    'الرقم الوظيفي': 'الرقم_الوظيفي',
    'الرقم_الوظيفي': 'الرقم_الوظيفي',
    'الرقم_وظيفي': 'الرقم_الوظيفي',

    # Emirate
    'الإمارة': 'الإمارة',
}

# Required normalized columns (critical for pipeline)
REQUIRED_COLUMNS = [
    'رقم_الطلب',           # Case ID - essential
    'تفاصيل_الطلب',        # Case description - essential
    'الحل',                # Resolution - essential for analysis
    'الخدمة',              # Service field - PRIMARY classification signal
]

# Optional but preferred columns
OPTIONAL_COLUMNS = [
    'تاريخ_الإنشاء',
    'تاريخ_الإغلاق',
    'قناة_تقديم_الخدمة',
    'الحالة',
    'شدة_الطلب',
    'إغلاق_الطلب_خلال_الوقت_المحدد',
    'تم_الحل_بواسطة',
    'الإدارة_العامة',
    'نوع_المكالمة',
    'الخدمة_الرئيسية',
    'اسم_مقدم_الطلب',
    'الجنسية',
    'رقم_الهوية',
    'الهاتف_الجوال',
    'الرقم_الوظيفي',
]

# Severity levels (شدة_الطلب)
VALID_SEVERITY_LEVELS = [
    'طلب روتينى',
    'طلب حرج',
    'طلب معقد',
]

# Case statuses (الحالة)
VALID_CASE_STATUSES = [
    'تم الموافقة على الحل',
    'طلب منجز',
    'طلب مرفوض',
]

# Complaint sub-categories (6 categories for complaints pipeline)
VALID_COMPLAINT_SUB_CATEGORIES = [
    'شكاوى مكررة (مرفوضة)',
    'شكاوى بلا تصنيف خدمي ("أخرى")',
    'شكاوى على الخدمات المرورية',
    'شكاوى أمنية وجنائية',
    'شكاوى شهادات وتصاريح',
    'شكاوى خارج الاختصاص والأخرى',
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

    # 3. Check severity levels (if present)
    severity_col = 'شدة_الطلب'
    if severity_col in df.columns:
        invalid_severity = df[~df[severity_col].isin(VALID_SEVERITY_LEVELS)]
        if not invalid_severity.empty:
            warnings.append(f"Note: {len(invalid_severity)} rows have unexpected severity levels")

    # 4. Check case statuses (الحالة)
    status_col = 'الحالة'
    if status_col in df.columns:
        invalid_status = df[~df[status_col].isin(VALID_CASE_STATUSES)]
        if not invalid_status.empty:
            warnings.append(f"Note: {len(invalid_status)} rows have unexpected case statuses")

    # 5. Check case type (نوع_المكالمة) - should be 'شكاوى'
    case_type_col = 'نوع_المكالمة'
    if case_type_col in df.columns:
        invalid_types = df[df[case_type_col] != 'شكاوى']
        if not invalid_types.empty:
            warnings.append(f"Note: {len(invalid_types)} rows have case_type != 'شكاوى'")

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

    Input: pandas DataFrame from uploaded file (with header=4 offset applied by orchestrator)
    Output: state with raw_df and validated_schema; computed complaint metrics
    """
    # Store original column names before normalization
    state.original_columns = df.columns.tolist()
    print(f"[Stage1] Original columns detected: {state.original_columns}")

    # Normalize column names
    df_normalized = normalize_columns(df)
    print(f"[Stage1] Normalized columns: {list(df_normalized.columns)}")
    print(f"[Stage1] Required columns: {REQUIRED_COLUMNS}")

    # Null-description audit
    null_audit_cols = {
        'تفاصيل_الطلب': 'Case description (تفاصيل_الطلب)',
        'الحل': 'Resolution (الحل)',
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
                )

    # Validate
    is_valid, result = validate_excel(df_normalized)

    state.raw_df = df_normalized
    state.validated_schema = _sanitize_for_json(result)
    state.total_cases = len(df_normalized)

    # --- COMPLAINTS-SPECIFIC STATE COMPUTATION ---

    # 1. Channel distribution (strip trailing spaces from raw values)
    if 'قناة_تقديم_الخدمة' in df_normalized.columns:
        channel_counts = df_normalized['قناة_تقديم_الخدمة'].str.strip().value_counts()
        state.channel_distribution = _sanitize_for_json(channel_counts.to_dict())

    # 2. Digital channel rate (تطبيق الهاتف + موقع إلكتروني + NCRM = digital)
    DIGITAL_CHANNELS = ['تطبيق الهاتف', 'موقع الكترونى', 'NCRM']
    if 'قناة_تقديم_الخدمة' in df_normalized.columns:
        digital_count = sum(
            state.channel_distribution.get(c, 0) for c in DIGITAL_CHANNELS
        )
        state.digital_channel_rate = round(
            digital_count / state.total_cases * 100, 1
        ) if state.total_cases else 0.0

    # 3. Severity distribution
    if 'شدة_الطلب' in df_normalized.columns:
        state.complaint_severity_distribution = _sanitize_for_json(
            df_normalized['شدة_الطلب'].value_counts().to_dict()
        )

    # 4. Department distribution (strip "الفجيرة - " prefix)
    dept_col = 'الإدارة_العامة'
    if dept_col in df_normalized.columns:
        dept_clean = df_normalized[dept_col].str.replace(
            r'^الفجيرة\s*-\s*', '', regex=True
        ).str.strip()
        state.department_distribution = _sanitize_for_json(dept_clean.value_counts().to_dict())

    # 5. Rejection rate (الحالة == 'طلب مرفوض')
    if 'الحالة' in df_normalized.columns:
        rejected = (df_normalized['الحالة'].str.strip() == 'طلب مرفوض').sum()
        state.rejection_rate = round(
            rejected / state.total_cases * 100, 1
        ) if state.total_cases else 0.0
        state.zero_rejection_flag = (rejected == 0)

    # 6. Closed cases count
    closed_col = 'تاريخ_الإغلاق'
    if closed_col in df_normalized.columns:
        state.closed_cases_count = int(df_normalized[closed_col].notna().sum())
    else:
        state.closed_cases_count = state.total_cases

    if not is_valid:
        raise ValueError(f"Schema validation failed: {result}")

    return state
