# Real Inquiries Flow — Prompt Logic Review & Consistency Audit

## Summary: 6 Issues Root Cause Analysis

All six issues stem from the same architectural problem: **numbers are computed at multiple points in the pipeline (stages 1–6) without a single authoritative source.** The LLM responses in stages 4 and 6 contain estimates that are never validated against ground truth, and downstream sections read from unstable sources.

---

## Issue 1: Digital-Channel Percentage (94% vs 96%)

### Current Implementation
**File: `generate_digital_gaps_section.py`, line 94–109**

```python
def _compute_submission_channel_pct(state: PipelineState) -> float:
    """% of cases submitted via digital channels (app or website)."""
    cases = state.all_classified or []
    total = len(cases) or 1
    digital_submissions = sum(
        1 for c in cases
        if c.case_channel and ("تطبيق" in str(c.case_channel) or "موقع" in str(c.case_channel))
    )
    return round(digital_submissions / total * 100, 1)
```

**Problem:**
- Only counts `تطبيق` (app) and `موقع` (website)
- **Silently drops `NCRM` channel**, which is also digital
- Function is **copy-pasted** in `generate_conclusion_section.py` (line 66–83) and likely in `stage6_json_report.py`
- Each copy has its own definition of "digital channels", so changing one doesn't update all

**Current Result:** 
- 48 NCRM + app + website cases out of 50 = 96%, but only app + website counted = 47 → 94%

### Fix Strategy

**Step 1: Define digital channels once at module level** (must be imported by all users)

**File: `generate_digital_gaps_section.py`, add at top after imports:**
```python
# Single authoritative definition of digital submission channels
_DIGITAL_SUBMISSION_CHANNELS = {"تطبيق", "موقع", "NCRM", "ncrm"}

def _compute_submission_channel_pct(state: PipelineState) -> float:
    """
    % of cases submitted via any digital channel (app, website, or NCRM).
    Single source of truth used in digital gaps section and conclusion.
    """
    cases = state.all_classified or []
    total = len(cases) or 1
    digital = sum(
        1 for c in cases
        if c.case_channel and any(
            kw in str(c.case_channel) for kw in _DIGITAL_SUBMISSION_CHANNELS
        )
    )
    return round(digital / total * 100, 1)
```

**Step 2: Import constant in dependent files**

**File: `generate_conclusion_section.py`:**
- Replace local `_compute_submission_channel_pct` with import from `generate_digital_gaps_section`
- Import the constant `_DIGITAL_SUBMISSION_CHANNELS`

**File: `stage6_json_report.py`:**
- Do the same — import `_DIGITAL_SUBMISSION_CHANNELS` and the helper function

**Step 3: Update all Arabic labels that say "(التطبيق / الموقع الإلكتروني)" to include NCRM**

**File: `generate_digital_gaps_section.py`:**
Search for all occurrences of `"(التطبيق / الموقع الإلكتروني)"` in prompts and replace with:
```
"(التطبيق / الموقع الإلكتروني + NCRM)"
```

### Verification Checkpoints

For the 50-case test file:
1. **Count NCRM cases:** `SELECT COUNT(*) WHERE قناة_تقديم_الخدمة contains "NCRM"` → expect ~1
2. **Count app cases:** expect ~24
3. **Count website cases:** expect ~23
4. **Total digital:** 1 + 24 + 23 = 48 → **48 / 50 = 96.0%** ✓
5. **Verify all three mentions in the report use 96%:** Section 5 intro, 5.1 context, Conclusion

---

## Issue 2: Section 5.2 Root-Cause Table Inflates Friction Counts

### Current Implementation
**File: `generate_digital_gaps_section.py`, line 186–225**

```python
def _build_root_cause_rows(state: PipelineState) -> List[Dict[str, str]]:
    """Pre-computed rows for Section 5.2 table."""
    rc_totals: Dict[str, int] = defaultdict(int)
    rc_best_friction: Dict[str, tuple] = {}
    
    for f in state.journey_map:
        rc_totals[f.root_cause_category] += f.case_count  # ⚠️ SUMS journey_map
        ...
```

**Problem:**
- **Sums `journey_map.case_count` per root_cause_category**, not actual case counts
- When multiple friction points share the same `root_cause_category`, their counts are added
- **Double-counts** cases if the same case is assigned to two friction points with overlapping sub_classifications
- Result: Row total exceeds actual distinct cases in that category

**Example:**
- Friction A (missing_info): 20 cases
- Friction B (missing_info): 15 cases
- Table shows: missing_info = 35 cases
- But actual distinct cases with missing_info sub_classification: 30 cases
- **Over-count by 5 cases**

### Fix Strategy

**File: `generate_digital_gaps_section.py`, replace `_build_root_cause_rows`:**

```python
def _build_root_cause_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Pre-computed rows for Section 5.2 root-cause table.
    
    Case counts derived from state.all_classified (ground truth), not from
    summing journey_map, to prevent double-counting when multiple friction
    points share the same root_cause_category.
    """
    from collections import defaultdict
    
    # Build mapping: root_cause_category → set of sub_classifications it covers
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
    
    # Authoritative counts: count each case exactly once per root_cause_category
    rc_actual_totals: Dict[str, int] = defaultdict(int)
    for case in (state.all_classified or []):
        sub = case.sub_classification
        for cat, subs in rc_to_subs.items():
            if sub in subs:
                rc_actual_totals[cat] += 1
                break  # Count each case in at most one category
    
    # Sort by actual total count descending
    sorted_rc = sorted(rc_actual_totals.items(), key=lambda x: x[1], reverse=True)
    
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

**File: `stage6_json_report.py`:**
- Import the updated `_build_root_cause_rows` from `generate_digital_gaps_section`
- No other changes needed — the import is already there

### Verification Checkpoints

For the 50-case test file:
1. **Sum all root-cause totals in Section 5.2:** should equal ≤ 50 (not exceed total cases)
2. **Verify each category's count matches sub_classification totals:** 
   - Count cases where `sub_classification IN ('friction1_subs', 'friction2_subs'...)` per category
3. **Example row should use the total, not best_count:** e.g., "25 حالة — friction_text"

---

## Issue 3: Section 6.2 Notification Table Counts Inconsistent with Section 6.1 FAQ Frequencies

### Current Implementation
**File: `generate_digital_transformation_section.py`, line 281–422**

- Section 6.1 FAQ table row frequencies: capped against actual `sub_counts` (authoritative)
- Section 6.2 notification rows: derive `cases_eliminated` from:
  1. `state.notification_opportunities` (set by Stage 4 LLM, possibly hallucinated)
  2. Further capped by `_reconcile_counts` (but cap isn't stored back to state)
- **Result:** Section 6.2 uses post-reconciliation counts, but Section 8 (roadmap) reads from original `journey_map`

**Problem:**
- Notification row "delivery alerts": 15 cases
- Roadmap row "delivery alerts": 18 cases (from journey_map, not reconciled)
- **Different numbers for the same intervention**

### Fix Strategy

**Step 1: Store reconciled notification counts in state**

**File: `state.py`, add new field to `PipelineState`:**
```python
reconciled_notification_counts: Dict[str, int] = Field(default_factory=dict)
# Keys are notification_type strings from notification_opportunities.
# Values are the post-reconciliation cases_eliminated counts.
# Populated at end of Stage 4 reconciliation.
```

**Step 2: Populate in stage4_analysis.py**

**File: `stage4_analysis.py`, update `_reconcile_counts` return signature:**
```python
def _reconcile_counts(
    journey_map: list,
    patterns: list,
    all_classified: list,
    notification_opportunities: list,
    proactive_case_count: int,
) -> tuple[list, list, list, dict]:
    """Returns tuple of (reconciled_journey_map, patterns, notifications, per_type_counts)"""
    
    # ... existing reconciliation code ...
    
    # At end, extract final per-type counts
    reconciled_counts_by_type: Dict[str, int] = {}
    for n in reconciled_notifications:
        ntype = n.get("notification_type") or n.get("content_summary") or ""
        if ntype:
            reconciled_counts_by_type[ntype] = n.get("cases_eliminated", 0)
    
    return reconciled_journey_map, reconciled_patterns, reconciled_notifications, reconciled_counts_by_type
```

**Step 3: Update call sites in `run_stage4` and `_retry_journey_map_only`:**
```python
(state.journey_map,
 state.patterns,
 state.notification_opportunities,
 state.reconciled_notification_counts) = _reconcile_counts(...)
```

**Step 4: Use reconciled counts in display**

**File: `generate_digital_transformation_section.py`, line 312, update `_build_notification_rows`:**
```python
def _build_notification_rows(state: PipelineState) -> List[Dict[str, str]]:
    """Use reconciled notification counts for consistency."""
    rows: List[Dict[str, str]] = []
    total_cases = len(state.all_classified) or state.total_cases
    
    if state.notification_opportunities:
        sorted_notifs = sorted(
            state.notification_opportunities,
            key=lambda n: n.get("cases_eliminated", 0),
            reverse=True,
        )
        for n in sorted_notifs:
            notif_type = n.get("notification_type") or n.get("content_summary") or ""
            
            # ⚠️ KEY FIX: Read from reconciled_notification_counts, not raw cases_eliminated
            cases = state.reconciled_notification_counts.get(notif_type, n.get("cases_eliminated", 0))
            
            # ... rest of row building ...
```

**Step 5: Update roadmap section to use reconciled counts**

**File: `generate_improvement_roadmap_section.py`, in `_build_display_roadmap_rows`:**
```python
# When building roadmap rows from notification_opportunities, prefer reconciled counts
if notification_opp:
    ntype = notification_opp.get("notification_type") or ""
    cases = state.reconciled_notification_counts.get(ntype, 
                                                      notification_opp.get("cases_eliminated", 0))
    # Use cases in impact statement
```

### Verification Checkpoints

For the 50-case test file:
1. **Verify notification table 6.2 row counts** match `state.reconciled_notification_counts` values
2. **Verify roadmap section 8 rows** use the same reconciled counts
3. **Cross-check:** Delivery notification in 6.2 has same case count as Tool 3 impact in section 7

---

## Issue 4: Section 6.2 Heading Does Not Match Sum of Table Rows

### Current Implementation
**File: `generate_digital_transformation_section.py`, line 478–497**

```python
def _total_notif_cases(notif_rows: List[Dict[str, str]], state: PipelineState) -> int:
    """Compute total eliminatable cases."""
    if state.proactive_notification_case_count:
        return state.proactive_notification_case_count  # ⚠️ Uses Stage 4 count
    
    if state.notification_opportunities:
        return sum(n.get("cases_eliminated", 0) for n in state.notification_opportunities)
    
    # Fallback to gap_table
    return sum(g.case_count for g in (state.gap_table or [])
               if g.proactive_notification_opportunity)
```

**Problem:**
- Reads `proactive_notification_case_count` (Stage 4 authoritative count, may be 20)
- But table rows have been further capped by `_reconcile_counts` (may sum to 18)
- **Heading says "مسار إلغاء 20 حالة"** but table rows sum to 18
- Reviewer sees: "20 cases" in heading, counts rows, finds only 18 → **credibility loss**

### Fix Strategy

**File: `generate_digital_transformation_section.py`, replace `_total_notif_cases`:**

```python
def _total_notif_cases(notif_rows: List[Dict[str, str]], state: PipelineState) -> int:
    """
    Compute total eliminatable cases by summing the notification table rows.
    
    This is the ONLY source of truth for the section heading — it always matches
    the table because it IS derived from the same row data.
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

**File: `generate_digital_transformation_section.py`, update heading generation:**
```python
# In generate_digital_transformation_section, after building notif_rows:
notif_headline = str(total_notif_cases(notif_rows, state)) if total_notif_cases(notif_rows, state) > 0 else "عدد من"
# Remove the "+" suffix — it implies "at least" but table shows exact numbers
```

### Verification Checkpoints

For the 50-case test file:
1. **Count Section 6.2 table rows:** sum the integers from "الحالات المُلغاة" column
2. **Check section heading:** should say "مسار إلغاء N حالة" where N = row sum
3. **Verify no "+" in the heading:** heading should be exact number, not "N+ حالة"

---

## Issue 5: Roadmap Rows 4/5/6 Duplicate Rows 1/2/3

### Current Implementation
**File: `generate_improvement_roadmap_section.py`, line 200–300 (approximately)**

- Builds rows from three sources without deduplication:
  1. `state.journey_map` friction points → roadmap rows
  2. `state.gap_table` proactive gaps → roadmap rows
  3. `report_sections_ar['ai_use_cases']` AI tools → roadmap rows
- **Same intervention** appears twice (e.g., "improve delivery notification" from both journey_map and gap_table)
- Both rows get renumbered 1–N, producing near-identical rows at different indices

### Fix Strategy

**File: `generate_improvement_roadmap_section.py`, add deduplication:**

```python
def _deduplicate_roadmap_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove near-duplicate roadmap rows using locked field signatures.
    
    Two rows are duplicates if they share the same root_cause_category AND
    sub_classification (the locked structural identity).
    Keeps the row with higher case_count; drops the other.
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
    
    return list(seen.values())


def _strip_internal_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal (underscore-prefixed) keys from row dict."""
    return {k: v for k, v in row.items() if not k.startswith("_")}
```

**In `_build_display_roadmap_rows` or similar:**
```python
# After assembling rows from all three sources, deduplicate:
rows = _deduplicate_roadmap_rows(rows)

# Re-sort by horizon
rows = sorted(rows, key=lambda r: _horizon_rank(r.get("الأفق الزمني", "")))

# Strip internal keys before returning
rows = [_strip_internal_keys(r) for r in rows]

# Renumber sequentially with str(i)
final_rows = []
for i, row in enumerate(rows, 1):
    row["#"] = str(i)
    final_rows.append(row)
```

### Verification Checkpoints

For the 50-case test file:
1. **Count roadmap table rows:** expect 5–6, not 7–8
2. **Verify no near-duplicate rows:** check that no two rows have same horizon + similar recommendation text
3. **Check row numbering:** should be sequential 1–N with no gaps

---

## Issue 6: Conclusion Impact Box Metric Does Not Update

### Current Implementation
**File: `generate_conclusion_section.py`, line 131–145**

```python
def _count_proactive_cancellable(state: PipelineState) -> int:
    """Count cases cancellable by proactive notification."""
    opps = state.notification_opportunities or []
    if opps:
        return sum(int(o.get('cases_eliminated', 0)) for o in opps)
    
    # Fallback: journey_map proactive friction points
    jm = state.journey_map or []
    return sum(j.case_count for j in jm if j.root_cause_category == 'no_proactive_notification')
```

**Problem:**
- Reads from `notification_opportunities` (which contains Stage 4 raw estimates, not reconciled)
- But Section 6.2 table has reconciled counts (smaller, more accurate)
- **Conclusion box says "N+ حالة"** but Section 6.2 says smaller number
- **Different numbers for the same metric** across report sections

### Fix Strategy

**Step 1: Add derived field to state**

**File: `state.py`, add to `PipelineState`:**
```python
final_notif_eliminatable: int = 0
# Sum of cases_eliminated across all reconciled notification rows.
# Set by Stage 6 after notification table rows are built.
# This is the authoritative number used in section headings, conclusion, and impact box.
```

**Step 2: Populate in stage6_json_report.py**

**File: `stage6_json_report.py`, in method `generate_json_report` or similar:**
```python
# After building notification table rows:
if "notification_table" in digital_transform_section:
    import re as _re
    total = 0
    for r in digital_transform_section["notification_table"]:
        digits = _re.sub(r"[^\d]", "", str(r.get("الحالات المُلغاة", "0")))
        if digits:
            total += int(digits)
    state.final_notif_eliminatable = total
```

**Step 3: Use in conclusion**

**File: `generate_conclusion_section.py`, update `_count_proactive_cancellable`:**
```python
def _count_proactive_cancellable(state: PipelineState) -> int:
    """Count cases cancellable by proactive notification (from final table)."""
    # Prefer the final reconciled count (set after section 6.2 table is built)
    if state.final_notif_eliminatable > 0:
        return state.final_notif_eliminatable
    
    # Fallback to reconciled notification counts
    if state.reconciled_notification_counts:
        return sum(state.reconciled_notification_counts.values())
    
    # Last resort: raw notification_opportunities (Stage 4 estimate)
    opps = state.notification_opportunities or []
    if opps:
        return sum(int(o.get('cases_eliminated', 0)) for o in opps)
    
    # Final fallback: journey_map proactive friction points
    jm = state.journey_map or []
    return sum(j.case_count for j in jm if j.root_cause_category == 'no_proactive_notification')
```

### Verification Checkpoints

For the 50-case test file:
1. **Check conclusion impact box:** "N+ حالة قابلة للإلغاء"
2. **Verify N equals section 6.2 heading number**
3. **Verify N equals sum of section 6.2 notification table rows**
4. **All three should be identical** across Word (.docx) and Excel (.xlsx) outputs

---

## Cross-Cutting: LLM Reinject Checklist

After all fixes, verify no LLM output can silently overwrite a pre-computed number:

| Section | Locked Column | Computation Site | Reinject Location |
|---------|--------------|------------------|-------------------|
| 3.1 Distribution | العدد, النسبة | `_build_rich_distribution_rows` (pure Python) | No LLM call |
| 3.2 Reclassification | N حالة / N% | `state.reclassified_count` (Stage 3) | Reinjected in prompt before LLM |
| 4 Friction table | الحالات | `state.journey_map.case_count` (reconciled Stage 4) | `_build_friction_rows` (pure Python) |
| 5.1 Gap table | الحالات | `state.gap_table.case_count` (Stage 5) | `_build_gap_rows` (pure Python) |
| 5.2 Root-cause | مثال على التحدي count | **Issue 2 fix:** `state.all_classified` lookup | `_build_root_cause_rows` (pure Python) |
| 6.1 FAQ | #, التكرار | `sub_counts` from `state.all_classified` | `_build_faq_rows_for_transform` (pure Python) |
| 6.2 Notification | الحالات المُلغاة, القناة | **Issue 3 fix:** `state.reconciled_notification_counts` | `_build_notification_rows` (pure Python) |
| 6.2 Heading | N حالة | **Issue 4 fix:** sum of table rows | Computed from `notif_rows` (pure Python) |
| 8 Roadmap | الأفق الزمني, #, الجهد | `state.journey_map` (reconciled) + `gap_table` | **Issue 5 fix:** deduplication before LLM |
| 9 Conclusion | N+ حالة | **Issue 6 fix:** `state.final_notif_eliminatable` | Computed at end of Stage 6 |

---

## Testing Checklist

Run the 50-case test file through the full pipeline:

### Issue 1 Verification
- [ ] Section 5 intro: "96.0% من الحالات" (not 94%)
- [ ] Section 5.1 context: includes NCRM in parentheses
- [ ] Conclusion: "96.0% من حالات التواصل" (consistent)

### Issue 2 Verification
- [ ] Section 5.2 root-cause table: sum of "مثال على التحدي" counts ≤ 50
- [ ] No single root-cause category shows > 50 cases
- [ ] counts match sub_classification totals from input Excel

### Issue 3 Verification
- [ ] Section 6.2 notification row "delivery": matches Section 7 Tool 3 count
- [ ] Section 8 roadmap "delivery" row: same count as Section 6.2
- [ ] No reconciliation-caused discrepancies

### Issue 4 Verification
- [ ] Section 6.2 heading: "مسار إلغاء N حالة" (exact number, no "+")
- [ ] N = sum of row integers from الحالات المُلغاة column
- [ ] Excel "Digital Transformation" sheet shows same N

### Issue 5 Verification
- [ ] Section 8 roadmap: 5–6 rows, not 8+
- [ ] No near-identical rows at different row numbers
- [ ] Row numbers sequential 1–N

### Issue 6 Verification
- [ ] Conclusion impact box: "N حالة قابلة للإلغاء" (exact number)
- [ ] N = Section 6.2 heading number
- [ ] N = sum of Section 6.2 table rows
- [ ] Word and Excel outputs show identical N

---

## Implementation Priority

1. **Issue 1** (digital-channel %): Easiest, most visible — fix first
2. **Issue 2** (root-cause counts): Medium difficulty, affects Section 5.2
3. **Issue 4** (notification heading): Easy once Issue 3 is done
4. **Issue 3** (reconciled counts): Hard, requires plumbing through multiple stages
5. **Issue 6** (conclusion metric): Depends on Issue 3/4, implement last
6. **Issue 5** (roadmap deduplication): Medium difficulty, independent implementation

---

## Debugging Commands

After implementing fixes, run these checks:

```python
# In stage6_json_report.py, after building each section:

print(f"[DEBUG] digital_channel_pct = {state.digital_channel_pct}%")
print(f"[DEBUG] root_cause totals: {[(cat, cnt) for cat, cnt in rc_actual_totals.items()]}")
print(f"[DEBUG] reconciled_notification_counts: {state.reconciled_notification_counts}")
print(f"[DEBUG] notification table row sum: {sum of الحالات المُلغاة}")
print(f"[DEBUG] final_notif_eliminatable: {state.final_notif_eliminatable}")
print(f"[DEBUG] roadmap_rows after dedup: {len(roadmap_rows)} rows")
```

Compare Word and Excel outputs:
```bash
# Word: Open .docx, search for the percentages/counts mentioned above
# Excel: Open .xlsx, check the "Digital Transformation" and "Roadmap" sheets
```

All six numbers must match across Word, Excel, and JSON outputs — if they don't, the fix isn't complete.
