# Detection Method: Word Heading Styles (Not Font Size)

## How Detection Works Now

The system uses a **hierarchical detection method** with Word styles as the primary source:

### Priority Order

1. **PRIMARY: Word Heading Styles** (Most Reliable)
   - `Heading 1` → Main section
   - `Heading 2` or `Heading 3` → Subsection

2. **FALLBACK: Pattern Matching**
   - Arabic ordinals with colon (أولاً:, ثانياً:) → Main section
   - Number format (2.1, 3.2, etc.) → Subsection

3. **TOC Filtering**
   - Font size < 11pt → Excluded (filters out table of contents)

## Why This Approach is Better

### ✅ Dynamic
- Works with any Word document that uses standard heading styles
- No hardcoded font sizes
- Adapts to different formatting

### ✅ Reliable
- Word heading styles are structural, not cosmetic
- Authors can change fonts without breaking detection
- Follows document structure intent

### ✅ Standard
- Uses Microsoft Word's built-in heading system
- Compatible with any properly formatted Word document
- Works with document navigation/outline

## How to Structure a Report for Auto-Detection

### For Authors

To ensure your report is automatically detected correctly:

1. **Main Sections**: Apply `Heading 1` style
   ```
   أولاً: Your Section Title
   ```

2. **Subsections**: Apply `Heading 2` style
   ```
   2.1 Your Subsection Title
   ```

3. **Numbering**: Use standard format
   - Main: أولاً, ثانياً, ثالثاً, etc.
   - Sub: 2.1, 2.2, 3.1, 3.2, etc.

### What Gets Excluded

- Table of contents (font < 11pt)
- Document title pages
- Headers/footers
- Text without heading styles or ordinal patterns

## Code Implementation

```python
def _classify_heading(self, para) -> str:
    # Skip TOC entries (small font)
    if font_size < 11:
        return None
    
    # PRIMARY: Check Word styles
    if 'Heading 1' in para.style.name:
        return 'main'
    elif 'Heading 2' in para.style.name:
        return 'sub'
    
    # FALLBACK: Pattern matching
    if matches_arabic_ordinal_pattern(text):
        return 'main'
    if matches_number_pattern(text):
        return 'sub'
    
    return None
```

## Benefits

### For Different Report Formats

The system will work with:
- ✅ Reports with different fonts
- ✅ Reports with different font sizes
- ✅ Reports with custom themes
- ✅ Reports with varying spacing
- ✅ Reports in different languages (as long as heading styles are used)

### For Maintenance

- ✅ No need to update code when report styling changes
- ✅ Works with any properly formatted Word document
- ✅ Easy to extend with more patterns
- ✅ Clear separation between structure and presentation

## Testing with Different Reports

To test with a new report:

1. **Check heading styles in Word**:
   - View → Navigation Pane
   - Should show document outline
   - Main sections at level 1
   - Subsections at level 2

2. **Run the extraction**:
   ```python
   from analysis import AdaptiveReportExtractor
   
   extractor = AdaptiveReportExtractor()
   report = extractor.extract_report("new_report.docx")
   
   # Should detect structure based on heading styles
   ```

3. **Verify results**:
   - 9 main sections (or as many as in your document)
   - Subsections nested correctly
   - Tables assigned appropriately

## Fallback Behavior

If heading styles are not applied:

1. System falls back to pattern matching
2. Looks for Arabic ordinals (أولاً:, ثانياً:)
3. Looks for numbered format (2.1, 3.2)
4. Excludes TOC based on font size

This ensures the system works even with inconsistently formatted documents.

## Summary

✅ **Primary method**: Word heading styles (Heading 1, Heading 2)  
✅ **Fallback method**: Pattern matching (ordinals, numbers)  
✅ **TOC filtering**: Font size < 11pt excluded  
✅ **Dynamic**: Works with any properly structured document  
✅ **Reliable**: Not dependent on specific font sizes or styling  

The system now detects structure based on **document organization** (heading styles), not **visual appearance** (font sizes).
