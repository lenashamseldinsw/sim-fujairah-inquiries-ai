# NoveIntelligence — Customer Inquiries Analytics

A headless FastAPI service that turns a period's customer-inquiry cases into an analysed
report: a six-stage pipeline classifies every case, finds the patterns and friction
points behind them, checks each against the service guidebook, and produces an Arabic
and English Word report, the report as structured data, and a per-case Excel workbook.

Ported from the Streamlit application in [`real/inquiries-flow/`](../real/inquiries-flow),
following [the porting guide](../api-youssef-porting-guide.md). The six stages are
**vendored unchanged** — they are the thing under parity test — and everything around
them is new: the contract, the job layer, storage, configuration and the Azure wrapper.

---

## The one thing to know

**Runs are asynchronous.** `POST /v1/inquiries` does *not* return a report. It answers
`202` with a `job_id`; you poll `GET /v1/jobs/{job_id}` until `status` is terminal and
read `result`.

Module 01 (Customer Data Analytics) answers its work route synchronously because a
report there is two model calls. A inquiries run is dozens of sequential calls across six
stages — minutes on a real export, far past the **230-second ceiling Azure's load
balancer puts on an HTTP response, which no plan changes**. The porting guide's §5.6
names this case: when a run cannot fit in about 200 seconds even in the best case, a
synchronous route is the wrong design.

Everything else is module 01's shape unchanged — same identity model, same error
envelope, same storage contract, same config conventions — so a caller who has
integrated that module will find nothing else surprising here.

---

## Quick start

```bash
cd noveintel-inquiries
cp .env.example .env          # put your CORE42_API_KEY in it
uv sync --extra api --extra serve
uv run uvicorn noveintel_inquiries.api.app:app --reload
```

Then open <http://localhost:8000/docs>.

```bash
# Is it configured?
curl -s localhost:8000/ready | jq

# Turn a real export into request bodies. This is where the spreadsheet
# knowledge lives now — the API itself takes structured records.
uv run python scripts/make_fixtures.py path/to/export.xlsx --out fixtures/

# Check a payload. Free, no model call, answers in milliseconds.
curl -s -X POST localhost:8000/v1/inquiries/validate \
     -H 'content-type: application/json' -d @fixtures/happy.json | jq

# Start a run. This spends money and takes minutes.
uv run python scripts/smoke.py fixtures/happy.json
```

---

## The API

| Route | What it does |
|---|---|
| `GET /health` | Liveness. No settings, no network. |
| `GET /ready` | Whether the service can accept a run: config resolves and there is a job store. |
| `POST /v1/inquiries/validate` | Runs stage 1 alone. No model call, no cost. |
| `POST /v1/inquiries` | Accepts a run. `202` with a `job_id`. |
| `GET /v1/jobs/{job_id}` | Polls it. `result` holds the bundle once it has succeeded. |

[`docs/api.md`](docs/api.md) has the per-route reference, curl examples and every
error and warning code. [`docs/schema.md`](docs/schema.md) covers every field,
including what OpenAPI types only as `object`.

### Validate before you run

The work route is asynchronous, so without the validate route the only way to discover
a missing column is to start a job and poll until it fails. Validate first — it is
free and it answers immediately.

### `include_english=false` roughly halves a run

The English report is a full translation of all nine sections and is the single
largest block of tokens in a run. Turn it off unless an English document is wanted.

---

## Configuration

Everything comes from the environment or a `.env` file — never from a Streamlit
secrets store. [`.env.example`](.env.example) lists every setting with its default;
only `CORE42_API_KEY` is required.

| Group | Prefix | Holds |
|---|---|---|
| `Settings` | `CORE42_` | Gateway: key, base URL, the reasoning and bulk model tiers, timeout |
| `PricingSettings` | `CORE42_` | `INPUT_COST_PER_1M`, `OUTPUT_COST_PER_1M` — both optional |
| `StorageSettings` | `NOVEINQ_STORAGE_` | Backend, directory, container, public base URL |
| `JobSettings` | `NOVEINQ_JOB_` | Backend, directory, TTL, runtime ceiling, concurrency |
| `ApiSettings` | `NOVEINQ_` | App API key, log level, max records |

Settings are cached and the Core42 client is a module-level singleton, so **editing
`.env` while the service runs changes nothing.** Restart the process.

### Costs are null rather than zero when unpriced

With `CORE42_INPUT_COST_PER_1M` / `CORE42_OUTPUT_COST_PER_1M` unset, a run reports its
tokens, a `null` cost, and a `pricing_not_configured` warning. An unpriced run and a
free one are different facts, and the service will not collapse them into a `0.0` that
ends up in a finance report.

---

## Deployment

### On-prem / anywhere with a process manager

```bash
uv sync --extra api --extra serve
uv run uvicorn noveintel_inquiries.api.app:app --host 0.0.0.0 --port 8000
```

### Azure Functions

```bash
uv sync --extra api --extra azure
uv export --extra api --extra azure --no-dev --no-emit-project \
    --format requirements-txt -o requirements.txt
func start          # /health answers at the ROOT, not /api/health
```

`function_app.py` and `host.json` are the entire Azure layer. Delete them and the
service is untouched — nothing under `noveintel_inquiries/` imports `azure.*`, and a test enforces it.

`host.json` sets `routePrefix: ""`. **This is mandatory**: the default prefixes every
route with `/api`, which FastAPI knows nothing about, so every request would 404.

App settings to set: `CORE42_API_KEY` (as a Key Vault reference),
`CORE42_REQUEST_TIMEOUT=240`, and the pricing rates. Leave `NOVEINQ_API_KEY` unset —
`AuthLevel.FUNCTION` means the platform checks `x-functions-key` before a request
reaches the app.

### Durability: pick a job backend and a dispatcher

Two independent settings, and the defaults are the development ones.

| | `NOVEINQ_JOB_BACKEND` | `NOVEINQ_JOB_DISPATCH` |
|---|---|---|
| **Development / single box** | `local` | `inprocess` |
| **Load-balanced, runs may be lost on restart** | `table` | `inprocess` |
| **Production** | `table` | `queue` |

**`backend`** says where job state lives. `local` keeps it in the worker's own memory,
mirrored to disk: a poll only finds a job on the instance that accepted it, so two
instances behind a load balancer 404 each other's jobs. `table` is Azure Table
Storage — any instance can serve any poll.

**`dispatch`** says where the run executes. `inprocess` runs it on the worker's event
loop, so the run dies with the worker. `queue` enqueues it for a queue-triggered
function; a message whose handler died is redelivered, and the run starts again.

> A redelivered run **starts over, it does not resume.** The stages are not
> checkpointed, and stitching one process's stage 4 onto another's stage 5 would
> produce a report whose figures came from two different runs.

With `dispatch=queue` set, `function_app.py` wires up:

* a **queue trigger** (`run_analysis_job`) that runs the pipeline with no HTTP
  connection open, so the 230-second ceiling does not apply — set `functionTimeout`
  in `host.json` above your longest expected run;
* a **poison-queue handler** (`run_analysis_job_poison`) that marks a job failed once
  its message has exhausted every delivery, so nobody polls a run that will never
  finish.

The request is stored in the document store under `_pending/` when the job is
accepted, because a queue message caps at 64 KiB and a real export is megabytes. It
is deleted when the run reaches a terminal state.

```bash
NOVEINQ_JOB_BACKEND=table
NOVEINQ_JOB_DISPATCH=queue
NOVEINQ_JOB_CONNECTION_STRING=<storage connection string>
NOVEINQ_JOB_QUEUE_NAME=analysis-runs
```

**Both functions must agree on the backend.** With `local`, the queue worker writes
to its own process memory and the HTTP instance serving the poll never sees it — set
`table` whenever you set `queue`.

**On a Consumption plan an idle worker is recycled**, which kills an in-process run.
With `dispatch=queue` the message is redelivered and the run resumes on another
worker, which is the main reason to use it. Still prefer an always-on plan.

---

## Layout

```
noveintel-inquiries/
├── function_app.py           AZURE ONLY — the ASGI adapter, ~5 lines
├── host.json                 AZURE ONLY — routePrefix "", timeout, logging
├── .funcignore               what must never reach wwwroot
├── requirements.txt          GENERATED by `uv export`; Azure installs from it
├── docs/                     api.md, schema.md
├── scripts/                  make_fixtures.py, smoke.py — excluded from deployment
├── tests/                    contract, API, storage, jobs, period, parity
└── noveintel_inquiries/
    ├── config.py             five pydantic-settings groups
    ├── pipeline.py           the entry points: validate_records, generate_report
    ├── exceptions.py         StageFailure — defined where the core can see it
    ├── api/                  app, routes, deps, errors + models/ (the contract)
    ├── engine/               the deterministic part: period resolution
    ├── jobs/                 the async job layer: store, runner
    ├── storage/              DocumentStore protocol, local store, key layout
    ├── core42/               VENDORED — the shared Core42 gateway integration
    ├── reporting/            VENDORED — sword_word_builder
    ├── resources/            VENDORED — the service guidebook the gap analysis reads
    └── stages/               VENDORED — the six pipeline stages, unchanged
```

### Why there is no `engine/` + `narratives/` split

The porting guide's rule 3 asks for a deterministic layer that computes every figure
and a narrative layer that writes prose around them. Module 01 is built that way. This
module is not, and forcing it would have been a rewrite rather than a port: its stages
**interleave** deterministic work with model calls by design — stage 2 classifies by
rule, stage 3 hands the remainder to the model, stages 4 and 5 reason over both.

So the rule is honoured in substance rather than in shape. `engine/` holds the part
that genuinely is pure and is shared with module 01 — resolving the reporting period —
and everything else the stages compute is surfaced as the bundle's **`metrics`**, which
is the ground truth a reader checks the prose against. `docs/schema.md` says which
figures are computed and which are written.

### What was changed in the vendored stages

The analysis is untouched. `tests/test_engine_parity.py` compares every stage byte for
byte against `real/inquiries-flow/pipeline/` and fails on any difference except these,
each of which is named there:

| File | Change |
|---|---|
| `llm.py` | Relative import in place of a `sys.path` insertion |
| `orchestrator.py` | Vendored guidebook path; `include_english` |
| `stage5_gap.py` | Vendored guidebook path |
| `stage6_artifacts.py` | Branding injection; the `include_english` gate |
| `stage6_json_report.py` | A stable `key` on each chart |
| `state.py` | The `branding` field |
| `build_report_{ar,en}.py` | Vendored Word builder; per-run logo |

---

## Known limitations

**Chart severity colours are not brandable, deliberately.** `entity.brand` now
drives the document's chrome — headings, banners, table headers, the cover, the table
of contents — and the accent slot in every chart. What it does *not* touch is the red
in the severity palette: red means critical, the same way the platform-locked status
colours do, and repainting it in a tenant's brand would destroy meaning rather than
apply an identity. The neutral greys beside it are left alone for the same reason.

**A run sent with no `brand` renders exactly as it always has.** `BrandColors` defaults
to the NoveAI platform palette because it is a shared contract model and must carry no
organisation's colours — but those defaults are not what an unbranded report uses. The
request only carries `brand` when the caller actually set it (`model_fields_set`), and
the builder falls back to its own design palette when it is absent. Without that
distinction, every existing report would silently repaint navy.

**Parity covers stage 1 and the vendoring, not a full run.** A genuine end-to-end
parity test would cost a full run against the live gateway on every CI build. What is
tested is that the stages are byte-identical to the originals, that the column contract
has not drifted, and that stage 1 reaches the same verdict on real input. Use
`scripts/smoke.py` for the rest, deliberately.

---

## Testing

```bash
uv run pytest              # 148 tests, no gateway and no network needed
```

The engine, the contract, the error envelope, storage and the job layer are all real.
Only the *run* is stubbed — a genuine one is minutes of model calls, and none of the
promises under test depend on what the model says.

Parity tests skip when `real/inquiries-flow/` is not in the checkout, which is the case
in a deployed service.
