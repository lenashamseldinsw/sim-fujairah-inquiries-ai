# Real Version - AI-Powered Analysis Pipelines

## Overview

The **real version** implements full AI-powered analysis using 6-stage pipelines for both **inquiries and complaints flows**. Each flow has independent analysis logic, caching, and report generation.

**Recommended Entry Point**: `app_inq_comp.py` (unified dual-flow app)

---

## 🚀 Running the Real Version

### Unified App (Both Flows)
```bash
cd real
streamlit run app_inq_comp.py
```
Single landing page with flow selection → separate pages for inquiries & complaints analysis.

### Legacy Single-Flow (Backward Compatibility)
```bash
cd real
APP_MODE=inquiries streamlit run app.py
```
Only supports inquiries flow. Use `app_inq_comp.py` for complaints.

---

## 📁 Folder Structure

```
real/
├── app_inq_comp.py                # Unified dual-flow UI (RECOMMENDED)
├── app.py                         # Legacy single-flow UI (backward compat)
├── report_display.py              # Unified report display handler
├── .env                           # Environment config
├── analysis/                      # Analyzer loaders (dynamic)
│   ├── __init__.py               # Exports get_analyzer_for_flow(), etc.
│   ├── base.py                   # Abstract Analyzer interface
│   └── real.py                   # Legacy RealAnalyzer (single-flow)
├── inquiries-flow/               # Inquiries pipeline
│   ├── analysis/
│   │   ├── __init__.py          # Exports inquiries analyzer
│   │   ├── base.py              # Analyzer interface
│   │   ├── real.py              # RealAnalyzer (6-stage pipeline)
│   │   └── dynamic_display.py   # Report display
│   ├── pipeline/                # 6-stage orchestrator + stages
│   └── output/                  # Generated reports & cache
├── complaints-flow/             # Complaints pipeline
│   ├── analysis/
│   │   ├── __init__.py          # Exports complaints analyzer
│   │   ├── base.py              # Analyzer interface
│   │   ├── real.py              # RealAnalyzer (6-stage pipeline)
│   │   └── dynamic_display.py   # Report display
│   ├── pipeline/                # 6-stage orchestrator + stages
│   └── output/                  # Generated reports & cache
├── inquiries-output/            # Root output (backward compat)
├── complaints-output/           # Root output (backward compat)
└── test_pipeline_*.py           # Test scripts per flow
```

---

## 🎯 Architecture

### Unified App (`app_inq_comp.py`)

**Flow**:
1. Landing page with flow selection (Inquiries | Complaints)
2. File upload and analysis (uses appropriate pipeline)
3. Results display with dynamic viewer
4. Download options (Word report, Excel, JSON)

**Key Function**:
```python
get_analyzer_for_flow(flow_type: str)  # Load correct pipeline
```

### Dynamic Analyzer Loading (`analysis/__init__.py`)

Previously hard-coded to inquiries. Now:
- `set_flow_context(flow_type)` - Set which flow to use
- `get_analyzer_for_flow(flow_type)` - Load analyzer for 'inquiries' or 'complaints'
- `get_display_for_flow(flow_type, lang, cache_dir)` - Load display for flow

### Independent Pipelines

Each flow has its own complete implementation:

#### Inquiries Flow (`inquiries-flow/`)
- **Pipeline**: 6-stage processing (classification → extraction → analysis → reconciliation → formatting → report generation)
- **Analyzer**: `inquiries-flow/analysis/real.py:RealAnalyzer`
- **Output**: `inquiries-flow/output/`
- **Cache**: `inquiries-flow/output/cache/`

#### Complaints Flow (`complaints-flow/`)
- **Pipeline**: 6-stage processing (similar structure to inquiries)
- **Analyzer**: `complaints-flow/analysis/real.py:RealAnalyzer`
- **Output**: `complaints-flow/output/`
- **Cache**: `complaints-flow/output/cache/`

---

## 🔄 How It Works

### Step-by-Step Flow

1. **User lands on app** → Selects "Inquiries" or "Complaints"
2. **Flow context set** → App loads appropriate analyzer
3. **User uploads file** → Routed to correct pipeline
4. **Pipeline processes** → 6 stages with progress display
5. **Results generated** → Word report, Excel, JSON
6. **Display renders** → Dynamic viewer shows results
7. **Downloads available** → User can download all outputs

### The 6-Stage Pipeline

Each flow implements:

1. **Stage 1**: File upload & initial validation
2. **Stage 2**: Data classification and categorization
3. **Stage 3**: Content extraction and structuring
4. **Stage 4**: Analysis and pattern detection
5. **Stage 5**: Data reconciliation and validation
6. **Stage 6**: Report generation and caching

---

## 🧪 Testing

### Test Inquiries Pipeline
```bash
cd real
python test_pipeline_inquiries.py
```

### Test Complaints Pipeline
```bash
cd real
python test_pipeline_complaints.py
```

---

## 🔧 Development

### Adding a New Stage

1. Create `inquiries-flow/pipeline/stage_X_name.py`
2. Implement stage function:
```python
def stage_X_name(state: PipelineState) -> PipelineState:
    """Process state and return updated state."""
    # Do work
    return state
```

3. Register in orchestrator:
```python
stages = [
    ("stage_X_name", stage_X_name),
]
```

### Modifying Analyzer

Edit `inquiries-flow/analysis/real.py` or `complaints-flow/analysis/real.py`:
- Implement `analyze(uploaded_file)` method
- Return properly structured report data
- Handle all validation in `validate_file()`

### Dynamic Display

Edit `inquiries-flow/analysis/dynamic_display.py` or `complaints-flow/analysis/dynamic_display.py`:
- Customize report rendering per flow
- Adjust styling and layouts
- Add flow-specific visualizations

---

## 📊 Report Structure

Both flows generate three outputs:

### 1. Word Report
- Generated with `sword_word_builder`
- Includes sections, tables, charts
- Bilingual (Arabic/English) support
- Downloadable from UI

### 2. Excel File
- Structured data export
- Multiple sheets per section
- Raw counts and metrics
- Downloadable from UI

### 3. JSON Cache
- Cached pipeline state
- Reusable for reruns
- Includes all computed metrics
- Stored in `output/cache/`

---

## 🔄 Workflow

### Development (inquiries-flow/ or complaints-flow/)

#### For Inquiries
```bash
cd real
# Edit: inquiries-flow/analysis/real.py
# Edit: inquiries-flow/pipeline/stage_*.py
streamlit run app_inq_comp.py
# Test: python test_pipeline_inquiries.py
```

#### For Complaints
```bash
cd real
# Edit: complaints-flow/analysis/real.py
# Edit: complaints-flow/pipeline/stage_*.py
streamlit run app_inq_comp.py
# Test: python test_pipeline_complaints.py
```

### Key Implementation Points

- **Independent analyzers**: Each flow has own RealAnalyzer
- **Separate pipelines**: 6 stages each, isolated per flow
- **Unified UI**: `app_inq_comp.py` routes between flows
- **Dynamic loading**: `get_analyzer_for_flow()` picks right one
- **No merging**: Each version is self-contained

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "get_analyzer_for_flow not found" | Check `analysis/__init__.py` exports function |
| Wrong analyzer loaded | Check `set_flow_context()` called before getting analyzer |
| Pipeline stages not running | Check stage functions in `pipeline/` folder exist |
| Reports not caching | Delete `output/cache/` and regenerate |
| Import errors | Make sure you're in `real/` folder, `analysis/__init__.py` exists |
| App won't start | Check `analysis/base.py` defines Analyzer abstract class |

---

## 📝 Environment Configuration

```
APP_MODE=real
INQUIRIES_OUTPUT=inquiries-flow/output
COMPLAINTS_OUTPUT=complaints-flow/output
```

Create/update `real/.env` with above.

---

## 🌍 Deployment

### Streamlit Cloud

1. Push repo to GitHub
2. Go to https://streamlit.io/cloud
3. Select repo and file: `real/app_inq_comp.py`
4. Deploy

### Docker

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY real/ .
EXPOSE 8501
CMD ["streamlit", "run", "app_inq_comp.py"]
```

```bash
docker build -t fujairah-real .
docker run -p 8501:8501 fujairah-real
```

---

## 📚 Related Documentation

- **[../CLAUDE.md](../CLAUDE.md)**: Full development guide and architecture
- **[../README.md](../README.md)**: Project overview and quick links
- **[../demo/README.md](../demo/README.md)**: Demo version (pre-built reports) documentation

---

**Note**: This is the **real/AI-powered version** with full analysis pipelines. For stable pre-built reports, see the `demo/` folder.
