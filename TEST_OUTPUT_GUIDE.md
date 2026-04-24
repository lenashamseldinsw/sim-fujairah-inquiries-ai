# Test Output Guide

## What the Test Does

`test_report_sections.py` runs a complete pipeline test with 50 random rows:

1. **Stage 1**: Schema validation (checks data format)
2. **Stage 2**: Rule-based classification (uses predefined rules)
3. **Stage 3**: LLM classification (uses Claude API for accuracy)
4. **Stage 4**: Pattern analysis (identifies customer journey issues)
5. **Stage 5**: Gap analysis (compares against guidebook)
6. **Stage 6**: Report generation (creates executive summary & methodology)

## Output Files Generated

### In `pipeline-test-output/`

#### Report Sections (NEW - saved by updated test)
- **`report_sections_ar_<timestamp>.json`** — Arabic report structure
  - Executive summary section
  - Methodology section with sources table and subsections
  
- **`report_sections_en_<timestamp>.json`** — English report structure
  - Same sections as Arabic but in English
  - Properly formatted tables with list rows (not dict)

#### Full Report
- **`report_full_<timestamp>.json`** — Complete report dictionary
  - Metadata
  - All sections fully formatted for display
  - Ready for Streamlit rendering

#### State Files (for recovery)
- **`pipeline_state/test_report_sections_state.json`** — Current pipeline state
  - All classified cases
  - Patterns and friction points
  - Gap analysis results
  - Report sections (AR & EN)

## Key Validation Points

When test completes, check these in the output JSON files:

### Executive Summary (report_sections_*.json)
```
{
  "executive_summary": {
    "id": "section_...",
    "title": "...",
    "content": "This report presents...",  // ✓ NOT empty, NOT stub
    "tables": [],
    "subsections": [...]  // ✓ May have findings table
  }
}
```

### Methodology Section
```
{
  "methodology": {
    "subsections": [
      {
        "title": "2.1 المصادر المُحلَّلة",  // Sources
        "tables": [
          {
            "columns": ["المصدر", "الطبيعة", "الحجم", "الفترة"],
            "rows": [                           // ✓ Should be LIST
              {"المصدر": "...", ...},
              {"المصدر": "...", ...}
            ],
            "row_count": 2                      // ✓ Should be 2
          }
        ]
      },
      // ... more subsections
    ]
  }
}
```

## Diagnostic Output

Watch for these in console output to confirm API key is flowing:

```
[GenSections] api_key present: True          ← ✓ API key reached stage 6
[GenSections] api_key length: 108            ← ✓ Valid key (108 chars)
[ExecSummary] Calling API with model claude-sonnet-4-6
[ExecSummary] total_cases=50, reclassified=...
[Methodology] Calling API, prompt length: ...
```

## Validation Script

After test completes, run:
```bash
python validate_output.py
```

This checks:
- ✅ Report sections files exist and are readable
- ✅ Executive summary has real content (not stubs)
- ✅ Methodology sources table has rows as LIST (not dict)
- ✅ Both AR and EN versions are properly formatted

## Common Issues & Solutions

### Issue: Empty content in executive summary
**Cause**: LLM call failed, fallback activated  
**Check**: Look for `[GenSections] api_key present: False`  
**Solution**: Verify API key in `~/.streamlit/secrets.toml`

### Issue: Sources table has dict rows instead of list
**Cause**: Test script didn't convert language-specific format  
**Check**: Look for `"rows": {"columns_ar": ...}` instead of `"rows": [{...}, {...}]`  
**Solution**: Already fixed in updated test_report_sections.py (uses language conversion)

### Issue: Test takes 5-10 minutes
**Expected**: LLM calls for stages 3, 4, 5 take time  
**Normal**: Processing 50 cases with Claude API interactions

## Files to Review

1. **report_sections_ar.json** — Check Arabic structure and table formatting
2. **report_sections_en.json** — Check English structure and table formatting  
3. **validate_output.py** — Run to automatically verify structure

## Success Criteria

✅ Test completes without errors
✅ Both report_sections_ar and report_sections_en generated
✅ Executive summary content is real text (not empty or stub)
✅ Methodology sources table has "rows": [...] (list, not dict)
✅ Both languages have 2 source entries
✅ validate_output.py passes all checks
✅ Console shows [GenSections], [ExecSummary], [Methodology] prints with api_key info
