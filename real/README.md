# Real Version — AI-Powered Analysis Pipelines

## Overview

The **real version** runs full AI-powered analysis using a **6-stage pipeline**, implemented independently for two flows: **inquiries** and **complaints**. Each flow has its own analyzer, pipeline, supporting files, and outputs.

**Recommended entry point:** `app_inq_comp.py` (unified dual-flow app).

---

## 🚀 Running the Real Version

```bash
# From project root
make real            # alias for make real-unified (recommended)
make real-unified    # both flows, unified app  → app_inq_comp.py
make real-single     # legacy single-flow app   → app.py (inquiries only)

# Or manually
cd real && streamlit run app_inq_comp.py
```

Opens at `http://localhost:8501`.

**API key:** read from Streamlit secrets (`~/.streamlit/secrets.toml` or the deployed app's secrets), **not** from `.env`. The `.env` here only sets `APP_MODE=real`.

---

## 📁 Folder Structure

```
real/
├── app_inq_comp.py                  # Unified dual-flow UI (RECOMMENDED)
├── app.py                           # Legacy single-flow UI (inquiries only)
├── report_display.py                # Unified report display handler
├── .env                             # APP_MODE=real (no API key here)
├── analysis/                        # Thin routing layer (no analyzer here)
│   ├── __init__.py                  # Dynamic loader: set_flow_context / get_analyzer_for_flow / get_display_for_flow
│   ├── base.py                      # Abstract Analyzer interface
│   └── dynamic_display.py           # Shared display base
│
├── inquiries-flow/                  # Inquiries pipeline (self-contained)
│   ├── analysis/
│   │   ├── __init__.py              # Exports RealAnalyzer + DynamicReportDisplay
│   │   ├── base.py
│   │   ├── real.py                  # RealAnalyzer for inquiries
│   │   └── dynamic_display.py
│   ├── pipeline/                    # 6-stage pipeline (see below)
│   ├── inquiries-supporting-files/  # guidebook_final.json
│   ├── sample-input/                # Sample .xlsx inputs
│   ├── reference-inquiries-outputs/ # Reference report + Excel
│   ├── pipeline-test-output/        # Generated reports (docx/xlsx/json)
│   └── test_*.py                    # Flow-specific tests
│
└── complaints-flow/                 # Complaints pipeline (self-contained)
    ├── analysis/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── real.py                  # RealAnalyzer for complaints
    │   └── dynamic_display.py
    ├── pipeline/                     # 6-stage pipeline (same shape as inquiries)
    ├── complaints-supporting-files/  # guidebook_final.json + complaints-management-methodology-v4.json
    └── test_*.py                     # Flow-specific tests
```

> **Note:** There is **no** `real/analysis/real.py` and **no** `real/chart_parser.py`. The `RealAnalyzer` implementations live inside each flow's `analysis/real.py` and are loaded dynamically by `real/analysis/__init__.py`.

---

## 🎯 Analyzer Routing (`real/analysis/__init__.py`)

`app_inq_comp.py` selects a flow at runtime; the routing layer loads the correct flow's analyzer/display by importing that flow's `analysis/__init__.py`:

```python
set_flow_context(flow_type)                       # 'inquiries' or 'complaints'
get_analyzer_for_flow(flow_type)                  # → RealAnalyzer() for that flow
get_display_for_flow(flow_type, lang, cache_dir)  # → DynamicReportDisplay for that flow
```

The default import (backward compatibility) loads the **inquiries** flow, exposing `RealAnalyzer`, `DynamicReportDisplay`, and `Analyzer`. Flow selection is also honoured via the `FLOW_TYPE` environment variable.

---

## 🔄 The 6-Stage Pipeline

Both flows implement the same pipeline shape. Orchestrated by `pipeline/orchestrator.py` (`PipelineOrchestrator`), with shared state in `pipeline/state.py` saved to JSON after each stage for crash recovery.

| Stage | File | Purpose |
|-------|------|---------|
| **1. Validation** | `stage1_validator.py` | Validate input schema; establish `total_cases` |
| **2. Rule classification** | `stage2_rules.py` | Rule-based classification; queue low-confidence cases for the LLM |
| **3. LLM classification** | `stage3_llm.py` | Claude classifies low-confidence cases; unresolved → human-review queue |
| **4. Analysis** | `stage4_analysis.py` | Pattern/cluster detection, FAQ candidates, friction (journey) mapping |
| **5. Gap analysis** | `stage5_gap.py` | Validate FAQs and identify gaps against the guidebook JSON |
| **6. Artifacts** | `stage6_artifacts.py`, `stage6_json_report.py` | Generate Word + Excel + in-memory report JSON |

**Section generators** (invoked during report building, per flow in `pipeline/`):
`generate_workload_map_section.py`, `generate_customer_journey_section.py`, `generate_digital_gaps_section.py`, `generate_digital_transformation_section.py`, `generate_ai_use_cases_section.py`, `generate_improvement_roadmap_section.py`, `generate_conclusion_section.py`.

**Report building & translation:** `build_report_ar.py`, `build_report_en.py`, `translate_report_en.py` produce the 9-section report; English translation runs the 9 sections **in parallel** for speed.

---

## 📊 Outputs

Each run produces three artifacts (written to the flow's output folder, e.g. `inquiries-flow/pipeline-test-output/`):

1. **Word report** (`.docx`) — built via `sword_word_builder`, bilingual-capable (Arabic default, English via parallel translation).
2. **Excel workbook** (`.xlsx`) — per-case classifications and section data.
3. **Report JSON** (`_data.json` / `report_final_ar_*.json`) — cached pipeline state and computed metrics.

---

## 🧪 Testing

Tests live **inside each flow folder**, not at `real/` top level:

```bash
# Inquiries
cd real/inquiries-flow
python test_report_sections.py
python test_faq_frequency_consistency.py
python test_dynamic_columns.py
python test_parallel_translation.py
python verify_json_structure.py

# Complaints
cd real/complaints-flow
python test_workload_map_validation.py
python test_roadmap_section8.py
python test_closure_rate_diagnostic.py
python test_section_3_4.py
```

---

## 🔧 Development

### Modify an analyzer
Edit `inquiries-flow/analysis/real.py` or `complaints-flow/analysis/real.py` (implement `analyze`, `validate_file`, `get_processing_stages`).

### Add/modify a pipeline stage
Edit the relevant `pipeline/stageN_*.py` and wire it in `pipeline/orchestrator.py`. State flows through `PipelineState` (`pipeline/state.py`).

### Adjust report sections
Edit the matching `pipeline/generate_*_section.py`, and `build_report_ar.py` / `build_report_en.py` for assembly.

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Missing API key | Set `ANTHROPIC_API_KEY` in Streamlit secrets, **not** `.env` |
| Wrong analyzer loaded | Ensure `set_flow_context()` (or `FLOW_TYPE`) is set before `get_analyzer_for_flow()` |
| "Could not find guidebook JSON" (Stage 5) | Confirm `guidebook_final.json` exists in the flow's `*-supporting-files/` |
| Stage 5 produces no gaps | Stage 4 must complete first (populates `journey_map`/`faq_candidates`); check `[Stage5]` logs |
| Empty `customer_journey` section | `journey_map` empty after Stage 4 — check `[Stage4]` warning in logs |
| `ModuleNotFoundError: analysis` | Run from inside `real/`; confirm `analysis/__init__.py` exists |

---

## 🌍 Deployment (Streamlit Cloud)

1. Push the repo to GitHub.
2. On https://streamlit.io/cloud, select the repo and set the entry file to `real/app_inq_comp.py`.
3. Add `ANTHROPIC_API_KEY` (and any other secrets) in the app's **Secrets** settings.
4. Deploy.

---

## 📚 Related Docs

- **[../CLAUDE.md](../CLAUDE.md)** — full development guide and architecture
- **[../README.md](../README.md)** — project overview and navigation
- **[../demo/README.md](../demo/README.md)** — stable demo version

---

**Note:** This is the **AI-powered version** with full analysis pipelines. For stable pre-built reports, see the `demo/` folder.
