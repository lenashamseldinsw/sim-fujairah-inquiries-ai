# Audit: Friction Point Case Count Reconciliation in stage6_json_report.py

**Invariant to enforce**: Every numeric count and percentage relating to a friction point must be derived from `state.journey_map[i].case_count` post-reconciliation, with no copies, caches, or re-derivations from raw classified case lists elsewhere in stage 6.

---

## Summary of Findings

### ❌ VIOLATIONS (3 critical + 1 high-risk)

| Location | Issue | Severity | Impact |
|----------|-------|----------|--------|
| Lines 750–752 | Friction rows from LLM, deduped without refresh | CRITICAL | Counts diverge from state.journey_map |
| Lines 152–232 | Text parsing in deduplication creates 2nd source | CRITICAL | Fragile, precision loss |
| Lines 870–880 | Gap rows include "الحالات" from LLM | CRITICAL | May be pre-reconciliation counts |
| Lines 971–983 | notif_intro_count computed from notif_rows (LLM) | HIGH | Percentage based on stale count |

### ✓ CORRECT (3 sections follow invariant)

| Location | Section | Status |
|----------|---------|--------|
| Lines 1352–1360 | Patterns section | ✓ Reads state.patterns, recomputes % |
| Lines 349–364 | Executive summary | ✓ Fresh state.all_classified, recompute % |
| Lines 514–524 | Workload map | ✓ Fresh state.all_classified, recompute % |

---

## Detailed Violations

### 1. 🔴 CRITICAL: Friction Rows Deduped Without Refresh (Lines 750–752)

**Code**:
```python
def build_customer_journey_section(self, lang: str = "ar") -> Dict[str, Any]:
    # ...
    friction_rows  = cj_raw["friction_table"]  # Line 750: from LLM output
    # ISSUE 3 FIX: Deduplicate near-duplicate friction points
    friction_rows  = _deduplicate_friction_rows(friction_rows)  # Line 752
```

**Problem**:
1. `cj_raw["friction_table"]` comes from LLM output in `state.report_sections_ar['customer_journey']['raw_data']`
2. While `generate_customer_journey_section()` does rebuild rows from `state.journey_map` at API time (line 249: `friction_rows = _build_friction_rows(state)`), by the time this code runs, reconciliation may have happened in a different stage or the LLM call may have been before reconciliation
3. Deduplication (line 752) then **mutates case counts** (see violation #2 below)
4. **No refresh/rebuild from state.journey_map post-deduplication**

**Violation of invariant**: The displayed friction_rows may contain case counts that were:
- Computed before `_reconcile_counts()` in stage 4, or
- Modified by text parsing in deduplication

**Evidence**:
- Lines 761–769: Guard assertion checks `friction.case_count` against actual sub_classification counts, but this is only a *warning*, not a *correction*
- No post-dedup validation that counts match state.journey_map

**Fix needed**: After deduplication, rebuild friction_rows from state.journey_map to ensure counts are post-reconciliation:
```python
friction_rows = cj_raw["friction_table"]
friction_rows = _deduplicate_friction_rows(friction_rows)
# REBUILD from state.journey_map to enforce single source of truth
friction_rows = self._rebuild_friction_rows_from_state()  # Read case_count from state.journey_map[i]
```

---

### 2. 🔴 CRITICAL: Text Parsing Creates Second Source of Truth (Lines 152–232)

**Code in `_deduplicate_friction_rows()`**:
```python
def _deduplicate_friction_rows(friction_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # ...
    try:
        # Combine case counts
        current_cases = int(current.get("الحالات", "0").replace(" cases", "").replace(" حالة", "").split()[0])
        for _, other_row in to_merge:
            other_cases = int(other_row.get("الحالات", "0").replace(" cases", "").replace(" حالة", "").split()[0])
            current_cases += other_cases
        current["الحالات"] = str(current_cases)  # Line 211: NEW COUNT, not from state
```

**Problem**:
1. Parses "الحالات" by string manipulation (removing " حالة", splitting, extracting first element)
2. This is **fragile**: if LLM format changes, parsing fails or loses precision
3. Merges counts from multiple rows **independently of state.journey_map**
4. Creates a **second source of truth** for case counts (the deduped count) separate from journey_map
5. The merged count is written back to the row without validation

**Violation of invariant**: Case counts in the final friction_rows may reflect:
- Deduped sums that don't exist in state.journey_map
- Precision loss from text parsing
- Divergence from reconciled counts if friction points in journey_map were not merged

**Risk**: If two near-duplicate friction points in journey_map are merged in display but journey_map is not updated, the total case count across all friction rows will exceed the sum of journey_map counts.

**Fix needed**: 
1. Don't deduplicate at display time — deduplicate in stage 4 when journey_map is built
2. Or, after deduplication, rebuild from state.journey_map to re-anchor counts to the single source of truth
3. Never parse case counts from text strings in stage 6 — always read from state objects

---

### 3. 🔴 CRITICAL: Gap Table "الحالات" Comes from LLM (Lines 870–880)

**Code**:
```python
def build_digital_gaps_section(self, lang: str = "ar") -> Dict[str, Any]:
    # ...
    gap_table_rows = dg_raw["gap_table"]  # Line 870: from LLM output
    
    gap_table_dict = {
        "columns": ["الموضوع", "الحالات", "الشدّة", "وضع التطبيق / الموقع الحالي", "نوع الفجوة", "التوصية"],
        "rows":    gap_table_rows,  # Line 876: used directly
        # ...
    }
```

**Problem**:
1. `dg_raw["gap_table"]` is LLM output from stage6_artifacts.py, generated via `generate_digital_gaps_section()`
2. The "الحالات" column in each gap row comes from that LLM output
3. No validation that these counts match state.journey_map or state.gap_table[i].case_count
4. If the LLM was called before or after reconciliation, the counts may be stale
5. **No rebuild/refresh from state data at report time**

**Violation of invariant**: Gap rows may show case counts that are:
- Pre-reconciliation values
- Different from state.gap_table[i].case_count
- Not derived from the authoritative source (state.journey_map + state.gap_table join)

**Evidence**:
- No assertion comparing gap_table_rows[i]["الحالات"] to state.gap_table[i].case_count
- No post-LLM refresh from state.gap_table

**Fix needed**: After reading from LLM, rebuild "الحالات" for each gap row from state.gap_table[i].case_count:
```python
gap_table_rows = dg_raw["gap_table"]
# REBUILD counts from state.gap_table to enforce single source of truth
for i, gap in enumerate(state.gap_table or []):
    if i < len(gap_table_rows):
        gap_table_rows[i]["الحالات"] = str(gap.case_count)
```

---

### 4. 🟠 HIGH: Notification Count Computed from LLM Rows (Lines 971–983)

**Code**:
```python
def build_digital_transformation_section(self, lang: str = "ar", section_number: int = 6) -> Optional[Dict[str, Any]]:
    # ...
    notif_rows    = dt_raw.get("notification_table", [])  # From LLM output
    
    notif_intro_count = sum(
        int("".join(filter(str.isdigit, r.get("الحالات المُلغاة", "0"))) or "0")
        for r in notif_rows
        if r.get("الحالات المُلغاة", "متعدد") != "متعدد"
    )  # Line 971–975: computed from LLM rows
    
    notif_intro = (
        f"تحليل البيانات يكشف أن {notif_intro_count}+ حالة تواصل "
        f"({round(notif_intro_count / (len(self.state.all_classified) or self.state.total_cases or 1) * 100, 0):.0f}% "
        # ...
    )  # Line 976–983: percentage based on notif_intro_count
```

**Problem**:
1. `notif_intro_count` is summed from `notif_rows`, which come from LLM output (`dt_raw["notification_table"]`)
2. This count is used in the section intro prose (line 977: `{notif_intro_count}+`)
3. The percentage is then computed (line 978) based on `notif_intro_count`
4. **The percentage may be out of sync with reconciled counts** if notif_intro_count reflects pre-reconciliation data
5. Additionally, line 972 parses "الحالات المُلغاة" via text regex, creating a derived value

**Violation of invariant**: The prose injection `{notif_intro_count}+` and the percentage `{...}%` are based on:
- Counts derived from LLM output, not state.journey_map
- Text parsing that may lose precision
- Not recomputed from authoritative state data at report time

**Evidence**:
- No assertion comparing sum of notif_rows to state.notification_opportunities or state.journey_map
- The percentage formula uses `notif_intro_count` which is computed, not fresh

**Fix needed**: Recompute notif_intro_count from authoritative state sources at report time:
```python
notif_intro_count = sum(
    n.get('cases_eliminated', n.get('case_count', 0))
    for n in (state.notification_opportunities or [])
)
notif_intro = (
    f"تحليل البيانات يكشف أن {notif_intro_count}+ حالة تواصل "
    f"({round(notif_intro_count / len(state.all_classified or []) * 100, 0):.0f}% "
    # ...
)
```

---

## Correct Implementations (For Reference)

### ✓ Patterns Section (Lines 1352–1360)
```python
type_total = sum(p.case_count for p in patterns_list)  # Fresh sum at report time
pattern_rows.append({
    "الفئة الفرعية": pattern.cluster_ar or pattern.cluster,
    "العدد": str(pattern.case_count),  # Direct from state.patterns[i].case_count
    "النسبة": f"{(pattern.case_count / type_total * 100):.1f}%",  # Recomputed, not cached
})
```
✓ **Follows invariant**: Reads from state.patterns, recomputes percentage at report time

### ✓ Executive Summary (Lines 349–364)
```python
complaint_count = sum(
    1 for c in self.state.all_classified
    if c.actual_contact_type == 'شكوى'
)  # Computed fresh from state.all_classified
complaint_rate = (complaint_count / total * 100) if total > 0 else 0  # Recomputed
body = f"...الشكاوى باتت تُمثّل {complaint_rate:.1f}% من عبء العمل الفعلي."  # Fresh percentage injected
```
✓ **Follows invariant**: Recomputes at report time, no caching

### ✓ Workload Map (Lines 514–524)
```python
all_classified = self.state.all_classified or []
total_cases = len(all_classified)  # Fresh at report time
corrected_dist = defaultdict(int)
for case in all_classified:
    corrected_dist[case.actual_contact_type] += 1  # Fresh counts
dist_rows = _build_rich_distribution_rows(corrected_dist, original_dist, total_cases)  # Recomputes % for each row
```
✓ **Follows invariant**: Builds distribution fresh, recomputes percentages

---

## Remediation Checklist

- [ ] **Violation 1 (friction rows)**: Add method to rebuild friction_rows from state.journey_map post-deduplication
- [ ] **Violation 2 (deduplication)**: Either move deduplication to stage 4 OR rebuild from state after dedup
- [ ] **Violation 3 (gap rows)**: Add code to refresh "الحالات" from state.gap_table[i].case_count
- [ ] **Violation 4 (notification count)**: Recompute notif_intro_count from state.notification_opportunities
- [ ] **General**: Add validation assertions in each section to verify counts match state sources
- [ ] **Testing**: Verify that after reconciliation, all displayed counts match their source in state objects

---

## Impact on Report Accuracy

If reconciliation changes friction point case counts, but stage 6 displays stale counts:
- **Section 4 (Customer Journey)**: Friction point counts and percentages will not match the reconciled totals
- **Section 5 (Digital Gaps)**: Gap impact counts will be pre-reconciliation values
- **Section 6 (Digital Transformation)**: Notification opportunity impact will be based on stale case counts
- **Cross-section inconsistency**: Total case count in Section 3 (workload map) may not equal sum of friction points in Section 4

The invariant ensures all friction-related numbers point to one source of truth: `state.journey_map[i].case_count` after `_reconcile_counts()`.
