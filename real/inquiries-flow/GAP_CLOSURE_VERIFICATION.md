# Gap Closure Verification — All 6 Bugs Now Fully Fixed

## Status: ✅ COMPLETE

All 6 bugs are now properly fixed with no remaining gaps.

---

## Bug 1 & 2: Friction Point Counts Inflated ✅ COMPLETE

**Files:** `stage4_analysis.py` — `_reconcile_counts()` function

**Fix Status:** Properly implemented with no gaps
- Single-friction sub-classifications use actual_counts[sub_class] directly
- Multi-friction sub-classifications enforce strict per-group cap as hard ceiling
- Proportional distribution respects actual counts
- Rounding drift is fixed to ensure totals equal actual_counts exactly

**Verification:** ✅ Code confirmed correct

---

## Bug 3: FAQ Frequency Capping ✅ NOW COMPLETE (Gap Closed)

**Files:** 
- `state.py` — FAQCandidate model
- `stage4_analysis.py` — ANALYSIS_TOOL + FAQ_ONLY_TOOL schemas + FAQ creation in both paths
- `generate_digital_transformation_section.py` — `_build_faq_rows_for_transform()`

**Gap That Was Closed:**
The FAQ_ONLY_TOOL schema (used in _retry_faq_only fallback) did NOT include sub_classification. When the fallback retry path fired, FAQCandidate objects were created without sub_classification populated, causing them to fall through to loose max(sub_counts.values()) capping.

**Fix Applied:**
1. Added `sub_classification` to FAQ_ONLY_TOOL schema (lines 556-559)
   - Now required field in the LLM output
   
2. Updated _retry_faq_only FAQCandidate creation (lines 633-645)
   - Now populates both `top_level` and `sub_classification` from LLM output
   - Guarantees no FAQs will have sub_classification=None after fallback retry

3. ANALYSIS_TOOL already had sub_classification (from earlier fix)

**Verification:** ✅ Both paths now populate sub_classification correctly

---

## Bug 4: FAQ Ranking Wrong ✅ NOW COMPLETE (Gap Closed)

**Files:** `generate_digital_transformation_section.py`
- `_build_faq_rows_for_transform()` 
- `_build_faq_prompt_context()`

**Gap That Was Closed:**
FAQ table was sorted by `faq.frequency` (LLM estimate), not by actual sub_classification case counts. This meant FAQs with underestimated frequencies appeared in wrong rank order. For example, a FAQ with LLM estimate of 3 cases would appear after one with estimate of 6, even if the actual counts were reversed (6 vs 7).

**Fix Applied:**

1. **_build_faq_rows_for_transform()** (lines 132-145):
   - Build sub_counts BEFORE sorting (moved above sort operation)
   - Created `_sort_key()` function that returns actual sub_classification count
   ```python
   def _sort_key(faq):
       sub = getattr(faq, "sub_classification", None)
       return sub_counts.get(sub, faq.frequency) if sub else faq.frequency
   sorted_faqs = sorted(source, key=_sort_key, reverse=True)
   ```
   - FAQs now sorted by actual case distribution, not LLM estimates

2. **_build_faq_prompt_context()** (lines 204-215):
   - Updated to use same `_sort_key()` logic for consistency
   - Now returns `sub_classification` in context for LLM (line 224)
   - Ensures LLM sees FAQs in order of actual impact, not LLM guesses

**Result:**
- FAQ with 6 actual cases appears at correct rank even if LLM underestimated at 3
- FAQ with 7 actual cases appears at correct rank even if LLM underestimated at 6
- Displayed frequencies match actual counts (6 and 7)
- Rank order matches actual impact

**Verification:** ✅ Sorting now uses actual counts as primary sort key

---

## Bug 5: Tool 1 Impact Inflated ✅ COMPLETE

**Files:** `generate_ai_use_cases_section.py` — `_build_ai_tool_rows()`

**Fix Status:** Properly implemented with no gaps
- Direct sub_classification lookup: only count "شكوى عن مخالفة مشكوك فيها"
- Fallback uses keyword "مشكوك" only (excludes "اعتراض")
- No mixing of contested valid fine cases
- Impact shows 7 cases (only disputed photos preventable by vision model)

**Verification:** ✅ Code confirmed correct

---

## Bug 6: Hardcoded Floors ✅ COMPLETE

**Files:** `generate_ai_use_cases_section.py`
- Tool 2 (agency_router): Removed `max(misrouted_cases, 5)`
- Tool 3 (document_quality_checker): Removed `max(stalled, 17)` and `max(rejected, 5)`, added helper
- Tool 4 (geo_friction_radar): Removed `max(geo_cases, 4)`

**Fix Status:** Properly implemented with no gaps
- All hardcoded floors removed
- Zero-count cases handled gracefully with "no cases detected" messages
- All impact statements data-driven

**Verification:** ✅ Code confirmed correct

---

## Complete Data Flow

```
state.all_classified (ground truth, Stage 2/3)
    ↓
Sub-classification case counts (verified against all_classified)
    ↓
Journey map reconciliation (capped per sub_classification, Stage 4)
    ↓
FAQs: frequency = actual sub_classification count (Bugs 3 & 4 fix)
FAQs: sorted by actual counts, not LLM estimates (Bug 4 gap fix)
    ↓
AI tool impacts (Tool 1 specific sub_classification, Tools 2-4 no floors)
```

---

## All Required Changes

### stage4_analysis.py
- ✅ Added sub_classification to ANALYSIS_TOOL schema
- ✅ Added sub_classification to FAQ_ONLY_TOOL schema (NEW - gap fix)
- ✅ Updated FAQ creation in main path to populate sub_classification
- ✅ Updated FAQ creation in _retry_faq_only to populate sub_classification (NEW - gap fix)
- ✅ Completely rewrote _reconcile_counts function

### state.py
- ✅ Added top_level and sub_classification fields to FAQCandidate

### generate_digital_transformation_section.py
- ✅ Moved sub_counts build before sorting (NEW - gap fix)
- ✅ Added _sort_key function for actual-count-based sorting (NEW - gap fix)
- ✅ Updated _build_faq_rows_for_transform to use new sort key (NEW - gap fix)
- ✅ Updated _build_faq_prompt_context to use new sort key (NEW - gap fix)
- ✅ Fixed frequency lookup to use sub_classification

### generate_ai_use_cases_section.py
- ✅ Added _build_document_checker_impact helper function
- ✅ Fixed Tool 1 to use sub_classification-specific lookup
- ✅ Removed max(misrouted_cases, 5) floor from Tool 2
- ✅ Removed max(stalled, 17) and max(rejected, 5) floors from Tool 3
- ✅ Removed max(geo_cases, 4) floor from Tool 4
- ✅ Added conditional impact statements for zero-count cases

---

## Invariants Verified

1. **Per-sub-classification cap:** ✅ Enforced in _reconcile_counts
2. **FAQ frequency authenticity:** ✅ Uses sub_classification count, not LLM estimate
3. **FAQ ranking reflects impact:** ✅ Sorted by actual counts, not LLM estimates
4. **No hardcoded floors:** ✅ All values data-driven
5. **Fallback paths secure:** ✅ FAQ_ONLY_TOOL now includes sub_classification

---

## Summary

**Before gaps closed:** Bugs 1, 2, 5, 6 were fully fixed. Bugs 3 & 4 had gaps:
- Bug 3: FAQ_ONLY_TOOL fallback could produce FAQs without sub_classification
- Bug 4: FAQ sort order used LLM estimates instead of actual counts

**After gaps closed:** All 6 bugs are now fully and completely fixed with no remaining gaps or edge cases.
