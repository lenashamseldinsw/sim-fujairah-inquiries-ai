# Section 3.1 Graph Fixes

## Fix 1: Classification Chart Title
**File:** `real/complaints-flow/pipeline/stage6_json_report.py`  
**Method:** `build_classification_chart()` (line ~420)

**Change:**
```python
# Before:
"title": "توزيع الشكاوى حسب الفئة الفرعية",

# After:
"title": "تصنيف أنواع الشكاوى",
```

**Reason:** Updated to match user requirement in the Word report design.

---

## Fix 2: Severity Chart Title & Blank Chart Issue
**File:** `real/complaints-flow/pipeline/stage6_json_report.py`  
**Method:** `build_severity_chart()` (line ~514)

### Problem
The severity pie chart was showing blank in both Streamlit and Word reports. Root causes:

1. **Title Mismatch:** "درجة خطورة الشكوى" should be "شدة الطلب"
2. **Broken Mapping:** Severity mapping was using wrong labels
   - Was mapping: 'شكوى روتينية' → 'شكوى عادية'
   - Should map: 'طلب روتينى' → 'شكوى عادية'
   - Excel input uses "طلب" (request) terminology, not "شكوى" (complaint)

### Solution

**Title Update:**
```python
# Before:
"title": "درجة خطورة الشكوى",
"name": "درجة الخطورة",

# After:
"title": "شدة الطلب",
"name": "شدة الطلب",
```

**Mapping Fix:**
```python
_SEVERITY_DISPLAY_MAP: Dict[str, str] = {
    # Request-based labels (primary)
    'طلب روتينى': 'شكوى عادية',
    'طلب روتيني': 'شكوى عادية',
    'روتينى': 'شكوى عادية',
    'روتيني': 'شكوى عادية',
    'طلب حرج': 'شكوى عاجلة',
    'حرج': 'شكوى عاجلة',
    'طلب معقد': 'شكوى معقدة',
    'معقد': 'شكوى معقدة',
    # Complaint-based labels (fallback, for backward compatibility)
    'شكوى روتينية': 'شكوى عادية',
    'شكوى روتيني': 'شكوى عادية',
    'شكوى حرجة': 'شكوى عاجلة',
    'شكوى معقدة': 'شكوى معقدة',
}
```

**Debug Logging Added:**
```python
print("[build_severity_chart] raw_df is None, skipping")
print(f"[build_severity_chart] No severity column found. Available columns: {df.columns.tolist()}")
print(f"[build_severity_chart] No valid severity data found. Total non-empty: {non_empty_count}")
print(f"[build_severity_chart] No severity categories matched. Raw counts: {dict(counts)}")
print(f"[build_severity_chart] Built pie chart with categories: {categories}, counts: {[counts[s] for s in categories]}")
```

These debug prints will help identify issues in future runs.

---

## Fix 3: Vertical Bar Charts
**File:** `real/complaints-flow/pipeline/stage6_json_report.py`

### Chart 1: Classification by Type
**Method:** `build_classification_chart()` (line ~420)

**Change:**
```python
# Added orientation parameter:
"orientation": "vertical"
```

### Chart 2: Distribution by Service
**Method:** `build_service_distribution_chart()` (line ~471)

**Change:**
```python
# Added orientation parameter:
"orientation": "vertical"
```

**Implementation Note:**
The `orientation: "vertical"` parameter instructs the chart rendering engine to:
- Display bars vertically (standing up) instead of horizontally
- Show categories on X-axis (horizontal)
- Show values on Y-axis (vertical)
- Auto-rotate category labels if they're too long

---

## Summary of Changes

| Issue | Fix | File | Method |
|-------|-----|------|--------|
| Classification title | Changed to "تصنيف أنواع الشكاوى" | stage6_json_report.py | build_classification_chart() |
| Severity chart blank | Fixed mapping "طلب" → "شكوى" | stage6_json_report.py | build_severity_chart() |
| Severity chart title | Changed to "شدة الطلب" | stage6_json_report.py | build_severity_chart() |
| Bar charts horizontal | Added vertical orientation | stage6_json_report.py | build_classification_chart(), build_service_distribution_chart() |
| Missing debug info | Added logging for troubleshooting | stage6_json_report.py | build_severity_chart() |

---

## Why Severity Chart Was Blank

**Root Cause:** Severity mapping mismatch

The Excel input contains severity values like:
- 'طلب روتينى' (request - normal)
- 'طلب حرج' (request - urgent)
- 'طلب معقد' (request - complex)

But the mapping was looking for:
- 'شكوى روتينية' (complaint - normal)
- 'شكوى حرجة' (complaint - urgent)
- 'شكوى معقدة' (complaint - complex)

When no values matched the mapping, the `counts` dictionary remained empty, which caused the method to return `None` (line 535: `if not counts: return None`), making the chart disappear from both Streamlit and Word output.

**How Fix Works:**
1. New mapping includes both "طلب" (request) and "شكوى" (complaint) variants
2. Variants without diacritics included ('روتينى' vs 'روتيني')
3. If input uses "طلب", it now maps to display "شكوى"
4. Logging helps identify if this ever happens again

---

## Testing the Fixes

To verify all three fixes work:

```bash
# 1. Run the complaints pipeline with test data
cd real && python -c "from complaints_flow.pipeline.orchestrator import run_pipeline; ..."

# 2. Check console output for debug messages
# Look for: "[build_severity_chart] Built pie chart with categories: ..."

# 3. Check generated JSON report
# Verify section 3.1 has:
# - Chart 1: "تصنيف أنواع الشكاوى" (vertical bars)
# - Chart 2: "توزيع الشكاوى على الخدمات" (vertical bars)
# - Chart 3: "شدة الطلب" (pie chart with data)
# - Chart 4: "إغلاق الطلب خلال الوقت المحدد" (pie chart)

# 4. Verify Word report
# Open generated .docx and check section 3.1:
# - All 4 graphs should render
# - Pie chart should show severity distribution
# - Bar charts should be vertical
```

---

## Chart Titles After Fixes

### Section 3.1 — Complete Chart List

1. **تصنيف أنواع الشكاوى** (Bar, Vertical)
   - Shows distribution across 6 complaint types
   - Data: all_classified[].sub_classification
   - Color: Gold (#B68A35)

2. **توزيع الشكاوى على الخدمات** (Bar, Vertical)
   - Shows distribution across services
   - Data: raw_df['الخدمة']
   - Color: Gold (#B68A35)

3. **شدة الطلب** (Pie Chart) ⭐ NOW FIXED
   - Shows severity distribution
   - Data: raw_df['شدة الطلب'] with fixed mapping
   - Colors: Gold (normal), Gray (urgent), Red (complex)

4. **إغلاق الطلب خلال الوقت المحدد** (Pie Chart)
   - Shows SLA closure performance
   - Data: all_classified[].sla_closed_on_time
   - Colors: Gold (on-time), Gray (late)

---

## Notes for Future Development

- Severity mapping now covers both "طلب" and "شكوى" terminology
- Debug logging will help identify future data issues
- If new severity variants appear in data, add them to `_SEVERITY_DISPLAY_MAP`
- Bar chart orientation can be easily changed via the `orientation` parameter
- All chart data is still dynamically extracted from pipeline state (no hardcoding)
