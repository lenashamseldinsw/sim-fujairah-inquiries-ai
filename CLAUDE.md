# Development Guide — NoveIntelligence services (`noveintel` branch)

This branch holds the two NoveIntelligence analytics services and one supporting
library, and nothing else:

```
noveintel-inquiries/    Domain 03 — Customer Inquiries Analytics   (prefix NOVEINQ_)
noveintel-complaints/   Domain 02 — Complaints Analytics           (prefix NOVECOMP_)
noveintel-ingest/       Document ingestion: Excel → pgvector        (prefix NOVEINGEST_)
```

The two services are self-contained, independently deployable FastAPI services (Azure
Functions or on-prem); `noveintel-ingest` is a library and CLI. The Streamlit application they were ported from (`demo/`, `real/`) lives on
the `main` and `real` branches and is **not** on this branch; this branch is not merged
back. Do not reintroduce it, and do not make either service import from outside its
own folder.

## 📋 Documentation Policy

**⚠️ DO NOT CREATE NEW .MD FILES.** The complete allowance is:

- **CLAUDE.md** (this file) — how the repository works and how to edit it;
- **README.md** (root) — what is here and where to start;
- **MEMORY.md** — the auto-memory index;
- per service, exactly four: `README.md`, `docs/api.md`, `docs/schema.md`,
  `docs/deployment.md`. A caller integrating the API needs them next to the code;
- `noveintel-ingest/README.md` — the library has no API, so one document.

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
| 1 Parser + engine | `engine/` (`parse`, `compute`, `frameworks`, `taxonomy`, `redact`, `wording`, `localize`) | Computes **every** number, on frozen labels. Pure; builds on `models/`, never on `api/`. |
| 2 Classifier | `classification/` (`rules`, `model`, `rootcause`, `umbrellas`, `classify`) | Creates labels — never a number about the population. |
| 3 Narrative writer | `narratives/` (`prompts`, `rules`, `context`, `writer`) | Writes prose only, from the engine's numbers. |

`analysis/` names the qualitative items S4–S6 table (frictions, notification
opportunities, guidebook gaps); the model assigns whole **case groups** to each
item and the engine sums them, so no count comes from a model (R6). `analysis/faqs.py`
is Section 04's FAQ detection — see the invariant below. `report/` places
everything into the report's sections (`assemble`), renders Word (`word`) and the companion workbook
(`workbook`). `pipeline.py` wires it and owns failure classification.

### Invariants worth knowing before editing

- **One denominator (R2).** `S` is the in-scope set after artefact rows, duplicates and
  the X4 scope; the parse log accounts for everything outside it. Cover total = Σ S3.2
  table = Σ per-type workbook sheets — `tests/test_pipeline.py` pins it.
- **Frozen labels are never overwritten.** A record's `label_*` fields come from an
  earlier run, stored by the platform; the classifier fills only what is missing.
- **Provenance is set by the pipeline**, never by the model: `auto` «آلي - موثوق»
  (keyword rules, or copied from an identical or near-identical case —
  `near_duplicate_similarity`, 0.95, embeddings on description + resolution; reviewers had
  labelled such Q2 pairs alike 95% of the time), `llm` «نموذج», `auto_corrected`
  «آلي - مُصحّح», `deep_review` «يدوي - مُراجع». **There is no human review queue** —
  «يدوي - مُراجع» is the deep AI review (`DEEP_MODEL` tier with `reasoning_effort` —
  gpt-5.1 does not reason unless asked; effort `low` by default — batches of 10, more examples)
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
- **Required inputs are decided in one place**, `models/requests.py::
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
- **Overlaps in `pipeline._run`**, which reads as the list of stages; each stage is a
  method of `pipeline._Run`, the run's state, and `_English` holds the translation
  side. The analysis runs in the background from stage 3, and FAQ detection beside it
  once the umbrellas exist (`start_faqs`); umbrella discovery, `compute` (which needs
  the umbrellas, never the analysis) and the narrative of the sections that do not use
  the analysis go ahead without them. `FAQ_COVERAGE` is therefore not a `compute` key:
  it is summed from the FAQ labels when the late figures are built. The narrative is
  three independent calls (`sections.EARLY_GROUPS` A and B, then `LATE_GROUP` C once
  the analysis and FAQs are in —
  Sections 04–05, the conclusion, the friction points), and
  `write_narratives(on_part=…)` hands each finished group to its English translation.
  The early groups read `metrics_early`, a dict nothing writes to afterwards; the full
  figures are a new dict. Progress is monotonic across the threads.
- **The report is the sample output's structure** (BO, 2026-10-14): executive summary,
  Sections 01–05 (statistics, service focus, root causes, digital-content opportunities,
  roadmap), conclusion, appendices. `models/enums.ReportSection` is what a tenant may
  ask for; `SECTION_TITLES` the printed names, which a request may use.
- **`sections.py` is the section registry** — one `Section` per section: title,
  numbering, X8, the analysis items it needs, its narrative fields and which call
  writes them, the context keys only it reads. The pipeline, the writer's split and
  `report/assemble.BUILDERS` (one builder per section) all read it. Adding a section is
  an entry, a builder and its prompt lines; `tests/test_sections.py` fails when one is
  missing or when the enabled entries and `ReportSection` disagree. The Definition
  Sheet's other sections (the Fujairah classification-map subsections, customer
  journey, guidebook gaps, digital transformation, AI use cases) are entries with
  `enabled=False`: real code, never shown and not exercised by any test. Bringing one
  back is `enabled=True` plus its key in `ReportSection` — and a test for it first.
- **Tenants choose sections by name** (`options.sections`). Sections do not depend on
  each other: a section's `analysis` lists what it needs from the qualitative analysis
  (Section 04 → FAQs, Section 05 → journey + FAQs, appendices → journey), and only
  those items run. The narrative tools carry only the fields asked for (shown section,
  input present); a section's `reads` lets `sections.prune_context` drop prompt data
  only hidden or disabled sections read.
  Umbrella discovery is not section-gated: with X8 on it always runs, because D8 is a
  label the platform stores.
- **Branding:** no `brand` → NoveAI Navy `#201853` / Magenta `#7E2362` (Prerequisites
  §5); the within / near / over colours are locked (`entity.TIMELINESS_COLORS`).
- **FAQs are questions, never answers** (handoff scope: "FAQ authoring … not part of
  the tool"). `analysis/faqs.py` embeds each case's root cause (else redacted
  description), groups by `faq_group_similarity` (0.88, calibrated on the Q2 master),
  shortlists catalogue entries by embedding, and has the model judge each group
  covered / partial / not covered — every group behind `FAQ_COVERAGE`, small ones too
  (inheriting a nearby group's verdict was wrong more often than right). The largest
  groups get a customer question; one call merges same-question groups. The verdicts
  are per-case labels (`faq_id`, `faq_status`, `faq_match`) that
  `engine.compute.faq_coverage` / `faq_catalogue_volume` sum. It starts after umbrella
  discovery (its population is defined by umbrella), on the analysis pool's second
  worker. No tool schema may ask for an answer; `tests/test_faqs.py` checks.
- **Embeddings are inquiries-only** — `core42/embeddings.py` is not one of the shared
  Core42 files and reads its own settings (`CORE42_MODEL_EMBED`,
  `CORE42_EMBED_DIMENSIONS`), so the eight shared files stay identical to the complaints
  service's. Approved models only: `text-embedding-3-large` (default), `qwen3-embedding`.
- **The classifier's answer is short on purpose** (output is billed at 8× input): batch-local
  ids (`c1`…), sub-classification codes (`M3.1` = third main service, first sub, in
  taxonomy order — `prompts.label_codes`), short keys, a ≤ 5-word reason naming the decisive fact in the reply (not the topic —
  77% of reasons cite what the agent did or said, against 38% when it was an 8-word "what
  decided it") and no
  `evidence` (the BO prompt defines it like the reason; its schema lists only the
  reason). `model.ModelClassifier._long` maps answers back to full labels, so nothing
  downstream reads codes. First pass in batches of 40 with ≤ 20 examples. Measured on
  500 human-reviewed Q2 cases: $1.19 → $0.66, main-service accuracy 76.0% → 76.6%,
  sub 68.2% → 68.0%, root causes as close to the reviewed ones. Re-measure before
  changing batch size, examples or the schema — batches of 60 with 12 examples were
  tried and sent 3× more cases to the deep review (dearer, sub accuracy −1.2).
- **Umbrella discovery answers compactly**: each umbrella lists its member root-cause ids
  (≈ 3 tokens each) instead of one assignment object per root cause (≈ 15); the first
  chunk runs on `CHAT_MODEL`, later chunks on `LIGHT_MODEL`; up to three passes send back
  only the ids a model left out. Grouping varies run to run even on gpt-5.1 (Rand 0.84
  between two runs); the mixed setup sat inside that band.
- **Read every tool call, never only the first** — `core42.tool_input(message)` merges
  all `tool_use` blocks (lists concatenated, empty fields filled). A model asked for one
  call sometimes answers in several; reading the first silently dropped the rest (the
  deep review returned 1 answer for 7 cases). Every call site uses it; the classifier
  also asks once more for any case still missing an answer.
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

`cd noveintel-inquiries && uv run pytest` — 445 tests, no network. `tests/fakes.py`
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

## Ingestion library (`noveintel-ingest/`)

Excel workbook → one chunk per row, serialised `Document: … | Sheet: … | Column:
value | …` → Core42 embeddings → pgvector. Its README describes the reader and the
store; what to know before editing:

- **Imports nothing from either service, and neither service imports it.** The bridge
  is data: `faq-catalogue` writes `reference.faq_catalogue` JSON. The inquiries
  pipeline embeds what it needs per run (FAQ detection, `core42/embeddings.py`) and
  never queries the vector store — keep the store out of the stateless pipeline.
- **Approved embedding models only** — `settings.ALLOWED_EMBEDDING_MODELS`:
  `text-embedding-3-large` (Embeddings 3 Large, default — measured, README) and
  `qwen3-embedding` (Qwen3 Embedding 8B — selectable, but overloaded on Core42 when
  tried on 2026-10-16 and never measured). The gateway serves others (`embed-v-4-0`); never add one that is
  not on the client's approved list.
- **A collection is bound to one model and size** (`ingest_collections`); mismatches
  are refused, never mixed. Vectors are Matryoshka-truncated to
  `NOVEINGEST_EMBED_DIMENSIONS` (1024) client-side, which keeps HNSW available (≤ 2000).
- **Chunk ids are content-addressed**: a re-ingest embeds only changed rows and syncs
  in one transaction; a collection is created only after embedding succeeds.
- **Gateway errors are classified by HTTP status**, not exception class: 429 and every
  5xx retry (Core42 answers outages with an unmapped 5xx, "no healthy upstream"),
  401/403 is the key, other 4xx are refused at once.
- **Embedded text is normalised** (`serialize.normalize_text`: whitespace, tatweel);
  queries get the same. Stored `fields` stay exactly as read.
- **Re-measure before changing the model**: `scripts/compare_models.py <xlsx>
  scripts/adpf_faq_queries.json` scores both approved models on question→answer and
  on customer phrasing (with unanswerable queries).
- **Python 3.12**, because the embedded Postgres the tests use (`pgserver`) has no
  newer wheels. Real runs set `NOVEINGEST_PG_DSN` — locally the Homebrew
  `postgresql@17` + `pgvector` database `noveintel` (README).
- `uv run pytest` — 37 tests against an embedded Postgres, no network.

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
`concurrency` (one process-wide in-flight cap around the network call only, AIMD on 429s) and
`tokens` (per-stage, per-run accounting). Call sites name a **tier** (`CHAT_MODEL`,
`FAST_MODEL`), never a deployment. Settings are cached: restart after editing `.env`.

| Variable | What it does |
|---|---|
| `CORE42_API_KEY` | Required. |
| `CORE42_BASE_URL` | No `/chat/completions` suffix. |
| `CORE42_MODEL` / `CORE42_MODEL_FAST` | Reasoning tier (analysis, narratives) / bulk tier (classification). |
| `CORE42_MODEL_LIGHT` | The light tier (default `CORE42_MODEL`; set `gpt-4.1-mini`): umbrella discovery after its first chunk. Measured unfit for the classifier's first pass and the FAQ judge — keep it off them. |
| `CORE42_MODEL_EMBED` / `CORE42_EMBED_DIMENSIONS` | Inquiries only: FAQ detection's embedding model (approved: `text-embedding-3-large`, default; `qwen3-embedding`) and stored size (1024). |
| `CORE42_MODEL_DEEP` / `LLM_DEEP_REASONING_EFFORT` | The deep review's model (default `CORE42_MODEL`) and reasoning effort (default `low`). A model rejecting `reasoning_effort` is asked again without it. |
| `LLM_MAX_CONCURRENCY` | In-flight requests per process, default 5 (matches the classifier's 5-batch fan-out). Raising it further usually means more 429s. |
| `LLM_ADAPTIVE_CONCURRENCY` | Default `true`: a 429 halves that cap (once per 10 s) and clean calls grow it back, so instances sharing a key back off together. |
| `LLM_MAX_RETRIES` / `LLM_RETRY_DELAY` | Attempts = retries + 1. |
| `CORE42_TOOL_MODE` | `auto`, `native` or `json`. |
| `CORE42_INPUT_COST_PER_1M` / `_OUTPUT_` | Optional; unset means cost is `null`, never `0.0`. |

### Editing

- A contract change (records, settings, reference lists, bundle) → update
  `docs/schema.md` and `docs/api.md` in the same change.
- A change shared by both services (the Core42 layer, the job layer, storage) → change
  both in the same commit; the copies must not diverge.
- Never commit a `.env`, a key, a tenant export or run output.
