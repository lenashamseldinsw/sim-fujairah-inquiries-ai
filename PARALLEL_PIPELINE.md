# Parallel Pipeline Architecture

## Overview

The real flow now uses a **parallel execution model** where analysis results are displayed immediately while artifacts (Excel and Word reports) are generated in the background.

## Pipeline Flow

```
Upload Excel File
    ↓
┌─────────────────────────────────────┐
│ Sequential Stages 1-5 (Data)        │
│ ────────────────────────────────    │
│ 1. Schema Validation                │
│ 2. Rule-Based Classification        │
│ 3. LLM Classification               │
│ 4. Pattern Analysis                 │
│ 5. Gap Analysis                     │
└─────────────────────────────────────┘
    ↓ Analysis Complete ✅
    ├──────────────────────────────────────────┐
    ↓                                          ↓
┌─────────────────────────┐      ┌──────────────────────────┐
│ IMMEDIATE (Main Thread) │      │ BACKGROUND (Worker Thread)│
│                         │      │                          │
│ Return Dict to UI:      │      │ Generate Artifacts:      │
│ • All 6 stages data     │      │ • Excel workbook         │
│ • Analysis results      │      │ • Word report (sword)    │
│ • artifact_status       │      │                          │
│                         │      │ Update artifact_status   │
│ Display Results:        │      │ Update report dict       │
│ • Sections as tabs      │      │ Mark ready when done     │
│ • Tables & charts       │      │                          │
│ • "Generating..." msg   │      │ On Error:                │
│                         │      │ Set error in status      │
│ Show Downloads:         │      │                          │
│ • Check ready flags     │      │                          │
│ • Include if available  │      │                          │
│ • Show fallback if not  │      │                          │
└─────────────────────────┘      └──────────────────────────┘
```

## Key Changes

### 1. RealAnalyzer.analyze() (`real/analysis/real.py`)

**Before:** Stages 1-6 ran sequentially, blocking until all artifacts were ready

**After:** 
- Stages 1-5 run sequentially
- Returns immediately with analysis dict + artifact status
- Stage 6 queued in background thread

```python
# Returns immediately with this structure:
{
    "sections": { ... },  # All analysis results ready
    "metadata": { ... },
    "artifacts_status": {
        "excel_ready": False,        # Will be True when generated
        "word_ready": False,         # Will be True when generated
        "excel_path": "/path/to/...",
        "word_path": "/path/to/...",
        "error": None                # Error message if generation fails
    }
}
```

### 2. Background Artifact Generation

New method `_generate_artifacts_background()`:
- Runs in daemon thread
- Has access to orchestrator state
- Generates Excel workbook
- Generates Word report using sword-word-builder
- Updates report dict when complete
- Handles errors gracefully

```python
def _generate_artifacts_background(self, report, excel_path, word_path):
    # Generate Excel
    generate_excel(self.orchestrator.state, excel_path)
    report["artifacts_status"]["excel_ready"] = True
    
    # Generate Word report
    generate_word_report(...)
    report["artifacts_status"]["word_ready"] = True
    
    # Add stage6 section when both complete
    report["sections"]["stage6_artifacts"] = { ... }
```

### 3. App.py Flow (`real/app.py`)

**process_with_analyzer():**
- Calls `ANALYZER.analyze()` once
- Immediately stores report in session state
- Stores artifact paths and ready flags
- Returns control to UI

**display_report_tabs():**
- Shows analysis sections immediately
- Displays "📄 Generating artifacts..." status if not ready
- Shows error if generation failed

**Download Buttons:**
- Check `output_files['excel_ready']` and `['word_ready']`
- Show status message while generating
- Once ready, include generated artifacts in ZIP
- Fallback to demo files if real artifacts not ready

## Benefits

### For Users
1. **Instant Feedback**: See analysis results immediately
2. **Progressive Enhancement**: Artifacts added as they become ready
3. **No Blocking**: UI remains responsive during artifact generation
4. **Status Visibility**: User knows artifacts are being generated

### For System
1. **Parallelized Work**: CPU-intensive artifact generation doesn't block UI
2. **Better Performance**: Users see results while expensive operations run
3. **Responsive Interface**: Streamlit redraws with updated artifact status
4. **Error Resilience**: Failed artifacts don't crash the app

## Session State Tracking

**During Analysis:**
```python
st.session_state = {
    'report_data': { ... },  # Analysis dict (immediate)
    'output_files': {
        'excel_path': '/path/...',
        'excel_ready': False,      # Updates when generation completes
        'word_path': '/path/...',
        'word_ready': False,       # Updates when generation completes
    }
}
```

## Artifact Generation Status

The report dict includes artifact status:

```python
report["artifacts_status"] = {
    "excel_ready": True/False,   # Check before downloading Excel
    "word_ready": True/False,    # Check before downloading Word
    "excel_path": "/path/...",   # Path to Excel file
    "word_path": "/path/...",    # Path to Word file
    "error": None or "Error message"  # Error if generation failed
}
```

## Download Behavior

**Immediate Download (while artifacts generating):**
- ZIP includes demo files as fallback
- User gets some content immediately
- ZIP updates automatically once real artifacts ready

**After Artifacts Ready:**
- ZIP includes generated Excel workbook
- ZIP includes generated Word report
- Download button shows real artifacts included

## Error Handling

If artifact generation fails:
- `artifacts_status["error"]` contains error message
- `display_report_tabs()` shows error notification
- User can still see analysis results
- Download includes demo files as fallback

## Threading Model

**Main Thread (Streamlit):**
- Runs analyzer stages 1-5
- Returns immediately
- Handles UI rendering
- Responsive to user interactions

**Worker Thread (Daemon):**
- Runs artifact generation (Excel + Word)
- Updates report dict when complete
- Exits when complete
- If main thread exits, worker terminates

## Implementation Details

### Threading Safety
- Report dict is thread-safe for status updates
- File I/O (Excel, Word generation) happens in worker thread only
- No concurrent writes to same files

### Performance
- Stages 1-5: ~10-30 seconds (user blocks during this)
- Stage 6: ~5-10 seconds (user sees results while this runs)
- Net user wait: ~10-30 seconds (same as before)
- User experience: Better (shows results earlier)

### Compatibility
- Works with Streamlit session state
- Compatible with all existing UI code
- Graceful fallback to demo files if needed
- No changes to base.py interface

## Testing the Flow

1. Upload a file
2. Watch progress reach 100% quickly
3. See analysis results appear in tabs
4. Notice "📄 Generating artifacts..." message
5. Wait for it to change to "artifacts ready"
6. Download includes generated artifacts
7. If artifacts fail, download includes demo files
