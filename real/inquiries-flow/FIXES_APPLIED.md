# Inquiries Flow — Reconciliation & Count Fixes Applied

## Summary

Three critical fixes have been applied to the **inquiries flow** to prevent LLM hallucination and ensure accurate case counting:

1. **Hard Ceiling Enforcement** in `stage4_analysis.py`
2. **Non-Delivery Case Counting** in `generate_ai_use_cases_section.py`  
3. **Notification Delivery Cap** in `generate_digital_transformation_section.py`

---

## Fix 1: Hard Ceiling Enforcement (stage4_analysis.py)

**Location**: After sub_classification budget allocation, before notification reconciliation (lines ~493-518)

**What it does**: After all reconciliation steps complete, enforces an absolute hard ceiling that no friction point can exceed the actual count of cases with its sub_classification.

**Code added**:
```python
# ── FINAL ENFORCEMENT: Hard ceiling per sub_classification ───────────────────────
# After all reconciliation, enforce hard cap: no friction point can exceed
# the actual count of cases with that sub_classification.
for i, friction in enumerate(reconciled_journey_map):
    sub = friction.sub_classification
    if sub and sub in actual_counts:
        actual_count = actual_counts[sub]
        if friction.case_count > actual_count:
            print(f"[Stage4] HARD CEILING CLAMP: ... {friction.case_count} → {actual_count}")
            reconciled_journey_map[i] = friction.model_copy(update={"case_count": actual_count})
```

**Why**: Closes the loophole where a friction point could still claim more cases than actually exist for that sub_classification.

---

## Fix 2: Non-Delivery Case Counting (generate_ai_use_cases_section.py)

**Location**: `_count_document_stall_cases()` function (lines 182-217)

**What changed**: 
- **BEFORE**: `_SUBS_NON_DELIVERY = { "شكوى عن عدم استلام الخدمة", "متابعة طلب مقدم" }`
- **AFTER**: `_SUB_NON_DELIVERY = "شكوى عن عدم استلام الخدمة"` (ONLY this one)

**Code changed**:
```python
def _count_document_stall_cases(state: PipelineState) -> Tuple[int, int]:
    """
    ...
    Stalled licenses: ONLY cases classified as "شكوى عن عدم استلام الخدمة"
    (CRITICAL: Do NOT include "متابعة طلب مقدم" — that's a follow-up inquiry, not a confirmed delivery failure)
    ...
    """
    # EXPERT CRITERION: Only count confirmed non-delivery cases, not follow-up inquiries
    _SUB_NON_DELIVERY = "شكوى عن عدم استلام الخدمة"
    
    stalled = sum(
        1 for c in (state.all_classified or [])
        if c.sub_classification == _SUB_NON_DELIVERY  # Changed from 'in _SUBS_NON_DELIVERY'
    )
```

**Why**: The expert's criterion is strict — only confirmed service delivery failures count for Tool 3's impact, not follow-up inquiries about in-progress requests.

---

## Fix 3: Notification Delivery Cap (generate_digital_transformation_section.py)

**Location**: `_build_notification_rows()` function (lines 262-330+)

**New helper function added**:
```python
def _count_delivery_stall_cases(state: PipelineState) -> int:
    """Count cases with ONLY "شكوى عن عدم استلام الخدمة" sub-classification."""
    DELIVERY_FAILURE_SUB_CLASS = "شكوى عن عدم استلام الخدمة"
    count = 0
    for case in (state.all_classified or []):
        if case.sub_classification == DELIVERY_FAILURE_SUB_CLASS:
            count += 1
    return count
```

**Special handling in notification rows**:
```python
# ── SPECIAL CAP: delivery notification rows ──────────────────────────────
# If this notification is about document delivery, cap cases_eliminated at
# the authoritative count from all_classified.
if (isinstance(cases, int) and
    notif_type and
    (("توصيل" in notif_type.lower() or "وثيقة" in notif_type.lower() or
      "استلام" in notif_type.lower()))):
    if cases > delivery_stall_count and delivery_stall_count > 0:
        cases = delivery_stall_count
```

**Why**: Ensures the notification table row about delivery alerts aligns with Tool 3's impact count, preventing inconsistency.

---

## Verification Checklist

After running the inquiries flow pipeline, verify:

### ✅ Step 1: Check Reconciliation Logs
Look for:
```
[Stage4] HARD CEILING CLAMP: friction '...' ... → X (authoritative sub_classification total)
[DigitalTransform] DELIVERY NOTIFICATION CAP: '...' cases_eliminated Y → Z
```

### ✅ Step 2: Verify Tool 3 Count
In Section 7 (AI Use Cases), Tool 3 "جهاز التحقق من جودة الوثائق":
- **Impact statement** should reference the exact count of "شكوى عن عدم استلام الخدمة" cases only
- NOT including follow-up inquiries

### ✅ Step 3: Verify Notification Table
In Section 6.2 "مسار إلغاء N حالة بالإشعار الاستباقي":
- Delivery-related notifications: الحالات المُلغاة capped at authoritative delivery count

### ✅ Step 4: Sum Friction Counts
Sum all friction case_counts in journey_map:
```
Total friction cases = len(all_classified)
```

### ✅ Step 5: Compare Excel Export
If exporting to Excel:
- Sheet "Journey Map": Sum of case_count column = len(all_classified)
- No over-counting or inconsistencies

---

## Files Modified

```
real/inquiries-flow/pipeline/
├── stage4_analysis.py (16 lines added)
│   └── Hard ceiling enforcement before notification reconciliation
├── generate_ai_use_cases_section.py (11 lines changed)
│   └── Changed _SUBS_NON_DELIVERY to exclude "متابعة طلب مقدم"
└── generate_digital_transformation_section.py (42 lines added)
    ├── New _count_delivery_stall_cases() function
    └── Special cap for delivery notifications in _build_notification_rows()
```

---

## Design Principles

### Authoritative Source Hierarchy

1. **Level 1**: `all_classified` — ground truth, each case counted exactly once
2. **Level 2**: `actual_counts[sub_classification]` — derived from all_classified, the ceiling
3. **Level 3**: `reconciled_journey_map` — capped by hard ceiling, never exceeds Level 2
4. **Level 4**: Pre-computed impact statements — locked in prompts
5. **Level 5**: Report sections — display Level 3 & 4, no new computation

**Key principle**: Numbers flow ONE DIRECTION (top to bottom). The LLM cannot invent or modify numeric values; it can only write descriptive text.

---

## What This Fixes

### Bugs Fixed
- **Friction over-counting**: Hard ceiling prevents friction points from claiming more cases than exist
- **Tool 3 over-counting**: Strict non-delivery counting (no follow-ups) ensures correct impact
- **Notification misalignment**: Delivery cap ensures Section 6.2 aligns with Section 7 Tool 3

### How It Works
- Numeric values are pre-computed from `all_classified` before the LLM sees them
- All numeric values are locked in the LLM prompt and marked as non-modifiable
- Helper functions like `_count_delivery_stall_cases()` provide authoritative counts
- Reconciliation enforces hard ceilings, not soft caps

---

## Testing

To test these fixes:

1. **Run the pipeline** on a dataset with ~100 cases including delivery failures
2. **Check logs** for `HARD CEILING CLAMP` and `DELIVERY NOTIFICATION CAP` messages
3. **Verify Tool 3 impact** references delivery-only count
4. **Verify notification table** delivery row matches Tool 3 count
5. **Sum friction case_counts** = total cases (should be exact match)

---

## Related Documentation

- `RECONCILIATION_AND_COUNT_FLOW.md` (in inquiries-flow) — Detailed reconciliation workflow
- Memory: `complaints_reconciliation_fixes.md` — Why these fixes are needed
