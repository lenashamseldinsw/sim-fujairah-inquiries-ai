# Development Guide — NoveIntelligence services (`noveintel` branch)

This branch holds the two NoveIntelligence analytics services and nothing else:

```
noveintel-inquiries/    Domain 03 — Customer Inquiries Analytics   (prefix NOVEINQ_)
noveintel-complaints/   Domain 02 — Complaints Analytics           (prefix NOVECOMP_)
```

Each is a self-contained, independently deployable FastAPI service (Azure Functions or
on-prem). The Streamlit application they were ported from (`demo/`, `real/`) lives on
the `main` and `real` branches and is **not** on this branch; this branch is not merged
back. Do not reintroduce it, and do not make either service import from outside its
own folder.

## 📋 Documentation Policy

**⚠️ DO NOT CREATE NEW .MD FILES.** The complete allowance is:

- **CLAUDE.md** (this file) — how the repository works and how to edit it;
- **README.md** (root) — what is here and where to start;
- **MEMORY.md** — the auto-memory index;
- per service, exactly four: `README.md`, `docs/api.md`, `docs/schema.md`,
  `docs/deployment.md`. A caller integrating the API needs them next to the code.

Anything else belongs in one of those.

---

## Inquiries service (`noveintel-inquiries/`) — the BO handoff, implemented

Built from the Business Owner's *Inquiries Analytics — AI-Team Handoff* (spec v1.2):
Prerequisites v1.2, the Domain Definition Sheet, the Data Mapping (Inquiries Tool) v2,
the Full Report Prompt, the classification and root-cause codebooks, the TAMM process
and KPI document, and the Platformisation Requirements R1–R12 from the Fujairah Pulse
Field Atlas. Fujairah Pulse is the reference build; ADPF is the second configuration.

### Three layers (Prerequisites §0)

| Layer | Package | Rule |
|---|---|---|
| 1 Parser + engine | `engine/` (`parse`, `compute`, `frameworks`, `taxonomy`, `redact`, `wording`, `localize`) | Computes **every** number, on frozen labels. Pure. |
| 2 Classifier | `classification/` (`rules`, `model`, `rootcause`, `umbrellas`, `classify`) | Creates labels — never a number about the population. |
| 3 Narrative writer | `narratives/` (`prompts`, `rules`, `context`, `writer`) | Writes prose only, from the engine's numbers. |

`analysis/` names the qualitative items S4–S6 table (frictions, notification
opportunities, FAQs, guidebook gaps); the model assigns whole **case groups** to each
item and the engine sums them, so no count comes from a model (R6). `report/` places
everything into the report's sections (`assemble`), renders Word (`word`) and the companion workbook
(`workbook`). `pipeline.py` wires it and owns failure classification.

### Invariants worth knowing before editing

- **One denominator (R2).** `S` is the in-scope set after artefact rows, duplicates and
  the X4 scope; the parse log accounts for everything outside it. Cover total = Σ S3.2
  table = Σ per-type workbook sheets — `tests/test_pipeline.py` pins it.
- **Frozen labels are never overwritten.** A record's `label_*` fields come from an
  earlier run, stored by the platform; the classifier fills only what is missing.
- **Provenance is set by the pipeline**, never by the model: `auto` «آلي - موثوق»
  (keyword rules, or copied from an identical case), `llm` «نموذج», `auto_corrected`
  «آلي - مُصحّح», `deep_review` «يدوي - مُراجع». **There is no human review queue** —
  «يدوي - مُراجع» is the deep AI review (`DEEP_MODEL` tier with `reasoning_effort` —
  gpt-5.1 does not reason unless asked — batches of 5, more examples)
  that cases below X6 or still breaking a codebook rule get. Whatever is still below
  X6 after it is flagged `low_confidence` and counted with its best labels.
  Thresholds are settings (X5/X6), never constants (R11).
- **Identity never leaves ingest (R3).** Sensitive columns redact their own row's text
  and are dropped; free text is redacted before any model call and in every artefact.
  `tests/test_pipeline.py::test_r3_*` plants an identity and searches every artefact.
- **Every prompt that writes report text carries `narratives/rules.py`**, the Full
  Report Prompt's style and hard rules. Change wording there, once — a prompt that
  restates a rule differently is how two prompts start contradicting each other.
- **The narrative pre-flight checklist is code** (`narratives/writer.py`): figures
  checked against the context with one corrective retry (a retry never replaces a more
  complete draft), banned words replaced, vocabulary applied, lists cleaned,
  conditional fields emptied, initiative counts taken from their reference.
- **Required inputs are decided in one place**, `api/models/requests.py::
  missing_required_fields`: columns U1–U4 + U9, settings X2–X4, the taxonomy. The
  route and the library path both refuse with "The following input field(s) were
  missing or unmapped: …".
- **The narrative is written once, in Arabic.** There is no English writing prompt:
  `writer.translate_narratives` translates the finished Arabic (two calls, one per
  part) in the background while the Arabic documents are built, with a glossary of the
  English names the report already prints. Fixed headings and taxonomy names are never
  sent for translation; AI-generated labels (root causes, umbrella names) go through
  `narratives/translate.py`. English is withheld when the taxonomy lacks English names
  (Domain 01 ruling).
- **Overlaps in `pipeline._run`**: the analysis runs in the background from stage 3;
  umbrella discovery, `compute` (which needs the umbrellas, never the analysis) and the
  narrative of the sections that do not use the analysis go ahead without it. The
  narrative is three independent calls (`_EARLY_GROUPS` A and B, then `_LATE_FIELDS`
  once the analysis is in — Sections 04–05, the conclusion, the friction points), and
  `write_narratives(on_part=…)` hands each finished group to its English translation.
  The early groups read `metrics_early`, a dict nothing writes to afterwards; the full
  figures are a new dict. Progress is monotonic across the threads.
- **The report is the sample output's structure** (BO, 2026-10-14): executive summary,
  Sections 01–05 (statistics, service focus, root causes, digital-content opportunities,
  roadmap), conclusion, appendices. `api/models/enums.ReportSection` is the list;
  `SECTION_TITLES` the printed names, which a request may use. The Definition Sheet's
  other sections (customer journey, guidebook gaps, digital transformation, AI use
  cases, the Fujairah classification-map subsections) are commented out, not deleted —
  in `assemble`, `pipeline`, `analysis` and `narratives/prompts`.
- **Tenants choose sections by name** (`options.sections`). Sections do not depend on
  each other: `pipeline._SECTION_NEEDS` lists the only three that need the qualitative
  analysis (Section 04 → FAQs, Section 05 → journey + FAQs, appendices → journey). The
  narrative tools carry only the fields asked for (shown section, input present);
  `pipeline._CONTEXT_READERS` drops prompt data only hidden or retired sections read.
  Umbrella discovery is not section-gated: with X8 on it always runs, because D8 is a
  label the platform stores.
- **Branding:** no `brand` → NoveAI Navy `#201853` / Magenta `#7E2362` (Prerequisites
  §5); the within / near / over colours are locked (`entity.TIMELINESS_COLORS`).
- **Thread pools are `core42.tokens.ScopedThreadPoolExecutor`**, never a bare
  `ThreadPoolExecutor` — the run's token ledger is a context variable.
  `tests/test_runs.py` fails on a bare one.

### The taxonomy preset and its examples

`resources/taxonomy_adpf_codebook_v1.json` is the ADPF classification codebook:
13 main services, sub-classifications, §4 signals, edge cases, a crosswalk learned from
the Q2 master, and 111 reviewed, redacted examples. The classifier shows each batch
the examples most similar to it. Signals and examples were calibrated against the Q2
reviewed labels — re-measure before changing them, and keep any new example redacted
(`engine.redact`).

### Testing

`cd noveintel-inquiries && uv run pytest` — 394 tests, no network. `tests/fakes.py`
answers every model call by tool name; `tests/fixtures/adpf_q2_2026_labels.json.gz` is
the labelled ADPF master (labels and structured columns only), against which
`tests/test_engine.py` reproduces the Full Report Prompt's worked example exactly.
`scripts/smoke.py fixtures/adpf_happy.json` makes a real run.

---

## Complaints service (`noveintel-complaints/`)

Still the six vendored Fujairah stages behind the same API shape (its README describes
them). The parity test against `real/complaints-flow/` was retired with the Streamlit
application; the stages are now maintained in place.

---

## Shared conventions (both services)

### Running one

```bash
cd noveintel-inquiries          # or noveintel-complaints
cp .env.example .env            # set CORE42_API_KEY
uv sync --extra api --extra serve
uv run uvicorn noveintel_inquiries.api.app:app --reload   # http://localhost:8000/docs
uv run pytest
```

### Asynchronous runs

`POST /v1/<flow>` answers `202` with a `job_id`; the caller polls `GET /v1/jobs/{id}`.
A run is minutes to hours of model calls — far past Azure's 230-second HTTP ceiling
(porting guide §5.6).

### Deployment: Azure or on-prem

| Setting | On-prem (default) | Azure |
|---|---|---|
| `<PREFIX>_STORAGE_BACKEND` — report files | `local` | `blob` |
| `<PREFIX>_JOB_BACKEND` — job status | `local` | `table` |
| `<PREFIX>_JOB_DISPATCH` — where a run executes | `inprocess` | `queue` |

On-prem installs no Azure package: the SDKs come only with the `azure` extra and are
imported inside methods. Queue, table and container names are per service by default
so the two can share a storage account — do not reintroduce a shared default.
`host.json`'s `functionTimeout` must stay above `<PREFIX>_JOB_MAX_RUNTIME_SEC`; size
both for the tenant's volume (`docs/deployment.md`).

### Concurrent runs share one process

- **A token ledger per run** — `core42.tokens.run_scope()`, carried into thread pools by
  `ScopedThreadPoolExecutor`.
- **Gateway failures are counted on that ledger**, so a step that failed because the
  gateway did is reported `upstream_error`, not `stage_failed`.
- **Exception text stays out of the job record** — the caller gets the run id; the log
  gets the text.
- **A run past its ceiling is stopped**: the next progress report raises `RunAbandoned`,
  which passes through untouched, and queued model batches are cancelled.
- A redelivered queue run **starts over**; nothing is checkpointed.

### Core42

Both services call Core42, an OpenAI-compatible gateway, through `<package>/core42/`:
`settings` (env, base-URL normalisation, model tiers), `client` (lazy singleton,
`max_retries=0`), `messages` (`Core42Client`, a Messages-shaped facade: tools, forced
tool choice, no temperature for reasoning models, a JSON-mode fallback when a gateway
rejects tools), `json_repair` (think blocks, fences, prose, trailing commas,
truncation — logged), `retry` (the only retry layer; 10 s floor for 429s),
`concurrency` (one process-wide in-flight cap around the network call only) and
`tokens` (per-stage, per-run accounting). Call sites name a **tier** (`CHAT_MODEL`,
`FAST_MODEL`), never a deployment. Settings are cached: restart after editing `.env`.

| Variable | What it does |
|---|---|
| `CORE42_API_KEY` | Required. |
| `CORE42_BASE_URL` | No `/chat/completions` suffix. |
| `CORE42_MODEL` / `CORE42_MODEL_FAST` | Reasoning tier (analysis, narratives) / bulk tier (classification). |
| `CORE42_MODEL_DEEP` / `LLM_DEEP_REASONING_EFFORT` | The deep review's model (default `CORE42_MODEL`) and reasoning effort (default `medium`). A model rejecting `reasoning_effort` is asked again without it. |
| `LLM_MAX_CONCURRENCY` | In-flight requests per process, default 5 (matches the classifier's 5-batch fan-out). Raising it further usually means more 429s. |
| `LLM_MAX_RETRIES` / `LLM_RETRY_DELAY` | Attempts = retries + 1. |
| `CORE42_TOOL_MODE` | `auto`, `native` or `json`. |
| `CORE42_INPUT_COST_PER_1M` / `_OUTPUT_` | Optional; unset means cost is `null`, never `0.0`. |

### Editing

- A contract change (records, settings, reference lists, bundle) → update
  `docs/schema.md` and `docs/api.md` in the same change.
- A change shared by both services (the Core42 layer, the job layer, storage) → change
  both in the same commit; the copies must not diverge.
- Never commit a `.env`, a key, a tenant export or run output.
