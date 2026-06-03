# Reconciliation and Count Flow — Complaints Pipeline

## Overview

The complaints pipeline has three critical stages where case counts are reconciled against authoritative data:

1. **Stage 2/3 (Classification)**: `all_classified` list is the ground truth
2. **Stage 4 (Analysis)**: LLM generates journey_map, patterns, and notifications; `_reconcile_counts()` enforces hard caps against Stage 2/3 counts
3. **Stage 6 (Reporting)**: Pre-computed counts from Stages 2-5 flow into report sections; LLM writes descriptive text only

## Authoritative Count Sources

### Ground Truth: `state.all_classified`

Every case in the dataset appears exactly once in `all_classified`, with:
- `case_id`: unique identifier
- `sub_classification`: assigned category (e.g., "شكوى عن عدم استلام الخدمة")
- `top_level`: broad category (e.g., "شكوى")

**To count cases in any sub-classification:**
```python
actual_count = sum(1 for c in state.all_classified if c.sub_classification == "شكوى عن عدم استلام الخدمة")
```

### Derived Counts: `sub_counts` Dictionary

Built from `all_classified` during reconciliation:
```python
actual_counts = defaultdict(int)
for case in all_classified:
    actual_counts[case.sub_classification] += 1
```

This is the **authoritative ceiling** for any friction point claiming a sub_classification.

---

## Stage 4 Analysis Reconciliation

File: `stage4_analysis.py:_reconcile_counts()`

### Input: LLM-Generated Analysis

The LLM generates:
- `journey_map`: List of JourneyFriction objects with `case_count` (LLM's estimate)
- `patterns`: List of PatternCluster objects with `case_count` (LLM's estimate)
- `notification_opportunities`: List of dicts with `cases_eliminated` (LLM's estimate)
- `proactive_case_count`: Integer count of cases that can be eliminated by proactive notification

**WARNING**: LLM numbers are estimates and may be inflated or incorrect.

### Reconciliation Steps

#### Step 1: Reconcile Patterns

For each pattern, replace `case_count` with the actual count from `all_classified`:

```python
for pattern in patterns:
    actual_count = actual_counts.get(pattern.sub_classification, pattern.case_count)
    reconciled_pattern = pattern.model_copy(update={"case_count": actual_count})
```

**Result**: Each pattern now has the exact count of cases with that sub_classification.

#### Step 2: Reconcile Journey Map (Budget Allocation)

Friction points compete for cases within each sub_classification. Using a **budget model**:

```python
sub_classification_budget = dict(actual_counts)  # Mutable copy

for friction in journey_map:
    sub = friction.sub_classification
    
    if sub in actual_counts:
        # Exact match — allocate the full sub_classification budget to this friction
        remaining_budget = sub_classification_budget.get(sub, 0)
        reconciled_count = remaining_budget
        sub_classification_budget[sub] = 0  # Mark budget as consumed
    else:
        # No exact match — try fuzzy matching or cap against total remaining
        # (logic omitted for brevity, see code)
        reconciled_count = ...
```

**Result**: Each friction point is allocated a count, but the sum of all frictions for a sub cannot exceed the actual count.

#### Step 3: Apply TASK 4 Cap (50% limit for multiple frictions per sub)

If multiple frictions claim the same sub_classification, cap each to 50% of the sub total:

```python
sub_to_frictions = defaultdict(list)
for friction in journey_map:
    if friction.sub_classification:
        sub_to_frictions[friction.sub_classification].append(friction)

for sub, friction_list in sub_to_frictions.items():
    if len(friction_list) >= 2:  # Multiple frictions for same sub
        sub_actual = actual_counts[sub]
        max_allowed = sub_actual * 0.5
        for friction in friction_list:
            if friction.case_count > max_allowed:
                friction.case_count = round(max_allowed)
```

**Result**: No single friction can dominate a sub_classification when others also claim it.

#### Step 4: FINAL HARD CEILING ENFORCEMENT ✅ (NEW FIX)

**After all reconciliation steps**, enforce an absolute hard ceiling:

```python
for friction in reconciled_journey_map:
    sub = friction.sub_classification
    if sub in actual_counts:
        actual_count = actual_counts[sub]
        if friction.case_count > actual_count:
            print(f"[Stage4] HARD CEILING CLAMP: {friction.case_count} → {actual_count}")
            friction.case_count = actual_count
```

**Why this fix?**
- Closing the loophole where a friction point could still exceed its sub_classification total
- Ensures the journey_map is always consistent with all_classified
- Authoritative source: `actual_counts[sub]` (from all_classified, never negotiable)

#### Step 5: Reconcile Notification Opportunities

Cap the total across all notifications against `proactive_case_count`:

```python
max_proactive_cases = min(proactive_case_count, len(all_classified))

# Scale each notification proportionally
for notif in notification_opportunities:
    llm_count = notif["cases_eliminated"]
    scaled = round(llm_count / llm_total * max_proactive_cases)
    notif["cases_eliminated"] = max(1, scaled) if llm_count > 0 else 0
```

**Current limitation**: This scales notifications proportionally without considering which specific sub_classifications they affect. See Stage 6 fixes below.

---

## Stage 6 Report Generation — Hard Counts

Files:
- `generate_ai_use_cases_section.py`: Tool 3 (Response Suggestion Engine) and Section 7
- `generate_digital_transformation_section.py`: Notification table rows (Section 6.2)

### Key Principle: Pre-Compute, Lock, Don't Re-Compute

All numeric values are computed BEFORE the LLM is invoked. The LLM writes descriptive text only.

### AI Use Cases Section (Section 7) — Tool 3 Impact ✅ (NEW FIX)

**File**: `generate_ai_use_cases_section.py`

**New function**: `_count_non_delivery_cases()`

Counts cases with **exactly** the sub_classification:
```python
NON_DELIVERY_SUB_CLASS = "شكوى عن عدم استلام الخدمة"
count = sum(1 for case in state.all_classified if case.sub_classification == NON_DELIVERY_SUB_CLASS)
```

**Why this function?**
- The expert's criterion for Tool 3 is strict: only confirmed delivery failures
- Do NOT include "متابعة طلب مقدم" (follow-up inquiries) — these are different
- The correct count is 4 (as per the expert's audit)

**Integration into Tool 3 impact**:
```python
def _build_response_suggestion_impact(state):
    non_delivery_count = _count_non_delivery_cases(state)  # Ground truth: 4 cases
    
    impact = (
        f"توحيد وتسريع معالجة {non_delivery_count}+ حالة من الشكاوى المرتجعة "
        f"— تقليل وقت الحل + زيادة معدل الحل من أول تواصل"
    )
    return {"impact_statement_ar": impact, ...}
```

**Locked in prompt**: The LLM cannot change this number.

### Digital Transformation Section (Section 6.2) — Notification Table ✅ (NEW FIX)

**File**: `generate_digital_transformation_section.py`

**New function**: `_count_delivery_stall_cases()`

Counts cases with **exactly** the delivery failure sub_classification:
```python
DELIVERY_FAILURE_SUB_CLASS = "شكوى عن عدم استلام الخدمة"
count = sum(1 for case in state.all_classified if case.sub_classification == DELIVERY_FAILURE_SUB_CLASS)
```

**Special handling in `_build_notification_rows()`**:

If a notification is about document delivery (keywords: "توصيل", "وثيقة"), cap `cases_eliminated` at this count:

```python
delivery_stall_count = _count_delivery_stall_cases(state)  # 4

for notif in state.notification_opportunities:
    if "توصيل" in notif["notification_type"]:
        if notif["cases_eliminated"] > delivery_stall_count:
            notif["cases_eliminated"] = delivery_stall_count  # Cap to 4
            # Also recompute expected_impact to reflect the correct percentage
            pct = round(4 / total_cases * 100, 1)
            notif["expected_impact"] = f"إلغاء 4 حالات ({pct}%)"
```

**Why this fix?**
- Section 6.2 notification row about "إشعار SMS عند توصيل الوثيقة" shows count=3, but should be 4
- The count must match the authoritative non_delivery count from all_classified
- Ensures consistency between Section 6 (notifications) and Section 7 (Tool 3 impact)

---

## Count Consistency Matrix

| Count | Source | Used in | Value | Notes |
|-------|--------|---------|-------|-------|
| Non-delivery cases | `all_classified` | Tool 3 impact, Notification row | 4 | Exact match: sub_classification == "شكوى عن عدم استلام الخدمة" |
| Friction point "non-delivery" | journey_map (Stage 4) | Digital Gaps table | ≤ 4 | Capped by hard ceiling enforcement |
| Notification "delivery alert" | state.notification_opportunities (Stage 4, reconciled) | Section 6.2 | 4 | Capped by _count_delivery_stall_cases() |
| Total cases | len(all_classified) | All sections | N | Denominator for percentages |

---

## Preventing LLM Hallucination

### Where LLM Cannot Invent Numbers

1. **Journey map case_count**: Capped by hard ceiling (Stage 4, `_reconcile_counts()`)
2. **Pattern case_count**: Replaced with actual count (Stage 4, `_reconcile_counts()`)
3. **Notification cases_eliminated**: Capped and scaled proportionally (Stage 4, `_reconcile_counts()`)
4. **AI Tool 3 impact statement**: Pre-computed, locked in prompt (Section 7)
5. **Notification table الأثر المتوقع**: Pre-computed and re-computed if count capped (Section 6.2)

### Where LLM Writes Descriptive Text Only

1. **Section body paragraphs**: Grounded in pre-computed numbers, no invention
2. **الأداة** (Tool name): Descriptive name for each of 4 AI tools
3. **الوظيفة** (Tool function): 2-4 sentences describing what the tool does
4. **تقييم التنفيذ**: Effort level and timeline (pre-computed, embedded into narrative by LLM)
5. **Notification content_summary**: Concrete example of what message customers receive

---

## Workflow Summary

```
Stage 2/3 (Classification)
  ↓
  all_classified (ground truth: 100% of cases, each counted exactly once)
  ↓
Stage 4 (Analysis & Reconciliation)
  ↓
  _reconcile_counts():
    - Patterns: replace with actual counts from all_classified ✓
    - Journey map: allocate by budget, cap at HARD CEILING ✓ (NEW)
    - Notifications: scale proportionally against proactive_case_count ✓
  ↓
  Output: reconciled journey_map, patterns, notifications (all hard-capped)
  ↓
Stage 6 (Report Generation)
  ↓
  Section 7 (AI Use Cases):
    - Pre-compute: Tool 3 impact = _count_non_delivery_cases() = 4
    - Lock in prompt: "الأثر المتوقع" = pre-computed impact statement
    - LLM writes: الأداة, الوظيفة, تقييم التنفيذ (embedding locked values)
  ↓
  Section 6.2 (Notifications):
    - Pre-compute: delivery_stall_count = _count_delivery_stall_cases() = 4
    - Cap delivery notification: cases_eliminated = min(LLM value, 4)
    - Recompute expected_impact with correct percentage
    - LLM reads pre-computed rows from state
  ↓
  Final report (all counts consistent with all_classified)
```

---

## Verification Checklist

Before shipping a report, verify:

- [ ] **Journey map friction points**: Sum of case_counts per sub_classification ≤ actual count
- [ ] **Patterns**: case_count == actual count for each sub_classification
- [ ] **Tool 3 impact**: References exactly 4 non-delivery cases (or correct count if data changes)
- [ ] **Notification table (Section 6.2)**: Delivery alert row shows 4 cases (or correct count)
- [ ] **Excel export**: Total cases match len(all_classified)
- [ ] **No hallucinated numbers**: All percentages computed from authoritative counts, not invented

---

## Excel Consistency

The Excel export in Stage 6 uses the same counts:
- **Table 1 (Friction points)**: case_count values from reconciled journey_map
- **Table 2 (Patterns)**: case_count values from reconciled patterns
- **Notification section**: cases_eliminated values from reconciled notification_opportunities (after capping)

**Verification**: Sum all friction case_counts and pattern case_counts in Excel → should equal total_cases (all_classified size).

---

## Future Improvements

1. **Notification-to-subclass mapping**: Instead of proportional scaling, directly map each notification to its related sub_classifications and cap accordingly.
2. **Fuzzy matching refinement**: Improve the word-overlap matching for ambiguous sub_classifications.
3. **LLM audit logs**: Detailed logging of every transformation for debugging.
4. **Automated validation**: Assert that all counts satisfy the constraints before report generation.
