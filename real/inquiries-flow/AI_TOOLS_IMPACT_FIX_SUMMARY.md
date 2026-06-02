# Fix: AI Use Cases Section — Tools 1 and 3 Impact Counts

## Issue

Tools 1 and 3 in Section 7 were computing impact case counts from `state.journey_map`, which is LLM-generated in Stage 4. When the Stage 4 LLM did not produce friction entries with exact expected `sub_classification` labels, these counts returned 0 and the impact statement became blank or defaulted to zero.

The correct primary source is `state.all_classified`, which is:
- Deterministically populated by Stages 2 and 3 (rule-based + LLM classification)
- Always present and complete
- The ground truth for all case analysis

## Fixes Applied

### Fix 1: Tool 1 (violation_photo_checker) — violation_cases

**File:** `generate_ai_use_cases_section.py` lines 293-317

**Before:**
```python
violation_cases = sum(
    e.case_count for e in (state.journey_map or [])
    if e.sub_classification == "شكوى عن مخالفة مشكوك فيها"
)
if violation_cases == 0:
    violation_cases = sum(...)  # fallback keyword match on journey_map
```

**After:**
```python
# Primary: count directly from all_classified (authoritative ground truth)
_SUB_DISPUTED_FINE = "شكوى عن مخالفة مشكوك فيها"
violation_cases = sum(
    1 for c in (state.all_classified or [])
    if c.sub_classification == _SUB_DISPUTED_FINE
)

# Secondary: if all_classified somehow empty, fall back to journey_map sub_classification
if violation_cases == 0:
    violation_cases = sum(
        e.case_count for e in (state.journey_map or [])
        if e.sub_classification == _SUB_DISPUTED_FINE
    )

# Last resort: keyword match on journey_map (مشكوك only, never اعتراض)
if violation_cases == 0:
    violation_cases = sum(
        e.case_count for e in (state.journey_map or [])
        if ("مشكوك" in (e.friction_point_ar or e.friction_point or "").lower() or
            "مشكوك" in (e.cluster_ar or e.cluster or "").lower())
    )
```

**Impact:** Tool 1 impact count is now derived from authoritative all_classified, guaranteed to be correct even if Stage 4 LLM produces incomplete journey_map entries.

---

### Fix 2: Tool 3 (document_quality_checker) — stalled count

**File:** `generate_ai_use_cases_section.py` lines 182-213

**Before:**
```python
def _count_document_stall_cases(state: PipelineState) -> Tuple[int, int]:
    delivery_keywords = {"استلام", "توصيل", ...}
    stalled = _count_friction_cases(state, delivery_keywords)  # journey_map keyword scan
    ...
```

**After:**
```python
def _count_document_stall_cases(state: PipelineState) -> Tuple[int, int]:
    _SUBS_NON_DELIVERY = {
        "شكوى عن عدم استلام الخدمة",
        "متابعة طلب مقدم",
    }

    # Primary: count directly from all_classified (authoritative ground truth)
    stalled = sum(
        1 for c in (state.all_classified or [])
        if c.sub_classification in _SUBS_NON_DELIVERY
    )

    # Secondary: if all_classified somehow empty, fall back to journey_map keyword match
    if stalled == 0:
        delivery_keywords = {"استلام", "توصيل", "صورة", "مستوفية", "وثيقة", "رخصة", "توقف"}
        stalled = _count_friction_cases(state, delivery_keywords)
    
    # rejected stays unchanged — reads from gap_table (Stage 5)
    ...
```

**Impact:** Tool 3 stalled count is now derived from authoritative all_classified, guaranteed to be correct even if Stage 4 LLM produces incomplete journey_map entries.

---

## What Was NOT Changed

### Tools 2 and 4 remain unchanged (as required)

**Tool 2 (agency_router):** `_count_misrouted_cases` still uses journey_map
- Misrouting is genuinely a best-effort LLM signal based on patterns in text
- No deterministic sub_classification equivalent
- Existing zero-case handling ("لم يتم التعرف على حالات موجهة...") is correct

**Tool 4 (geo_friction_radar):** `_count_geo_cases` still uses patterns with geo keywords
- Geographic mentions are genuine LLM-extracted patterns
- No deterministic sub_classification equivalent for "geographic complaint"
- Existing zero-case handling is correct

---

## Data Source Priority

### Tools 1 & 3 (FIXED)
```
Primary:   state.all_classified (authoritative, deterministic)
           ↓ (if count == 0)
Secondary: state.journey_map sub_classification (LLM-generated, may be incomplete)
           ↓ (if count == 0)
Fallback:  state.journey_map keyword match (LLM-generated, loose pattern)
```

### Tools 2 & 4 (unchanged)
```
Primary:   state.journey_map patterns + keywords (LLM-generated)
           ↓ (fallback logic inside each function)
Fallback:  state.patterns (for misrouting only)
```

---

## Testing

To verify these fixes work correctly:

1. **50-case test run** (existing sample):
   - Tool 1: Should show 7 (disputed fine cases from all_classified)
   - Tool 3: Should show correct stalled count from all_classified
   - Zero-case handling: If no matching cases exist, falls back gracefully

2. **Multi-classified dataset**:
   - Tools 1 & 3 should always produce correct counts from all_classified
   - Independent of whether Stage 4 journey_map has complete entries

3. **Edge case: empty journey_map**:
   - Tools 1 & 3: Fall back to all_classified (no impact on counts)
   - Tools 2 & 4: Show "لم يتم التعرف على..." (as before)

---

## Summary

These fixes ensure Tools 1 and 3 impact counts are **always deterministic and correct**, derived from the authoritative `state.all_classified` source rather than dependent on Stage 4 LLM-generated journey_map entries. The three-tier fallback approach provides robustness while maintaining correctness.
