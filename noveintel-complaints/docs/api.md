# API reference — Customer Complaints Analytics

Base URL is the service root. On Azure Functions that is the site root, **not**
`/api` — `host.json` sets `routePrefix: ""` precisely so the paths here are the paths
everywhere.

All request and response bodies are JSON. All field names are `snake_case`. Record
fields additionally accept the normalised Arabic column name, and a payload may mix
the two.

---

## The shape of a run

```
POST /v1/complaints/validate    →  200   free, milliseconds, no model call
POST /v1/complaints             →  202   { job_id, poll_url, estimated_seconds }
GET  /v1/jobs/{job_id}          →  200   { status, progress, result?, error? }
                                          poll until status is terminal
```

`queued` and `running` mean poll again. `succeeded`, `failed` and `cancelled` are
terminal; a further poll tells you nothing new.

A run takes minutes. Poll every 10–15 seconds; polling every second only adds load.

---

## `GET /health`

Liveness. Dependency-free by design: a probe that failed when the model gateway was
down would have the host restart a service whose only problem is elsewhere.

```bash
curl -s localhost:8000/health
```
```json
{ "status": "ok" }
```

Never gated by `NOVECOMP_API_KEY`.

---

## `GET /ready`

Whether the service can actually accept a run. Configuration resolves and a job store
exists. It does **not** check that the gateway is reachable — that would cost a model
call per probe.

```bash
curl -s localhost:8000/ready
```
```json
{
  "status": "ready",
  "model": "gpt-5.1",
  "model_fast": "gpt-5.1",
  "auth_required": false,
  "max_records": 100000,
  "storage": { "backend": "local", "container": "complaints-reports", "available": true },
  "jobs": { "available": true },
  "pricing_configured": false
}
```

Storage and pricing are **reported but do not decide the answer**: neither stops a run
producing an analysis. A broken store costs the artefacts and says so in the result's
warnings; missing rates cost the cost figure and likewise say so.

The job store **does** decide it. Without one, an accepted run could never be reported
on, and accepting work we cannot answer for is worse than refusing it.

`503 not_configured` when `CORE42_API_KEY` is unset or the job store could not be
built. The process stays up — a 503 that names the problem beats a crash loop.

---

## `POST /v1/complaints/validate`

Runs stage 1 alone: column normalisation, the required-column check, and resolving
the period. **No model call, no cost, milliseconds.**

This route exists because the work route is asynchronous. Without it, the only way to
find a missing column is to start a job and poll until it fails.

```bash
curl -s -X POST localhost:8000/v1/complaints/validate \
     -H 'content-type: application/json' -d @fixtures/happy.json
```
```json
{
  "total_cases": 25,
  "columns": ["رقم_الطلب", "تفاصيل_الطلب", "..."],
  "schema": { "...": "stage 1's own validation result" },
  "period": {
    "granularity": "quarterly", "index": 1, "year": 2025,
    "start": "2025-01-05", "end": "2025-03-28",
    "label_ar": "الربع الأول 2025", "label_en": "Q1 2025"
  },
  "period_error": null
}
```

A `200` means the run will be **accepted**. It is not a promise that it will succeed:
stages 3–6 depend on the gateway, and no validation anticipates that.

`period` is `null` with `period_error` set when no record carried a readable date. The
run is still accepted; the report simply carries a weaker period label.

---

## `POST /v1/complaints`

Accepts a run. Returns `202` immediately — **not a report**.

```bash
curl -s -X POST localhost:8000/v1/complaints \
     -H 'content-type: application/json' \
     -H 'X-API-Key: ...' \
     -d @fixtures/happy.json
```

### Request

```json
{
  "records": [
    {
      "case_number": "1001",
      "case_details": "استفسار عن تجديد الرخصة",
      "resolution": "تمت المعالجة والاعتذار للمتعامل",
      "service": "تجديد رخصة القيادة",
      "date_opened": "2025-01-15",
      "service_channel": "هاتف"
    }
  ],
  "options": {
    "language": "ar",
    "include_english": true,
    "granularity": null
  },
  "entity": {
    "name_ar": "شرطة الفجيرة",
    "name_en": "Fujairah Police",
    "name_short": "Fujairah Police",
    "logo_base64": "data:image/png;base64,...",
    "brand": { "primary": "#201853", "secondary": "#7E2362" },
    "center_name_ar": "مركز الاتصال",
    "center_name_en": "Contact Centre"
  }
}
```

**Required record fields:** `case_number`, `case_details`, `resolution`, `service`. Everything else is optional — a missing
closure date means the case is open, a missing department means the workload map has
one fewer dimension, and neither is a reason to refuse the run.

**Required means the column, not the value.** Every record must carry these keys, but `case_details`, `resolution`, `service` may be `null` for a blank cell — the pipeline keeps such rows and routes them down its fallback path, and refusing them would sink a whole export over one blank resolution. `case_number` is the exception: it must have a value, or the case cannot be traced back to its row in the workbook. Send `null` for a blank cell rather than leaving the key out; a missing key means the column is missing.

**`entity` is required and has no defaults.** A report must never carry another
tenant's name, logo or colours.

**Send the logo as `logo_base64`.** `logo_path` is read from the *server's*
filesystem, which is almost never what a caller means over HTTP. It fails soft: the
cover renders without a logo.

**`options.include_english=false` roughly halves the run.** The English report is a
full translation of all nine sections and is the largest block of tokens in a run.

### Response — `202`

```json
{
  "job_id": "a35ca2b3339a",
  "status": "queued",
  "poll_url": "/v1/jobs/a35ca2b3339a",
  "created_at": "2026-09-28T13:20:28.889833Z",
  "estimated_seconds": 190
}
```

`job_id` is also the run id: it appears in every log line the run produces and in
every stored artefact's key. Quote it when reporting a problem.

`estimated_seconds` is for pacing a poll loop, not a promise.

---

## `GET /v1/jobs/{job_id}`

```bash
curl -s localhost:8000/v1/jobs/a35ca2b3339a
```

While running:
```json
{
  "job_id": "a35ca2b3339a",
  "status": "running",
  "created_at": "2026-09-28T13:20:28Z",
  "started_at": "2026-09-28T13:20:28Z",
  "finished_at": null,
  "stage": "stage3",
  "progress": 0.4,
  "message": "Stage 3: AI Classification",
  "result": null,
  "error": null
}
```

Once succeeded, `result` holds the full bundle — see [`schema.md`](schema.md).

On failure:
```json
{
  "status": "failed",
  "error": {
    "code": "stage_failed",
    "message": "Stage 5 gap analysis produced no gaps after 3 LLM attempts…",
    "stage": "stage5"
  },
  "result": null
}
```

**A poll that finds a failed job is a successful poll** — `200`, not `5xx`. The
failure belongs to the run, not to the request asking about it.

`404 job_not_found` means either no such job or one past its TTL. The two are
deliberately not distinguished; telling them apart would mean keeping expired ids
forever.

**A poll finds a job only where the job store can see it.** With
`NOVECOMP_JOB_BACKEND=local` that is the single instance that accepted it, so a
load-balanced deployment 404s its own jobs; with `table` any instance can serve any
poll. See the README's durability table.

New job error codes when the durable path is in use:

| `code` | Meaning |
|---|---|
| `worker_restarted` | The worker died mid-run (local backend only). Abandoned, not resumed — retrying is safe |
| `runtime_exceeded` | The run passed `NOVECOMP_JOB_MAX_RUNTIME_SEC` and was abandoned |
| `request_unavailable` | A queued run could not read its stored request. Retry the run |
| `delivery_failed` | The queued message exhausted every delivery attempt. Check the worker logs for this job id |
| `cancelled` | The worker was shutting down |

---

## Errors

Every failure has the same envelope:

```json
{ "error": { "code": "...", "message": "One sentence.", "detail": null } }
```

Branch on `code`, never on `message`.

| Status | `code` | Meaning |
|---|---|---|
| 400 | `unprocessable_records` | Validated, but cannot be analysed — no resolvable period, say |
| 401 | `unauthorized` | Missing or wrong `X-API-Key` |
| 404 | `job_not_found` | No such job, or it has expired |
| 422 | `missing_required_columns` | Records omit a required key. `detail` names the columns and the offending record indices |
| 422 | `too_many_records` | The export exceeds `NOVECOMP_MAX_RECORDS` |
| 422 | `invalid_request` | The body failed schema validation |
| 500 | `internal_error` | Unhandled. The message is deliberately generic — exception text can echo customer data |
| 502 | `upstream_error` | The gateway failed or returned something unusable |
| 503 | `not_configured` | Settings are missing, or there is no job store |

### `missing_required_columns`

A required column absent from every row is the commonest way a real export is wrong,
and pydantic reports it per record. A hundred thousand rows with no resolution column
would otherwise produce a hundred thousand identical errors. They are folded into one:

```json
{
  "error": {
    "code": "missing_required_columns",
    "message": "5 record(s) are missing the required column resolution. …",
    "detail": {
      "columns": ["resolution"],
      "records": [0, 1, 2, 3, 4],
      "records_total": 5
    }
  }
}
```

At most 20 indices are named; `records_total` is the true count.

### Records are never echoed

Pydantic attaches the offending record to each error as `input`. That is customer
data — for the complaints module, a named person with an identity-document number — so
`input` and `ctx` are stripped before the response is rendered. The field is still
named, so you can find what to fix.

---

## Warnings

A warning arrives **inside a successful result**, in `result.warnings`. It is
something that went wrong without costing the run.

| `code` | Meaning |
|---|---|
| `document_storage_failed` | An artefact was built but could not be stored, and is absent from `documents`. The analysis is unaffected |
| `english_export_unavailable` | The English translation did not complete. Arabic is unaffected. Not emitted when `include_english` was `false` — it was not wanted, so it is not missing |
| `pricing_not_configured` | Tokens counted but not priced. `usage.cost` is `null` |
| `human_review_required` | Some cases could not be classified with confidence. They are counted; their category is the model's best guess, and they are flagged in the workbook |
| `partial_analysis` | A stage produced less than usual — an empty friction map, say — so the affected report sections are thinner. Expected on a small or very uniform export |

**Check `warnings` before assuming every artefact is present.**

---

## Authentication

When `NOVECOMP_API_KEY` is set, every `/v1` route requires it in `X-API-Key`. Unset
means unenforced, which is right behind something that already authenticates: on Azure
Functions the platform checks `x-functions-key` first, so `NOVECOMP_API_KEY` is
normally left unset there.

`NOVECOMP_API_KEY` never gates `/health` or `/ready`. **On Azure the function key does**: the platform checks `x-functions-key` on every route before a request reaches the app, so probes must send it too.

---

## Fetching the artefacts

The result carries **references, not bytes**. There is no download route: this service
does not serve file content.

```json
"documents": {
  "report":      { "ar": { "url": "...", "container": "complaints-reports", "key": "..." } },
  "workbook":    { "url": "...", "key": "..." },
  "report_data": { "ar": { "url": "...", "key": "..." } }
}
```

A hosted caller fetches `url`. An on-prem caller that holds its own storage
credentials — and has no reason to trust a URL we minted — resolves `container` +
`key` itself. Both describe the same object.

What `url` is depends on the storage backend:

| Backend | `url` | `expires_at` |
|---|---|---|
| `blob` (Azure) | An https link with a read-only SAS token. Anyone holding it can download the file, with no Azure access of their own | When the token expires — `NOVECOMP_STORAGE_SAS_TTL_SEC`, a week by default |
| `blob`, connection string without `AccountKey` | The plain blob URL. Only someone with their own access to the account can open it | `null` |
| `local` (on-prem) | A `file:` URI on the service's own disk | `null` |
| `local` with `NOVECOMP_STORAGE_PUBLIC_BASE_URL` | `<base>/<container>/<key>`, fetchable from whatever serves the folder | `null` |

Fetch before `expires_at`. A link that has expired cannot be renewed through this API;
the object is still in storage under its `key`.

For local testing, serving the folder is enough:

```bash
python -m http.server 10000 -d storage
```

Keys are laid out widest-first, so prefix listings are the useful ones:

```
<entity-slug>/<period-start>/<run-id>/report_ar.docx
```
