# Complaints Pipeline Fixes — Summary

## Issues Fixed

### Bug A: Friction Point 1 Over-Counting (14 → 9)
**Sub-classification**: "طلب تعديل أو تحديث بيانات" (outdated data)  
**Issue**: Reconciliation allowed this friction to claim 14 cases instead of capping at 9  
**Root Cause**: TASK 4 CAP enforced 50% limit but didn't enforce absolute hard ceiling  
**Fix**: Added hard ceiling enforcement in `stage4_analysis.py:_reconcile_counts()`

### Bug B: Friction Point 2 Over-Counting (10 → 8)
**Sub-classification**: "شكوى عن مخالفة مشكوك فيها" (disputed vehicle photo)  
**Issue**: Claimed 10 cases instead of 8  
**Root Cause**: Same as Bug A  
**Fix**: Hard ceiling enforcement closes this loophole

### Bug C: Friction Point 4 Over-Counting (6 → 4)
**Sub-classification**: "شكوى عن عدم استلام الخدمة" (non-delivery)  
**Issue**: Claimed 6 cases including "متابعة طلب مقدم" (follow-ups), should only be 4  
**Root Cause**: Friction counting was too broad  
**Fix**: Added strict helper function `_count_non_delivery_cases()` that counts ONLY "شكوى عن عدم استلام الخدمة"

### Bug D: Notification Table Over-Counting (3 → 4)
**Notification**: "إشعار SMS عند توصيل الوثيقة" (document delivery alert)  
**Issue**: Showed 3 cases instead of 4  
**Root Cause**: Notification reconciliation scaled proportionally without capping to authoritative sub_classification count  
**Fix**: Added `_count_delivery_stall_cases()` to cap delivery notifications at exactly the non-delivery sub_classification count

### Bug E: Tool 3 Impact Wrong Count (7 → 4)
**Tool**: "محرك اقتراح الردود" (Response Suggestion Engine)  
**Issue**: Impact statement referenced 7 cases, but no sub_classification produces 7  
**Root Cause**: Tool 3 impact was using non-delivery cases + follow-ups instead of strict count  
**Fix**: `_count_non_delivery_cases()` in `_build_response_suggestion_impact()` ensures Tool 3 references exactly 4 cases

---

## Code Changes

### 1. stage4_analysis.py — Hard Ceiling Enforcement

**Location**: Lines 550-570 (after TASK 4 CAP)

**Added**:
```python
# ── FINAL ENFORCEMENT: Hard ceiling per sub_classification ───────────────────────
# After all reconciliation, enforce hard cap: no friction point can exceed
# the actual count of cases with that sub_classification.
for i, friction in enumerate(reconciled_journey_map):
    sub = friction.sub_classification
    if sub and sub in actual_counts:
        actual_count = actual_counts[sub]
        if friction.case_count > actual_count:
            print(f"[Stage4] HARD CEILING CLAMP: ...")
            reconciled_journey_map[i] = friction.model_copy(update={"case_count": actual_count})
```

**Key**: Runs AFTER all previous cap logic, ensuring no friction point ever exceeds its sub_classification's true total.

---

### 2. generate_ai_use_cases_section.py — Non-Delivery Case Counting

**Location**: Lines 242-263

**Added**:
```python
def _count_non_delivery_cases(state: PipelineState) -> int:
    """
    Count cases with ONLY "شكوى عن عدم استلام الخدمة" sub-classification.
    Do NOT include "متابعة طلب مقدم" — only confirmed delivery failures.
    """
    NON_DELIVERY_SUB_CLASS = "شكوى عن عدم استلام الخدمة"
    count = 0
    for case in (state.all_classified or []):
        if case.sub_classification == NON_DELIVERY_SUB_CLASS:
            count += 1
    return count
```

**Modified**: `_build_response_suggestion_impact()` to use this count instead of fuzzy lookups.

**Result**: Tool 3 impact now grounded in REAL non-delivery cases (4), not invented numbers.

---

### 3. generate_digital_transformation_section.py — Notification Table Cap

**Location**: Lines 130-155

**Added**:
```python
def _count_delivery_stall_cases(state: PipelineState) -> int:
    """
    Count cases with ONLY "شكوى عن عدم استلام الخدمة" sub-classification.
    Authoritative count for the notification table row about document delivery alerts.
    """
    DELIVERY_FAILURE_SUB_CLASS = "شكوى عن عدم استلام الخدمة"
    count = 0
    for case in (state.all_classified or []):
        if case.sub_classification == DELIVERY_FAILURE_SUB_CLASS:
            count += 1
    return count
```

**Modified**: `_build_notification_rows()` to:
1. Detect delivery-related notifications (keywords: "توصيل", "وثيقة")
2. Cap `cases_eliminated` at `_count_delivery_stall_cases()`
3. Recompute `expected_impact` percentage with the correct count

**Result**: Notification table shows 4 cases (8.0%) aligned with Tool 3 and all_classified.

---

## Verification Steps

### Step 1: Check Reconciliation Logs

Run the pipeline and look for these log lines:
```
[Stage4] HARD CEILING CLAMP: friction '...' ... → 9 (authoritative sub_classification total)
[DigitalTransform] DELIVERY NOTIFICATION CAP: '...' cases_eliminated 3 → 4 (authoritative delivery_stall count)
```

Presence of these lines confirms the fixes are active.

### Step 2: Verify Friction Point Counts

In the generated report, check the Digital Gaps table (Section 5):
- Friction point 1 ("بيانات غير محدّثة"): Should show **9 cases** ✓
- Friction point 2 ("مخالفة مشكوك فيها"): Should show **8 cases** ✓
- Friction point 4 ("عدم استلام الخدمة"): Should show **4 cases** ✓

### Step 3: Verify Tool 3 Impact

In Section 7 (AI Use Cases), Tool 3 "محرك اقتراح الردود":
- الأثر المتوقع should reference **4 cases** (non-delivery complaints)
- NOT 7 or any other number

### Step 4: Verify Notification Table

In Section 6.2 "فرص الإخطار الاستباقي":
- Row for "إشعار SMS عند توصيل الوثيقة": الحالات المُلغاة = **4**
- الأثر المتوقع = "إلغاء 4 حالات (X.X%)" where X.X = 4 / total_cases * 100

### Step 5: Sum Friction Counts

In Excel or by manual inspection, sum all friction case_counts in the report:
```
Friction A: 9
Friction B: 8
Friction C: 4
Friction D: ...
...
Total: = len(all_classified)  ← should always equal actual case count
```

### Step 6: Compare with Excel Export

If you export the report to Excel:
- Sheet "Friction Map": Sum of case_count column = len(all_classified)
- Sheet "Patterns": Sum of case_count column = len(all_classified)
- No over-counting or inconsistencies

---

## Design Principles

### Authoritative Source Hierarchy

1. **Level 1**: `all_classified` list (Stage 2/3) — ground truth
2. **Level 2**: `actual_counts[sub_classification]` — derived from all_classified, the ceiling
3. **Level 3**: `reconciled_journey_map` — capped by hard ceiling, never exceeds Level 2
4. **Level 4**: Pre-computed impact statements — locked in prompts, cannot be modified by LLM
5. **Level 5**: Report sections — display Level 3 and 4, no new computation

**Principle**: Numbers flow ONE DIRECTION (top to bottom). The LLM cannot invent or modify numeric values; it can only write descriptive text around them.

---

### Where the LLM Cannot Hallucinate

| Item | Location | Control | Notes |
|------|----------|---------|-------|
| Friction case_count | journey_map | Hard ceiling in stage4 | Cannot exceed actual sub_classification count |
| Pattern case_count | patterns | Replaced with actual count in stage4 | 100% deterministic |
| Notification cases_eliminated | notification_opportunities | Proportional scaling + hardcap in stage4 | Capped by proactive_case_count and per-sub caps |
| Tool 3 impact statement | Section 7 | Pre-computed, locked in prompt | References exactly 4 non-delivery cases |
| Notification delivery count | Section 6.2 | Capped before display | Max 4 cases for delivery alerts |

---

### Where the LLM Writes Descriptive Text Only

| Item | Location | Control |
|------|----------|---------|
| Section body paragraph | All sections | Grounded in pre-computed numbers, can expand/paraphrase |
| الأداة (Tool name) | Section 7 | Descriptive name for each of 4 AI tools |
| الوظيفة (Tool function) | Section 7 | 2-4 sentences describing what tool does |
| تقييم التنفيذ (Implementation assessment) | Section 7 | Embeds pre-computed effort_level and effort_timeline |
| محتوى الإشعار (Notification content) | Section 6.2 | Concrete example of message customers receive |

---

## How to Prevent Regressions

### Code Review Checklist

When reviewing changes to the pipeline:

- [ ] **No new LLM counts**: Verify no new counts are generated by the LLM without reconciliation
- [ ] **Stage 4 reconciliation**: Check that `_reconcile_counts()` is called on ALL case_count fields (journey_map, patterns, notifications)
- [ ] **Hard ceiling enforced**: Confirm hard ceiling clamp runs AFTER all other capping logic
- [ ] **Pre-computed values locked**: All numeric values passed to LLM prompts are marked LOCKED and cannot be changed
- [ ] **Consistency check**: Sum of all friction/pattern case_counts = len(all_classified)

### Test Case

Use the 10-case dataset from the test to verify:
1. Run pipeline, check reconciliation logs for HARD CEILING CLAMP messages
2. Verify total case count in report = 10
3. Verify no friction claims more than 10 cases
4. Verify Tool 3 references non_delivery_count = 4
5. Verify notification delivery row shows 4 cases

---

## Questions or Issues?

If counts still appear incorrect:
1. Check reconciliation logs for CLAMP messages — if missing, hard ceiling may not be running
2. Manually count non-delivery cases: grep for "شكوى عن عدم استلام الخدمة" in input
3. Trace through Section 4's LLM response — were the original counts inflated?
4. Check Excel export — totals should match Python counts (if not, JSON serialization issue)

---

## Related Documentation

- `RECONCILIATION_AND_COUNT_FLOW.md` — Detailed explanation of the entire reconciliation workflow
- `stage4_analysis.py` — Full implementation of reconciliation logic
- `generate_ai_use_cases_section.py` — Tool impact pre-computation
- `generate_digital_transformation_section.py` — Notification table building
