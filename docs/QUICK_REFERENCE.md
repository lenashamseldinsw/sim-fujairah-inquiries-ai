# Quick Reference: Adaptive Report System

## For Users

### Viewing a Report

The system automatically detects structure and caches results:

```python
# In Streamlit app (already integrated)
from report_display import display_report_tabs
display_report_tabs(lang='ar')
```

### Working with Different Reports

Just change the file path:

```python
from analysis import DynamicReportDisplay

display = DynamicReportDisplay(lang='ar')
display.display_report("inquiries-output/new_report.docx")
```

## For Developers

### Basic Extraction

```python
from analysis import AdaptiveReportExtractor

extractor = AdaptiveReportExtractor()

# Auto-detects structure + caches as JSON
report = extractor.extract_report("path/to/report.docx")

# Access data
for section in report['sections']:
    print(f"Section: {section['title']}")
    print(f"Tables: {len(section['tables'])}")
```

### Cache Management

```python
# List cached reports
cached = extractor.list_cached_reports()

# Clear specific cache
extractor.clear_cache("report.docx")

# Clear all cache
extractor.clear_cache()

# Force refresh (bypass cache)
report = extractor.extract_report("report.docx", force_refresh=True)
```

### Custom Structure Detection

```python
from analysis import ReportStructureDetector

detector = ReportStructureDetector("path/to/report.docx")
structure = detector.detect_structure()

# Access detected structure
for section in structure['sections']:
    print(f"{section['title']} - Level {section['level']}")
```

## Testing

```bash
# Run comprehensive test
python test_adaptive_system.py

# Test with cache cleared
python test_adaptive_system.py --clear

# Test specific report
python test_adaptive_system.py --report inquiries-output/your_report.docx
```

## Common Tasks

### Add New Heading Pattern

Edit `analysis/report_structure_detector.py`:

```python
def _is_heading(self, para) -> bool:
    heading_indicators = [
        # Add your pattern here
        r'(Your custom pattern)',
    ]
```

### Change Cache Location

Edit `analysis/adaptive_extractor.py`:

```python
class AdaptiveReportExtractor:
    CACHE_DIR = Path("your/custom/path")
```

### Filter Displayed Sections

Edit `analysis/dynamic_display.py`:

```python
# In display_report method
main_sections = [
    sec for sec in sections 
    if your_custom_filter(sec)
]
```

## File Locations

- **Core System**: `analysis/`
- **Cache**: `inquiries-output/cache/`
- **Documentation**: `analysis/README.md`, `ADAPTIVE_SYSTEM_SUMMARY.md`
- **Test Script**: `test_adaptive_system.py`
- **Legacy (backward compat)**: `report_extractor.py`, `report_display.py`

## Performance

- **First run**: ~2-3 seconds (extraction + caching)
- **Cached runs**: ~0.1-0.2 seconds (load JSON)
- **Cache size**: ~50-200 KB per report

## Troubleshooting

### Sections not detected
- Check Word heading styles
- Add custom patterns to `_is_heading()`
- Verify font size ≥14pt for headings

### Tables in wrong section
- Tables assigned by proximity
- Check document structure
- Adjust `_find_table_position()` if needed

### Cache not updating
- Modification time drives invalidation
- Use `force_refresh=True`
- Or clear cache manually

### Charts not showing
- Charts extracted by `chart_parser.py`
- Check if charts exist (not just images)
- Review extraction in test output

## Need Help?

1. Read `analysis/README.md` - comprehensive guide
2. Read `ADAPTIVE_SYSTEM_SUMMARY.md` - implementation details
3. Run `python test_adaptive_system.py` - verify system
4. Check cache: `extractor.list_cached_reports()`
