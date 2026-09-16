# Development Guide for Fujairah Pulse AI Platform

## 📋 Documentation Policy

**⚠️ DO NOT CREATE NEW .MD FILES** — All project-level documentation must consolidate into:
- **CLAUDE.md** (this file) - Development guide, architecture, and workflows
- **README.md** - Project overview and navigation
- **demo/README.md** - Demo version setup and features
- **real/README.md** - Real version setup and features
- **MEMORY.md** - Implementation decisions and context (auto-memory system)

**Any notes or documentation needed** should be added to one of these files, not scattered as new .md files. If you find yourself creating a new .md file, it probably belongs in CLAUDE.md, README.md, or one of the folder-specific READMEs instead.

**Why?** Scattered documentation becomes stale, unmaintainable, and hard to find. Consolidation keeps everything in one place.

---

## Architecture Overview

This project uses a **dual-implementation strategy** to maintain a stable demo version while developing the full agentic AI system in parallel.

### Two Branches, Two Implementations

- **`main` branch**: Contains the demo version with simulated outputs. This is the stable, production-ready interface.
- **`real` branch**: Contains the full agentic AI implementation. Development happens here without affecting the demo.

### Folder-Based Separation (Reorganized)

Each implementation (demo and real) is now completely **self-contained** in its own folder:

```
sim-fujairah-inquiries-ai/
├── demo/                           # Demo version (stable, main branch)
│   ├── app.py                     # Demo UI (Streamlit)
│   ├── chart_parser.py            # Chart parsing utilities
│   ├── analysis/
│   │   ├── __init__.py            # Exports demo components
│   │   ├── base.py                # Abstract Analyzer interface
│   │   ├── dynamic_display.py     # Dynamic report display
│   │   ├── demo.py                # DemoAnalyzer (simulated with extraction)
│   │   ├── adaptive_extractor.py  # Report extraction with caching
│   │   └── report_structure_detector.py  # Auto-detects report structure
│   ├── inquiries-output/          # Inquiries reports and cache
│   ├── complaints-output/         # Complaints reports and cache
│   ├── .env                       # Demo environment config
│   └── test_adaptive_system.py    # Test script for extraction
│
├── real/                           # Real version (development, real branch)
│   ├── app.py                     # Single-flow UI (legacy, for backward compatibility)
│   ├── app_inq_comp.py            # UNIFIED UI for both inquiries + complaints flows
│   ├── report_display.py          # Report display handler (supports both flows)
│   ├── core42/                    # Core42 LLM integration, shared by both flows
│   │   ├── settings.py            # Env config, base-URL normalisation, model tiers
│   │   ├── client.py              # Chat-completions client (lazy singleton)
│   │   ├── messages.py            # Core42Client — the Messages-shaped facade
│   │   ├── json_repair.py         # Truncation / fence / <think> repair cascade
│   │   ├── retry.py               # Error classification + 10s floor for 429s
│   │   ├── concurrency.py         # One process-wide in-flight cap
│   │   └── tokens.py              # Per-stage token and cost tracking
│   ├── smoke_core42*.py           # Standalone gateway probes (real API calls)
│   ├── analysis/                  # Thin routing layer (NO analyzer/real.py here)
│   │   ├── __init__.py            # Dynamic loader: set_flow_context / get_analyzer_for_flow / get_display_for_flow
│   │   ├── base.py                # Abstract Analyzer interface
│   │   └── dynamic_display.py     # Shared display base
│   │   # NOTE: RealAnalyzer lives in each flow's analysis/real.py, loaded dynamically
│   ├── inquiries-flow/            # Inquiries pipeline
│   │   ├── analysis/
│   │   │   ├── __init__.py        # Exports inquiries analyzer + display
│   │   │   ├── base.py            # Analyzer interface
│   │   │   ├── real.py            # RealAnalyzer for inquiries (6-stage pipeline)
│   │   │   └── dynamic_display.py # Report display for inquiries
│   │   ├── pipeline/              # 6-stage pipeline orchestrator + stages (llm.py = Core42 shim)
│   │   └── output/                # Generated reports and cache
│   ├── complaints-flow/           # Complaints pipeline
│   │   ├── analysis/
│   │   │   ├── __init__.py        # Exports complaints analyzer + display
│   │   │   ├── base.py            # Analyzer interface
│   │   │   ├── real.py            # RealAnalyzer for complaints (6-stage pipeline)
│   │   │   └── dynamic_display.py # Report display for complaints
│   │   ├── pipeline/              # 6-stage pipeline orchestrator + stages (llm.py = Core42 shim)
│   │   └── output/                # Generated reports and cache
│   ├── inquiries-output/          # Root output folder (backward compatibility)
│   ├── complaints-output/         # Root output folder (backward compatibility)
│   ├── .env                       # Real environment config
│   └── test files...              # Test scripts for each flow
│
├── docs/                           # Documentation (consolidated)
├── Makefile                        # Updated: cd demo/real && streamlit run app.py
├── .env.demo, .env.real, .env.example  # Reference environment files
└── sword_word_builder/             # Shared utility (unchanged)
```

**Why This Structure?**
- Each version can evolve independently without affecting the other
- UI changes in demo don't affect real and vice versa
- Analysis logic is completely separate
- Each folder is runnable: `cd demo && streamlit run app.py`
- Easier to manage dependencies and configurations per version

## Running the Application

### Demo Version (Stable)

The demo version with simulated outputs:

```bash
make demo
# Or manually:
cd demo && streamlit run app.py
```

Opens at `http://localhost:8501` with pre-built reports for both inquiries and complaints flows.

### Real Version - Unified App (Recommended)

The real version with AI-based analysis supporting **both inquiries and complaints** flows:

```bash
cd real && streamlit run app_inq_comp.py
```

**Features:**
- Single landing page with flow selection
- Separate pages for inquiries and complaints analysis
- Unified analyzer routing that loads the correct pipeline
- Both flows generate Word reports, Excel files, and JSON data
- Display integrates with dynamic_report_display.py for both flows

**How it works:**
1. User lands on home page and selects "Inquiries" or "Complaints"
2. App loads the appropriate analyzer from `inquiries-flow/` or `complaints-flow/`
3. File is processed through the 6-stage pipeline
4. Results displayed with dynamic report viewer
5. Download links provided for Word and Excel outputs

### Real Version - Legacy Single Flow (Backward Compatibility)

If you need to run just one flow:

```bash
# Set which flow to run
export APP_MODE=inquiries  # or 'complaints'
cd real && streamlit run app.py
```

**Note:** `app.py` only supports inquiries. Use `app_inq_comp.py` for complaints.

## Core42 Integration (Real Version)

The real pipelines call **Core42**, an OpenAI-compatible gateway, through the
official `openai` SDK with a custom `base_url`. Everything provider-specific
lives in `real/core42/`, shared by both flows; no pipeline stage talks to the SDK
directly.

### Configuration

Credentials are read from `real/.env` first, then from Streamlit secrets
(`.streamlit/secrets.toml` — Streamlit Cloud has no `.env`). `../.env.example`
documents every setting; the ones that matter:

| Variable | What it does |
|---|---|
| `CORE42_API_KEY` | Shared by every endpoint. The app refuses to start without it. |
| `CORE42_BASE_URL` | **No** `/chat/completions` suffix — the SDK appends the path. A trailing suffix is stripped automatically. |
| `CORE42_MODEL` | Reasoning tier: analysis, gap analysis, report prose. |
| `CORE42_MODEL_FAST` | Bulk tier: Stage 3 per-case classification. Same value is fine. |
| `LLM_MAX_OUTPUT_TOKENS` | Hard ceiling per call, sent as `max_completion_tokens`. |
| `LLM_OUTPUT_TOKEN_HEADROOM` | Multiplier on each call site's `max_tokens`, because reasoning tokens eat the output budget before any text is produced. |
| `LLM_MAX_CONCURRENCY` | In-flight requests **per process**. Streamlit workers multiply it. |
| `LLM_MAX_RETRIES` / `LLM_RETRY_DELAY` | Attempts = retries + 1. 429s use a 10s floor of their own. |
| `CORE42_TOOL_MODE` | `auto` (default), `native`, or `json` — see *Tool calling* below. |

Settings are cached and the client is a module singleton, so **editing `.env`
while the app runs changes nothing**. Restart the process.

### Package layout

```
real/core42/
├── settings.py     # Env config, base-URL normalisation, model tiers, fail-fast
├── client.py       # Chat-completions client: lazy singleton, max_retries=0
├── messages.py     # Core42Client — the Messages-shaped facade the pipeline calls
├── json_repair.py  # Repair cascade: <think> blocks, fences, prose, trailing commas, truncation
├── retry.py        # Error classification + the 10s back-off floor for 429s
├── concurrency.py  # One process-wide in-flight cap (llm_slot)
└── tokens.py       # Per-stage token and cost tracking
```

Each flow reaches the package through `pipeline/llm.py`, a shim that inserts
`real/` on `sys.path` and re-exports. Pipeline stages only ever write
`from .llm import Core42Client, CHAT_MODEL` — a relative import, which is what
makes them survive the `sys.modules` purge that keeps the two flows from
importing each other's stages. The name `core42` deliberately matches none of the
purge patterns, so the client singleton, the concurrency gate and the token
ledger all survive a flow switch.

### The adapter, and why it exists

The pipeline was written against `anthropic.Anthropic`. Rather than rewrite 34
call sites and their response handling, `core42.Core42Client` keeps that surface
and maps it onto the gateway:

| Call site writes | Adapter sends |
|---|---|
| `messages=[...]`, `system=...` | OpenAI chat messages (system first) |
| `tools=[{name, input_schema}]` | OpenAI function tools (`function.parameters`) |
| `tool_choice={"type": "any"}` | `tool_choice="required"` |
| `max_tokens=N` | `max_completion_tokens=N × headroom` |
| `temperature=0.2` | **nothing** — reasoning models reject a non-default temperature |
| reads `message.content[0].text` | a `TextBlock` |
| reads `block.type == "tool_use"`, `block.input` | a `ToolUseBlock` built from `tool_calls` |
| reads `message.stop_reason` | mapped from `finish_reason` (`length` → `max_tokens`) |

Models are named by **tier**, not by deployment: call sites pass `CHAT_MODEL` or
`FAST_MODEL` and `settings.resolve_model()` maps those onto whatever the
environment configures, so switching model is one variable and never a code
change.

### Tool calling, and its fallback

Stages 3, 4 and 5 force a tool call and read the arguments back as structured
data. If the deployment's model rejects function tools, the adapter logs the
rejection at ERROR, caches the verdict for the process, and retries in JSON mode
with the tool's schema inlined in the prompt — returning the parsed object as a
`tool_use` block. The same fallback runs when a forced tool call comes back as
prose. So a gateway without tool support costs quality, never a crash.
`python real/smoke_core42_tools.py` says which path a deployment will take.

### JSON repair

Gateway models return unparseable JSON in five recurring ways, all handled before
any parse: `<think>` reasoning blocks (closed, or left open by truncation),
markdown fences, surrounding prose, trailing commas, and **truncation** — which
Core42 does far more often than other providers. Every stage of the cascade runs
on the fence-stripped original, so a failed repair cannot corrupt the next
attempt, and the aggressive clean preserves Arabic (a naive non-printable strip
deletes the entire report). Each truncation repair is logged at WARNING: a
silently repaired truncation is how a half-empty report ships. Both flows'
`pipeline/json_utils.py` strip `<think>` blocks before their own strategies run.

### Operational notes

* **Concurrency is capped once, globally.** Stage 3 fans out to 5 threads, Stage
  6 to 7, and the translation to 9; every outbound call passes through
  `llm_slot()`, which wraps the network call only — never a retry back-off, or
  the effective concurrency collapses to whatever fraction is not sleeping.
* **Retries have one owner.** The SDK client is built with `max_retries=0`;
  `core42/retry.py` is the only retry layer. Deterministic failures (bad key, bad
  model, malformed request) are never retried.
* **Every run reports its spend.** `PipelineOrchestrator.report_token_usage()`
  prints calls, tokens and cost per stage at the end of a full run, and the
  result lands in `results['token_usage']`.

### Smoke tests

Standalone by design — they read `.env` directly and make real API calls, so they
prove the credentials and the endpoint independently of any application code.
When something breaks, they say in five seconds whether the problem is ours or
the gateway's.

```bash
cd real
python smoke_core42.py             # key, base URL, api-key header, models, JSON mode
python smoke_core42_tools.py       # native function calling vs. the JSON fallback
python smoke_core42_rate_limits.py # where LLM_MAX_CONCURRENCY should sit
```

---

## Adaptive Report System (Demo Only)

The **demo version** features **automatic structure detection** that works with any Word report without hardcoding.

### Key Features

1. **Auto-Detection**: Automatically detects sections from Word headings
2. **Smart Table Assignment**: Tables are assigned to sections based on proximity
3. **JSON Caching**: Extracted structures are cached for fast subsequent loads
4. **Dynamic Display**: UI adapts to whatever structure is detected
5. **Automatic Cache Usage**: Display automatically uses cached JSON if available

### Using Extraction in Demo

```python
from analysis import DemoAnalyzer, AdaptiveReportExtractor, DynamicReportDisplay

# Extract report (uses cache if available)
extractor = AdaptiveReportExtractor()
report = extractor.extract_report("inquiries-output/your_report.docx")

# Display report dynamically
display = DynamicReportDisplay(lang='ar')
display.display_report("inquiries-output/your_report.docx")  # Uses cache automatically
```

See `docs/ADAPTIVE_SYSTEM_SUMMARY.md` and `docs/README.md` for full documentation.

## How It Works

### The Analyzer Interface (Analysis Layer)

All analyzer implementations inherit from their respective `analysis/base.py:Analyzer`, which defines three abstract methods:

```python
class Analyzer(ABC):
    def analyze(self, uploaded_file) -> Dict[str, Any]:
        """Analyze a file and return report structure."""
    
    def validate_file(self, uploaded_file) -> tuple[bool, str]:
        """Validate file format and size."""
    
    def get_processing_stages(self) -> list:
        """Return processing stages for progress display."""
```

**Demo version** (`demo/analysis/base.py`):
- Used by `DemoAnalyzer` (simulated with extraction utilities)
- Can be customized for demo-specific needs

**Real version** (`real/analysis/base.py`):
- Used by `RealAnalyzer` (AI-based implementation)
- Can be customized for real analyzer requirements

### Independent Execution

Each version runs independently:

- **Demo**: `cd demo && streamlit run app.py` 
  - Uses `demo/app.py` which imports from `demo/analysis/`
  - Runs `DemoAnalyzer` with extraction and simulated data
  
- **Real**: `cd real && streamlit run app.py`
  - Uses `real/app.py` which imports from `real/analysis/`
  - Runs `RealAnalyzer` with AI-based analysis (TODO)

### Environment Files

Local `.env` files in each folder:

- **`demo/.env`**: Sets `APP_MODE=demo` (the demo makes no LLM calls)
- **`real/.env`**: Sets `APP_MODE=real` plus the Core42 credentials and limits — see *Core42 Integration* above
- **Root `.env.*` files**: For reference, not used by the app

## Workflow: Demo vs Real Development

### Demo Version (Stable, `main` branch)

Work in the `demo/` folder:

1. UI improvements and bug fixes in `demo/app.py`
2. Report display enhancements in `demo/analysis/dynamic_display.py`
3. Extraction utilities in `demo/analysis/` (demo-specific)
4. Test with `make demo`
5. Commit when changes are finalized

### Real Version (Development, `real` branch)

Work in the `real/` folder:

1. Implement AI-based analysis in `real/analysis/real.py`
2. LLM calls go through `real/core42/` — see *Core42 Integration*
3. Update `real/app.py` if UI logic needs to differ
4. Test with `make real`
5. Push to `real` branch when features are complete

### Keeping Versions Independent

- **Each version is self-contained** — changes in demo don't affect real and vice versa
- **UI changes can be isolated** — modify `demo/app.py` without affecting `real/app.py`
- **Analysis logic is separate** — `DemoAnalyzer` and `RealAnalyzer` evolve independently
- **No merging needed** — each branch works independently

### When Changes Should Be Applied to Both

Update both versions if:
- Bug fixes in `base.py` (the abstract analyzer interface)
- Critical UI improvements that benefit both versions
- Dependency updates or compatibility fixes
- Documentation updates

## For Claude (Editing Guidelines)

When working on this codebase, **identify which version** the request applies to:

### Decision Tree

- **Edit `demo/`** if the request involves:
  - UI improvements or bug fixes
  - Changes to how the interface looks/works
  - Modifications to report display
  - Extraction/caching improvements
  - Pre-built report data
  
- **Edit `real/`** if the request involves:
  - Implementing the agentic AI analysis
  - Changing the Core42 integration or prompts
  - Building analysis agents
  - Real analyzer logic

- **Edit both** if the request involves:
  - Updating the `Analyzer` base class interface
  - Adding new processing stages
  - Changing file validation logic
  - Critical bugs that affect both versions
  - Dependency updates

### Quick Commands

```bash
# Demo development
cd demo && streamlit run app.py

# Real development  
cd real && streamlit run app.py

# Or use make
make demo
make real

# Clean up caches/temp files
make clean
```

## Extending the System

### Improving the Demo Analyzer

Edit `demo/analysis/demo.py`:
- Adjust processing stages
- Improve the report loading logic
- Add more realistic simulation

The demo analyzer uses extraction utilities from `demo/analysis/`:
- `AdaptiveReportExtractor` - for extracting reports with caching
- `ReportStructureDetector` - for auto-detecting report structure

And display components from `demo/analysis/`:
- `DynamicReportDisplay` - for displaying extracted reports (automatically uses cache)

### Implementing the Real Analyzer

Edit `real/analysis/real.py`:
- Implement all stub methods
- Call Core42 through `Core42Client` from `pipeline/llm.py`
- Return properly structured report data

The real analyzer will use display components from `real/analysis/`:
- `DynamicReportDisplay` - for displaying results (currently stubbed)

**Note:** The real analyzer will implement its own AI-based analysis logic, not use extraction from demo.

### Creating a New Implementation

If you need a third implementation (e.g., `experimental`):

1. Create a new folder: `experimental/` at root level
2. Copy `demo/` structure as a template
3. Create `experimental/analysis/experimental.py` with `ExperimentalAnalyzer`
4. Update `experimental/app.py:get_analyzer()` to return the new analyzer
5. Add to Makefile: `make experimental: cd experimental && streamlit run app.py`
6. Create `experimental/.env` with `APP_MODE=experimental`

## Unified Real App Architecture

### New Files (Real Version)

#### `real/app_inq_comp.py`
The unified app that handles both inquiries and complaints flows:
- **Lines 1-50**: Imports and setup (dynamic flow imports from `analysis`)
- **Lines 200-400**: CSS styling for both flows (gold for inquiries, blue for complaints)
- **Lines 400-600**: Session state initialization
- **Lines 600-700**: Analyzer setup - uses `get_analyzer_for_flow()` to load correct analyzer
- **Lines 700-1000**: Landing page with flow selection (two cards)
- **Lines 1000-1500**: Inquiries page (file upload, processing, display)
- **Lines 1500-2000**: Complaints page (file upload, processing, display)
- **Lines 2000-2100**: Main router that switches between pages

**Key function:**
```python
get_analyzer_for_flow(flow_type: str)  # Load analyzer for 'inquiries' or 'complaints'
```

#### `real/report_display.py`
Unified report display handler:
- `display_report_tabs(lang, flow_type, period)` - Displays reports for either flow
- Automatically selects cache dir based on flow_type
- Uses `get_display_for_flow()` to load the correct DynamicReportDisplay

#### `real/analysis/__init__.py` (UPDATED)
Now supports **dynamic analyzer loading** for both flows:
- `set_flow_context(flow_type)` - Sets which flow to use
- `get_analyzer_for_flow(flow_type)` - Factory to create analyzer for specific flow
- `get_display_for_flow(flow_type, lang, cache_dir)` - Factory to create display for specific flow
- Backward compatible: `RealAnalyzer`, `DynamicReportDisplay` still work for default flow (inquiries)

**Old behavior:** Always loaded inquiries analyzer (had `or True` bug)  
**New behavior:** Dynamically loads from appropriate flow folder based on context

## Key Files Explained

### `real/app_inq_comp.py` (NEW - Unified)
The recommended entry point for the real version. Supports both flows in one app.

### `real/report_display.py` (NEW - Unified)
Handles report display for both flows. Called by app_inq_comp.py after analysis.

### `real/analysis/__init__.py` (UPDATED - Now Dynamic)
Previously hard-coded to inquiries. Now dynamically loads analyzers via `get_analyzer_for_flow()`.

### `demo/app.py`

- **Lines 1-15**: Imports and environment setup (all from `demo/analysis/`)
- **Lines 1480-1485**: `get_analyzer()` function returns `DemoAnalyzer`
- **Lines 1488-1496**: `validate_file()` delegates to analyzer
- **Lines 1498-1551**: `display_report_tabs()` helper for displaying reports
- **Remaining**: UI/Streamlit code for the demo version

### `demo/analysis/__init__.py`

- Exports all demo components: `DemoAnalyzer`, `AdaptiveReportExtractor`, etc.
- Uses relative imports to load from local analysis folder
- Allows simple imports like `from analysis import DemoAnalyzer`

### `demo/analysis/base.py`

- Abstract base class defining the `Analyzer` interface
- Defines three abstract methods all analyzers must implement
- Can be customized per version if needed

### `demo/analysis/dynamic_display.py`

- Dynamically displays report structures without hardcoding
- Creates tabs based on detected sections
- Renders tables and charts with proper styling
- **Automatically uses cached JSON** from extraction
- Streamlit component for UI display

### `demo/analysis/demo.py`

- Implements `DemoAnalyzer` - simulates file processing
- Uses `AdaptiveReportExtractor` to load pre-built reports
- Defines processing stages for progress display
- Good reference implementation of the Analyzer interface

### `demo/analysis/adaptive_extractor.py`

- Extracts report structure from Word documents with intelligent caching
- Auto-detects sections using `ReportStructureDetector`
- **Caches extracted data in JSON** (`inquiries-output/cache/`) for fast loads
- Handles both inquiries and complaints flow reports
- Demo-specific extraction logic

### `demo/analysis/report_structure_detector.py`

- Automatically detects report structure (sections, subsections, tables)
- Uses Word heading styles as primary detection method
- Organizes content hierarchically
- Makes the system adaptable to different report formats

### `real/app.py`

- **Identical copy of** `demo/app.py` (independent development)
- **Different imports**: Uses `RealAnalyzer` from `real/analysis/`
- **Same UI**: Can be customized separately from demo
- Allows UI changes specific to the real version

### `real/analysis/real.py`

- Scaffold for `RealAnalyzer` with TODO comments
- Will implement the full agentic AI analysis
- Calls Core42 via `pipeline/llm.py`
- Will implement its own analysis logic (not extraction-based)

## How the Demo Works

1. **User uploads file** → `demo/app.py` calls `DemoAnalyzer`
2. **DemoAnalyzer** simulates processing with `get_processing_stages()`
3. **After simulation**, `display_report_tabs()` is called
4. **display_report_tabs()** uses `DynamicReportDisplay` to show the report
5. **DynamicReportDisplay** calls `AdaptiveReportExtractor.extract_report()`
6. **Extractor checks cache** - if JSON exists in `demo/inquiries-output/cache/`, loads from cache (instant!)
7. **If no cache**, extracts from Word document and creates cache
8. **Display renders** extracted structure with sections, tables, and charts

The cached JSON file is automatically reused on subsequent views of the same report.

## Caching in Action

- **First load**: Extracts from Word → creates `demo/inquiries-output/cache/[hash].json` → displays
- **Subsequent loads**: Uses `demo/inquiries-output/cache/[hash].json` → displays instantly
- **Force refresh**: Call `extractor.extract_report(path, force_refresh=True)` to bypass cache

## Demo-Specific Utilities

Extraction utilities are located in `demo/analysis/` because:
- They're used by `DemoAnalyzer` for simulated processing
- They enable quick display of pre-built reports using cached JSON
- The real analyzer will implement its own AI-based analysis (not extraction)

**Real version**: Doesn't use extraction; will implement AI-based analysis instead

## Troubleshooting

### "ModuleNotFoundError: No module named 'analysis'"

**Solution**: Make sure you're running from the correct folder:
```bash
cd demo  # or cd real
streamlit run app.py
```

Or use the Makefile: `make demo` or `make real`

### "RealAnalyzer not implemented"

**Expected behavior**: The real analyzer is still in development. Use `make demo` for the stable version.

### ".env file not being loaded"

**Solution**: Ensure `python-dotenv` is installed: `pip install python-dotenv`

Check that `.env` file exists in the folder you're running from:
- `demo/.env` for demo version
- `real/.env` for real version

### "Report file not found" (Demo mode)

The demo analyzer looks for Word reports in `demo/inquiries-output/` or `demo/complaints-output/`:

**Inquiries**:
- `demo/inquiries-output/تقرير تحليل استفسارات المتعاملين .docx`

**Complaints**:
- `demo/complaints-output/تقرير تحليل شكاوى المتعاملين.docx`

Check that files exist with correct names (watch for trailing spaces).

### "Cache not being used"

The cache is automatically created and used. Check for cached files:
```bash
# From demo folder
ls -la inquiries-output/cache/
ls -la complaints-output/cache/
```

To verify cache is working, run extraction twice—the second run should be instant.

### Import errors after reorganization

If you see import errors, make sure:
1. You're in the correct folder (`demo/` or `real/`)
2. `analysis/__init__.py` exists and is properly formatted
3. All relative imports use `.` notation (e.g., `from .base import Analyzer`)

## Notes for Future Development

- Each version (`demo/` and `real/`) is completely independent
- UI changes can be isolated to the version that needs them
- The `Analyzer` base interface should remain stable
- Extraction logic is demo-specific (`demo/analysis/`)
- Real analyzer will implement AI-based analysis, not extraction
- New implementations can follow the `demo/` structure as a template
