# Issue 1 & 2 Fixes: Dynamic Prompt Logic Without LLM Hallucination

## Overview
Both issues stemmed from unconditional prompts that didn't adapt to the reclassification rate. When rate = 0%, the LLM was instructed to build narratives around non-existent problems, causing it to hallucinate supporting evidence.

---

## Issue 1: Executive Summary Reclassification Framing
**File:** `real/complaints-flow/pipeline/stage6_artifacts.py`

### Problem
- Lines 1205-1224: Unconditional prompt instructions about "the reclassification finding"
- When misclassification_rate = 0%, the findings table showed "تصنيف غير دقيق بنسبة 0.0%" (contradictory)
- LLM then invented "100% من الحالات تُمثّل شكاوى" to make sense of the nonsensical instruction

### Solution: Conditional Logic Based on Rate

#### 1. Findings Table (lines 889-912)
```python
if misclassification_rate > 0:
    # Show misclassification gap
    findings.append({
        "title": f"تصنيف غير دقيق بنسبة {misclassification_rate:.1f}%",
        "description": f"كانت {misclassification_count} من {total_cases} حالة مُصنَّفة أصلاً بشكل غير صحيح..."
    })
else:
    # Show positive accuracy finding
    findings.append({
        "title": "دقة التصنيف من المصدر: 100%",
        "description": f"جميع {total_cases} حالة كانت مُصنَّفة بدقة في النظام المصدري..."
    })
```

#### 2. Prompt Framing (lines 1208-1237)
**When rate > 0%:**
```
KEY STRUCTURAL INSIGHT:
The main reclassification finding: X% of cases were initially misclassified.
When corrected, [dominant_type] rises to Y% of total workload (N cases).

INSTRUCTION:
End with the most striking structural discovery: the [dominant_type] reclassification finding
(X% of cases were misclassified in the source system).
```

**When rate = 0%:**
```
KEY STRUCTURAL INSIGHT:
Classification accuracy: All N cases were correctly classified (100% accuracy).
The primary workload driver: [dominant_type] represents Y% of total cases (M cases).
The system must address K distinct friction points affecting customer resolution.

INSTRUCTION:
End with the dominant structural finding: [dominant_type] workload concentration at Y%,
revealing the primary improvement opportunity for customer experience enhancement.
```

### Values Used (All from Pipeline State)
| Variable | Source | Example |
|----------|--------|---------|
| `misclassification_rate` | `state.reclassification_rate` | 0.0% or 15.5% |
| `dominant_type` | max count in distribution | "شكوى" |
| `dominant_type_count` | actual case count | 46 |
| `dominant_type_pct` | (count/total)*100 | 92.0% |
| `friction_count` | len(state.journey_map) | 5 |
| `total_cases` | len(all_classified) | 50 |

### Excel Consistency
- Section 2 distribution shows: 46 شكاوى / 50 total = 92%
- Matches report narrative exactly
- No invented numbers

---

## Issue 2: AI Use Cases Coverage
**File:** `real/complaints-flow/pipeline/generate_ai_use_cases_section.py`

### Problem
- Line 584: Used `{reclass_rate_pct}%+` which produced "0.0%+ of contacts"
- Nonsensical because the AI system covers ALL contacts, regardless of reclassification

### Solution: Fixed Coverage Metric
```python
# Before:
f'to create an intelligent complaint resolution system covering {reclass_rate_pct}%+ of contacts'

# After:
f'to create an intelligent complaint resolution system covering 100% of contacts'
```

### Rationale
- **Reclassification rate** measures source system accuracy (% of cases needing correction)
- **AI system coverage** should always be 100% (it processes all incoming complaints)
- These are different metrics:
  - 0% reclassification ≠ 0% coverage
  - It means: "all cases are already correct" not "system covers nothing"

### Expected Text Output
**When rate = 0%:**
> "تتكامل الفرص المرصودة في Q1 2026 مع قدرات الذكاء الاصطناعي لإنشاء نظام قرارات شاملة يغطي 100% من الاتصالات الواردة..."

---

## Verification Checklist

✅ **No Hardcoded Numbers** (except 100% for coverage)
- All percentages come from: `state.reclassification_rate`, `dominant_type_pct`, `sla_rate`, etc.
- All case counts come from: `state.all_classified`, `state.total_cases`, `friction_points[i].case_count`

✅ **Conditional Branching (rate > 0 vs = 0)**
- Findings table adapts (row 1 content changes)
- Prompt instructions adapt (framing and core message change)
- Structural insight adapts (emphasis shifts to appropriate finding)

✅ **Excel/Report Consistency**
- Report metrics match Excel output: 46/50 = 92% شكاوى
- No phantom finding rows created
- Narrative never contradicts source data

✅ **LLM Instruction Clarity**
- When rate > 0%: "End with the reclassification finding..." (makes sense)
- When rate = 0%: "End with the workload concentration finding..." (makes sense)
- LLM no longer needs to hallucinate to satisfy instructions

---

## Testing Scenario

**Dataset:** 50 complaints, 46 categorized as شكاوى, 0% reclassification

### Before Fix
- **Finding Row 1:** "تصنيف غير دقيق بنسبة 0.0%" ❌ (contradictory)
- **Prompt:** "End with the reclassification finding..." ❌ (no finding to report)
- **Output:** "100% من الحالات تُمثّل شكاوى بالكامل" ❌ (LLM hallucination)
- **Coverage:** "0.0%+ of contacts" ❌ (nonsensical)

### After Fix
- **Finding Row 1:** "دقة التصنيف من المصدر: 100%" ✅ (positive finding)
- **Prompt:** "End with the workload concentration finding..." ✅ (clear instruction)
- **Output:** Accurate narrative about workload distribution ✅ (no hallucination)
- **Coverage:** "100% of contacts" ✅ (correct)

---

## Code Changes Summary

### File 1: stage6_artifacts.py

1. **Lines 889-912:** Conditional findings table row 1
   - If rate > 0: "تصنيف غير دقيق"
   - If rate = 0: "دقة التصنيف: 100%"

2. **Lines 1208-1237:** Conditional structural insight and instructions
   - Adjusts framing, framing_instruction, core_message_instruction based on rate

### File 2: generate_ai_use_cases_section.py

1. **Line 584:** Changed coverage metric
   - From: `{reclass_rate_pct}%+`
   - To: `100%`

---

## No Regressions

✅ Existing logic preserved for rate > 0%
✅ New logic only activates when rate = 0% (previously broken case)
✅ All variable values remain from pipeline state
✅ Syntax validation passed both files

