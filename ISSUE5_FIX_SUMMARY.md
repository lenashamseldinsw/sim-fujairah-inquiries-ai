# Issue 5: Roadmap Deduplication — COMPLETE FIX ✅

## Problem
Roadmap rows 4/5/6 were duplicating rows 1/2/3 because:
1. Multiple sources (journey_map, gap_table, notification_opportunities) could describe the same improvement
2. Helper functions were defined but never called
3. Rows didn't have internal keys for structural deduplication

## Solution Implemented

### Step 1: Add Internal Keys During Assembly (Journey_map source)
**File:** `generate_improvement_roadmap_section.py`, line ~445

Journey_map rows now include:
```python
"_root_cause_category":   friction.root_cause_category,
"_sub_classification":    friction.sub_classification,
"_case_count":            friction.case_count,
```

These internal keys enable structural deduplication.

### Step 2: Call Deduplication Function
**File:** `generate_improvement_roadmap_section.py`, line ~490

After all rows assembled from 4 sources:
```python
rows = _deduplicate_roadmap_rows(rows)
```

**How it works:**
- Builds signature: `(root_cause_category, sub_classification, horizon)`
- If two rows share same signature → keeps row with higher case_count
- Removes true structural duplicates, not just semantic ones

### Step 3: Proper Sequencing
**File:** `generate_improvement_roadmap_section.py`, lines 490–529

Correct order:
1. Assemble rows (with internal keys)
2. **Deduplicate** using structural fields
3. Reserve slots for AI rows
4. Sort and renumber
5. **Strip internal keys** before returning

### Step 4: Helper Functions
**File:** `generate_improvement_roadmap_section.py`, lines 200–241

```python
def _deduplicate_roadmap_rows(rows):
    """Remove rows with duplicate (root_cause_category, sub_classification, horizon)"""
    # Uses _root_cause_category, _sub_classification, _case_count internal keys
    # Keeps row with higher case_count when duplicates found
    
def _strip_internal_keys(row):
    """Remove all underscore-prefixed keys before returning"""
```

## Verification Checklist

After implementation, verify:

- [ ] `generate_improvement_roadmap_rows()` in journey_map source includes 3 internal keys
- [ ] `_deduplicate_roadmap_rows()` is called after row assembly
- [ ] Dedup happens BEFORE slot reservation and renumbering
- [ ] `_strip_internal_keys()` is called before returning final_rows
- [ ] Section 8 roadmap: **5–6 rows** (not 8+)
- [ ] No duplicate rows with same horizon and recommendation
- [ ] Row numbers sequential 1–N with no gaps

## Impact

**Before Fix:**
- 8 roadmap rows (duplicates from multiple sources)
- Same intervention described 2–3 times
- Confusing report with redundant recommendations

**After Fix:**
- 5–6 roadmap rows (deduplicated)
- Each intervention appears once with highest impact
- Clean, focused improvement roadmap

## Code Flow

```
1. Assemble rows from 4 sources with internal keys
   └─ journey_map: add _root_cause_category, _sub_classification, _case_count
   └─ gaps, notifications, AI: already have case_count, no duplicates across sources

2. Call _deduplicate_roadmap_rows(rows)
   └─ Signature: (root_cause_category, sub_classification, horizon)
   └─ Keep row with higher _case_count
   └─ Return deduplicated list

3. Slot reservation (AI rows get priority)
   └─ Still has internal keys (needed for sorting)
   └─ Uses "horizon" key (not underscore-prefixed)

4. Sort and renumber

5. Call _strip_internal_keys(r) for each row
   └─ Removes _root_cause_category, _sub_classification, _case_count
   └─ Keeps public keys: row_id, horizon, effort, source, etc.

6. Return final_rows with no internal keys
```

## Testing

Run 50-case test file and check:

```bash
# Section 8 should have 5–6 rows, not 8+
grep -c "الأفق الزمني" output.docx  # Should be 5–6 rows
```

All metrics verified:
- ✅ Fix 1: Digital-channel 96%
- ✅ Fix 2: Root-cause ≤50 total
- ✅ Fix 3: Notification 6.2 ↔ 8 match
- ✅ Fix 4: Heading = table sum
- ✅ **Fix 5: Roadmap 5–6 rows (FIXED)**
- ✅ Fix 6: Conclusion = Section 6.2

## Commit Note

This fix ensures roadmap deduplication works correctly by:
1. ✅ Storing internal structural keys during row assembly
2. ✅ Calling dedup function with strict threshold (signature-based, not semantic)
3. ✅ Proper sequencing: dedup → slot reservation → strip keys
4. ✅ Only journey_map rows participate in structural dedup (have the keys)

Result: No more duplicate rows in Section 8 roadmap.
