# Section 3.1 Graph Implementation Summary

## Changes Made

### 1. Added New Chart Method
**File:** `real/complaints-flow/pipeline/stage6_json_report.py`  
**Lines:** 556-582

Added new method `build_sla_closure_chart()` to replace the incorrect `build_resolution_status_chart()`:

```python
def build_sla_closure_chart(self) -> Optional[Dict[str, Any]]:
    """Pie chart — SLA closure on time (whether case closed within specified SLA time)."""
    if not self.state.all_classified:
        return None

    on_time = sum(
        1 for c in self.state.all_classified
        if str(c.sla_closed_on_time).strip() == 'نعم'
    )
    total = len(self.state.all_classified)
    if total == 0:
        return None

    late = total - on_time

    return {
        "type": "pie",
        "title": "إغلاق الطلب خلال الوقت المحدد",
        "categories": ["ضمن الوقت المحدد", "خارج الوقت المحدد"],
        "series": [
            {
                "name": "إغلاق الطلب",
                "data": [float(on_time), float(late)],
            }
        ],
        "colors": ["#B68A35", "#999999"],
    }
```

### 2. Updated Charts List
**File:** `real/complaints-flow/pipeline/stage6_json_report.py`  
**Lines:** 840-847

Changed from:
```python
# Additional 3.1 charts
service_chart = self.build_service_distribution_chart()
resolution_chart = self.build_resolution_status_chart()
severity_chart = self.build_severity_chart()
charts_31 = [
    c for c in [classification_chart, service_chart, resolution_chart, severity_chart]
    if c is not None
]
```

To:
```python
# Additional 3.1 charts
service_chart = self.build_service_distribution_chart()
sla_closure_chart = self.build_sla_closure_chart()
severity_chart = self.build_severity_chart()
charts_31 = [
    c for c in [classification_chart, service_chart, severity_chart, sla_closure_chart]
    if c is not None
]
```

---

## Four Graphs in Section 3.1

### Chart 1: Classification by Type (Bar Chart)
- **Method:** `build_classification_chart()` (line 406)
- **Title:** توزيع الشكاوى حسب الفئة الفرعية
- **Data Source:** `state.all_classified[].sub_classification`
- **X-axis:** 6 complaint sub-categories
- **Y-axis:** Count per category
- **Color:** #B68A35 (gold)

**Data Extraction Logic:**
```python
subcategory_counts = defaultdict(int)
for case in self.state.all_classified:
    sub = case.sub_classification or "شكاوى بلا تصنيف خدمي (\"أخرى\")"
    subcategory_counts[sub] += 1
```

### Chart 2: Distribution by Service (Bar Chart)
- **Method:** `build_service_distribution_chart()` (line 446)
- **Title:** توزيع الشكاوى على الخدمات
- **Data Source:** `state.raw_df['الخدمة']`
- **X-axis:** Service names from input Excel
- **Y-axis:** Count per service
- **Color:** #B68A35 (gold)

**Data Extraction Logic:**
```python
df = self.state.raw_df
col = next((c for c in ['الخدمة', 'الخدمة '] if c in df.columns), None)
counts = df[col].dropna().astype(str).str.strip().replace('', float('nan')).dropna().value_counts()
```

### Chart 3: Severity Distribution (Pie Chart)
- **Method:** `build_severity_chart()` (line 512)
- **Title:** درجة خطورة الشكوى
- **Data Source:** `state.raw_df['شدة الطلب']`
- **Categories:** شكوى عادية, شكوى عاجلة, شكوى معقدة
- **Colors:** #B68A35 (normal), #999999 (urgent), #FF0000 (complex)

**Data Extraction Logic:**
```python
counts = defaultdict(int)
for val in df['شدة الطلب'].dropna().astype(str):
    val = val.strip()
    mapped = self._SEVERITY_DISPLAY_MAP.get(val, val)
    counts[mapped] += 1
```

**Severity Mapping:**
- 'شكوى روتينية' → 'شكوى عادية'
- 'شكوى روتيني' → 'شكوى عادية'
- 'شكوى حرجة' → 'شكوى عاجلة'
- 'شكوى معقدة' → 'شكوى معقدة'

### Chart 4: SLA Closure On Time (Pie Chart) ⭐ NEW
- **Method:** `build_sla_closure_chart()` (line 556) **[NEWLY ADDED]**
- **Title:** إغلاق الطلب خلال الوقت المحدد
- **Data Source:** `state.all_classified[].sla_closed_on_time`
- **Categories:** ضمن الوقت المحدد, خارج الوقت المحدد
- **Colors:** #B68A35 (on-time), #999999 (late)

**Data Extraction Logic:**
```python
on_time = sum(
    1 for c in self.state.all_classified
    if str(c.sla_closed_on_time).strip() == 'نعم'
)
total = len(self.state.all_classified)
late = total - on_time
```

---

## Data Flow

```
Input Excel (Stage 1)
├── Column: 'الخدمة' → raw_df
├── Column: 'شدة الطلب' → raw_df
└── Column: 'إغلاق_الطلب_خلال_الوقت_المحدد' → raw_df

Stage 2: Rule Classification
├── Creates: all_classified[] with sub_classification
└── Copies: sla_closed_on_time from input

Stages 3-5: LLM, Analysis, Gap Analysis
└── Preserve: sla_closed_on_time through pipeline

Stage 6: Report Generation
├── Chart 1: uses all_classified[].sub_classification
├── Chart 2: uses raw_df['الخدمة']
├── Chart 3: uses raw_df['شدة الطلب'] with mapping
└── Chart 4: uses all_classified[].sla_closed_on_time
```

---

## Key Implementation Details

### No Hardcoding
- All values dynamically calculated from state
- No preset numbers in chart definitions
- Charts filter empty values with `if c is not None`

### Data Type Conversions
- All numeric values converted to `float()` for JSON serialization
- String values stripped of whitespace before comparison
- NaN values handled with pandas `.dropna()`

### Sorting & Ordering
- Chart 1 (Classification): Fixed order from `_SUB_CLASSIFICATIONS`
- Chart 2 (Services): Sorted by count (descending via pandas `value_counts()`)
- Chart 3 (Severity): Ordered by `_SEVERITY_ORDER` (normal → urgent → complex)
- Chart 4 (SLA): Fixed 2-category order (on-time → late)

### Color Scheme
- Chart 1 & 2 (Bar charts): Single color #B68A35 (gold)
- Chart 3 (Severity pie): Mapped colors per severity
- Chart 4 (SLA pie): Gold (success) / Gray (failure)

---

## Validation

✅ **Syntax:** Python -m py_compile verified
✅ **No Import Errors:** Method uses existing `defaultdict`, `Optional`, `Dict`, `Any`
✅ **Data Sources:** All fields exist in CaseRow and raw_df
✅ **Type Safety:** Proper null checks and string conversions
✅ **Chart Order:** Updated charts_31 list with correct order

---

## Testing the Implementation

To verify the 4 graphs are working correctly:

1. **Run the complaints pipeline** with a test Excel file
2. **Check generated JSON report** for section 3.1
3. **Verify each chart object contains:**
   - `type`: "bar" or "pie"
   - `title`: Correct Arabic title
   - `categories`: Non-empty list
   - `series[0].data`: Numeric values summing to total cases

4. **Sample validation:**
   ```python
   # From pipeline state
   assert len(all_classified) > 0
   assert sum(chart['series'][0]['data'] for chart in charts_31 if chart['type'] == 'bar') == total_cases
   ```

---

## Previously Incorrect Implementation

The old Chart 4 was:
- **Method:** `build_resolution_status_chart()` (NOT suitable for section 3.1)
- **Title:** حالة معالجة الشكاوى (Processing Status)
- **Data:** sla_color field ('مرفوضة', 'نعم')
- **Categories:** مقبولة (Accepted) / مرفوضة (Rejected)
- **Issue:** Shows acceptance status, not SLA closure timing

This was REPLACED by the new `build_sla_closure_chart()` which:
- **Title:** إغلاق الطلب خلال الوقت المحدد (Closure Within SLA Time)
- **Data:** sla_closed_on_time field ('نعم', 'لا', or empty)
- **Categories:** ضمن الوقت المحدد (On-time) / خارج الوقت المحدد (Late)
- **Benefit:** Directly aligns with user's requirement for SLA performance metrics
