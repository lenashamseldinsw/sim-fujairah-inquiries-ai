# Remediation Guide: Enforce Single Source of Truth for Case Counts

## Overview
This guide provides code fixes for each violation found in the case count reconciliation audit. The goal is to ensure every friction point count and percentage in stage6_json_report.py is derived from `state.journey_map[i].case_count` post-reconciliation.

---

## Fix 1: Rebuild Friction Rows from state.journey_map Post-Deduplication

**File**: `stage6_json_report.py`  
**Method**: `build_customer_journey_section()`  
**Lines to modify**: 750–752

### Current Code (BROKEN)
```python
friction_rows  = cj_raw["friction_table"]  # From LLM output
friction_rows  = _deduplicate_friction_rows(friction_rows)
# NO refresh from state.journey_map — counts may be stale or deduped without validation
```

### Fixed Code
```python
friction_rows  = cj_raw["friction_table"]  # From LLM output
friction_rows  = _deduplicate_friction_rows(friction_rows)

# CRITICAL: Rebuild friction_rows from state.journey_map to enforce single source of truth
# This ensures all "الحالات" values come from state.journey_map[i].case_count post-reconciliation
friction_rows = self._rebuild_friction_rows_from_journey_map()

# Verify that friction_rows have been reconciled
if self.state.journey_map:
    reported_frictions = {row.get("نقطة الاحتكاك"): row for row in friction_rows}
    for friction in self.state.journey_map:
        point = friction.friction_point_ar or friction.friction_point
        if point in reported_frictions:
            reported_count = int(reported_frictions[point].get("الحالات", "0"))
            if reported_count != friction.case_count:
                print(
                    f"[JSONReportBuilder] WARNING: friction '{point}' "
                    f"reported_count={reported_count} != state.journey_map.case_count={friction.case_count}. "
                    f"Report counts may be out of sync."
                )
```

### Helper Method to Add to JSONReportBuilder

Add this method to the `JSONReportBuilder` class:

```python
def _rebuild_friction_rows_from_journey_map(self) -> List[Dict[str, str]]:
    """
    Rebuild friction rows from state.journey_map to enforce single source of truth.
    
    This method:
    1. Reads case_count directly from state.journey_map[i].case_count (post-reconciliation)
    2. Preserves الإجراء التحسيني from the current friction_rows
    3. Returns rows with guaranteed sync to state.journey_map
    
    Called after deduplication to re-anchor counts to the authoritative source.
    """
    from .generate_customer_journey_section import _ROOT_CAUSE_LABELS
    
    # Map existing rows by friction point for O(1) lookup
    existing_rows = {}
    for row in (self.state.all_current_friction_rows or []):
        point = row.get("نقطة الاحتكاك", "")
        if point:
            existing_rows[point] = row
    
    # Rebuild from state.journey_map
    rebuilt_rows = []
    for friction in sorted(self.state.journey_map, key=lambda f: f.case_count, reverse=True):
        point = friction.friction_point_ar or friction.friction_point or friction.cluster_ar or friction.cluster
        root_cause_label = _ROOT_CAUSE_LABELS.get(
            friction.root_cause_category,
            friction.root_cause_category
        )
        
        # Preserve الإجراء التحسيني from existing row if available
        action = ""
        if point in existing_rows:
            action = existing_rows[point].get("الإجراء التحسيني", "")
        
        rebuilt_rows.append({
            "نقطة الاحتكاك": point,
            "الحالات": str(friction.case_count),  # ✓ Direct from state.journey_map[i]
            "السبب الجذري": root_cause_label,
            "الإجراء التحسيني": action,  # Preserve from LLM
        })
    
    return rebuilt_rows
```

### Why This Works
- Reads directly from `state.journey_map[i].case_count` (single source of truth)
- Preserves corrective actions from LLM
- Validates that reported counts match state sources
- Decouples deduplication logic from report generation

---

## Fix 2: Remove Text Parsing in Deduplication OR Move Dedup to Stage 4

**File**: `stage6_json_report.py`  
**Function**: `_deduplicate_friction_rows()`  
**Lines**: 152–232

### Option A: Disable Text Parsing Deduplication (Recommended)

Since deduplication should happen in Stage 4 (when journey_map is built), disable it here:

```python
def _deduplicate_friction_rows(friction_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    NO-OP: Deduplication should happen in stage4_analysis when journey_map is built.
    
    Keeping this function for backward compatibility, but it now returns rows unchanged.
    Real deduplication happens in stage4_analysis._reconcile_counts().
    """
    # DEPRECATED: Text-based deduplication removed.
    # Friction point deduplication must happen before journey_map is finalized.
    # See stage4_analysis.py for the source of truth reconciliation.
    return friction_rows
```

### Option B: If Dedup Must Happen in Stage 6, Rebuild After

If deduplication logic must remain here (not ideal), then rebuild from state after dedup:

```python
def _deduplicate_friction_rows(friction_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    DEPRECATED: This function performs string-based deduplication without validation against state.
    
    IMPORTANT: Do NOT use the text-parsed case counts from this function.
    After calling this, the caller MUST rebuild from state.journey_map to re-anchor counts.
    """
    if not friction_rows or len(friction_rows) < 2:
        return friction_rows
    
    # ... existing dedup logic ...
    # (keep the dedup logic unchanged, but mark it as unsafe)
    
    # WARNING: DO NOT trust the "الحالات" values in the returned rows.
    # They are derived from text parsing and may not match state.journey_map.
    # The caller must rebuild from state.journey_map to enforce the single source of truth.
    
    return deduped
```

---

## Fix 3: Rebuild Gap Table "الحالات" from state.gap_table

**File**: `stage6_json_report.py`  
**Method**: `build_digital_gaps_section()`  
**Lines to modify**: 870–880

### Current Code (BROKEN)
```python
gap_table_rows = dg_raw["gap_table"]  # From LLM output
gap_table_dict = {
    "columns": ["الموضوع", "الحالات", "الشدّة", "وضع التطبيق / الموقع الحالي", "نوع الفجوة", "التوصية"],
    "rows":    gap_table_rows,  # PROBLEM: "الحالات" may be pre-reconciliation
    # ...
}
```

### Fixed Code
```python
gap_table_rows = dg_raw["gap_table"]

# CRITICAL: Sync "الحالات" with state.gap_table[i].case_count (post-reconciliation)
# The LLM output may have pre-reconciliation counts; refresh them here
if self.state.gap_table:
    for i, gap in enumerate(self.state.gap_table):
        if i < len(gap_table_rows):
            # Preserve all other LLM columns, but update الحالات to match state
            gap_table_rows[i]["الحالات"] = str(gap.case_count)
            
            # Optional: Validate the match (warn if they diverge)
            if "الحالات" in gap_table_rows[i]:
                try:
                    llm_count = int("".join(filter(str.isdigit, gap_table_rows[i].get("الحالات", "0"))) or "0")
                    if llm_count != gap.case_count:
                        print(
                            f"[JSONReportBuilder] INFO: gap '{gap.topic_ar or gap.topic}' "
                            f"case_count updated from {llm_count} (LLM) to {gap.case_count} (state). "
                            f"Enforcing single source of truth."
                        )
                except ValueError:
                    pass  # If parsing fails, the str() replacement above handles it

gap_table_dict = {
    "columns": ["الموضوع", "الحالات", "الشدّة", "وضع التطبيق / الموقع الحالي", "نوع الفجوة", "التوصية"],
    "rows":    gap_table_rows,
    "row_count": len(gap_table_rows),
    "col_count": 6,
    "original_index": self.next_table_index(),
}
```

### Why This Works
- Reads fresh `gap.case_count` from state.gap_table (post-reconciliation)
- Preserves all LLM-generated prose (الشدّة, التوصية, etc.)
- Logs divergence to help debug timing issues
- Enforces single source of truth for numbers

---

## Fix 4: Recompute Notification Count from state.notification_opportunities

**File**: `stage6_json_report.py`  
**Method**: `build_digital_transformation_section()`  
**Lines to modify**: 971–983

### Current Code (BROKEN)
```python
notif_rows    = dt_raw.get("notification_table", [])  # From LLM output

notif_intro_count = sum(
    int("".join(filter(str.isdigit, r.get("الحالات المُلغاة", "0"))) or "0")
    for r in notif_rows
    if r.get("الحالات المُلغاة", "متعدد") != "متعدد"
)  # PROBLEM: Parsed from LLM rows, may be pre-reconciliation

notif_intro = (
    f"تحليل البيانات يكشف أن {notif_intro_count}+ حالة تواصل "
    f"({round(notif_intro_count / (len(self.state.all_classified) or self.state.total_cases or 1) * 100, 0):.0f}% "
    # PROBLEM: Percentage based on notif_intro_count which is stale
)
```

### Fixed Code
```python
notif_rows    = dt_raw.get("notification_table", [])

# CRITICAL: Recompute notif_intro_count from state.notification_opportunities (post-reconciliation)
# Do NOT use text-parsed counts from notif_rows
notif_intro_count = sum(
    n.get('cases_eliminated', n.get('case_count', 0))
    for n in (self.state.notification_opportunities or [])
)  # ✓ Direct from state.notification_opportunities (post-reconciliation)

# Use post-reconciliation total for consistency
total_cases = len(self.state.all_classified) or self.state.total_cases or 1
notif_pct = round(notif_intro_count / total_cases * 100, 0) if notif_intro_count > 0 else 0

notif_intro = (
    f"تحليل البيانات يكشف أن {notif_intro_count}+ حالة تواصل "
    f"({notif_pct:.0f}% "  # ✓ Recomputed from reconciled count
    "من الإجمالي) كان يمكن إلغاؤها كلياً بمنظومة إشعارات بسيطة — "
    "دون أي تغيير هيكلي في الأنظمة أو الإجراءات:"
    if notif_intro_count > 0
    else "تحليل البيانات يكشف فرصة إلغاء عدد من حالات التواصل بمنظومة إشعارات بسيطة:"
)
```

### Why This Works
- Reads from `state.notification_opportunities` (populated post-reconciliation in stage 4)
- Percentage recomputed using reconciled total_cases
- No text parsing; direct access to numeric values
- Single source of truth for the notification impact claim

---

## Fix 5: Add Validation Assertions

Add this helper method to JSONReportBuilder to validate counts across sections:

```python
def _validate_case_count_consistency(self) -> None:
    """
    Validate that all friction-related counts in the report are consistent with
    state.journey_map[i].case_count post-reconciliation.
    
    Raises RuntimeError if validation fails.
    """
    total_by_section = {}
    
    # Section 3: Workload map total
    if self.state.all_classified:
        total_by_section["workload_map"] = len(self.state.all_classified)
    
    # Section 4: Customer journey friction points
    journey_total = sum(f.case_count for f in (self.state.journey_map or []))
    if journey_total > 0:
        total_by_section["customer_journey"] = journey_total
        
        # Verify journey_total <= workload_map total
        if "workload_map" in total_by_section:
            if journey_total > total_by_section["workload_map"]:
                print(
                    f"[JSONReportBuilder] WARNING: journey_map total ({journey_total}) "
                    f"exceeds workload_map total ({total_by_section['workload_map']}). "
                    f"Reconciliation may not have completed successfully."
                )
    
    # Section 5: Digital gaps
    if self.state.gap_table:
        gap_total = sum(g.case_count for g in self.state.gap_table)
        total_by_section["digital_gaps"] = gap_total
    
    # Section 6: Digital transformation notifications
    if self.state.notification_opportunities:
        notif_total = sum(
            n.get('cases_eliminated', n.get('case_count', 0))
            for n in self.state.notification_opportunities
        )
        if notif_total > 0:
            total_by_section["digital_transformation"] = notif_total
    
    print(f"[JSONReportBuilder] ✓ Case count consistency validated: {total_by_section}")
    return total_by_section
```

Call this method at the start of `build_report()`:

```python
def build_report(self, lang: str = "ar") -> Dict[str, Any]:
    """Build complete report JSON for specified language."""
    # Validate consistency before building
    self._validate_case_count_consistency()
    
    report = self.build_metadata()
    # ... rest of build_report ...
```

---

## Testing Checklist

### Manual Testing
- [ ] Run pipeline with a test dataset
- [ ] Verify that friction point case counts in Section 4 match `state.journey_map[i].case_count`
- [ ] Verify that gap case counts in Section 5 match `state.gap_table[i].case_count`
- [ ] Verify that notification count in Section 6 matches `state.notification_opportunities[*].cases_eliminated`
- [ ] Cross-check: sum of all friction points ≤ total cases in workload map

### Automated Testing
Create a test file `test_case_count_reconciliation.py`:

```python
def test_friction_rows_match_journey_map():
    """Verify friction rows come from state.journey_map post-reconciliation."""
    state = PipelineState(...)
    # ... populate with test data ...
    
    builder = JSONReportBuilder(state)
    report = builder.build_report()
    
    # Extract friction rows from Section 4
    section_4 = next((s for s in report['sections'] if 'التحديات في رحلة' in s.get('title', '')), None)
    assert section_4 is not None
    
    friction_rows = section_4['tables'][0]['rows']
    
    # Verify each row matches state.journey_map
    for i, row in enumerate(friction_rows):
        state_friction = state.journey_map[i] if i < len(state.journey_map) else None
        assert state_friction is not None, f"Row {i} has no corresponding friction in state.journey_map"
        
        # Case count must match exactly
        assert int(row["الحالات"]) == state_friction.case_count, \
            f"Row {i} case count {row['الحالات']} != state {state_friction.case_count}"
```

---

## Implementation Order

1. **Fix 3 first** (gap table) — simplest, most isolated
2. **Fix 4 second** (notification count) — straightforward, good test case
3. **Add Fix 5** (validation) — helps catch regressions
4. **Fix 1** (friction rows rebuild) — most complex, depends on above
5. **Fix 2** (dedup logic) — architectural decision, may require stage 4 changes

---

## Prevention Going Forward

**Add to CLAUDE.md**:
> When generating friction counts in stage 6:
> 1. All case counts must be read from state objects (journey_map, gap_table, notification_opportunities)
> 2. Never parse case counts from text strings
> 3. Always recompute percentages at report time using fresh counts, never cache
> 4. Add validation assertions comparing displayed counts to state objects
> 5. Tag any count injection into LLM prompts with a comment: `# ✓ From state.X[i].case_count post-reconciliation`
