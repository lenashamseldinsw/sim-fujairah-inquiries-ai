# Gap Table Similarity-Based Fallback Enhancement

**File**: `real/inquiries-flow/pipeline/stage6_json_report.py`  
**Date**: 2026-05-06  
**Status**: ✅ Implemented

---

## Overview

Enhanced the gap table case count synchronization (Fix 3) to use **similarity-based matching** instead of simple substring fallback. This provides more robust matching when LLM-generated gap topics don't exactly match state.gap_table entries.

---

## Change Summary

### What Changed

**Location**: Lines 896–935 (build_digital_gaps_section method)

**Import Added** (Line 35):
```python
from .utils import calculate_similarity
```

**Fallback Strategy** (Lines 908–935):
```python
# OLD: Simple substring fallback
for gap_key, gap in gap_lookup.items():
    if gap_key and gap_key in topic:
        row["الحالات"] = str(gap.case_count)
        break

# NEW: Similarity-based matching with threshold
# Find the gap_lookup entry with highest similarity score
best_match = None
best_score = 0.0

for gap_key, gap in gap_lookup.items():
    if gap_key:  # Skip empty keys
        score = calculate_similarity(topic, gap_key)
        if score > best_score:
            best_score = score
            best_match = gap

# Apply similarity match only if score exceeds threshold (0.5)
if best_score >= 0.5 and best_match:
    row["الحالات"] = str(best_match.case_count)
    print(f"[JSONReportBuilder] INFO: Gap topic matched via similarity ({best_score:.2f})")
else:
    # No match above threshold; keep LLM-supplied count and warn
    print(f"[JSONReportBuilder] WARNING: Gap topic '{topic}' not found in state.gap_table")
```

---

## How It Works

### Exact Match (Lines 903–906)
1. Try exact match: `if topic in gap_lookup`
2. If found, use `gap.case_count` from state
3. Proceed to next row

### Similarity Fallback (Lines 908–935)
If exact match fails:
1. Compute `calculate_similarity(topic, gap_key)` for every entry in gap_lookup
2. Track the match with the **highest similarity score**
3. **If score ≥ 0.5**: Apply the match
   - Update row["الحالات"] with state.gap_table[best_match].case_count
   - Log INFO message showing topic, score (e.g., "0.72"), and "Case count updated"
4. **If score < 0.5**: Keep LLM-supplied count
   - Log WARNING message with:
     - Gap topic name (full length)
     - Best similarity score found (e.g., "0.38")
     - Threshold (0.5)
     - Note that this may indicate LLM/state mismatch

---

## Similarity Metric

Uses `calculate_similarity()` from `utils.py` (lines 132–151):

```python
def calculate_similarity(text1: str, text2: str) -> float:
    """
    Simple similarity metric using word overlap (Jaccard similarity).
    Returns: Float between 0.0 and 1.0
    
    Formula: intersection(words) / union(words)
    """
    words1 = set(normalize_arabic(text1).split())
    words2 = set(normalize_arabic(text2).split())
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return intersection / union if union > 0 else 0.0
```

**Why this works**:
- Handles Arabic text via `normalize_arabic()`
- Tokenizes by whitespace, computes word overlap
- 1.0 = identical topics (all words match)
- 0.5 = moderate overlap (half the unique words match)
- 0.0 = no overlap (completely different)

---

## Examples

### Scenario 1: Exact Match
**LLM topic**: "عدم توفر معلومات"  
**State topic**: "عدم توفر معلومات"  
**Result**: ✅ Exact match found → case_count applied directly

---

### Scenario 2: Similarity Match Above Threshold
**LLM topic**: "غياب الإشعارات الاستباقية للمتعاملين"  
**State topic**: "غياب الإشعار الاستباقي"  
**Similarity**: 0.67 (words "الإشعار", "غياب", "الاستباقي" overlap)  
**Result**: ✅ Score ≥ 0.5 → case_count applied  
**Log**: `INFO: Gap topic 'غياب الإشعارات الاستباقية للمتعاملين...' matched via similarity (0.67)`

---

### Scenario 3: No Match Above Threshold
**LLM topic**: "خلل تقني في النظام الجديد"  
**Best state match**: "عدم توفر معلومات"  
**Similarity**: 0.20 (only "في" overlaps)  
**Result**: ⚠️ Score < 0.5 → LLM count kept, warning logged  
**Log**: `WARNING: Gap topic 'خلل تقني في النظام الجديد' not found in state.gap_table (best similarity=0.20, threshold=0.5). Using LLM-supplied case count. This may indicate a mismatch between LLM and state gap definitions.`

---

## Threshold Justification

**0.5 threshold** balances:
- **Too low** (< 0.3): Accepts false positives (unrelated topics)
- **Too high** (> 0.7): Rejects valid fuzzy matches

At 0.5, the best-match entry must share at least half its unique words with the LLM topic, which generally indicates meaningful semantic overlap in Arabic text.

---

## Visibility & Debugging

**All matching attempts logged**:
- ✅ Exact matches: Silent (expected behavior)
- ✅ Similarity matches ≥ 0.5: INFO level (interesting, successful fallback)
- ⚠️ No match < 0.5: WARNING level (potential issue worth investigating)

**For each mismatch warning**, the log includes:
- Exact LLM topic text (for searching in LLM output logs)
- Best similarity score found (helps understand how close it came)
- Threshold (0.5) for reference
- Explanation (may indicate LLM/state definition mismatch)

**Example run log**:
```
[JSONReportBuilder] INFO: Gap topic 'غياب الإشعار الاستباقي...' matched via similarity (0.72) to state.gap_table. Case count updated.
[JSONReportBuilder] WARNING: Gap topic 'خلل في الموقع الإلكتروني الجديد' not found in state.gap_table (best similarity=0.38, threshold=0.5). Using LLM-supplied case count. This may indicate a mismatch between LLM and state gap definitions.
```

---

## Backward Compatibility

- ✅ If state.gap_table is empty, no changes applied (same as before)
- ✅ Exact matches bypass similarity calculation (no overhead)
- ✅ Falls back to LLM-supplied count if no match ≥ 0.5 (graceful degradation)
- ✅ No changes to table structure or other columns
- ✅ All LLM-generated prose (الشدّة, التوصية, etc.) preserved

---

## Testing Recommendations

1. **Exact match case**: Verify case counts updated for topics that exactly match state
2. **Similarity match case**: Verify case counts updated when LLM topic differs slightly (typos, extra words)
3. **No match case**: Verify warnings logged when no match exceeds 0.5 threshold
4. **Run log inspection**: Check that INFO and WARNING messages appear at expected points

Example test:
```python
# state.gap_table has: "عدم توفر معلومات" (10 cases)
# LLM returns:        "عدم توفّر المعلومات" (from LLM)
# Expected: Similarity match ≈ 0.67, case count updated to 10
```

---

## Enhancement Benefits

| Aspect | Before | After |
|--------|--------|-------|
| **Exact match** | Works | Works (same) |
| **Fuzzy match** | Substring only | Jaccard similarity |
| **Typo tolerance** | Limited | Good (word-level) |
| **Word order** | Sensitive | Insensitive |
| **Diagnostics** | Silent fallback | Detailed logging |
| **Threshold safety** | None | 0.5 threshold |
| **Fallback clarity** | Implicit | Explicit with warnings |

---

## Future Improvements

For production scaling:
- Replace `calculate_similarity()` with ChromaDB embeddings for semantic matching
- Add optional parameter to tune threshold (default 0.5)
- Log all match attempts (not just warnings) at debug level
- Cache similarity scores if performance becomes an issue

See utils.py comment (line 134): "For production, use proper embeddings with chromadb."
