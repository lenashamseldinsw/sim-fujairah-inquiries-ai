# Schema reference — Customer Complaints Analytics

Every field of the request and the result, including the parts OpenAPI can only type
as `object`.

---

## Request

### `GenerateComplaintsReportRequest`

| Field | Type | Required | Notes |
|---|---|---|---|
| `records` | `ComplaintRecord[]` | ✔ | At least one. |
| `options` | `AnalysisOptions` | | Defaults apply when omitted. |
| `entity` | `EntityInfo` | ✔ | No defaults of its own. |

### `AnalysisOptions`

| Field | Type | Default | Notes |
|---|---|---|---|
| `language` | `"ar"` \| `"en"` | `"ar"` | Which report the caller asked for. Echoed back as `primary_language`. The **Arabic report is always produced** — the analysis runs in Arabic. To decide whether English exists at all, use `include_english`. |
| `include_english` | `bool` | `true` | Produce the English report. A full translation of all nine sections and the largest block of tokens in a run; `false` roughly halves cost and wall clock. |
| `granularity` | `"monthly"` \| `"quarterly"` \| `"semi_annual"` \| `"annual"` \| `null` | `null` | How to label the period. Omit to derive it from the case dates. **Setting it does not filter the data** — every record sent is analysed; only the label changes. |

Deliberately short: the knobs here are the ones the pipeline honours. An option the
six stages ignored would be a lie in the OpenAPI document.

### `ComplaintRecord`

Every field accepts two names — the `snake_case` one and the normalised Arabic column
— and a payload may mix them. Unknown keys are **kept** and passed through to the
dataframe, so a tenant recording an extra column has it counted in the "structured
fields" figure the methodology section prints.

| JSON name | Arabic column | Required | Notes |
|---|---|---|---|
| `case_number` | `رقم_الطلب` | ✔ | A string, not a number: leading zeros are meaningful. |
| `case_details` | `تفاصيل_الطلب` | ✔ | What the customer complained about. A free-text field the classification reads. |
| `resolution` | `الحل` | ✔ | How it was answered. The second free-text field, and what the gap analysis compares against the guidebook. |
| `service` | `الخدمة` | ✔ | **Required here, unlike the inquiries module** — it is the primary signal the complaint classification runs on. |
| `main_service` | `الخدمة_الرئيسية` | | The parent service, where a two-level tree is recorded. |
| `severity` | `شدة_الطلب` | | As assigned by the source system; not re-derived from the text. |
| `contact_type` | `نوع_المكالمة` | | Where present, what the reclassification rate is measured against. |
| `status` | `الحالة` | | Feeds closure reporting alongside the closure date. |
| `service_channel` | `قناة_تقديم_الخدمة` | | Open vocabulary; drives the digital-submission analysis. |
| `date_opened` | `تاريخ_الإنشاء` | | The reporting period is derived from these. |
| `date_closed` | `تاريخ_الإغلاق` | | Null or empty means still open. |
| `closed_within_sla` | `إغلاق_الطلب_خلال_الوقت_المحدد` | | Yes/no. See below. |
| `resolved_by` | `تم_الحل_بواسطة` | | Feeds the per-handler workload view. |
| `general_administration` | `الإدارة_العامة` | | Drives the workload map's per-department view. |
| `created_by` | `انشاء_بواسطة` | | Who entered it into the source system. |
| `owner` | `المالك` | | Current owner. |
| `emirate` | `الإمارة` | | Where recorded. |
| `applicant_name` | `اسم_مقدم_الطلب` | | ⚠️ **Personal data.** |
| `nationality` | `الجنسية` | | ⚠️ **Personal data.** Open vocabulary. |
| `national_id` | `رقم_الهوية` | | ⚠️ **Personal data.** |
| `mobile` | `الهاتف_الجوال` | | ⚠️ **Personal data.** |
| `employee_number` | `الرقم_الوظيفي` | | ⚠️ **Personal data.** Where the complaint concerns an employee. |

> ⚠️ **The five fields marked above identify a real person, and everything sent is
> written into the stored workbook.** Send them only if the report needs them. The
> error handler never echoes a rejected record back, for exactly this reason.
> `PERSONAL_DATA_FIELDS` is exported from `api.models` so a caller can strip them in
> one step.

#### How blank values are read

A spreadsheet export carries several spellings of "empty", and all of them mean the
same thing. `""`, `"  "`, `"-"`, `"--"`, `"nan"`, `"none"`, `"null"`, `"n/a"`, `"na"`,
`"#n/a"`, `"#null!"` and a float `NaN` are all read as no value — case-insensitively,
after collapsing whitespace.

Any of these means `null`, and a `null` reaches the pipeline as an empty cell — exactly as the
original app read it from Excel. That holds for the required columns too, except
`case_number`, where a blank value is a validation error.

**Required means the column, not the value.** Every record must carry these keys, but `case_details`, `resolution`, `service` may be `null` for a blank cell — the pipeline keeps such rows and routes them down its fallback path, and refusing them would sink a whole export over one blank resolution. `case_number` is the exception: it must have a value, or the case cannot be traced back to its row in the workbook. Send `null` for a blank cell rather than leaving the key out; a missing key means the column is missing.

Whitespace inside a value is *collapsed*, not merely stripped: Arabic pasted out of a
web form carries newlines and runs of spaces mid-string, and the pipeline compares
these values against each other.

A number, date or boolean in a text column is stringified — an ordinary export
artefact. A **dict or list is rejected**: that cannot come from a cell, and `str()`
would turn a caller's structural mistake into a plausible-looking value that survives
into the report.

#### Yes/no fields

`closed_within_sla` accepts `"نعم"`/`"لا"`, `"yes"`/`"no"`, `"y"`/`"n"`, `"true"`/`"false"`,
`1`/`0` and real booleans. Anything unrecognised becomes `null` rather than being
guessed — a cell reading "partially" is not a no, and treating it as one would move a
case into the compliant column.

#### Dates

Any format pandas can read; ISO 8601 is safest. **ISO is tried first**, because
`2025-01-05` is unambiguously 5 January and a day-first reading turns it into 1 May.
Only what ISO cannot read is retried day-first, which is right for the ambiguous slash
formats the regional source systems produce — there `03/04/2025` is 3 April.

An unreadable date is dropped rather than raised on. A run whose period is weakly
labelled is still a run worth doing.

### `EntityInfo`

| Field | Type | Required | Notes |
|---|---|---|---|
| `name_ar` | `string` | ✔ | Used when the report language is `ar`. |
| `name_en` | `string` | ✔ | Used for `en`, and slugified into every storage key. |
| `name_short` | `string` | | Identity line under the name on the cover. |
| `logo_base64` | `string` | | With or without a `data:image/...;base64,` prefix. **The HTTP form.** |
| `logo_path` | `string` | | A path on the *server's* filesystem — library use only. Mutually exclusive with `logo_base64`. |
| `brand.primary` | hex colour | | Defaults to NoveAI Navy `#201853`. **Carried but not yet applied** — see below. |
| `brand.secondary` | hex colour | | Defaults to NoveAI Magenta `#7E2362`. Likewise. |
| `closing_statement` | `string` | | Replaces the model-written closing when present. |
| `center_name_ar` / `_en` | `string` | | Sub-unit shown on the cover. |

**No tenant defaults, ever.** Names are required; everything else is simply absent
when not given. Defaulting any of it would mean a tenant that supplies a name but no
logo silently prints someone else's.

A logo that will not decode is **dropped with a log warning**, not raised on: a cover
without a logo is cosmetic, and throwing away six stages of analysis over a malformed
data URI is not a trade anyone would choose.

**`brand` drives the document's look.** Headings, section banners, table headers, the
cover and the table of contents take `primary`; accents take `secondary`. Charts take
`primary` for their accent series.

Two deliberate exceptions:

* **Semantic colours are not brandable.** The red in the severity palette means
  critical, and the neutral greys beside it carry no identity. Repainting them in a
  tenant's brand would destroy meaning. This is the same reasoning that makes
  `STATUS_COLORS` platform-locked.
* **Omitting `brand` is not the same as sending its defaults.** `BrandColors` defaults
  to the NoveAI palette because it is a shared contract model that must carry no
  organisation's colours — but a request that leaves `brand` out renders in the
  report's own design palette instead, which is what every report looked like before
  theming existed. Send `brand` explicitly to override it, including if you genuinely
  want the NoveAI palette.

A malformed colour (`"navy"`, `"#12345"`, a non-string) falls back to the design
palette rather than reaching the document, where a bad value produces a file Word
offers to repair. `#abc` shorthand and a missing `#` are both accepted.

`STATUS_COLORS` — `compliant` `#2E8B6B`, `watch` `#C68A2E`, `breach` `#B5393F` — is
**platform-locked** and not tenant-configurable: a compliant cell must read the same
across every tenant.

---

## Result

### `ComplaintsBundle`

| Field | Type | Notes |
|---|---|---|
| `run_id` | `string` | 12 hex chars. Also the job id, the log correlation id, and part of every storage key. |
| `period` | `Period` | The window the run covers. |
| `total_cases` | `int` | Cases analysed after validation — the denominator for every percentage. |
| `metrics` | `object` | The deterministic ground truth. **Detailed below.** |
| `charts` | `ChartSpec[]` | Select by `key`, never by position. |
| `report` | `{ "ar": object, "en"?: object }` | The report as structured data. **Detailed below.** |
| `documents` | `RunDocuments` | Where the artefacts were filed. |
| `usage` | `RunUsage` | Tokens and cost, in total and per stage. |
| `warnings` | `BundleWarning[]` | Non-fatal problems. Empty on a clean run. |
| `primary_language` | `"ar"` \| `"en"` | What was **asked for**, not what was produced. |

### `Period`

`granularity`, `index` (1-12 / 1-4 / 1-2 / 1), `year`, `start`, `end` (ISO dates),
`label_ar`, `label_en`.

Named off the **end** of the span: a run lapping into a new quarter is still a report
about the quarter that closed. Identical in shape to module 01's, so one parser reads
both.

### `metrics` — the ground truth

OpenAPI types this as `object` because its contents follow the data. Every figure the
report prints comes from here, and **this is what to check the prose against.**
Nothing in it is recomputed — recomputing would create a second source of truth that
could disagree with the document.

| Key | Type | Meaning |
|---|---|---|
| `total_cases` | `int` | Cases after validation. |
| `classified_cases` | `int` | Cases carrying a final classification. Equals `total_cases` on a complete run. |
| `rule_classified_count` | `int` | Settled by stage 2's rules, with no model call. |
| `llm_queue_count` | `int` | Handed to stage 3 because the rules were not confident. |
| `human_review_count` | `int` | Stage 3 was not confident either. Counted in the totals; flagged in the workbook. |
| `reclassified_count` | `int` | Cases whose true type differs from what was recorded. |
| `reclassification_rate` | `float` | The above as a percentage of `total_cases`. |
| `contact_type_counts` | `{string: int}` | Final classification distribution. |
| `original_contact_type_counts` | `{string: int}` | As originally recorded. The pair is what the reclassification chart shows. |
| `channel_counts` | `{string: int}` | Cases per submission channel. |
| `department_counts` | `{string: int}` | Cases per owning department. |
| `patterns` | `object[]` | Stage 4 clusters: `cluster`, `sub_theme`, `case_count`, `example_case_ids`, Arabic variants. |
| `journey_map` | `object[]` | Friction points: `cluster`, `friction_point`, `root_cause_category`, `case_count`. |
| `validated_faqs` | `object[]` | Stage 5-validated FAQs: `question`, `answer`, `frequency`, `validation_status`. |
| `gap_table` | `object[]` | Guidebook gaps: `topic`, `case_count`, `guidebook_status`, `severity`, `recommendation`, coverage and clarity assessments. |
| `notification_opportunities` | `object[]` | Cases a proactive message would have prevented. |
| `proactive_notification_case_count` | `int` | The reconciled total for the above. |
| `month_year` | `string \| null` | The period as the pipeline labelled it internally. |
| `guidebook` | `object` | `pages`, `faq_count`, `year`, `topics` — what the gap analysis was checked against. |

`root_cause_category` is one of `missing_info`, `inaccessible_info`,
`no_proactive_notification`, `platform_bug`, `policy_complexity`.

`guidebook_status` is one of `Covered`, `Partially Covered`, `Missing`; `severity` is
`Critical`, `Medium` or `Adequate`.

### `report` — the document as data

Also typed `object`. Keyed by language; each value is the structure the Word document
was rendered from, so a consumer can render its own instead of handing a reader a
`.docx`.

Nine sections: `executive_summary`, `methodology`, `workload_map`,
`customer_journey`, `digital_gaps`, `digital_transformation`, `ai_use_cases`,
`improvement_roadmap`, `conclusion`.

Each carries an `id`, a `title`, a `level`, prose `content`, and lists of `tables` and
`charts`. A table has `columns`, `rows`, `row_count` and `col_count`.

`"en"` is absent when `include_english` was `false`, or when the translation did not
complete — in which case `warnings` carries `english_export_unavailable`.

### `charts` — `ChartSpec[]`

| Field | Type | Notes |
|---|---|---|
| `key` | `ChartKey` | Stable identifier. **Select on this.** |
| `kind` | `bar` \| `column` \| `pie` \| `doughnut` \| `line` \| `stacked_bar` | |
| `title_ar` / `title_en` | `string` | English falls back to Arabic when untranslated. |
| `categories_ar` / `categories_en` | `string[]` | Same order. |
| `series` | `{ name_ar, name_en, values[] }[]` | One value per category. |
| `colors` | `string[]` | One per series, or per category for a pie. Empty means the consumer picks. |

`ChartKey` for this module: `classification_mix`, `service_distribution`, `resolution_status`, `severity_mix`, `sla_closure`.

**The number of charts varies with the data** — a tenant that records no severity gets
no severity chart — so a key absent from `charts` is not an error, and indexing by
position renders the wrong chart under the right heading. This is the cross-module
contract the BO adopted on 2026-08-27.

### `documents` — `RunDocuments`

| Field | Type | Notes |
|---|---|---|
| `report` | `{ "ar": DocumentRef, "en"?: DocumentRef }` | The Word reports. Module 01's shape, so one parser reads both modules. |
| `workbook` | `DocumentRef \| null` | Every classified case, with the audit columns the report's counts can be verified against with a COUNTIF. |
| `report_data` | `{ "ar": DocumentRef, "en"?: DocumentRef }` | The report JSON the documents were rendered from. |

#### `DocumentRef`

`container`, `key`, `filename`, `content_type`, `size_bytes`, `url`, `expires_at`.

`expires_at` is `null` for a backend whose links do not expire — which the local
filesystem store's do not. A SAS-minting backend fills it in.

### `usage` — `RunUsage`

| Field | Type | Notes |
|---|---|---|
| `tokens` | `int` | `input_tokens + output_tokens`. |
| `cost` | `float \| null` | USD. **`null` when unpriced, never `0.0`** — an unpriced run and a free one are different facts. |
| `input_tokens` / `output_tokens` | `int` | Priced separately; output typically costs several times input. |
| `calls` | `int` | Calls that returned a response. Dozens in a real run. |
| `model` | `string \| null` | As reported by the responses. Several names joined by `", "` means one rate pair priced more than one model, and the cost is approximate. |
| `by_stage` | `{string: StageUsage}` | The same figures per stage. Aggregate cost says nothing actionable; cost per stage says which prompt to cut. |

One honest limit: this counts calls the code saw return. A gateway retrying
internally never surfaces an object to read, so a heavily-retried run may have cost
more. It is a good-faith accounting of observed calls, not a billing reconciliation.

---

## Job models

### `JobAccepted`

`job_id`, `status` (always `queued`), `poll_url`, `created_at`, `estimated_seconds`.

### `JobState`

`job_id`, `status`, `created_at`, `started_at`, `finished_at`, `stage`, `progress`
(0.0–1.0, in steps at stage boundaries), `message` (for display — do not branch on
it), `result`, `error`.

### `JobError`

`code` — one of `unprocessable_records`, `upstream_error`, `stage_failed`,
`runtime_exceeded`, `worker_restarted`, `cancelled`, `internal_error` — plus `message`
and `stage`.

`worker_restarted` means the worker died mid-run. The job was **abandoned rather than
resumed**: resuming half a pipeline would stitch one process's stage 4 onto another's
stage 5 and produce a report whose figures came from two different runs. Retrying is
safe.
