# Development Guide for Fujairah Pulse AI Platform

## Architecture Overview

This project uses a **dual-implementation strategy** to maintain a stable demo version while developing the full agentic AI system in parallel.

### Two Branches, Two Implementations

- **`main` branch**: Contains the demo version with simulated outputs. This is the stable, production-ready interface.
- **`real` branch**: Contains the full agentic AI implementation. Development happens here without affecting the demo.

### Separation of Concerns

The codebase is organized to clearly separate **UI logic** from **analysis logic**, with analysis further organized by implementation:

```
sim-fujairah-inquiries-ai/
├── app.py                          # UI layer (Streamlit)
├── report_display.py               # Backward-compatible wrapper (legacy)
├── report_extractor.py             # Backward-compatible wrapper (legacy)
├── analysis/                       # Analysis logic layer (refactored)
│   ├── __init__.py                # Re-exports from subfolders
│   ├── shared/                    # Shared components (base + display)
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract Analyzer interface
│   │   └── dynamic_display.py     # Dynamic report display
│   ├── demo/                      # Demo analyzer + extraction utilities
│   │   ├── __init__.py
│   │   ├── demo.py                # DemoAnalyzer (simulated - uses extraction)
│   │   ├── adaptive_extractor.py  # Report extraction with caching
│   │   └── report_structure_detector.py  # Auto-detects report structure
│   ├── real/                      # Real analyzer implementation
│   │   ├── __init__.py
│   │   └── real.py                # RealAnalyzer (with AI agents - TODO)
│   └── legacy/                    # Legacy modules (backward compatibility)
│       ├── __init__.py
│       ├── report_display.py      # Old display logic
│       └── report_extractor.py    # Old extraction logic
├── docs/                           # Documentation (consolidated)
│   ├── README.md
│   ├── ADAPTIVE_SYSTEM_SUMMARY.md
│   ├── DETECTION_METHOD.md
│   ├── HIERARCHICAL_IMPLEMENTATION.md
│   ├── QUICK_REFERENCE.md
│   └── WORKFLOW.md
├── chart_parser.py                # Chart parsing utilities
├── outputs/
│   └── cache/                     # JSON cache for extracted reports
└── .env                           # APP_MODE configuration
```

## Adaptive Report System (New)

The system now features **automatic structure detection** that works with any Word report without hardcoding.

### Key Features

1. **Auto-Detection**: Automatically detects sections from Word headings
2. **Smart Table Assignment**: Tables are assigned to sections based on proximity
3. **JSON Caching**: Extracted structures are cached for fast subsequent loads
4. **Dynamic Display**: UI adapts to whatever structure is detected
5. **Automatic Cache Usage**: Display automatically uses cached JSON if available

### Quick Start

```python
from analysis import DynamicReportDisplay, AdaptiveReportExtractor

# Extract report (uses cache if available)
extractor = AdaptiveReportExtractor()
report = extractor.extract_report("outputs/your_report.docx")

# Display report dynamically
display = DynamicReportDisplay(lang='ar')
display.display_report("outputs/your_report.docx")  # Uses cache automatically
```

See `docs/ADAPTIVE_SYSTEM_SUMMARY.md` and `docs/README.md` for full documentation.

## How It Works

### The Analyzer Interface (Analysis Layer)

All analyzer implementations inherit from `analysis/shared/base.py:Analyzer`, which defines three methods. The demo analyzer uses the extraction utilities from `analysis/demo/`:

```python
class Analyzer(ABC):
    def analyze(self, uploaded_file) -> Dict[str, Any]:
        """Analyze a file and return report structure."""
    
    def validate_file(self, uploaded_file) -> tuple[bool, str]:
        """Validate file format and size."""
    
    def get_processing_stages(self) -> list:
        """Return processing stages for progress display."""
```

### Demo vs Real Mode (APP_MODE)

The `app.py` file loads an environment variable `APP_MODE` to select which analyzer to use:

- `APP_MODE=demo` → loads `DemoAnalyzer` (from `analysis/demo/demo.py`)
- `APP_MODE=real` → loads `RealAnalyzer` (from `analysis/real/real.py`)

The UI calls the analyzer through the abstract interface, so it doesn't need to know which implementation is running.

### Environment Files

Use `.env` files to set the mode when running:

- **`.env.demo`**: Sets `APP_MODE=demo` for the stable version (main branch)
- **`.env.real`**: Sets `APP_MODE=real` for the development version (real branch)
- **`.env.example`**: Template showing available options

## Workflow: Main vs Real Branch

### On `main` Branch (Demo Version)

1. UI improvements and bug fixes go here
2. All analysis is simulated with pre-built reports
3. Use `make demo` or `cp .env.demo .env && streamlit run app.py`
4. Commit when the demo UI is finalized

### On `real` Branch (Development)

1. Implement the full agentic AI system in `analysis/real.py`
2. UI changes from `main` can be merged in (they'll use the real analyzer)
3. Use `make real` or `cp .env.real .env && streamlit run app.py`
4. Push to `real` branch when features are complete

### Merging UI Changes

When UI improvements are made on `main`, they can be merged into `real`:

```bash
# On real branch
git merge main
```

Since the UI layer (`app.py`, `report_display.py`) is separate from the analyzer, merges are usually clean.

## For Claude (Editing Guidelines)

When you're asked to work on this codebase, **always ask which version I should edit** if it's ambiguous:

> "Which version should I edit — **demo** (main branch) or **real** (real branch development)?"

### Decision Tree

- **Edit demo** if the request involves:
  - UI improvements or bug fixes
  - Changes to how the interface looks/works
  - Modifications to report display
  
- **Edit real** if the request involves:
  - Implementing the agentic AI analysis
  - Adding Claude API integration
  - Building analysis agents
  - Making demo/real analyzer more robust

- **Edit both** if the request involves:
  - Updating the abstract `Analyzer` interface
  - Adding new processing stages
  - Changing file validation logic

## Running the App

### Demo Mode (Simulated)

```bash
make demo
# or
cp .env.demo .env
streamlit run app.py
```

Opens at `http://localhost:8501` with pre-built report simulation.

### Real Mode (Development)

```bash
make real
# or
cp .env.real .env
streamlit run app.py
```

Opens at `http://localhost:8501` but will fail until the `RealAnalyzer` is implemented.

## Extending the System

### Adding a New Analyzer Type

1. Create a new folder in `analysis/` (e.g., `analysis/experimental/`)
2. Create `analysis/experimental/__init__.py` that exports your analyzer
3. Create `analysis/experimental/experimental.py` with your implementation
4. Inherit from `Analyzer` in `analysis/shared/base.py`
5. Implement all abstract methods
6. Update `analysis/__init__.py` to import and export it
7. Add the mode to `app.py:get_analyzer()`:
   ```python
   if APP_MODE == 'experimental':
       return ExperimentalAnalyzer()
   ```
8. Create `.env.experimental` file
9. Update the Makefile with a `make experimental` target

### Improving the Demo Analyzer

Edit `analysis/demo/demo.py`:
- Adjust processing stages
- Improve the report loading logic
- Add more realistic simulation

The demo analyzer uses extraction utilities from `analysis/demo/`:
- `AdaptiveReportExtractor` - for extracting reports with caching
- `ReportStructureDetector` - for auto-detecting report structure

And display components from `analysis/shared/`:
- `DynamicReportDisplay` - for displaying extracted reports (automatically uses cache)

### Implementing the Real Analyzer

Edit `analysis/real/real.py`:
- Implement all stub methods
- Add Claude API integration
- Build analysis agents
- Return properly structured report data

The real analyzer will use display components from `analysis/shared/`:
- `DynamicReportDisplay` - for displaying results

Note: The real analyzer will implement its own analysis logic, not use extraction from demo.

## Key Files Explained

### `app.py`

- **Lines 1-15**: Imports and environment setup
- **Lines 1453-1465**: `get_analyzer()` function that selects the right analyzer
- **Lines 1467-1475**: Updated `validate_file()` that delegates to analyzer
- **Lines 1531-1562**: New `process_with_analyzer()` that handles file processing
- Calls `display_report_tabs()` which automatically uses cached JSON if available
- Rest: Unchanged UI/Streamlit code

### Root-level backward compatibility wrappers

- `report_display.py` - Delegates to `analysis.legacy.report_display`
- `report_extractor.py` - Delegates to `analysis.legacy.report_extractor`
- Maintained for existing code that imports from root level

### `analysis/__init__.py`

- Main entry point for the analysis module
- Re-exports all public classes from subfolders
- Maintains backward compatibility by exporting everything
- Imports extraction utilities from real/ (not shared/)

### `analysis/shared/base.py`

- Abstract base class defining the analyzer interface
- All implementations must inherit from `Analyzer` and provide the three abstract methods
- Keep this stable; new methods should be added carefully

### `analysis/shared/dynamic_display.py`

- Dynamically displays any report structure without hardcoding
- Creates tabs based on detected sections
- Renders tables and charts
- **Automatically uses cached JSON** from `analysis/demo/adaptive_extractor.py`
- Used by the UI layer for display

### `analysis/demo/adaptive_extractor.py`

- Extracts report structure from Word documents with caching
- Auto-detects sections using `ReportStructureDetector`
- **Caches extracted data in JSON** (`outputs/cache/`) for fast subsequent loads
- Used by demo analyzer and display layer
- Includes extraction utilities (extraction is demo-specific)

### `analysis/demo/report_structure_detector.py`

- Automatically detects report structure (sections, subsections, tables)
- Uses Word heading styles as primary detection method
- Organizes content hierarchically
- Makes the system adaptable to different report formats
- Part of demo extraction utilities

### `analysis/demo/demo.py`

- Simulates file processing with realistic timing
- Uses `AdaptiveReportExtractor` from `analysis/demo/` to load pre-built reports
- Extraction uses cache automatically when available
- Good reference for what a complete implementation looks like

### `analysis/real/real.py`

- Scaffold with TODO comments
- Stub methods that will be implemented on the real branch
- Shows the expected structure for the full agentic AI implementation
- Will use its own analysis logic (not extraction-based)

### `analysis/legacy/` folder

- `report_display.py` - Old display logic (delegates to shared.dynamic_display)
- `report_extractor.py` - Old extraction logic (delegates to real.adaptive_extractor)
- Kept for backward compatibility

## How the Demo Works

1. **User uploads file** → `app.py` calls `DemoAnalyzer`
2. **DemoAnalyzer** simulates processing with `process_with_analyzer()`
3. **After simulation**, `display_report_tabs()` is called
4. **display_report_tabs()** uses `DynamicReportDisplay` to show the report
5. **DynamicReportDisplay** calls `AdaptiveReportExtractor.extract_report()` from `analysis/demo/`
6. **Extractor checks cache** - if JSON exists in `outputs/cache/`, loads from cache (instant!)
7. **If no cache**, extracts from Word document and creates cache
8. **Display renders** extracted structure with sections, tables, and charts

The cached JSON file is automatically reused on subsequent views of the same report.

## Caching in Action

- **First load**: Extracts from Word → creates `outputs/cache/[hash].json` → displays
- **Subsequent loads**: Uses `outputs/cache/[hash].json` → displays instantly
- **Force refresh**: Call `extractor.extract_report(path, force_refresh=True)` to bypass cache

## Extraction Location

All extraction utilities are in `analysis/demo/` because:
- They're used by the demo analyzer for simulated processing
- They enable the demo to display pre-built reports quickly using cached JSON
- The real analyzer will implement its own AI-based analysis (not extraction)

## Troubleshooting

### "Module 'analysis' not found"

Make sure `analysis/__init__.py` exists and is properly formatted.

### "RealAnalyzer not implemented"

This is expected on the demo branch. Switch to real mode to test real analyzer development.

### ".env file not being loaded"

Ensure `python-dotenv` is installed: `pip install python-dotenv`

### "Report file not found" (Demo mode)

The demo analyzer expects a pre-built Word report at:
- `outputs/تقرير تحليل استفسارات المتعاملين.docx` (without trailing space)
- `outputs/تقرير تحليل استفسارات المتعاملين .docx` (with trailing space)

Check that one of these files exists.

### "Cache not being used"

The cache is automatically created and used. Check `outputs/cache/` for JSON files:
```bash
ls -la outputs/cache/
```

To verify extraction used the cache, run the extraction code twice and compare timings—the second run should be instant.

## Notes for Future Development

- The abstract interface (`Analyzer`) should remain stable
- UI improvements can happen independently on `main`
- Real analyzer development can proceed independently on `real`
- When switching between branches, `make demo` or `make real` will set up the right environment
- All documentation has been consolidated in `docs/` folder
- Extraction logic is in `analysis/demo/` (used for simulated demo processing)
- Demo automatically uses cached JSON for fast display
- Real analyzer will implement its own AI-based analysis (not use demo extraction)
