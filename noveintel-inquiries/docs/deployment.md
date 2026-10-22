# Deployment — Customer Inquiries Analytics

How to run this service on **Azure Functions** or on an **on-prem server**. The code
is the same in both cases; only the settings differ.

The complaints and inquiries services are deployed separately. This document covers
**noveintel-inquiries**; `../noveintel-complaints/docs/deployment.md` is its twin, with the
`NOVECOMP_` prefix.

---

## Pick a setup

| | Azure (recommended) | On-prem server |
|---|---|---|
| Runs the API | Azure Function App | `uvicorn` behind your own reverse proxy |
| Report files | Azure Blob Storage | A folder on the server's disk |
| Job status | Azure Table Storage | The server's memory, mirrored to disk |
| Long runs | Azure Storage queue + worker function | Run inside the API process |
| Survives a restart | Yes — the run starts again | No — running jobs are reported failed |
| More than one instance | Yes | No — run exactly one |

The settings for each are in the presets at the bottom of this page.

---

## Azure

### What to create

| Resource | Notes |
|---|---|
| **Function App** | Linux, **Python 3.12** or 3.13. 3.11 will not start: the code needs 3.12+. |
| **Hosting plan** | **Premium (EP1) or Dedicated.** Not Consumption — see *Timeouts* below. |
| **Storage account** | The Function App needs one anyway. The same account holds the queue, the job table and the report files. |
| **Key Vault** (recommended) | For `CORE42_API_KEY` and the storage connection strings. |
| **Application Insights** (optional) | Logging is already wired for it. |

**Sharing one storage account between the two services is fine.** Each service
uses its own queue, table and container by default, so they cannot see each
other's work:

| | Queue | Table | Container |
|---|---|---|---|
| inquiries | `inquiries-runs` | `inquiriesjobs` | `inquiries-reports` |
| complaints | `complaints-runs` | `complaintsjobs` | `complaints-reports` |

Only override these names if you know why; if you do, keep them different per
service.

### Created automatically

You do not need to create the queue, the poison queue, the table or the blob
container. Each is created on first use.

### Timeouts

There are two timeouts, and **they must agree**:

| Where | Setting | Default |
|---|---|---|
| `host.json` | `functionTimeout` — how long Azure lets a function run | `01:15:00` (75 min) |
| App setting | `NOVEINQ_JOB_MAX_RUNTIME_SEC` — how long the code lets a run go | `3600` (1 hour) |

The shipped values agree: Azure's limit sits above the code's, so a run that is too
long is stopped by the code, recorded `runtime_exceeded`, and not retried. **If you
raise `NOVEINQ_JOB_MAX_RUNTIME_SEC`, raise `functionTimeout` with it.** If Azure's
timeout is the shorter one, a long run is killed, retried from the start, killed
again, and finally marked `delivery_failed` — paying for the run several times over.

The Consumption plan cannot go past 10 minutes, which is too short for a real
export, and it shuts down idle workers. That is why it is not supported.

#### Sizing the ceiling for a tenant's volume

Classification dominates a large run: about four cases in five go to the model, in
batches of 40, `LLM_MAX_CONCURRENCY` (default 5) at a time; the uncertain ones get a
deep review in batches of 10 with low reasoning. With root causes on (X8), every case
goes to the model — the rule chain cannot write a root cause. After classification the
journey analysis runs in the background, and FAQ detection beside it once the umbrellas
exist; the figures and the narrative of every section that does not use them go ahead
without them. The
narrative is three parallel calls — the descriptive sections, the root-cause sections,
and (once the analysis is in) Sections 04–05 with the conclusion and friction points —
and each is translated the moment it is final. Measured against Core42 (`gpt-5.1`), a
40-case run with root causes on and the sample output's sections:

| Step | Cost |
|---|---|
| Classification | measured on 500 human-reviewed ADPF Q2 cases, X8 on: 3.9 min, 16 calls, 443 input and 76 output tokens per case — ≈ $0.66 per 500 cases at gpt-5.1 list prices ($1.25 / $10 per 1M); 3–11% of cases deep-reviewed (the share varies run to run). Before the short schema and batches of 40: 5.7 min, $1.19 |
| Umbrella discovery (X8) | ≈ 1 min per 350 distinct root causes, sequential; ≈ 12 s at 40 cases. Compact output with `CORE42_MODEL_LIGHT=gpt-4.1-mini`: ≈ $0.01 per later chunk (≈ $0.15 for Q2's 5,766 root causes, from ≈ $1.56) |
| Analysis (journey, FAQs), in the background | 30–40 s at 40 cases; the first two narrative groups are written meanwhile |
| FAQ detection at scale | the ADPF Q2 master with the 142-question catalogue: 8,860 cases → ≈ 3,100 question groups, ≈ 1,800 judged; 4–5.5 min, ≈ 104 calls, ≈ 650 k input and 50–75 k output tokens (embeddings included). It starts after classification and umbrella discovery and overlaps only the figures and the first two narrative groups (≈ 70 s), so on a Q2-sized run it adds about 3–4 min before the Section 04–05 narrative can start |
| Arabic narrative, three groups | ≈ 70 s including the wait for the analysis, independent of volume |
| English translation still running after the Arabic | ≈ 20 s |

Two 40-case runs took 133 s and 135 s (410 s with the narrative as one call, 529 s
before any overlap). The three groups send the figures three times, so the narrative's
input tokens are about 2.3 times what one call used; the output is unchanged. So a 1,000-case export finishes well
inside the default hour, but a quarter like ADPF Q2 2026 (10,630 cases, root-cause extraction on, ≈ 5,800 distinct causes) needs about
two hours: set `NOVEINQ_JOB_MAX_RUNTIME_SEC=9000` and `functionTimeout` to `02:45:00` on
a Premium or Dedicated plan. Frozen labels from an earlier pass skip classification
entirely.

The 230-second limit on HTTP responses does not apply here: the API answers
immediately and the work runs in the queue worker.

#### Several instances share one gateway

`LLM_MAX_CONCURRENCY` caps model calls in flight **per worker process**, but Core42
meters the key, so the gateway sees the sum: instances × `FUNCTIONS_WORKER_PROCESS_COUNT`
(default 1) × `LLM_MAX_CONCURRENCY`, across both services if they share a key. Two things
keep that sum in check:

* **The cap adapts** (`LLM_ADAPTIVE_CONCURRENCY`, on by default). A 429 halves a
  process's cap, at most once per 10 s, and each round of clean calls raises it by one
  back to `LLM_MAX_CONCURRENCY`. Instances under one quota back off together without
  talking to each other; an instance that never sees a 429 runs at the full cap.
* **Cap the instance count.** Adapting slows instances down but does not stop more from
  starting. Set the Function App's maximum scale-out limit (the *Scale out* blade;
  the site property `functionAppScaleLimit`) so that the sum above stays within the
  concurrency Core42 grants the key.

### App settings

**Required**

| Setting | Value |
|---|---|
| `CORE42_API_KEY` | The Core42 key — as a Key Vault reference |
| `CORE42_BASE_URL` | `https://api.core42.ai/v1` |
| `CORE42_MODEL` | e.g. `gpt-5.1` |
| `CORE42_MODEL_FAST` | e.g. `gpt-5.1` (may equal `CORE42_MODEL`) |
| `CORE42_MODEL_DEEP` | Optional. The deep review's model; defaults to `CORE42_MODEL` |
| `NOVEINQ_STORAGE_BACKEND` | `blob` |
| `NOVEINQ_STORAGE_CONNECTION_STRING` | The storage account's connection string, **including `AccountKey`** — without it callers get links they cannot open (see below) |
| `NOVEINQ_JOB_BACKEND` | `table` |
| `NOVEINQ_JOB_DISPATCH` | `queue` |
| `NOVEINQ_JOB_CONNECTION_STRING` | The storage account's connection string. **Set this even if you are not using the queue**: the worker functions are always registered and fail to start without it |

**Optional**

| Setting | Default | Notes |
|---|---|---|
| `CORE42_INPUT_COST_PER_1M`, `CORE42_OUTPUT_COST_PER_1M` | unset | USD per million tokens. Unset means costs are reported as empty, not zero |
| `CORE42_REQUEST_TIMEOUT` | `240` | Seconds per model call |
| `NOVEINQ_STORAGE_SAS_TTL_SEC` | `604800` | How long download links work (7 days) |
| `NOVEINQ_JOB_MAX_RUNTIME_SEC` | `3600` | Keep below `functionTimeout` |
| `NOVEINQ_JOB_TTL_SEC` | `86400` | How long a finished job can still be polled. Report files outlive this |
| `NOVEINQ_JOB_MAX_CONCURRENT` | `2` | Runs at once per worker. Each holds its whole export in memory |
| `NOVEINQ_MAX_RECORDS` | `100000` | Larger exports are refused up front |
| `LLM_DEEP_REASONING_EFFORT` | `low` | How hard the deep review reasons (`none` · `minimal` · `low` · `medium` · `high` · `xhigh`). gpt-5.1 does not reason without it |
| `LLM_MAX_CONCURRENCY` | `5` | Model calls in flight per worker. Raising it usually makes runs *slower* (more 429s) |
| `LLM_ADAPTIVE_CONCURRENCY` | `true` | Halve the in-flight cap on a 429 and grow it back on clean calls; `false` keeps it fixed. See *Several instances share one gateway* |
| `NOVEINQ_LOG_LEVEL` | `INFO` | |

A setting declared but left blank means its default, as if it were not there — a
copied template with empty values is safe.

**Leave unset:** `NOVEINQ_API_KEY`. Azure already checks the function key
before a request reaches the app; setting both makes callers send two keys.

### Download links

With `blob` storage, every file in a result comes with a **signed link** that
works for `NOVEINQ_STORAGE_SAS_TTL_SEC`, and `expires_at` says when it stops.
The caller needs no Azure access to use it.

Signing needs the account key. If the connection string has no `AccountKey`
(for example a SAS-only string), links are plain blob URLs with
`expires_at: null`, and only someone with their own access to the account can
open them.

### Networking

The Function App calls `https://api.core42.ai`. If it is VNet-integrated with
restricted outbound traffic, allow that host.

### Deploy

```bash
cd noveintel-inquiries
# requirements.txt is what Azure installs — regenerate it after any dependency change
uv export --extra api --extra azure --no-dev --no-emit-project \
    --format requirements-txt -o requirements.txt
func azure functionapp publish <function-app-name> --python
```

`.funcignore` keeps secrets, tests, docs and local data out of the package.

### Check it worked

```bash
URL=https://<function-app-name>.azurewebsites.net
KEY=<function key>

curl -s "$URL/health" -H "x-functions-key: $KEY"   # {"status":"ok"} — at the root, not /api/health
curl -s "$URL/ready"  -H "x-functions-key: $KEY"   # storage.backend "blob", storage.available true
```

In the portal, the Function App should list three functions:

| Function | What it does |
|---|---|
| `http_app` | The API |
| `run_analysis_job` | Picks runs up from the queue and runs the pipeline |
| `run_analysis_job_poison` | Marks a run failed after it has crashed on every retry |

Then post a small file to `/v1/inquiries/validate` (free), and a small run to
`/v1/inquiries` (costs tokens), and poll it until it finishes. `scripts/smoke.py`
does all of that: `python scripts/smoke.py fixtures/happy.json --url "$URL" --function-key "$KEY"`.

### Calling it

**Every request needs the function key** in the `x-functions-key` header —
including `/health` and `/ready`. Azure checks it before the request reaches the
app, so the app cannot exempt any route.

That matters for monitoring: an uptime probe or a load-balancer health check must
send the key, or it will see `401` and report the service as down.

---

## On-prem

No Azure account and no Azure packages. Install without the `azure` extra:

```bash
cd noveintel-inquiries
uv sync --extra api --extra serve
cp .env.example .env          # set CORE42_API_KEY; the defaults below need nothing else
uv run uvicorn noveintel_inquiries.api.app:app --host 0.0.0.0 --port 8000
```

The defaults are already the on-prem settings: `local` storage, `local` jobs,
`inprocess` runs. Nothing tries to reach Azure, and the code never imports an
Azure library unless you choose a `blob` or `table` backend.

### What to know

* **Run exactly one instance.** Job status lives in that process's memory. A second
  instance behind a load balancer cannot see the first one's jobs, so polls 404.
* **A restart loses running jobs.** They come back as `failed` with
  `worker_restarted`. Finished jobs and their files are kept. Retrying is safe.
* **Put the folders somewhere persistent and backed up.** Set
  `NOVEINQ_STORAGE_DIR` and `NOVEINQ_JOB_DIR` to absolute paths, for example
  `/var/lib/noveintel-inquiries/storage`. The stored files include the reports and the per-case
  workbook — customer data.
* **Download links are `file://` paths** on the server by default, which callers
  on other machines cannot open. Either serve the storage folder from your web
  server and set `NOVEINQ_STORAGE_PUBLIC_BASE_URL` to its address, or have
  callers resolve `container` + `key` against the folder themselves.
* **Set `NOVEINQ_API_KEY`** if the service is reachable by anything other than a
  trusted gateway. Callers then send it as `X-API-Key`.
* Outbound access to `https://api.core42.ai` is the only network requirement.

---

## Presets

Copy the block that matches your setup into the app settings (Azure) or `.env`
(on-prem), alongside the `CORE42_*` settings.

**Azure — production**

```bash
NOVEINQ_STORAGE_BACKEND=blob
NOVEINQ_STORAGE_CONNECTION_STRING=<connection string with AccountKey>
NOVEINQ_JOB_BACKEND=table
NOVEINQ_JOB_DISPATCH=queue
NOVEINQ_JOB_CONNECTION_STRING=<connection string>
```

**On-prem — single server**

```bash
NOVEINQ_STORAGE_BACKEND=local
NOVEINQ_STORAGE_DIR=/var/lib/noveintel-inquiries/storage
NOVEINQ_JOB_BACKEND=local
NOVEINQ_JOB_DISPATCH=inprocess
NOVEINQ_JOB_DIR=/var/lib/noveintel-inquiries/jobs
```

**Local development** — nothing to set; the defaults write to `./storage` and
`./jobs`.

### Combinations that do not work

| Setting | Problem |
|---|---|
| `JOB_DISPATCH=queue` with `JOB_BACKEND=local` | The worker writes job status into its own memory, so polls never see progress |
| `JOB_DISPATCH=queue` with `STORAGE_BACKEND=local` | The worker may run on another machine and cannot read the request the API saved |
| `STORAGE_BACKEND=blob` without the `azure` extra | The startup log says so and `/ready` shows `storage.available: false`. Runs still produce an analysis, but no files are stored |
| More than one instance with `JOB_BACKEND=local` | Each instance only sees its own jobs |
