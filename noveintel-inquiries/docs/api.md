# API reference — Customer Inquiries Analytics

Base URL is the service root. On Azure Functions that is the site root, **not**
`/api` — `host.json` sets `routePrefix: ""` precisely so the paths here are the paths
everywhere.

All request and response bodies are JSON. All field names are `snake_case`. A record's
keys are the universal column names (`case_id`, `description`, …); a recognised export
header (`Case Number`, «رقم الطلب») or a legacy field name (`case_number`) is renamed on
the way in, matched by folded spelling. [`schema.md`](schema.md) lists every column.

---

## The shape of a run

```
POST /v1/inquiries/validate    →  200   free, milliseconds, no model call
POST /v1/inquiries             →  202   { job_id, poll_url, estimated_seconds }
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

Never gated by `NOVEINQ_API_KEY`.

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
  "storage": { "backend": "local", "container": "inquiries-reports", "available": true },
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

## `POST /v1/inquiries/validate`

Parses the payload alone — header recognition, artefact rows, duplicates, the
case-type scope, redaction — checks every required input and resolves the period.
**No model call, no cost, milliseconds.**

```bash
curl -s -X POST localhost:8000/v1/inquiries/validate \
     -H 'content-type: application/json' -d @fixtures/happy.json
```
```json
{
  "total_cases": 10630,
  "period": { "granularity": "quarterly", "index": 2, "year": 2026, "start": "2026-04-01",
              "end": "2026-06-30", "label_ar": "الربع الثاني 2026", "label_en": "Q2 2026" },
  "parse_log": {
    "records_received": 11713, "artefact_rows_dropped": 1083, "duplicates_removed": 0,
    "scope_excluded": {"complaint": 0}, "in_scope_total": 10630,
    "columns_mapped": ["case_id", "description", "resolution_text", "case_type", "..."],
    "columns_unmapped": [], "columns_present_but_empty": [],
    "label_columns_supplied": [], "system_columns_dropped": ["(Do Not Modify) Case"],
    "sensitive_columns_excluded": ["customer_name"], "scope": "inquiries_and_service_requests"
  },
  "taxonomy": "adpf_codebook_v1",
  "root_cause_extraction": true
}
```

A `200` means the run will be **accepted**: every required input arrived and the period
resolves. It is not a promise the run succeeds — classification and the narrative
depend on the gateway.

Refusals are the ones a run would hit: `422 missing_required_columns` naming every
missing input, and `400 unprocessable_records` when no `opened_datetime` is readable.

---

## `POST /v1/inquiries`

Accepts a run. Returns `202` immediately — **not a report**. Required inputs and the
period are checked first, so a request that cannot run is refused here rather than
failing as a job minutes later.

```bash
curl -s -X POST localhost:8000/v1/inquiries \
     -H 'content-type: application/json' -H 'X-API-Key: ...' -d @fixtures/happy.json
```

### Request

```json
{
  "records": [
    {
      "case_id": "260630-7987523",
      "opened_datetime": "2026-06-30T23:37:48",
      "case_type": "Information - معلومات",
      "channel": "Phone",
      "description": "كيف يمكنني ضم مدة خدمة سابقة؟",
      "resolution_text": "من خلال هذه الخدمة يمكن للمؤمن عليه تقديم طلب ضم مدة خدمته السابقة …",
      "sla_status": "🟢 Green",
      "status": "Closed",
      "crm_service": "Add Previous Service Period-ضم مدة خدمة سابقة"
    }
  ],
  "settings": {
    "timeliness_target_working_days": 2,
    "timeliness_framework": "entity_process_kpi",
    "case_type_scope": "inquiries_and_service_requests",
    "root_cause_extraction": true,
    "frameworks": [{ "id": "entity_process_kpi" }, { "id": "tamm_contact_centre" }]
  },
  "reference_lists": {
    "taxonomy": "adpf_codebook_v1",
    "transactions": [{ "main_service": "إنهاء خدمة المؤمن عليه", "sub_service": "صرف المعاشات التقاعدية", "total_requests": 231 }],
    "faq_catalogue": [{ "question_ar": "كيف يمكنني ضم مدة خدمة سابقة؟", "main_service": "ضم الخدمة السابقة" }],
    "guidebook": { "title": "دليل الخدمات", "pages": 160, "year": "2025", "entries": [{ "title": "…", "text": "…" }] },
    "umbrellas": { "version": "2026-Q1", "umbrellas": [{ "id": "u1", "name_ar": "طلب إجراءات ومتطلبات الخدمة", "name_en": "Procedures & requirements" }] }
  },
  "history": {
    "previous_period": { "label_ar": "الربع الأول 2026", "label_en": "Q1 2026", "total_cases": 11799,
                         "within_deadline_pct": 98.8, "digital_share_pct": 16.3 }
  },
  "options": { "language": "ar", "include_english": true, "granularity": null,
               "sections": null },
  "entity": {
    "name_ar": "صندوق أبوظبي للتقاعد", "name_en": "Abu Dhabi Pension Fund",
    "logo_base64": "data:image/png;base64,...",
    "brand": { "primary": "#201853", "secondary": "#7E2362" },
    "closing_statement": "رؤية الجهة …"
  }
}
```

**Required inputs** — the columns `case_id` (U1), `description` (U2), `resolution_text`
(U3), `case_type` (U4), `opened_datetime` (U9); the settings
`timeliness_target_working_days` (X2), `timeliness_framework` (X3), `case_type_scope`
(X4); and `reference_lists.taxonomy`. A column is present when any record carries it.
A blank cell in a present column is not a refusal: a blank `case_id` marks an export
artefact row (dropped and counted in the parse log); a blank description or resolution
degrades that case to «لم يُزوَّد».

**Optional inputs are graceful.** Without the guidebook the S5 gap table is omitted
with a data note; without transactions the inquiries-per-100 ratio is omitted; without
an SLA field timeliness is reported as not computable; each becomes a fixed-wording
recommendation in the report, never a zero.

**`entity` is required and has no tenant defaults.** Without `brand` the report uses the
documented NoveAI palette. Send the logo as `logo_base64`.

**`include_english=false`** skips the English translation and document. The narrative
is written once, in Arabic, in three groups side by side; each group's English
translation starts the moment that group is final, while the others are still being
written, and the Arabic documents are built while the translations finish. The translation uses the English
names the taxonomy and the run already hold, so it needs English names in the taxonomy.

**`sections`** chooses the report's sections (Module 06's "which sections show") by
name: the section key or its printed title in Arabic or English, in any order — case,
spacing, hyphens and Arabic diacritics do not matter. Ids such as `S1` are not accepted.

```json
"sections": ["executive_summary", "statistics", "Root causes and their link to services",
             "فرص المحتوى الرقمي الموجَّه", "improvement_roadmap", "conclusion", "appendices"]
```

| Key | Title |
|---|---|
| `executive_summary` | الملخص التنفيذي · Executive summary |
| `statistics` | الإحصاءات العامة ولوحة المؤشرات · General statistics and indicator dashboard |
| `service_focus` | تركيز الخدمات ذات الأولوية · Priority service focus |
| `root_causes` | الأسباب الجذرية وارتباطها بالخدمات · Root causes and their link to services |
| `digital_content_opportunities` | فرص المحتوى الرقمي الموجَّه · Targeted digital-content opportunities |
| `improvement_roadmap` | خارطة الطريق التحسينية المقترحة · Proposed improvement roadmap |
| `conclusion` | الخلاصة والتوصيات · Conclusion and recommendations |
| `appendices` | الملاحق · Appendices |

Omit it for every section the run can produce. The report keeps its own order, the cover
is always included, and Sections 01–05 are numbered among those shown. `service_focus`
and `root_causes` also need `settings.root_cause_extraction`; asked for without it they
are left out with a `section_omitted` warning. An unknown name — including a retired
section such as `customer_journey`, `digital_gaps` or `ai_use_cases` — is a `422`.

A hidden section costs nothing in the narrative: its fields are left out of the writing
and translation tools (as is any field whose input is absent), the data only it reads is
left out of the prompt, its AI-generated labels are not translated, and the root-cause
instructions are given only when `service_focus` or `root_causes` is shown. Each section
depends on no other; only three draw on the qualitative analysis, which runs only when
one of them is shown:

| Section | Analysis it needs |
|---|---|
| `digital_content_opportunities` | FAQ detection — embeddings to group the cases' questions and shortlist catalogue entries, then about one judging call per 30 question groups and one merge call (questions only, never answers) |
| `improvement_roadmap` | journey frictions and notifications, FAQs — its initiatives cite them |
| `appendices` | journey frictions — the friction-point appendix |
| every other section | none — engine figures only |

FAQ detection starts after umbrella discovery (its population is defined by umbrella)
and runs beside the figures and the first narrative groups. With a catalogue it judges
every question group in the procedures umbrella, small ones included, so its call
count grows with the number of distinct questions: on the ADPF Q2 master (10,628
cases) see `deployment.md`. Without a catalogue it judges only the largest groups, for
their question.

The guidebook gap analysis is retired with the digital-gap section; a guidebook, when
sent, adds its FAQs to the entries FAQ detection judges against and is listed in the
methodology.

### Response — `202`

```json
{ "job_id": "a35ca2b3339a", "status": "queued", "poll_url": "/v1/jobs/a35ca2b3339a",
  "created_at": "2026-09-28T13:20:28.889833Z", "estimated_seconds": 4900 }
```

`job_id` is also the run id: it is in every log line and every stored artefact's key.
`estimated_seconds` paces a poll loop; root-cause extraction roughly doubles it.

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
  "stage": "stage2",
  "progress": 0.31,
  "message": "Stage 2: Model classification 18/40",
  "result": null,
  "error": null
}
```

While running, `stage` is the step number the progress message names — six steps:
parse, classify, analyse, compute, narrate, build the documents. Once succeeded,
`result` holds the full bundle — see [`schema.md`](schema.md).

On failure:
```json
{
  "status": "failed",
  "error": {
    "code": "upstream_error",
    "message": "The model gateway failed during classification, so the run could not finish. …",
    "stage": "classification"
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
`NOVEINQ_JOB_BACKEND=local` that is the single instance that accepted it, so a
load-balanced deployment 404s its own jobs; with `table` any instance can serve any
poll. See the README's durability table.

Every code a failed job can carry:

| `code` | Meaning |
|---|---|
| `unprocessable_records` | The pipeline refused the data — no case left after the scope, say. The message says why |
| `missing_required_columns` | A required input was missing. Normally refused at the route instead |
| `stage_failed` | A step could not complete. `stage` names it: `parsing`, `classification`, `analysis`, `computing`, `narratives` or `documents` |
| `upstream_error` | The model gateway failed during the run — an outage, rate limiting, a refused call. `stage` names where. Usually worth retrying later |
| `internal_error` | Unhandled. The message names the exception type only |
| `runtime_exceeded` | The run passed `NOVEINQ_JOB_MAX_RUNTIME_SEC` and was abandoned. Applies on both the in-process and the queue path |
| `worker_restarted` | The worker died mid-run (local backend only). Abandoned, not resumed — retrying is safe |
| `request_unavailable` | A queued run could not read its stored request. Retry the run |
| `delivery_failed` | The queued message exhausted every delivery attempt. Check the worker logs for this job id |
| `cancelled` | The worker was shutting down |

**A failed job's `message` never carries exception text.** Where a stage failed on an
exception, the message says so and gives the run id; the exception itself is in the
service log under that id. Exception text can carry a fragment of a record or of a
model reply, and anyone who can poll the job can read the message. Messages the
pipeline writes itself — "no case remained after the case-type scope" — come through
as they are.

---

## Errors

Every failure has the same envelope:

```json
{ "error": { "code": "...", "message": "One sentence.", "detail": null } }
```

Branch on `code`, never on `message`.

| Status | `code` | Meaning |
|---|---|---|
| 400 | `unprocessable_records` | Validated, but cannot be analysed — no readable opening date, say |
| 401 | `unauthorized` | Missing or wrong `X-API-Key` |
| 404 | `job_not_found` | No such job, or it has expired |
| 422 | `missing_required_columns` | A required column, setting or the taxonomy did not arrive. `detail.fields` names each |
| 422 | `too_many_records` | The export exceeds `NOVEINQ_MAX_RECORDS` |
| 422 | `invalid_request` | The body failed schema validation |
| 404, 405 | `http_error` | No such route, or the wrong method for it. `message` is the framework's own — `Not Found`, `Method Not Allowed` |
| 500 | `internal_error` | Unhandled. The message is deliberately generic — exception text can echo customer data |
| 503 | `not_configured` | Settings are missing, or there is no job store |

No route calls the model gateway, so no route answers `502`. A gateway failure
happens inside a run and is reported on the job, as `upstream_error`.

### `missing_required_columns`

Every missing required input, in one answer — columns first, then settings, then the
taxonomy:

```json
{
  "error": {
    "code": "missing_required_columns",
    "message": "The following input field(s) were missing or unmapped: resolution_text (U3 · الحل / Resolution), settings.case_type_scope (X4 · Case-type scope / نطاق أنواع الحالات).",
    "detail": {
      "fields": [
        { "field": "resolution_text", "id": "U3", "label": "الحل / Resolution" },
        { "field": "settings.case_type_scope", "id": "X4", "label": "Case-type scope / نطاق أنواع الحالات" }
      ]
    }
  }
}
```

"Unmapped" covers a column the platform did not map onto its universal name and that
no recognised header spelling matched.

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
| `english_export_unavailable` | No English report: the taxonomy has no English names for services the report prints (Domain 01 ruling — `detail` lists them), or the English translation failed. Not emitted when `include_english` was `false` |
| `pricing_not_configured` | Tokens counted but not priced. `usage.cost` is `null` |
| `low_confidence_after_review` | Cases stayed below the review threshold (X6) even after the deep AI review. They are counted with their best labels; the methodology states how many; `classification.deep_review` and the labels document list them |
| `umbrellas_pending_confirmation` | Umbrellas were proposed this run. The Domain Admin confirms, renames, merges or splits them; send the confirmed set back as `reference_lists.umbrellas` |
| `narrative_unverified_figures` | After one corrective retry the prose still holds a figure not in the engine output. `detail.figures` lists them — check before publishing |
| `narrative_incomplete` | The model left out narrative fields even after a retry; they are empty in the report. `detail.fields` names them |
| `section_omitted` | An optional input was absent, so a section or table was left out with a data note |
| `metric_gap` | Framework indicators cannot be computed from this export; the report recommends enabling the field |
| `partial_analysis` | A qualitative step (journey, FAQs, gaps, umbrellas) produced less than usual; the affected tables are thinner |

**Check `warnings` before assuming every artefact is present.**

---

## Authentication

When `NOVEINQ_API_KEY` is set, every `/v1` route requires it in `X-API-Key`. Unset
means unenforced, which is right behind something that already authenticates: on Azure
Functions the platform checks `x-functions-key` first, so `NOVEINQ_API_KEY` is
normally left unset there.

`NOVEINQ_API_KEY` never gates `/health` or `/ready`. **On Azure the function key does**: the platform checks `x-functions-key` on every route before a request reaches the app, so probes must send it too.

---

## Fetching the artefacts

The result carries **references, not bytes**. There is no download route: this service
does not serve file content.

```json
"documents": {
  "report":      { "ar": { "url": "...", "container": "inquiries-reports", "key": "..." } },
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
| `blob` (Azure) | An https link with a read-only SAS token. Anyone holding it can download the file, with no Azure access of their own | When the token expires — `NOVEINQ_STORAGE_SAS_TTL_SEC`, a week by default |
| `blob`, connection string without `AccountKey` | The plain blob URL. Only someone with their own access to the account can open it | `null` |
| `local` (on-prem) | A `file:` URI on the service's own disk | `null` |
| `local` with `NOVEINQ_STORAGE_PUBLIC_BASE_URL` | `<base>/<container>/<key>`, fetchable from whatever serves the folder | `null` |

Fetch before `expires_at`. A link that has expired cannot be renewed through this API;
the object is still in storage under its `key`.

For local testing, serving the folder is enough:

```bash
python -m http.server 10000 -d .data/storage
```

Keys are laid out widest-first, so prefix listings are the useful ones:

```
<entity-slug>/<period-start>/<run-id>/report_ar.docx
```
