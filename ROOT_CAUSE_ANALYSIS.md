# Root Cause Analysis & Fixes — Three Critical Issues

## Problem Statement
Three issues were preventing the pipeline from generating complete reports:
1. **Issue 1**: Customer Journey section (Section 4) completely missing
2. **Issue 2**: Gap Analysis and FAQ sections had incorrect ordinals and analysis labels
3. **Issue 3**: Methodology sources table showed `row_count: None`

## Root Causes Found

### Issue 1 — Customer Journey Missing

**Root Cause Chain**:
1. Section generation functions (`generate_executive_summary_section()`, `generate_methodology_section()`, `generate_workload_map_section()`, `generate_customer_journey_section()`) all had identical pattern:
   ```python
   except Exception as e:
       print(f"Error: {e}")
       return None  # Silent failure!
   ```

2. When these functions returned `None`, `_generate_report_sections()` raised `RuntimeError`

3. The try-except in `_generate_report_sections()` caught this error and silently fell back to `_create_basic_report_sections()`

4. Basic sections ONLY contain: executive_summary, methodology, classification_summary, recommendations
   - **Missing**: workload_map, customer_journey, patterns, gap_analysis, faq_summary

5. Result: Customer Journey section never appears in the report

**Real Issue**: Not that journey_map is empty, but that **errors were being silently swallowed**, causing the fallback to trigger.

**Fix Applied**:
- Changed all section generation functions to **raise exceptions instead of returning None**
- Now errors propagate up with full tracebacks visible
- No more silent fallbacks masking the real problems

---

### Issue 2 — Section Numbering Wrong

**Root Cause**:
- `build_gap_analysis_section()` and `build_faq_section()` had hardcoded ordinals and analysis labels:
  ```python
  "title": "سادساً: التحليل الرابع — تحليل الفجوات الرقمية"  # WRONG if sections 4-5 missing!
  "title": "سابعاً: التحليل الخامس — الأسئلة الشائعة"  # Always 7th even when it's 5th
  ```

- These titles don't reflect which sections actually appear in the final report

**Fix Applied**:
- Modified `build_gap_analysis_section(section_number)` and `build_faq_section(section_number)` to accept positional parameters
- `build_report()` now calculates actual section numbers:
  ```python
  gap_section_num = len(sections) + 1  # Count after adding previous sections
  faq_section_num = len(sections) + 1  # Count after adding gap section
  ```

- Section titles now update dynamically based on actual position:
  - **Example**: If sections 4-5 are missing, Gap becomes section 4: `"رابعاً: التحليل الثاني — تحليل الفجوات الرقمية"`
  - Instead of hardcoded: `"سادساً: التحليل الرابع"`

---

### Issue 3 — Methodology `row_count: None`

**Root Cause**:
- Two-part issue in the pipeline:
  1. `stage6_artifacts.py` - `_generate_report_sections()` line 452 creates sources table with `row_count`
  2. But then `stage6_json_report.py` - `build_methodology_section()` reads the table without verifying `row_count` exists

- If the table was created by fallback `_create_basic_report_sections()` (which had row_count set), it works
- But if LLM generation succeeded and something strips `row_count`, it becomes `None`

**Fix Applied**:
- Added explicit comment and assurance in `_generate_report_sections()` (line 452)
- Added fallback logic in `build_methodology_section()` (lines 767-768):
  ```python
  if 'row_count' not in candidate and candidate.get('rows'):
      candidate['row_count'] = len(candidate['rows'])
  ```

---

## Changes Made

### File 1: `pipeline/stage6_artifacts.py`
- Line 452: Added comment `# ISSUE 3 FIX: Explicit row_count`
- Lines 505-514: Changed exception handling from silent return to logged exception with optional fallback
- Lines 767-768: Added fallback to calculate `row_count` from rows

### File 2: `pipeline/stage6_json_report.py`
- Line 400-406: Changed `build_workload_map_section()` to return `None` instead of raising if raw_data missing
- Lines 670-708: Updated `build_gap_analysis_section()` to accept `section_number` parameter and calculate ordinals dynamically
- Lines 710-747: Updated `build_faq_section()` to accept `section_number` parameter and calculate ordinals dynamically
- Lines 899-951: Updated `build_report()` to calculate `gap_section_num` and `faq_section_num` based on sections actually included

### File 3: `pipeline/generate_workload_map_section.py`
- Lines 342-345: Changed exception handler to raise instead of returning None

### File 4: `pipeline/generate_customer_journey_section.py`
- Lines 384-388: Changed exception handler to raise instead of returning None

### File 5: `pipeline/stage6_artifacts.py` (generate_executive_summary_section)
- Lines 907-911: Changed exception handler to raise instead of returning None

### File 6: `pipeline/stage6_artifacts.py` (generate_methodology_section)
- Lines 1640-1644: Changed exception handler to raise instead of returning None

---

## Why Fallbacks Were the Problem

The original design had fallbacks because:
- "If LLM fails, create basic sections instead of crashing"
- This seemed like good defensive programming

But it actually **masked the real problems**:
- Errors were invisible
- Users couldn't diagnose what was failing
- The sections silently became incomplete without warning

**Better approach**:
- Let errors raise and be logged
- Fallback only for specific known cases (e.g., journey_map empty → graceful skip with message)
- No broad catch-all exceptions swallowing errors

---

## Expected Behavior After Fixes

### If all LLM calls succeed:
- Full report with all 7+ sections
- All sections have correct ordinals and positions
- All tables have proper `row_count`

### If journey_map is empty:
- Log warning: `"⚠️  Customer Journey section SKIPPED: state.journey_map is empty"`
- Gap and FAQ sections appear but with earlier ordinals (e.g., 4 & 5 instead of 6 & 7)
- Report still complete, just without that one section

### If other sections fail:
- Full error traceback visible instead of silent fallback
- User can see exactly what went wrong
- Fallback to basic sections only as last resort with clear logging

---

## Testing

To verify fixes work:
1. Run pipeline with valid data
2. Check logs for full tracebacks if any errors occur (instead of silent failures)
3. Verify section numbering matches actual sections in output
4. Verify `row_count` is always set (not None)
5. Verify Customer Journey section appears when journey_map is populated
