# Adaptive Report Extraction System

This directory contains the refactored, adaptive report extraction and display system that automatically detects report structure without hardcoding.

## Architecture Overview

```
analysis/
├── base.py                      # Abstract Analyzer interface
├── demo.py                      # Demo analyzer (uses adaptive extraction)
├── real.py                      # Real analyzer (stub for real branch)
├── report_structure_detector.py # Auto-detects sections and structure
├── adaptive_extractor.py        # Extraction with caching
├── dynamic_display.py           # Dynamic display based on structure
└── __init__.py                  # Module exports
```

## Key Features

### 1. Automatic Structure Detection

The `ReportStructureDetector` class automatically detects:
- **Sections** by finding heading paragraphs (using style, formatting, and patterns)
- **Tables** and their positions in the document
- **Charts** and their positions
- **Relationships** between tables/charts and sections (proximity-based assignment)

### 2. Caching System

The `AdaptiveReportExtractor` class provides:
- **JSON caching** of extracted report structures
- **Cache key generation** based on filename + modification time + size
- **Automatic cache invalidation** when source file changes
- **Cache management** functions (clear, list cached reports)

Cache files are stored in: `inquiries-output/cache/`

### 3. Dynamic Display

The `DynamicReportDisplay` class:
- **Generates tabs dynamically** based on detected sections
- **Displays tables** regardless of their structure
- **Shows content** from sections
- **Renders charts** using Chart.js
- **Supports RTL** (right-to-left) for Arabic content

## Usage

### Basic Usage

```python
from analysis import AdaptiveReportExtractor, DynamicReportDisplay

# Extract report (with caching)
extractor = AdaptiveReportExtractor()
report = extractor.extract_report("path/to/report.docx")

# Display in Streamlit
display = DynamicReportDisplay(lang='ar')
display.display_report("path/to/report.docx")
```

### Forcing Refresh

```python
# Force re-extraction (bypass cache)
report = extractor.extract_report("path/to/report.docx", force_refresh=True)
```

### Cache Management

```python
# List all cached reports
cached = extractor.list_cached_reports()
for cache_info in cached:
    print(f"{cache_info['document_name']} - {cache_info['sections_count']} sections")

# Clear cache for specific document
extractor.clear_cache("report.docx")

# Clear all cache
extractor.clear_cache()
```

### Backward Compatibility

The old API still works:

```python
# Old code still works
from report_extractor import extract_full_report
from report_display import display_report_tabs

report = extract_full_report("path/to/report.docx")  # Now uses adaptive extraction
display_report_tabs(lang='ar')  # Now uses dynamic display
```

## How It Works

### 1. Section Detection

The detector finds sections by:

1. **Checking paragraph styles** for "Heading" styles
2. **Analyzing formatting** (bold + large font = heading)
3. **Matching patterns** against common Arabic/English heading patterns
4. **Assigning levels** based on style or font size

Example patterns matched:
- التحليل / تحليل / Analysis
- الملخص / ملخص / Summary
- الخلاصة / Conclusion
- حالات الاستخدام / Use Cases

### 2. Table Assignment

Tables are assigned to sections based on **proximity**:

1. Find table position in document
2. Find which section the table falls between
3. Assign table to that section
4. Extract table data (columns, rows)

### 3. Caching Logic

```
User uploads file
    ↓
Generate cache key (filename + mtime + size)
    ↓
Check if cache exists
    ↓
Yes → Load from JSON cache (fast)
    ↓
No → Extract structure + Save to cache
```

Cache key ensures:
- Different files have different caches
- Modified files trigger re-extraction
- Same file (unchanged) uses cache

### 4. Display Generation

```
Load report structure
    ↓
Extract sections list
    ↓
Generate tab titles dynamically
    ↓
For each section:
    - Show content
    - Show tables
    - Show charts
```

## Adding a New Report

To process a different report:

1. **Place the Word document** in `inquiries-output/` directory
2. **Update the path** in your code:

```python
display = DynamicReportDisplay(lang='ar')
display.display_report("inquiries-output/your_new_report.docx")
```

3. **Done!** The system will automatically:
   - Detect sections
   - Extract tables
   - Assign tables to sections
   - Generate display
   - Cache results

No code changes needed!

## Configuration

### Heading Detection Patterns

To add more heading patterns, edit `ReportStructureDetector.HEADING_PATTERNS`:

```python
HEADING_PATTERNS = [
    r'(التحليل|تحليل|Analysis)',
    r'(Your custom pattern)',
    # Add more...
]
```

### Cache Directory

To change cache location, edit `AdaptiveReportExtractor.CACHE_DIR`:

```python
CACHE_DIR = Path("inquiries-output/cache")  # Change as needed
```

## Troubleshooting

### Problem: Sections not detected

**Solution**: Check if your headings use proper styles or formatting:
- Use "Heading 1", "Heading 2", etc. styles in Word
- Or make headings bold with larger font (>12pt)
- Or add pattern to `HEADING_PATTERNS`

### Problem: Tables assigned to wrong section

**Solution**: The assignment uses proximity. Ensure:
- Tables appear after section headings
- No large gaps between section heading and tables
- Or manually adjust `_find_table_position()` logic

### Problem: Cache not updating

**Solution**:
- File modification time drives cache invalidation
- Force refresh: `extract_report(path, force_refresh=True)`
- Or clear cache: `extractor.clear_cache()`

### Problem: Charts not showing

**Solution**:
- Charts are extracted by `chart_parser.py`
- Currently shown in first section or sections without tables
- Check that charts exist in Word document (not just images)

## Migration from Old System

The old hardcoded system used:
- Fixed 8 sections in `report_extractor.py`
- Hardcoded table mapping (table index → section)
- Fixed tab titles in `report_display.py`

The new adaptive system:
- ✅ Auto-detects any number of sections
- ✅ Auto-assigns tables based on proximity
- ✅ Generates tabs dynamically
- ✅ Caches results for performance
- ✅ Works with any Word report structure

Old code still works (backward compatible), but internally uses the new system.

## Performance

### First Run (No Cache)
- ~5-10 seconds for typical report
- Includes structure detection + table extraction + chart parsing

### Subsequent Runs (With Cache)
- ~0.1-0.5 seconds
- Just loads JSON from cache

### Cache Size
- Typical report: 50-200 KB JSON
- Scales with number of tables/sections

## Future Improvements

Potential enhancements:
1. **Machine learning** for better section detection
2. **OCR integration** for scanned PDFs
3. **Multi-document** report generation
4. **Export to other formats** (HTML, Markdown, etc.)
5. **Section merging/splitting** UI
6. **Custom templates** for different report types

## Files Reference

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `report_structure_detector.py` | Auto-detects structure | `ReportStructureDetector` |
| `adaptive_extractor.py` | Extraction + caching | `AdaptiveReportExtractor` |
| `dynamic_display.py` | Dynamic UI display | `DynamicReportDisplay` |
| `base.py` | Abstract interface | `Analyzer` |
| `demo.py` | Demo implementation | `DemoAnalyzer` |

## Legacy Files

These files are kept for backward compatibility but delegate to new system:
- `report_extractor.py` → now uses `adaptive_extractor.py`
- `report_display.py` → now uses `dynamic_display.py`

New code should import from `analysis/` module directly.
