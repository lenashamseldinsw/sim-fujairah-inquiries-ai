# Development Guide for Fujairah Pulse AI Platform

## Architecture Overview

This project uses a **dual-implementation strategy** to maintain a stable demo version while developing the full agentic AI system in parallel.

### Two Branches, Two Implementations

- **`main` branch**: Contains the demo version with simulated outputs. This is the stable, production-ready interface.
- **`real` branch**: Contains the full agentic AI implementation. Development happens here without affecting the demo.

### Separation of Concerns

The codebase is organized to clearly separate **UI logic** from **analysis logic**:

```
sim-fujairah-inquiries-ai/
├── app.py                      # UI layer (Streamlit) - uses analyzers via interface
├── report_display.py           # Report visualization (UI)
├── analysis/                   # Analysis logic layer
│   ├── __init__.py
│   ├── base.py                # Abstract Analyzer interface
│   ├── demo.py                # DemoAnalyzer (simulated, for main branch)
│   └── real.py                # RealAnalyzer (stub, for real branch)
├── report_extractor.py        # Data extraction utilities
├── chart_parser.py            # Chart parsing utilities
└── .env                       # Loaded by app.py to select APP_MODE
```

## How It Works

### The Analyzer Interface (Analysis Layer)

All analyzer implementations inherit from `analysis/base.py:Analyzer`, which defines three methods:

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

- `APP_MODE=demo` → loads `DemoAnalyzer` (from `analysis/demo.py`)
- `APP_MODE=real` → loads `RealAnalyzer` (from `analysis/real.py`)

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

1. Create a new file in `analysis/` (e.g., `analysis/experimental.py`)
2. Inherit from `Analyzer` in `analysis/base.py`
3. Implement all abstract methods
4. Update `analysis/__init__.py` to export it
5. Add the mode to `app.py:get_analyzer()`:
   ```python
   if APP_MODE == 'experimental':
       return ExperimentalAnalyzer()
   ```
6. Create `.env.experimental` file
7. Update the Makefile with a `make experimental` target

### Improving the Demo Analyzer

Edit `analysis/demo.py`:
- Adjust processing stages
- Improve the report loading logic
- Add more realistic simulation

### Implementing the Real Analyzer

Edit `analysis/real.py`:
- Implement all stub methods
- Add Claude API integration
- Build analysis agents
- Return properly structured report data

## Key Files Explained

### `app.py`

- **Lines 1-15**: Imports and environment setup
- **Lines 1453-1465**: `get_analyzer()` function that selects the right analyzer
- **Lines 1467-1475**: Updated `validate_file()` that delegates to analyzer
- **Lines 1531-1562**: New `process_with_analyzer()` that handles file processing
- Rest: Unchanged UI/Streamlit code

### `analysis/base.py`

- Abstract base class defining the analyzer interface
- All implementations must provide the three abstract methods
- Keep this stable; new methods should be added carefully

### `analysis/demo.py`

- Simulates file processing with realistic timing
- Loads pre-built reports from `outputs/`
- Good reference for what a complete implementation looks like

### `analysis/real.py`

- Scaffold with TODO comments
- Stub methods that will be implemented on the real branch
- Shows the expected structure for the full implementation

## Troubleshooting

### "Module 'analysis' not found"

Make sure `analysis/__init__.py` exists and is properly formatted.

### "RealAnalyzer not implemented"

This is expected on the demo branch. Switch to real mode to test real analyzer development.

### ".env file not being loaded"

Ensure `python-dotenv` is installed: `pip install python-dotenv`

### "Report file not found" (Demo mode)

The demo analyzer expects a pre-built Word report at `outputs/تقرير تحليل استفسارات المتعاملين.docx`. Check that this file exists.

## Notes for Future Development

- The abstract interface (`Analyzer`) should remain stable
- UI improvements can happen independently on `main`
- Real analyzer development can proceed independently on `real`
- When switching between branches, `make demo` or `make real` will set up the right environment
