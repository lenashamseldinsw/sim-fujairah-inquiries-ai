# Dynamic Excel Column Preservation Update

## Overview

Updated the Excel output generation to **dynamically preserve all input columns** from the uploaded Excel file, rather than hardcoding a fixed set of columns. This ensures that the output Excel maintains the exact same columns as the input, with AI-generated columns appended at the end.

## Changes Made

### 1. State Model (`real/inquiries-flow/pipeline/state.py`)

**Added field to store original column names:**
```python
original_columns: List[str] = Field(default_factory=list)
```

This field stores the column names from the input Excel file before normalization.

### 2. Stage 1 Validator (`real/inquiries-flow/pipeline/stage1_validator.py`)

**Updated `run_stage1()` to capture original columns:**
```python
def run_stage1(state: PipelineState, df: pd.DataFrame) -> PipelineState:
    # Store original column names before normalization
    state.original_columns = df.columns.tolist()
    
    # ... rest of the function
```

### 3. Stage 6 Artifacts (`real/inquiries-flow/pipeline/stage6_artifacts.py`)

**Completely rewrote `_populate_all_cases_sheet()` function:**

#### Key improvements:

1. **Dynamic Column Headers**: Uses `state.original_columns` instead of hardcoded list
2. **Smart Data Mapping**: 
   - For columns mapped to `CaseRow` attributes → gets data from the case object
   - For unmapped columns → retrieves data from `state.raw_df` (preserves original values)
   - For missing columns → leaves empty
3. **Backward Compatibility**: Falls back to default column list if `original_columns` is empty
4. **Case Number Lookup**: Creates an efficient lookup dictionary by case number to retrieve raw data for unmapped columns

#### Updated function calls:
```python
# All calls now pass the state parameter
_populate_all_cases_sheet(ws_all, state.all_classified, state)
_populate_all_cases_sheet(ws_type, subset, state)
_populate_all_cases_sheet(ws_misclass, misclassified, state)
```

## How It Works

### Flow:

1. **Stage 1**: Input Excel is uploaded
   - Original column names are stored in `state.original_columns`
   - DataFrame is normalized for internal processing
   - Raw DataFrame is stored in `state.raw_df`

2. **Stages 2-5**: Classification and analysis
   - Work with normalized column names
   - Results stored in `CaseRow` objects

3. **Stage 6**: Excel output generation
   - Uses `state.original_columns` for headers (preserves exact names from input)
   - Maps data back using COLUMN_MAPPING
   - For unmapped columns, retrieves from `state.raw_df`
   - Appends AI-generated columns at the end

### Example:

**Input Excel columns:**
```
رقم الطلب | تفاصيل الطلب | تاريخ الإنشاء | قناة تقديم الخدمة | نوع المكالمة | ...
```

**Output Excel columns:**
```
رقم الطلب | تفاصيل الطلب | تاريخ الإنشاء | قناة تقديم الخدمة | نوع المكالمة | ... | التصنيف_الفعلي | التصنيف_الفرعي | السبب | إعادة_التصنيف
```

The output preserves **all input columns in their original order and with original names**, then adds the 4 AI-generated columns.

## AI-Generated Columns

These 4 columns are always appended at the end:

1. **التصنيف_الفعلي** (Actual Classification)
2. **التصنيف_الفرعي** (Sub-classification)
3. **السبب** (Classification Reason)
4. **إعادة_التصنيف** (Reclassification Flag: نعم/لا)

## Benefits

1. **Flexibility**: Works with any input Excel structure
2. **Data Preservation**: No data loss from unmapped columns
3. **Consistency**: Output matches input structure exactly
4. **Future-Proof**: No need to update code when input columns change
5. **Backward Compatible**: Falls back to defaults if `original_columns` is not set

## Testing Recommendations

To verify the changes work correctly:

1. Test with the standard Fujairah Police input Excel
2. Test with input files that have extra columns not in COLUMN_MAPPING
3. Test with input files missing optional columns
4. Verify all sheets in the Excel workbook have correct columns
5. Check that unmapped columns preserve their original data

## Files Modified

- `real/inquiries-flow/pipeline/state.py` - Added `original_columns` field
- `real/inquiries-flow/pipeline/stage1_validator.py` - Capture original columns
- `real/inquiries-flow/pipeline/stage6_artifacts.py` - Dynamic column generation
