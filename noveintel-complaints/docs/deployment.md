# Deployment — Customer Complaints Analytics

How to run this service on **Azure Functions** or on an **on-prem server**. The code
is the same in both cases; only the settings differ.

The complaints and inquiries services are deployed separately. This document covers
**noveintel-complaints**; `../noveintel-inquiries/docs/deployment.md` is its twin, with the
`NOVEINQ_` prefix.

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
| App setting | `NOVECOMP_JOB_MAX_RUNTIME_SEC` — how long the code lets a run go | `3600` (1 hour) |

The shipped values agree: Azure's limit sits above the code's, so a run that is too
long is stopped by the code, recorded `runtime_exceeded`, and not retried. **If you
raise `NOVECOMP_JOB_MAX_RUNTIME_SEC`, raise `functionTimeout` with it.** If Azure's
timeout is the shorter one, a long run is killed, retried from the start, killed
again, and finally marked `delivery_failed` — paying for the run several times over.

The Consumption plan cannot go past 10 minutes, which is too short for a real
export, and it shuts down idle workers. That is why it is not supported.

The 230-second limit on HTTP responses does not apply here: the API answers
immediately and the work runs in the queue worker.

### App settings

**Required**

| Setting | Value |
|---|---|
| `CORE42_API_KEY` | The Core42 key — as a Key Vault reference |
| `CORE42_BASE_URL` | `https://api.core42.ai/v1` |
| `CORE42_MODEL` | e.g. `gpt-5.1` |
| `CORE42_MODEL_FAST` | e.g. `gpt-5.1` (may equal `CORE42_MODEL`) |
| `NOVECOMP_STORAGE_BACKEND` | `blob` |
| `NOVECOMP_STORAGE_CONNECTION_STRING` | The storage account's connection string, **including `AccountKey`** — without it callers get links they cannot open (see below) |
| `NOVECOMP_JOB_BACKEND` | `table` |
| `NOVECOMP_JOB_DISPATCH` | `queue` |
| `NOVECOMP_JOB_CONNECTION_STRING` | The storage account's connection string. **Set this even if you are not using the queue**: the worker functions are always registered and fail to start without it |

**Optional**

| Setting | Default | Notes |
|---|---|---|
| `CORE42_INPUT_COST_PER_1M`, `CORE42_OUTPUT_COST_PER_1M` | unset | USD per million tokens. Unset means costs are reported as empty, not zero |
| `CORE42_REQUEST_TIMEOUT` | `240` | Seconds per model call |
| `NOVECOMP_STORAGE_SAS_TTL_SEC` | `604800` | How long download links work (7 days) |
| `NOVECOMP_JOB_MAX_RUNTIME_SEC` | `3600` | Keep below `functionTimeout` |
| `NOVECOMP_JOB_TTL_SEC` | `86400` | How long a finished job can still be polled. Report files outlive this |
| `NOVECOMP_JOB_MAX_CONCURRENT` | `2` | Runs at once per worker. Each holds its whole export in memory |
| `NOVECOMP_MAX_RECORDS` | `100000` | Larger exports are refused up front |
| `LLM_MAX_CONCURRENCY` | `4` | Model calls in flight per worker. Raising it usually makes runs *slower* (more 429s) |
| `NOVECOMP_LOG_LEVEL` | `INFO` | |

A setting declared but left blank means its default, as if it were not there — a
copied template with empty values is safe.

**Leave unset:** `NOVECOMP_API_KEY`. Azure already checks the function key
before a request reaches the app; setting both makes callers send two keys.

### Download links

With `blob` storage, every file in a result comes with a **signed link** that
works for `NOVECOMP_STORAGE_SAS_TTL_SEC`, and `expires_at` says when it stops.
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
cd noveintel-complaints
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

Then post a small file to `/v1/complaints/validate` (free), and a small run to
`/v1/complaints` (costs tokens), and poll it until it finishes. `scripts/smoke.py`
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
cd noveintel-complaints
uv sync --extra api --extra serve
cp .env.example .env          # set CORE42_API_KEY; the defaults below need nothing else
uv run uvicorn noveintel_complaints.api.app:app --host 0.0.0.0 --port 8000
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
  `NOVECOMP_STORAGE_DIR` and `NOVECOMP_JOB_DIR` to absolute paths, for example
  `/var/lib/noveintel-complaints/storage`. The stored files include the reports and the per-case
  workbook — customer data.
* **Download links are `file://` paths** on the server by default, which callers
  on other machines cannot open. Either serve the storage folder from your web
  server and set `NOVECOMP_STORAGE_PUBLIC_BASE_URL` to its address, or have
  callers resolve `container` + `key` against the folder themselves.
* **Set `NOVECOMP_API_KEY`** if the service is reachable by anything other than a
  trusted gateway. Callers then send it as `X-API-Key`.
* Outbound access to `https://api.core42.ai` is the only network requirement.

---

## Presets

Copy the block that matches your setup into the app settings (Azure) or `.env`
(on-prem), alongside the `CORE42_*` settings.

**Azure — production**

```bash
NOVECOMP_STORAGE_BACKEND=blob
NOVECOMP_STORAGE_CONNECTION_STRING=<connection string with AccountKey>
NOVECOMP_JOB_BACKEND=table
NOVECOMP_JOB_DISPATCH=queue
NOVECOMP_JOB_CONNECTION_STRING=<connection string>
```

**On-prem — single server**

```bash
NOVECOMP_STORAGE_BACKEND=local
NOVECOMP_STORAGE_DIR=/var/lib/noveintel-complaints/storage
NOVECOMP_JOB_BACKEND=local
NOVECOMP_JOB_DISPATCH=inprocess
NOVECOMP_JOB_DIR=/var/lib/noveintel-complaints/jobs
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
