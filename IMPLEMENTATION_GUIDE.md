# Implementation Guide: Fix Report Consistency Issues (Priority Order)

## Before Starting
- Run a git diff to understand the current state
- Have the 50-case test file (`Inquiries_2025_test_50cases.xlsx`) ready for testing after each fix
- Keep this guide and the review document open side-by-side

---

## Fix 1: Digital-Channel Percentage (Issue 1) ⭐ START HERE
**Difficulty:** Easy | **Impact:** Visible in Section 5 and Conclusion | **Files:** 2

### Step 1a: Add module-level constant in `generate_digital_gaps_section.py`

**File:** `real/inquiries-flow/pipeline/generate_digital_gaps_section.py`

**Location:** After imports (around line 64–65), before `_SEVERITY_EMOJI` constant

**Insert:**
```python
# Single authoritative definition of digital submission channels
# Used in all sections and conclusion to ensure consistency
_DIGITAL_SUBMISSION_CHANNELS = {"تطبيق", "موقع", "NCRM", "ncrm"}
```

### Step 1b: Update `_compute_submission_channel_pct` function

**File:** Same file, line 94–109

**Replace the entire function with:**
```python
def _compute_submission_channel_pct(state: PipelineState) -> float:
    """
    % of cases submitted via digital channels (app, website, or NCRM).
    
    This is the submission channel metric — how many customers submitted their case
    through "تطبيق" (app), "موقع" (website), or "NCRM" rather than phone/in-person.
    Single source of truth for all sections.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    digital_submissions = sum(
        1 for c in cases
        if c.case_channel and any(
            kw in str(c.case_channel) for kw in _DIGITAL_SUBMISSION_CHANNELS
        )
    )
    return round(digital_submissions / total * 100, 1)
```

### Step 1c: Update Arabic labels in prompts

**File:** Same file

**Find:** Search for `"(التطبيق / الموقع الإلكتروني)"` 

**Replace with:** `"(التطبيق / الموقع الإلكتروني + NCRM)"` 

**Locations to check:**
- Line ~190–210: Digital gap section intro paragraph template
- Any prompt strings that reference submission channels
- In `generate_conclusion_section.py` if it also has this text

### Step 1d: Update `generate_conclusion_section.py`

**File:** `real/inquiries-flow/pipeline/generate_conclusion_section.py`

**Location:** Top of file, after imports (around line 50)

**Add import:**
```python
from .generate_digital_gaps_section import _DIGITAL_SUBMISSION_CHANNELS
```

**Location:** Line 66–83 (the `_compute_submission_channel_pct` function in conclusion section)

**Replace with:**
```python
def _compute_submission_channel_pct(state: PipelineState) -> tuple[float, str]:
    """
    Compute the submission channel percentage from case_channel data.
    
    Uses _DIGITAL_SUBMISSION_CHANNELS constant from generate_digital_gaps_section
    to ensure consistency across all report sections.
    """
    cases = state.all_classified or []
    total = len(cases) or 1

    digital_submissions = sum(
        1 for c in cases
        if c.case_channel and any(
            kw in str(c.case_channel) for kw in _DIGITAL_SUBMISSION_CHANNELS
        )
    )
    pct = round(digital_submissions / total * 100, 1)
    return pct, f"{pct}%"
```

### Step 1e: Update `stage6_json_report.py` (if it has a copy)

**File:** `real/inquiries-flow/pipeline/stage6_json_report.py`

**Search for:** `_compute_submission_channel_pct` in this file

**If found:** Replace with import from `generate_digital_gaps_section` or use the same constant

**Tip:** Search the entire file for "(التطبيق / الموقع" to find all locations that need updating

### Test Fix 1
```bash
cd /Users/lena/Documents/Sword/sim-fujairah-inquiries-ai/real
# Run with 50-case test file
# Check Section 5 intro: should say ~96% (not 94%)
# Check Conclusion: should also say 96%
```

**Expected Output:**
- Section 5 intro: "حوالي 96.0% من الحالات"
- Section 5.1 context: mentions "التطبيق / الموقع الإلكتروني + NCRM"
- Conclusion digital metric: "96.0% من حالات التواصل"

---

## Fix 2: Section 5.2 Root-Cause Table Counts (Issue 2)
**Difficulty:** Medium | **Impact:** Section 5.2 accuracy | **Files:** 1

### Step 2a: Replace `_build_root_cause_rows` function

**File:** `real/inquiries-flow/pipeline/generate_digital_gaps_section.py`

**Location:** Line 186–225

**Replace entire function with:**
```python
def _build_root_cause_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Pre-computed rows for Section 5.2 root-cause table.
    
    Case counts are derived from state.all_classified (ground truth), not from
    summing journey_map, to prevent double-counting when multiple friction
    points share the same root_cause_category.
    
    Each case is counted exactly once per root_cause_category.
    """
    # Step 1: Build mapping of root_cause_category → sub_classifications it covers
    rc_to_subs: Dict[str, set] = defaultdict(set)
    rc_best_friction: Dict[str, tuple] = {}  # cat → (count, text)
    
    for f in state.journey_map:
        cat = f.root_cause_category
        if f.sub_classification:
            rc_to_subs[cat].add(f.sub_classification)
        text = f.friction_point_ar or f.friction_point
        current_best = rc_best_friction.get(cat, (0, ""))[0]
        if f.case_count >= current_best:
            rc_best_friction[cat] = (f.case_count, text)
    
    # Step 2: Count actual cases per root_cause_category (ground truth)
    # Each case is counted exactly once, even if multiple friction points
    # share the same root_cause_category
    rc_actual_totals: Dict[str, int] = defaultdict(int)
    for case in (state.all_classified or []):
        sub = case.sub_classification
        for cat, subs in rc_to_subs.items():
            if sub in subs:
                rc_actual_totals[cat] += 1
                break  # Count each case in at most one category
    
    # Step 3: Sort by actual total count descending
    sorted_rc = sorted(rc_actual_totals.items(), key=lambda x: x[1], reverse=True)
    
    # Step 4: Build rows with locked case counts
    rows = []
    for i, (cat, total_count) in enumerate(sorted_rc, 1):
        label = _ROOT_CAUSE_LABELS.get(cat, cat)
        _, example_text = rc_best_friction.get(cat, (0, ""))
        
        # Use the authoritative total (not best_count) in the example cell
        example_cell = (
            f"{total_count} حالة — {example_text}" if example_text else str(total_count)
        )
        rows.append({
            "#":               str(i),
            "السبب الجذري":    label,
            "مثال على التحدي": example_cell,
        })
    return rows
```

### Step 2b: Add import if not present

**File:** Same file, top of file after existing imports

**Check if present:**
```python
from collections import defaultdict
```

**If missing, add it.** If present, skip this step.

### Test Fix 2
```bash
# After running pipeline with 50-case test:
# Sum the integers in Section 5.2 "مثال على التحدي" column
# Result should be ≤ 50 (total cases)
# Each category's count should match sub_classification totals
```

**Expected Output:**
- "مثال على التحدي" cells show: "25 حالة — friction text", "15 حالة — ..." etc.
- No category exceeds the total distinct cases for that root_cause category
- Sum of all row counts ≤ 50

---

## Fix 3: Notification Count Reconciliation (Issue 3) 🔧 HARD
**Difficulty:** High | **Impact:** Sections 6.2, 8, and 9 consistency | **Files:** 4–5

### Step 3a: Add field to state

**File:** `real/inquiries-flow/pipeline/state.py`

**Location:** Inside `PipelineState` class, around line 165–170 (after other notification fields)

**Add field:**
```python
    # --- ISSUE 3 FIX: Reconciled notification counts ---
    reconciled_notification_counts: Dict[str, int] = Field(default_factory=dict)
    # Keys are notification_type strings from notification_opportunities.
    # Values are the post-reconciliation cases_eliminated counts.
    # Populated at end of Stage 4 reconciliation.
```

### Step 3b: Update stage4_analysis.py `_reconcile_counts` return

**File:** `real/inquiries-flow/pipeline/stage4_analysis.py`

**Location:** Line 348–377 (function signature and docstring)

**Update signature:**
```python
def _reconcile_counts(
    journey_map: list,
    patterns: list,
    all_classified: list,
    notification_opportunities: list,
    proactive_case_count: int,
) -> tuple[list, list, list, dict]:  # ⬅️ CHANGED: added 'dict' return type
    """
    Reconcile LLM-supplied case_counts with authoritative counts from all_classified.
    
    Returns:
        Tuple of (reconciled_journey_map, reconciled_patterns, reconciled_notifications, per_type_counts)
        where per_type_counts is Dict[str, int] mapping notification_type → cases_eliminated
    """
```

**Location:** End of `_reconcile_counts` function (around line 450–500)

**Add before final return statement:**
```python
    # Extract final per-type counts for cross-section consistency (Issue 3 fix)
    reconciled_counts_by_type: Dict[str, int] = {}
    for n in reconciled_notifications:
        ntype = n.get("notification_type") or n.get("content_summary") or ""
        if ntype:
            reconciled_counts_by_type[ntype] = n.get("cases_eliminated", 0)
    
    return (reconciled_journey_map,
            reconciled_patterns,
            reconciled_notifications,
            reconciled_counts_by_type)  # ⬅️ CHANGED: return 4-tuple instead of 3-tuple
```

**Important:** Make sure the function's original final `return` statement is replaced or updated.

### Step 3c: Update call sites in stage4_analysis.py

**File:** Same file, search for calls to `_reconcile_counts`

**Find:** Both `run_stage4` and `_retry_journey_map_only` functions

**Pattern to find:**
```python
state.journey_map, state.patterns, state.notification_opportunities = _reconcile_counts(...)
```

**Replace with:**
```python
state.journey_map, state.patterns, state.notification_opportunities, state.reconciled_notification_counts = _reconcile_counts(...)
```

**Repeat for both call sites.**

### Step 3d: Update `generate_digital_transformation_section.py`

**File:** `real/inquiries-flow/pipeline/generate_digital_transformation_section.py`

**Location:** `_build_notification_rows` function, around line 305–315

**Find this code:**
```python
    if state.notification_opportunities:
        sorted_notifs = sorted(
            state.notification_opportunities,
            key=lambda n: n.get("cases_eliminated", 0),
            reverse=True,
        )
        for n in sorted_notifs:
            notif_type = n.get("notification_type") or n.get("content_summary") or ""
            cases = n.get("cases_eliminated", 0)  # ⬅️ CHANGE THIS LINE
```

**Replace the line marked with arrow:**
```python
            # Use reconciled count if available, else fall back to raw value
            cases = state.reconciled_notification_counts.get(
                notif_type, 
                n.get("cases_eliminated", 0)
            )
```

### Step 3e: Update `generate_improvement_roadmap_section.py` (if needed)

**File:** `real/inquiries-flow/pipeline/generate_improvement_roadmap_section.py`

**Location:** Wherever notification_opportunity case counts are used (likely in row building)

**Pattern to find:**
```python
cases = notification_opp.get("cases_eliminated", 0)
```

**Replace with:**
```python
ntype = notification_opp.get("notification_type") or ""
cases = state.reconciled_notification_counts.get(ntype, notification_opp.get("cases_eliminated", 0))
```

### Test Fix 3
```bash
# After running pipeline:
# Check that Section 6.2 notification counts match 
# the "final" delivery case count from Stage 5
# Check that roadmap section uses same counts as 6.2
```

**Expected Output:**
- Section 6.2 "delivery notification" row: uses reconciled count
- Section 8 roadmap "delivery notification" row: same count as Section 6.2
- `state.reconciled_notification_counts` dict populated after stage4

---

## Fix 4: Section 6.2 Heading = Sum of Table Rows (Issue 4)
**Difficulty:** Easy (depends on Fix 3) | **Impact:** Section 6.2 internal consistency | **Files:** 1

### Step 4a: Replace `_total_notif_cases` function

**File:** `real/inquiries-flow/pipeline/generate_digital_transformation_section.py`

**Location:** Line 478–497

**Replace entire function with:**
```python
def _total_notif_cases(notif_rows: List[Dict[str, str]], state: PipelineState) -> int:
    """
    Compute total eliminatable cases by summing the notification table rows.
    
    This is the ONLY source of truth for the section heading — it always matches
    the table because it IS derived from the same row data. No reading from 
    state.proactive_notification_case_count (which may differ from reconciled total).
    """
    import re as _re
    total = 0
    for row in notif_rows:
        raw = row.get("الحالات المُلغاة", "0")
        # Strip Arabic grammar words to extract just the integer
        digits = _re.sub(r"[^\d]", "", str(raw))
        if digits:
            total += int(digits)
    return total
```

### Step 4b: Find and update heading generation code

**File:** Same file, search for "مسار إلغاء" or the section heading

**Pattern to find:**
```python
notif_headline = f"{notif_total}+ حالة"  # or similar with "+"
```

**Replace with:**
```python
notif_total = _total_notif_cases(notif_rows, state)
notif_headline = str(notif_total) if notif_total > 0 else "عدد من"
# NO "+" suffix — use exact number, not "N+ cases"
```

### Test Fix 4
```bash
# After running pipeline:
# Check Section 6.2 heading: "مسار إلغاء N حالة" (exact number)
# Manually sum the row integers from الحالات المُلغاة column
# Heading N should equal your manual sum
```

**Expected Output:**
- Section 6.2 heading: "مسار إلغاء 18 حالة" (no "+")
- Table rows sum to exactly 18

---

## Fix 5: Roadmap Row Deduplication (Issue 5)
**Difficulty:** Medium | **Impact:** Section 8 row count and clarity | **Files:** 1

### Step 5a: Add deduplication helper functions

**File:** `real/inquiries-flow/pipeline/generate_improvement_roadmap_section.py`

**Location:** After imports, before `_horizon_rank` function (around line 155)

**Add functions:**
```python
def _deduplicate_roadmap_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove near-duplicate roadmap rows using locked field signatures.
    
    Two rows are duplicates if they share the same root_cause_category AND
    sub_classification (the locked structural identity). The row with the
    higher case_count is kept; the other is dropped.
    
    Must run BEFORE renumbering so indices stay stable.
    """
    seen: Dict[str, Dict[str, Any]] = {}  # signature → row
    
    for row in rows:
        # Build signature from locked structural fields only
        sig = (
            row.get("_root_cause_category", ""),
            row.get("_sub_classification", ""),
            row.get("الأفق الزمني", ""),
        )
        sig_str = str(sig)
        
        existing = seen.get(sig_str)
        if existing is None:
            seen[sig_str] = row
        else:
            # Keep the row with higher case_count
            existing_count = existing.get("_case_count", 0)
            new_count = row.get("_case_count", 0)
            if new_count > existing_count:
                seen[sig_str] = row
                print(f"[Roadmap] Dedup: Replacing row sig={sig_str} with higher count {new_count}")
    
    return list(seen.values())


def _strip_internal_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal (underscore-prefixed) keys from row dict."""
    return {k: v for k, v in row.items() if not k.startswith("_")}
```

### Step 5b: Update row assembly logic

**File:** Same file, in `_build_display_roadmap_rows` function

**Pattern to find:**
```python
rows = []
# ... code that builds rows from journey_map, gap_table, ai_use_cases ...
# ... then sorts rows ...
# ... then renumbers with "#" ...
return rows
```

**Replace that section with:**
```python
rows = []
# ... code that builds rows from journey_map, gap_table, ai_use_cases ...
# Store internal fields: _root_cause_category, _sub_classification, _case_count

# BEFORE renumbering: deduplicate
rows = _deduplicate_roadmap_rows(rows)

# Re-sort by horizon (after dedup to maintain order)
rows = sorted(rows, key=lambda r: _horizon_rank(r.get("الأفق الزمني", "")))

# Strip internal keys before final return
rows = [_strip_internal_keys(r) for r in rows]

# Renumber sequentially with str(i)
final_rows = []
for i, row in enumerate(rows, 1):
    row["#"] = str(i)
    final_rows.append(row)

return final_rows
```

**Important:** Make sure that when you build rows from the three sources (journey_map, gap_table, ai_use_cases), you store `_root_cause_category`, `_sub_classification`, and `_case_count` as internal (underscore-prefixed) keys so deduplication can use them.

### Test Fix 5
```bash
# After running pipeline:
# Count Section 8 roadmap table rows
# Should be 5–6 rows, not 8+
# Verify no near-identical recommendations
```

**Expected Output:**
- Section 8 roadmap: 5–6 rows (not duplicated)
- Row numbering sequential 1–N

---

## Fix 6: Conclusion Impact Box Metric (Issue 6) 🔧 DEPENDS ON FIX 3 & 4
**Difficulty:** Hard (requires orchestration) | **Impact:** Conclusion section final accuracy | **Files:** 3

### Step 6a: Add field to state

**File:** `real/inquiries-flow/pipeline/state.py`

**Location:** Inside `PipelineState` class, after `final_notif_eliminatable` (around line 170–175)

**Add field:**
```python
    # --- ISSUE 6 FIX: Final notification count for conclusion ---
    final_notif_eliminatable: int = 0
    # Sum of cases_eliminated across all reconciled notification rows.
    # Set by Stage 6 after notification table rows are built.
    # This is the number used in conclusion and impact box.
```

### Step 6b: Populate in stage6_json_report.py

**File:** `real/inquiries-flow/pipeline/stage6_json_report.py`

**Location:** In `generate_json_report` function, after building digital_transformation section

**Pattern to find:**
```python
digital_trans_section = self.build_digital_transformation_section(lang=lang)
```

**Add after it:**
```python
# Extract final notification table total (Issue 6 fix)
if "notification_table" in digital_trans_section:
    import re as _re
    total = 0
    for row in digital_trans_section.get("notification_table", []):
        raw = row.get("الحالات المُلغاة", "0")
        digits = _re.sub(r"[^\d]", "", str(raw))
        if digits:
            total += int(digits)
    state.final_notif_eliminatable = total
    print(f"[Stage6] Set final_notif_eliminatable = {state.final_notif_eliminatable}")
```

### Step 6c: Update `_count_proactive_cancellable` in generate_conclusion_section.py

**File:** `real/inquiries-flow/pipeline/generate_conclusion_section.py`

**Location:** Line 131–145

**Replace entire function with:**
```python
def _count_proactive_cancellable(state: PipelineState) -> int:
    """
    Count cases cancellable by proactive notification.
    
    Uses final_notif_eliminatable (set after Section 6.2 table is built)
    for consistency with notification heading and table.
    Falls back through reconciled counts → raw notification_opportunities.
    """
    # Prefer the final reconciled count (set after section 6.2 table is built)
    if state.final_notif_eliminatable > 0:
        return state.final_notif_eliminatable
    
    # Fallback to reconciled notification counts
    if state.reconciled_notification_counts:
        total = sum(state.reconciled_notification_counts.values())
        if total > 0:
            return total
    
    # Last resort: raw notification_opportunities (Stage 4 estimate)
    opps = state.notification_opportunities or []
    if opps:
        total = sum(int(o.get('cases_eliminated', 0)) for o in opps)
        if total > 0:
            return total
    
    # Final fallback: journey_map proactive friction points
    jm = state.journey_map or []
    return sum(j.case_count for j in jm if j.root_cause_category == 'no_proactive_notification')
```

### Test Fix 6
```bash
# After running pipeline:
# Check Conclusion: "N+ حالة قابلة للإلغاء" (or just "N حالة")
# Verify N matches Section 6.2 heading and table sum
# Verify Word and Excel both show same N
```

**Expected Output:**
- Conclusion impact box: "20 حالة قابلة للإلغاء" (exact number)
- Matches Section 6.2 heading and table sum
- Word (.docx) and Excel (.xlsx) outputs consistent

---

## Validation After All Fixes

### Run Full Pipeline with 50-Case Test

```bash
cd /Users/lena/Documents/Sword/sim-fujairah-inquiries-ai/real
# Run the inquiries flow with the test file
```

### Checklist

- [ ] Fix 1 — Digital channel: 96% across all sections
- [ ] Fix 2 — Root-cause: sum of Section 5.2 row counts ≤ 50
- [ ] Fix 3 — Notification reconciliation: Section 6.2 and 8 counts match
- [ ] Fix 4 — Notification heading: exact number, no "+"
- [ ] Fix 5 — Roadmap dedup: 5–6 rows, no duplicates
- [ ] Fix 6 — Conclusion metric: matches Sections 6.2 and 8
- [ ] Word output: all numbers consistent
- [ ] Excel output: all numbers consistent
- [ ] Word and Excel match each other

### Debug Output

During implementation, add these debug prints to verify state population:

```python
# After Stage 1:
print(f"[Stage1] digital_channel_pct = {state.digital_channel_pct}%")

# After Stage 4:
print(f"[Stage4] reconciled_notification_counts = {state.reconciled_notification_counts}")

# After Stage 6 digital_trans:
print(f"[Stage6] final_notif_eliminatable = {state.final_notif_eliminatable}")
```

### Cross-Check Numbers

In the final reports:

| Metric | Section 5 | Section 6 | Section 8 | Section 9 | Excel |
|--------|-----------|-----------|-----------|-----------|-------|
| Digital channel % | 96.0% | — | — | 96.0% | 96.0% |
| Root-cause totals | ≤ 50 | — | — | — | ≤ 50 |
| Notification count | — | 18 | 18 | 18 | 18 |
| Roadmap rows | — | — | 5–6 | — | 5–6 |

All values must match across all outputs.

---

## Troubleshooting

### "state.reconciled_notification_counts is empty"
- Check that `_reconcile_counts` return statement has 4 values
- Check that `run_stage4` unpacks 4 values: `... = _reconcile_counts(...)`

### "Section 6.2 heading still shows N+"
- Search for `"+` in the heading generation code
- Remove the `"+ حالة"` and use exact number only

### "Roadmap has 8 rows instead of 6"
- Check that `_deduplicate_roadmap_rows` is called BEFORE renumbering
- Verify that rows store `_root_cause_category`, `_sub_classification` as internal keys

### "Conclusion shows different number than Section 6.2"
- Ensure `state.final_notif_eliminatable` is populated after building notification table
- Check that conclusion reads `state.final_notif_eliminatable` before falling back

---

## Commit Message Template

When complete, use this commit message:

```
Fix: Report consistency — lock numeric values and prevent LLM hallucination

- Issue 1: Digital-channel % now includes NCRM (94% → 96%)
- Issue 2: Root-cause table counts from all_classified (no double-count)
- Issue 3: Notification counts reconciled across sections 6.2, 8, 9
- Issue 4: Section 6.2 heading sums actual table rows (exact N, no +)
- Issue 5: Roadmap deduplicates near-identical rows (5–6 rows, not 8)
- Issue 6: Conclusion impact metric uses final_notif_eliminatable

All numeric values now computed once from ground truth and reinjected
after LLM responses. Word and Excel outputs guaranteed consistent.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```
