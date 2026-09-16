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

**LLM provider:** [Core42](../CLAUDE.md#core42-integration-real-version), an OpenAI-compatible gateway.
Credentials are read from `real/.env` first and then from Streamlit secrets (`.streamlit/secrets.toml`, or the deployed app's secrets — Streamlit Cloud has no `.env`).
At minimum set `CORE42_API_KEY`, `CORE42_BASE_URL` and `CORE42_MODEL`; see `../.env.example` for every setting.

Before a first run on a new deployment, prove the gateway independently of the app:

```bash
cd real
python smoke_core42.py             # key, base URL, api-key header, model, JSON mode
python smoke_core42_tools.py       # does this deployment support function calling?
python smoke_core42_rate_limits.py # where LLM_MAX_CONCURRENCY should sit
```

---

## 📁 Folder Structure

```
real/
├── app_inq_comp.py                  # Unified dual-flow UI (RECOMMENDED)
├── app.py                           # Legacy single-flow UI (inquiries only)
├── report_display.py                # Unified report display handler
├── .env                             # APP_MODE=real + Core42 credentials and limits
├── smoke_core42*.py                 # Standalone gateway probes (real API calls)
├── core42/                          # Core42 integration, shared by both flows
│   ├── settings.py                  # Env config, base-URL normalisation, fail-fast
│   ├── client.py                    # Chat-completions client (lazy singleton)
│   ├── messages.py                  # Core42Client — the Messages-shaped facade
│   ├── json_repair.py               # Truncation / fence / <think> repair cascade
│   ├── retry.py                     # Error classification + 10s floor for 429s
│   ├── concurrency.py               # One process-wide in-flight cap
│   └── tokens.py                    # Per-stage token and cost tracking
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
| `Core42 is not configured` | Set `CORE42_API_KEY` + `CORE42_BASE_URL` in `real/.env` or Streamlit secrets, then **fully restart** — settings are cached and the client is a singleton |
| 401 on every call | The gateway needs the `api-key` header as well as the bearer token; confirm the key, then run `python smoke_core42.py` |
| `unsupported parameter` | Something sent `max_tokens`; the client sends `max_completion_tokens` |
| Reports come back thin or half-empty | Output ceiling hit — look for `finish_reason=length` and `repaired by closing open JSON structures` in the logs, then raise `LLM_MAX_OUTPUT_TOKENS` / `LLM_OUTPUT_TOKEN_HEADROOM` |
| 429 storm, run slower than before | Lower `LLM_MAX_CONCURRENCY` (it is per process — Streamlit workers multiply it); `smoke_core42_rate_limits.py` finds the ceiling |
| Stage 3/4/5 fall back to JSON mode | The deployment rejected function calling — expected, logged at ERROR once. Confirm with `smoke_core42_tools.py`; set `CORE42_TOOL_MODE=json` to skip the one-time rejection |
| Wrong analyzer loaded | Ensure `set_flow_context()` (or `FLOW_TYPE`) is set before `get_analyzer_for_flow()` |
| "Could not find guidebook JSON" (Stage 5) | Confirm `guidebook_final.json` exists in the flow's `*-supporting-files/` |
| Stage 5 produces no gaps | Stage 4 must complete first (populates `journey_map`/`faq_candidates`); check `[Stage5]` logs |
| Empty `customer_journey` section | `journey_map` empty after Stage 4 — check `[Stage4]` warning in logs |
| `ModuleNotFoundError: analysis` | Run from inside `real/`; confirm `analysis/__init__.py` exists |

---

## 🌍 Deployment (Streamlit Cloud)

1. Push the repo to GitHub.
2. On https://streamlit.io/cloud, select the repo and set the entry file to `real/app_inq_comp.py`.
3. Add `CORE42_API_KEY`, `CORE42_BASE_URL`, `CORE42_MODEL`, `CORE42_MODEL_FAST` (and any other secrets) in the app's **Secrets** settings.
   Streamlit Cloud has no `.env`, so secrets are the only source there.
   `LLM_MAX_CONCURRENCY` is per worker process — divide the budget you want by the worker count.
4. Deploy.

---

## 📚 Related Docs

- **[../CLAUDE.md](../CLAUDE.md)** — full development guide and architecture
- **[../README.md](../README.md)** — project overview and navigation
- **[../demo/README.md](../demo/README.md)** — stable demo version

---

**Note:** This is the **AI-powered version** with full analysis pipelines. For stable pre-built reports, see the `demo/` folder.
