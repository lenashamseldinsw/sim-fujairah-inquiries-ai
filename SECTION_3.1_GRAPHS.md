# Section 3.1: Four Complaint Analysis Graphs

## Overview
Section 3.1 of the complaints flow report displays 4 graphs to analyze complaint distribution. All data is extracted from pipeline stages 1-5 without hardcoding.

---

## Graph 1: Distribution by Service (Bar Chart)
**Title:** توزيع الشكاوى على الخدمات

### Data Source
- **Field:** `raw_df['الخدمة']` or `raw_df['الخدمة ']` (stage 1 output)
- **Data Type:** Category/String
- **Processing:** 
  - Extract unique services
  - Count complaints per service
  - Sort by count (descending)

### Chart Structure
```
X-axis:  Service names (from input Excel)
Y-axis:  Count of complaints per service
Type:    Bar chart (horizontal bars for readability)
Color:   #B68A35 (gold)
```

### Implementation
- **Method:** `build_service_distribution_chart()` in stage6_json_report.py
- **Lines:** 446-482
- **Pandas aggregation:** `df['الخدمة'].value_counts()`

### Sample Data (from user images)
- يجب على الخدمات المرورية: 35 complaints
- خدمات مرورية: 19 complaints
- أمنية وجنائية: 18 complaints
- شكاوى عاجلة: 6 complaints
- ... (and more services)

---

## Graph 2: Classification by Complaint Type (Bar Chart)
**Title:** تصنيف أنواع الشكاوى

### Data Source
- **Field:** `all_classified[].sub_classification` (stages 2-5 pipeline output)
- **Data Type:** One of 6 complaint sub-categories
- **Processing:**
  - Count cases per sub_classification
  - Use all 6 complaint types from `_SUB_CLASSIFICATIONS`

### Chart Structure
```
X-axis:  Six complaint sub-categories:
         1. شكاوى مكررة (مرفوضة)
         2. شكاوى بلا تصنيف خدمي ("أخرى")
         3. شكاوى على الخدمات المرورية
         4. شكاوى أمنية وجنائية
         5. شكاوى شهادات وتصاريح
         6. شكاوى خارج الاختصاص والأخرى

Y-axis:  Count of complaints per type
Type:    Bar chart
Color:   #B68A35 (gold)
```

### Implementation
- **Method:** `build_classification_chart()` in stage6_json_report.py
- **Lines:** 406-431
- **Logic:**
  ```python
  subcategory_counts = defaultdict(int)
  for case in self.state.all_classified:
      sub = case.sub_classification or "شكاوى بلا تصنيف خدمي (\"أخرى\")"
      subcategory_counts[sub] += 1
  ```

### Sample Data (from user images)
- شكاوى بلا تصنيف خدمي ("أخرى"): 74 complaints
- شكاوى على الخدمات المرورية: 67 complaints
- شكاوى أمنية وجنائية: 22 complaints
- شكاوى شهادات وتصاريح: 5 complaints
- شكاوى مكررة (مرفوضة): 5 complaints
- شكاوى خارج الاختصاص والأخرى: 1 complaint

---

## Graph 3: Severity Distribution (Pie Chart)
**Title:** شدة الطلب

### Data Source
- **Field:** `raw_df['شدة الطلب']` or `raw_df['شدة_الطلب']` (stage 1 input)
- **Data Type:** Severity level string
- **Processing:**
  - Map raw severity values to standardized display names
  - Count complaints per severity level

### Severity Mapping
```python
_SEVERITY_DISPLAY_MAP = {
    'شكوى روتينية': 'شكوى عادية',
    'شكوى روتيني': 'شكوى عادية',
    'شكوى حرجة': 'شكوى عاجلة',
    'شكوى معقدة': 'شكوى معقدة',
}

# Display order
_SEVERITY_ORDER = ['شكوى عادية', 'شكوى عاجلة', 'شكوى معقدة']
```

### Chart Structure
```
Categories:
  - شكوى عادية (Normal) - #B68A35 (gold)
  - شكوى عاجلة (Urgent) - #999999 (gray)
  - شكوى معقدة (Complex) - #FF0000 (red)

Type:    Pie chart with percentage labels
Colors:  Mapped to severity level
```

### Implementation
- **Method:** `build_severity_chart()` in stage6_json_report.py
- **Lines:** 512-554
- **Logic:**
  ```python
  for val in df['شدة الطلب'].dropna().astype(str):
      val = val.strip()
      mapped = self._SEVERITY_DISPLAY_MAP.get(val, val)
      counts[mapped] += 1
  ```

### Sample Data (from user images)
- شكوى عادية: 98% (majority of complaints)
- شكوى عاجلة: 2% (urgent complaints)
- شكوى معقدة: 0% (no complex complaints in sample)

---

## Graph 4: SLA Closure On Time (Pie Chart) ⭐ NEW
**Title:** إغلاق الطلب خلال الوقت المحدد

### Data Source
- **Field:** `all_classified[].sla_closed_on_time` (stages 2-5 pipeline output)
- **Data Type:** String ('نعم' = yes / 'لا' = no, or empty)
- **Processing:**
  - Count cases where sla_closed_on_time == 'نعم'
  - Remaining cases are late/outside SLA

### Chart Structure
```
Categories:
  - ضمن الوقت المحدد (Within SLA time) - #B68A35 (gold)
  - خارج الوقت المحدد (Outside SLA time) - #999999 (gray)

Type:    Pie chart with percentage labels
Colors:  Gold/Gray for success/failure
```

### Implementation
- **Method:** `build_sla_closure_chart()` in stage6_json_report.py (NEWLY ADDED)
- **Lines:** 556-587
- **Logic:**
  ```python
  on_time = sum(
      1 for c in self.state.all_classified
      if str(c.sla_closed_on_time).strip() == 'نعم'
  )
  total = len(self.state.all_classified)
  late = total - on_time
  ```

### Sample Data (from user images)
- ضمن الوقت المحدد: 96% (cases closed on time)
- خارج الوقت المحدد: 4% (cases closed late/outside SLA)

---

## Data Flow Through Pipeline

### Stage 1: Input Validation (stage1_validator.py)
- **Input:** Excel file with raw complaint data
- **Populates:**
  - `raw_df` with columns including 'الخدمة', 'شدة الطلب'
  - Input schema validation

### Stage 2: Rule Classification (stage2_rules.py)
- **Input:** `raw_df`
- **Creates:** `rule_classified` list of CaseRow objects
- **Populates:**
  - `sla_closed_on_time` from Excel's 'إغلاق_الطلب_خلال_الوقت_المحدد' column
  - `sub_classification` based on rules (one of 6 complaint types)

### Stage 3: LLM Classification (stage3_llm.py)
- **Input:** `rule_classified` + low-confidence queue
- **Creates:** `llm_classified` list with LLM-enhanced classifications
- **Preserves:** `sla_closed_on_time` from original case

### Stage 4: Pattern Analysis (stage4_analysis.py)
- **Input:** `all_classified` (merged rule + LLM results)
- **Analyzes:** Patterns and journey friction
- **Does NOT modify:** `sla_closed_on_time` values

### Stage 5: Gap Analysis (stage5_gap.py)
- **Input:** `all_classified`
- **Generates:** Gap analysis table
- **Does NOT modify:** `sla_closed_on_time` values

### Stage 6: Report Generation (stage6_json_report.py)
- **Reads from:**
  - `state.raw_df` → for Graph 1 (services) and Graph 3 (severity)
  - `state.all_classified` → for Graph 2 (classification) and Graph 4 (SLA closure)
- **Creates:** 4 chart objects for section 3.1

---

## Chart Order in Section 3.1

The 4 charts appear in this order:
1. **Classification by Type** (`classification_chart`)
2. **Distribution by Service** (`service_chart`)
3. **Severity Distribution** (`severity_chart`)
4. **SLA Closure On Time** (`sla_closure_chart`)

### Implementation
In stage6_json_report.py, line 816-819:
```python
charts_31 = [
    c for c in [classification_chart, service_chart, severity_chart, sla_closure_chart]
    if c is not None
]
```

---

## Key Points

✅ **No hardcoding:** All values derived from pipeline stages 1-5
✅ **Accurate counts:** Each chart counts actual cases from state
✅ **Proper mapping:** Severity and SLA values mapped from input
✅ **Dynamic filtering:** Charts only include non-None values
✅ **Data consistency:** Same data flows from input through all stages
✅ **SLA field added:** New `build_sla_closure_chart()` method added for graph 4

---

## Testing Checklist

To verify the graphs are correct:

1. **Graph 1 (Services):** Check that services in Excel match x-axis labels and counts match value_counts()
2. **Graph 2 (Classification):** Verify 6 categories appear, counts sum to total cases
3. **Graph 3 (Severity):** Check that severity values from Excel are mapped correctly
4. **Graph 4 (SLA):** Count cases with 'نعم' in 'إغلاق_الطلب_خلال_الوقت_المحدد' column

Each chart's data is calculated from the actual pipeline state, not hardcoded.
