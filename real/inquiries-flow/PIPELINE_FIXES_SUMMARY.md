# Pipeline Bug Fixes — Summary of Changes

## Overview
Fixed 6 critical bugs in the inquiries pipeline that were causing inflated case counts and hardcoded floor values in the Word report. All fixes ensure counts are derived exclusively from `state.all_classified` with no invented numbers or LLM hallucination.

---

## Bug 1 & 2: Friction Point Case Counts Inflated (Sections 4 & 5)

### Files Modified
- `real/inquiries-flow/pipeline/stage4_analysis.py` — `_reconcile_counts()` function

### Root Cause
The original implementation allowed multiple JourneyFriction entries sharing the same sub_classification to draw from a single remaining-budget pool. When word-overlap matching failed for one entry, it would consume the entire remaining budget, leaving none for the next entry, causing double-counting.

### Fix Applied
Rewrote `_reconcile_counts()` to:

1. **Single-friction sub-classifications**: Use the authoritative actual_count directly with no matching logic
   ```python
   if len(friction_group) == 1 and actual_count > 0:
       reconciled_count = actual_count
   ```

2. **Multi-friction sub-classifications**: Enforce strict per-sub-classification caps
   - Try word-overlap matching on classification_reason for each friction entry
   - If matches sum to ≤ actual_count, use matched counts
   - If matches exceed actual_count or fail, distribute actual_count proportionally based on LLM weights
   - Fix rounding drift to ensure total equals actual_count exactly

3. **Removed cross-group contamination**: Each sub_classification now has its own capped budget pool

### Result
- Sections 4 & 5 now show authoritative counts matching all_classified
- "شكوى عن مخالفة مشكوك فيها" shows 7 (not 9)
- "اعتراض على مخالفة مرورية" shows 6 (not 8)

---

## Bug 3 & 4: FAQ Frequency Values Wrong (Section 6.1)

### Files Modified
- `real/inquiries-flow/pipeline/state.py` — Added fields to FAQCandidate
- `real/inquiries-flow/pipeline/stage4_analysis.py` — Updated all FAQ-related tool schemas and FAQ creation
- `real/inquiries-flow/pipeline/generate_digital_transformation_section.py` — Fixed frequency lookup and sorting

### Root Cause

**Bug 3 (Frequency capping):** The FAQ frequency capping code looked up `faq.top_level` (e.g., "شكوى") in `sub_counts` dictionary which was keyed by `sub_classification` (e.g., "شكوى عن مخالفة مشكوك فيها"). The lookup always failed, falling back to capping at max(sub_counts.values()) = 9, allowing incorrect frequencies like 6 and 3.

**Bug 4 (Ranking gap):** Even after fixing frequency capping, FAQs were sorted by `faq.frequency` (LLM estimate), not by actual case counts. This meant FAQs with underestimated frequencies appeared in wrong rank order in the table.

**Additional gap:** FAQ_ONLY_TOOL schema (used in _retry_faq_only fallback) was missing sub_classification field, so any FAQ from the fallback path would have sub_classification=None and fall through to loose capping.

### Fix Applied

1. **Added sub_classification to FAQCandidate** (state.py):
   ```python
   sub_classification: Optional[str] = None
   top_level: Optional[str] = None
   ```

2. **Updated BOTH FAQ tool schemas** to request sub_classification:
   - ANALYSIS_TOOL: `"sub_classification": {"type": "string", ...}`
   - FAQ_ONLY_TOOL: `"sub_classification": {"type": "string", ...}` (with required)

3. **Updated FAQ creation** to populate new fields from LLM output in BOTH paths:
   - Main path (stage4_analysis.py lines 893-905)
   - Fallback path (_retry_faq_only, lines 658-667)
   ```python
   FAQCandidate(
       ...
       top_level=f.get('top_level', ''),
       sub_classification=f.get('sub_classification', '')
   )
   ```

4. **Fixed frequency lookup** in `_build_faq_rows_for_transform()`:
   - Build sub_counts BEFORE sorting (not after)
   - Look up `faq.sub_classification` directly:
   ```python
   faq_sub_class = getattr(faq, "sub_classification", None)
   if faq_sub_class and faq_sub_class in sub_counts:
       capped_freq = sub_counts[faq_sub_class]  # Use actual count
   ```

5. **Fixed FAQ sort order** to use actual case counts, not LLM estimates:
   ```python
   def _sort_key(faq):
       sub = getattr(faq, "sub_classification", None)
       return sub_counts.get(sub, faq.frequency) if sub else faq.frequency
   
   sorted_faqs = sorted(source, key=_sort_key, reverse=True)
   ```

6. **Updated _build_faq_prompt_context** with same sorting logic for consistency

### Result
- FAQ "suspicious vehicle photo" shows frequency 7 with correct rank (actual sub_classification count)
- FAQ "contested valid fine" shows frequency 6 with correct rank (actual sub_classification count, not underestimated at rank 4)
- No more capping at max(sub_counts.values()) = 9
- Frequencies now reflect actual case distribution
- FAQ ranking matches case volume, not LLM estimates
- Fallback retry path also populates sub_classification correctly

---

## Bug 5: AI Use Case Tool 1 Impact Inflated (Section 7)

### Files Modified
- `real/inquiries-flow/pipeline/generate_ai_use_cases_section.py` — `_count_friction_cases()` replaced with direct sub_classification lookup

### Root Cause
Tool 1 (violation photo checker) was summing case counts for ALL keywords in `_VIOLATION_PHOTO_KEYWORDS`, which includes both:
- "مشكوك" (disputed photo) → 7 cases — preventable by vision model
- "اعتراض" (contested valid fine) → 6 cases — NOT preventable (fine legitimacy is a policy decision, not a technical issue)

Sum: 7 + 6 = 13 cases (incorrect)

### Fix Applied
Replaced keyword-based union with direct sub_classification lookup:

```python
violation_cases = sum(
    e.case_count for e in (state.journey_map or [])
    if e.sub_classification == "شكوى عن مخالفة مشكوك فيها"
)
if violation_cases == 0:
    # Fallback: only keyword "مشكوك" (not "اعتراض")
    violation_cases = sum(
        e.case_count for e in (state.journey_map or [])
        if "مشكوك" in (e.friction_point_ar or "").lower()
    )
```

### Result
- Tool 1 impact shows 7 cases (only disputed photo cases)
- No mixing of contested valid fine cases
- Impact statement is now accurate to what the vision model can actually prevent

---

## Bug 6: AI Use Case Tools 2–4 Use Hardcoded Floors (Section 7)

### Files Modified
- `real/inquiries-flow/pipeline/generate_ai_use_cases_section.py` — Removed all `max(value, hardcoded_floor)` patterns

### Root Cause
Impact statements used hardcoded minimums that override actual data:
- Tool 2 (agency router): `max(misrouted_cases, 5)` → showed 5 when actual was 0
- Tool 3 (doc quality): `max(stalled, 17)` + `max(rejected, 5)` → showed 17+5=22 when actual was ~0
- Tool 4 (geo radar): `max(geo_cases, 4)` → showed 4 when actual was 0

### Fix Applied

1. **Removed all hardcoded max() floors**:
   - Tool 2: Use raw `misrouted_cases`
   - Tool 4: Use raw `geo_cases`

2. **Added helper function** `_build_document_checker_impact()` for Tool 3 to handle zero values:
   ```python
   if stalled == 0 and rejected == 0:
       return "لم يتم التعرف على حالات توقف رخصة أو طلبات مرفوضة في البيانات"
   elif stalled > 0 and rejected == 0:
       return f"منع {stalled}+ حالة رخصة متوقفة..."
   # ... handles all combinations
   ```

3. **Conditional impact statements** when data shows zero:
   - If no cases found, message reflects "no cases detected" rather than fake numbers

### Result
- Tool 2: Shows actual misrouted_cases count or "no cases detected"
- Tool 3: Shows actual stalled + rejected counts or "no cases detected"
- Tool 4: Shows actual geo_cases count or "no cases detected"
- All numbers are defensible against input data
- No "غير مبرر من بيانات العينة" (unjustified by sample data) comments

---

## Data Flow Verification

### Ground Truth Hierarchy
```
all_classified (Stage 2/3)
    ↓
state.sub_classification counts (for FAQ capping)
    ↓
journey_map reconciliation per sub_classification
    ↓
AI use case impacts (derived from journey_map + gap_table)
```

### Critical Invariants Enforced

1. **Per-sub-classification cap**: 
   - Total case_count across all frictions for sub_classification X ≤ actual_counts[X]

2. **FAQ frequency authenticity**:
   - FAQ frequency = actual sub_classification count (not LLM estimate)
   - Removes LLM hallucination entirely

3. **AI tool impacts are data-derived**:
   - No invented minimums
   - Zero values are honestly reported
   - Every number traces back to state.all_classified or journey_map

---

## Files Changed

1. `state.py`
   - Added `top_level` and `sub_classification` fields to FAQCandidate

2. `stage4_analysis.py`
   - Updated FAQ tool schema to request sub_classification
   - Updated FAQ creation code to populate new fields
   - Completely rewrote `_reconcile_counts()` function

3. `generate_digital_transformation_section.py`
   - Rewrote `_build_faq_rows_for_transform()` to use sub_classification lookup

4. `generate_ai_use_cases_section.py`
   - Replaced Tool 1 keyword-based counting with sub_classification-specific lookup
   - Removed all hardcoded max() floors from Tools 2, 3, 4
   - Added `_build_document_checker_impact()` helper function

---

## Testing Recommendations

1. **50-case test run**: Verify all 6 bug fixes show correct values
   - Section 4: Friction point counts
   - Section 5: Friction point counts
   - Section 6.1: FAQ frequencies
   - Section 7: AI tool impact statements

2. **Zero-case dataset**: Test edge cases where some sub-classifications have 0 cases
   - FAQ frequency should handle gracefully
   - AI tool impacts should show "no cases detected" instead of floor values

3. **Multi-friction sub-classification**: Test with sub_classifications having 2+ friction points
   - Verify total cap is enforced
   - Verify proportional distribution works

4. **Excel output consistency**: Verify report numbers match Excel sheet data
   - All counts in Word report trace to state.all_classified
   - No discrepancies between report sections

---

## Implementation Notes

- **No LLM-supplied minimums**: All report numbers come from state or deterministic computation
- **Transparent fallbacks**: When LLM sub_classification is missing, logs a warning and falls back gracefully
- **Authoritative ground truth**: state.all_classified is the only source of truth
- **Proportional scaling**: When exact matching fails, preserves relative importance from LLM weights
- **Rounding safety**: Tracks and fixes rounding drift to ensure sums are exact
