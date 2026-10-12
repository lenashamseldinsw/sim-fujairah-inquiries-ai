# Schema reference — Customer Inquiries Analytics

Every field of the request and the result. The OpenAPI document at `/docs` has the
same models; this adds what it cannot say — which inputs are required, what each
engine key is computed from, and what the model writes versus what the engine counts.

---

## Request

### `GenerateInquiriesReportRequest`

| Field | Type | Required | Notes |
|---|---|---|---|
| `records` | `InquiryRecord[]` | yes, ≥ 1 | One per case. |
| `settings` | `TenantSettings` | X2, X3, X4 | The Definition Sheet's context fields. |
| `reference_lists` | `ReferenceLists` | `taxonomy` | The tenant's tables. |
| `history` | `History \| null` | no | Stored snapshots for the comparison (R9). |
| `options` | `AnalysisOptions` | no | `language`, `include_english`, `granularity`, `sections`. |
| `entity` | `EntityInfo` | yes | Identity and branding. |

A request missing any required input is refused with `422 missing_required_columns`
and the message *"The following input field(s) were missing or unmapped: …"*, naming
each with its U-/X-id ([`api.md`](api.md)).

### `InquiryRecord` — the universal columns

Records are keyed by the canonical names below. A key spelled like any listed alias, or
the Arabic or English label, is renamed on the way in; matching folds ه/ة, the hamza
forms of alef, ى/ي, diacritics, tatweel, spaces/underscores/hyphens and case (R4).
`(Do Not Modify) …` system columns are dropped and listed in the parse log. Unknown keys
are kept as unmapped pass-throughs and never read by a section.

**Required means the column, not the value.** A required column is present when any
record carries it. A blank `case_id` marks an export artefact row — dropped and counted.
A blank description or resolution is kept and degrades to «لم يُزوَّد».

| Id | Field | Arabic / English | Kind | Required | Also recognised as | Role |
|---|---|---|---|---|---|---|
| U1 | `case_id` | رقم الطلب / Case ID | text | **yes** | `Case Number`, `case_number`, `رقم الحالة` | Dedup key; evidence ids. A row without one is an export artefact: dropped and counted. |
| U2 | `description` | تفاصيل الطلب / Description | long_text | **yes** | `case_details`, `وصف الحالة` | What the customer asked. Classification input H; redacted before any model sees it. |
| U3 | `resolution_text` | الحل / Resolution | long_text | **yes** | `Resolution Response`, `resolution`, `رد المعالجة` | What the agent did. Classification input I — outranks the description. |
| U4 | `case_type` | نوع المكالمة / Recorded type | text | **yes** | `Case Type`, `contact_type`, `نوع الحالة` | The CRM's own type label. Scope filter and the recorded side of recorded-vs-actual. |
| U5 | `crm_service` | الخدمة / Recorded service | text |  | `Service Name`, `service` | The CRM's service tag. Context only — the recorded side of RECORDED_VS_TRUE. |
| U6 | `crm_service_group` | الخدمة الرئيسية / Recorded main service | text |  | `Service Category`, `main_service` | The CRM's service grouping. Classifier context only. |
| U7 | `severity` | شدة الطلب / Severity | text |  | `Priority`, `شدة الشكوى` | Severity distribution; labels relabelled through the vocabulary list. |
| U8 | `channel` | قناة تقديم الخدمة / Channel | text |  | `Case Channel`, `service_channel`, `قناه تقديم الخدمة`, `القناة` | Channel mix and the digital-channel share. |
| U9 | `opened_datetime` | تاريخ الإنشاء / Opened date-time | datetime | **yes** | `Date Opened`, `date_opened`, `Created On` | Period anchor and the monthly distribution. |
| U10 | `closed_datetime` | تاريخ إغلاق الطلب / Closed date-time | datetime |  | `date_closed`, `تاريخ الإغلاق`, `Date Closed` | Closed-cases count. Blank means open. |
| U11 | `sla_status` | إغلاق الطلب خلال الوقت المحدد / SLA status | text |  | `SLA Color`, `sla_compliance`, `سلا امتثال`, `SLA Status` | Normalised to within / near / over / unspecified. |
| U12 | `status` | الحالة / Status | text |  | `Status`, `الحالة SLA`, `Case Status` | Open/closed split, pending detection, and the SLA fallback when U11 is blank. |
| U13 | `department` | الإدارة العامة / Department | text |  | `general_administration`, `إدارة عامة`, `Department` | Department distribution. |
| U14 | `owner` | المالك / Owner | text |  | `Owner` | Agent-level reporting (X9) when enabled; queue owners are told from people. |
| U15 | `resolved_by` | تم الحل بواسطة / Resolved by | text |  | — | Carried to the companion workbook only. |
| U16 | `sub_classification_hint` | التصنيف الفرعي / Sub-classification hint | text |  | `sub_classification` | A hint for the rule chain when it names a taxonomy entry. |
| U17 | `escalation_datetime` | موعد التصعيد / Escalation date-time | datetime |  | `Next Escalation Date` | SLA window; pending-case detection. |
| U18 | `entity` | الإمارة / Entity / emirate | text |  | `Entity`, `الجهة` | Scoping a multi-entity export. |
| U19 | `accepted_datetime` | تاريخ القبول / Accepted date-time | datetime |  | — | TAMM acceptance indicator. |
| U20 | `classified_datetime` | تاريخ التصنيف / Classified date-time | datetime |  | — | TAMM classification indicator. |
| U21 | `first_response_datetime` | تاريخ أول رد / First-response date-time | datetime |  | — | Timestamp-based timeliness. |
| U22 | `resolved_datetime` | تاريخ الحل / Resolved date-time | datetime |  | `Resolved On` | TAMM resolution indicator and timestamp-based timeliness. |
| U23 | `customer_verdict` | رأي المتعامل / Customer verdict | text |  | — | TAMM accuracy indicator (accepted / dissatisfied). |
| U24 | `reopen_flag` | إعادة فتح / Reopen flag | flag |  | — | TAMM accuracy indicator. |
| U25 | `fcr_flag` | الحل من أول اتصال / First-contact resolution flag | flag |  | `FCR` | TAMM first-contact-resolution indicator. |
| U25b | `closure_reason` | سبب الإغلاق / Closure reason | text |  | — | FCR exclusions (auto-closed, closed on customer request, …). |
| U25c | `satisfaction_score` | درجة الرضا / Satisfaction score | number |  | — | Carried; a metric gap recommendation when absent. |
| U-title | `crm_title` | عنوان الحالة / Case title | text |  | `Case Title` | The CRM's auto-title. Never used as truth (codebook golden rule). |
| U-updated | `updated_datetime` | تاريخ التحديث / Updated date-time | datetime |  | `Updated Date` | Last touch. Not a closure proxy unless the tenant says so. |

#### Frozen labels (D1–D8)

Labels an earlier run settled and the platform stored. The classifier fills only what
is missing and never overwrites one. `label_provenance` accepts the Arabic or English
provenance names; labels supplied without one are treated as reviewed (`deep_review`).

Provenance values (D6), as printed: «آلي - موثوق» (`auto` — keyword rules, or labels
copied from an identical case) · «نموذج» (`llm` — the model's first pass) · «آلي - مُصحّح»
(`auto_corrected` — corrected by a codebook rule) · «يدوي - مُراجع» (`deep_review` — the
deep AI review, a second higher-effort pass; not a person).

| Id | Field | Recognised as |
|---|---|---|
| D1 | `label_contact_type` | التصنيف الفعلي, `actual_contact_type` |
| D2a | `label_main_service` | الخدمة الرئيسية المصنفة, `classified_main_service` |
| D2 | `label_sub_classification` | تصنيف إدارة التميز, `classified_sub_classification` |
| D3 | `label_reason` | سبب التصنيف, `classification_reason` |
| D5 | `label_confidence` | ثقة النموذج, `ثقة التصنيف`, `confidence` |
| D6 | `label_provenance` | مصدر السبب الجذري, `مصدر التصنيف`, `provenance` |
| D7 | `label_root_cause` | السبب الجذري للاستفسار, `root_cause` |
| D8 | `label_bundle` | حزمة السبب الجذري, `الحزمة الموضوعية`, `bundle`, `umbrella` |
| D1b | `label_true_type` | النوع الحقيقي, `true_type` |

#### Sensitive columns — excluded at ingest (R3, BR-34/35)

Accepted only so their values can redact the same row's free text; then dropped. They
are never stored, sent to a model, logged or written to an artefact.

| Field | Recognised as |
|---|---|
| `customer_name` | اسم مقدم الطلب, Customer, `applicant_name`, `اسم المتعامل`, `Customer Name` |
| `nationality` | الجنسية, Nationality |
| `national_id` | رقم الهوية, ID number, `emirates_id`, `id_number`, `Emirates ID` |
| `mobile` | الهاتف الجوال, Mobile, `mobile_number`, `phone`, `رقم الهاتف`, `Phone` |
| `employee_number` | الرقم الوظيفي, Employee number, `الرقم الوظيفى` |
| `created_by` | انشاء بواسطة, Created by, `إنشاء بواسطة` |
| `email` | البريد الإلكتروني, Email, `e-mail` |

#### How values are read

`""`, `"-"`, `"--"`, `"nan"`, `"none"`, `"null"`, `"n/a"`, `"na"`, `"#n/a"`, `"#null!"` and a
float `NaN` are blank. Whitespace inside a value is collapsed. A number, date or
boolean in a text column is stringified; a dict or list is rejected.

- **Dates** — ISO 8601 first, then day-first (`03/04/2026` is 3 April). The same rule
  reads the period and every per-case date.
- **SLA** — `sla_status` is normalised to `within` · `near` · `over` · `unspecified`:
  SLA colours (🟢 Green / 🟡 Amber / 🔴 Red), `نعم`/`لا`, yes/no, booleans. When blank,
  `status` is read for an unmistakable timeliness word only; "Closed" is not "on time".
- **Recorded type** — `case_type` is read to `inquiry` · `service_request` · `complaint`
  · `incident` · `suggestion` · `compliment` (bilingual "Information - معلومات" works);
  `settings.case_type_map` covers a tenant's own values.
- **Bilingual labels** — "English - عربي" values are split; either half matches.
- **Free text** is redacted before anything reads it: names → `[الاسم]`, Emirates ID →
  `[الهوية الإماراتية]`, case and tracking references → `[رقم التتبع]`, dates →
  `[تاريخ]`, amounts → `[مبلغ]`, employer names → `[جهة العمل]`, phone / e-mail →
  `[بيانات اتصال]`. Links are kept.

### `TenantSettings` — X1–X12

| Id | Field | Default | Notes |
|---|---|---|---|
| X1 | `source_system` | — | Printed in the introduction and the sources table. |
| X2 | `timeliness_target_working_days` | **required** | ADPF: 2. |
| X3 | `timeliness_framework` | **required** | `entity_process_kpi` · `tamm` · `gsr` · `other`. |
| X4 | `case_type_scope` | **required** | `inquiries_and_service_requests` · `inquiries_only` · `all_recorded_types`. Applied after dedup; excluded types counted. |
| X5 | `llm_threshold` | 0.75 | Rule-chain confidence below this → the model. |
| X6 | `review_threshold` | 0.65 | Below this, or still breaking a codebook rule → the deep AI review. Still below after it → flagged `low_confidence`, counted with its best labels. ≤ X5; ADPF ran X5 = X6 = 0.90. |
| X7 | `digital_channel_definition` | `all_non_phone` | Or `live_chat_and_self_service`. `digital_channels` overrides with an explicit list. |
| X8 | `root_cause_extraction` | `false` | Root causes, umbrellas, S10–S11. |
| X8a | `umbrella_count_range` | `"6–10"` | The discovery step's target. |
| X9 | `agent_level_reporting` | `false` | Per-owner figures, queues excluded, never ranked. Owner names reach the workbook only when on. |
| X10 | `focus_services_count` | 2 | S11 (1–5). |
| X11 | `working_calendar` | `"Sun–Thu 07:30–15:30"` | Working-time maths; `public_holidays` adds dates. |
| X12 | `comparison_basis` | `previous_period` | Or `same_period_last_year` — which `history` snapshot is read. |
| — | `frameworks` | the X3 framework | Registry selections with targets — see below. |
| — | `deflectable_bundles` | procedures, eligibility, values, payment dates, locations | Umbrella names that count as self-serviceable. |
| — | `event_threshold_pct` / `event_min_cases` | 50 / 30 | EVENTS. |
| — | `top_root_causes` / `root_causes_per_bundle` | 12 / 5 | ROOT_CAUSE_TOP. |
| — | `queue_owner_pattern` | `SM-ND\|queue\|قائمة\|فريق` | Regex telling queues from people. |
| — | `case_type_map` | — | Recorded value → canonical type. |

#### The framework registry (`frameworks`)

`[{ "id": "...", "targets": { ... } }]`. Each indicator is computed when the export
supports it, otherwise reported as a fixed-wording recommendation to enable the field —
never as zero.

| Framework `id` | Indicator | Needs | Default target |
|---|---|---|---|
| `entity_process_kpi` | Response-time compliance | `sla_status`, or resolved/closed timestamps | X2 working days |
| `tamm_contact_centre` | Acceptance | `accepted_datetime` | 120 working minutes (`acceptance_minutes`) |
| | Classification | `classified_datetime` | 16 working hours (`classification_working_hours`) |
| | Resolution | `sla_status`, or `resolved_datetime` | the agreed SLA |
| | Accuracy | `customer_verdict` or `reopen_flag` | — |
| | Pending cases | open cases + `escalation_datetime` | — |
| | First-contact resolution | `fcr_flag` (+ `closure_reason` for the exclusions) | — |
| `ad_gov_customer_service_guide` | Guide compliance | — | reference only, cited in the closing |
| `gsr` | GSR pillars | — | reference only |

### `ReferenceLists`

| Field | Required | Shape |
|---|---|---|
| `taxonomy` | **yes** | `"adpf_codebook_v1"`, or `{ main_services: [{ name_ar, name_en?, signals[], guidance?, crm_service_aliases[], sub_classifications: [{ name_ar, name_en?, signals[] }] }], crm_service_map: {tag: main}, edge_cases[], other_service?, examples[] }` |
| `faq_catalogue` | no | `[{ question_ar, answer_ar?, question_en?, answer_en?, main_service?, keywords[] }]` — FAQ coverage |
| `vocabulary` | no | `{ ar: {avoid: use}, en: {avoid: use} }`. Omitted: the ADPF list; `{}`: none |
| `transactions` | no | `[{ main_service, sub_service?, service_code?, total_requests, taxonomy_main_service?, taxonomy_sub_classification?, counts_in_denominator }]` |
| `guidebook` | no | `{ title, pages, year, topics[], entries: [{title, text}] }`, or the Fujairah `guidebook_final.json` shape unchanged |
| `umbrellas` | no | `{ version, umbrellas: [{ id, name_ar, name_en?, meaning_ar?, meaning_en? }] }` — the confirmed set |

**The `adpf_codebook_v1` preset** is the ADPF classification codebook v1: 13 main
services and their sub-classifications with the codebook's assignment signals, English
names, the edge cases, a crosswalk learned from the Q2 master, and 111 reviewed,
redacted examples. The classifier shows each batch the examples most similar to it.

`taxonomy.examples` is how a tenant teaches the classifier its reviewers' practice:
`[{ description, resolution, main_service, sub_classification, root_cause? }]`, redacted.

### `History`

`{ previous_period?: PeriodSnapshot, same_period_last_year?: PeriodSnapshot }`. A
`PeriodSnapshot` is what every bundle returns as `snapshot`: `label_ar`, `label_en`,
`total_cases`, `classified`, `within_deadline_pct`, `digital_share_pct`,
`reclassification_rate`, `channel_pct`, `bundle_counts`, `contact_type_counts`,
`main_service_counts`.

### `EntityInfo`

`name_ar`, `name_en` (required); `name_short`, `center_name_ar`, `center_name_en`,
`logo_base64` (or `logo_path`, server-side), `brand: { primary, secondary }`,
`closing_statement` (the vision statement the closing ties to).

**Colours (Prerequisites §5).** Without `brand`: NoveAI Navy `#201853` and Magenta
`#7E2362`. With it: the tenant's colours on headings, banners, table headers, the cover,
the contents and chart accents. The within / near / over colours `#2E8B6B` / `#C68A2E`
/ `#B5393F` are platform-locked.

---

## Result

### `InquiriesBundle`

| Field | Notes |
|---|---|
| `run_id` | Job id, log correlation id, part of every artefact key. |
| `period` | The reporting window, from the opening dates. |
| `total_cases` | `|S|` — in-scope cases after artefact rows, duplicates and the scope. The one denominator (R2). |
| `metrics` | The engine output — below. |
| `narratives` | `{ ar, en? }` — `ReportNarratives`: `report` (29 fields) and `sections`. |
| `classification` | `ClassificationSummary` — below. |
| `charts` | `ChartSpec[]` — select by `key`. |
| `report` | `{ ar, en? }` — S0–S11 as data. |
| `documents` | `RunDocuments`. |
| `snapshot` | `PeriodSnapshot` — store it; send it back as `history`. |
| `usage` | `RunUsage`. |
| `warnings` | `BundleWarning[]` — [`api.md`](api.md) lists the codes. |
| `primary_language` | As requested. |

### `metrics` — the engine output (Data Mapping §4)

Every number the report prints is here; the prose is checked against it. `S` is the
in-scope case set, `L` its labelled subset whose true type is an inquiry or service
request.

| Key | Computed as |
|---|---|
| `KPI` | `total_cases` = \|S\|; `classified` = \|L\| and `classified_pct`; `closed_cases`; `reclassification_rate`; `main_services`, `sub_classes` (distinct in L); `bundles`; `within_deadline_pct` = (within + near) / \|S\|; `digital_share_pct`; `top_service` {name, pct of L, count}; `inq_per_100_tx`; period label and date range; `source_system`; `deep_reviewed`; `low_confidence_after_review` |
| `MONTHLY` | counts of S by opening month, % of S, month-over-month change |
| `CHANNEL` | counts and % of S by channel as recorded, with the digital flag |
| `CASE_TYPE_RECORDED` | counts and % of S by recorded type |
| `MAIN_SERVICE`, `SUB_CLASS` | counts and % of L; a «غير مصنَّف» row = \|S\| − \|L\| − out-of-scope, % of S |
| `ACTUAL_TYPE` | D1 over S (sums to \|S\| — the S3.2 table) |
| `RECORDED_VS_ACTUAL` | recorded type vs D1, per contact type, and the crosstab |
| `RECLASSIFICATION` | D4 count, rate over S, redacted evidence sample |
| `SUB_CLASS_BY_TYPE` | D2 within each D1 |
| `SERVICE` | the recorded service tag (O9) |
| `RECORDED_VS_TRUE` | catalogue crosswalk(recorded tag) = main service: match / mismatch %, least- and most-matching tags |
| `TIMELINESS`, `SLA` | within · near · over · unspecified, counts and % of S; within-deadline and breached % |
| `NEAR_OVER_BY_SERVICE` | share of near + over within each main service (≥ 10 cases) |
| `SEVERITY` | after relabelling (عادي → روتيني، عاجل → حرج) |
| `CLOSED` | closed = closed date present; closure rate |
| `DEPARTMENT` | counts, with each department's dominant type and sub-classification |
| `OUT_OF_SCOPE_DETECTED` | true type complaint / incident / compliment — the Domain 02 handoff |
| `CLASSIFICATION_QUALITY` | provenance split and %, mean confidence, % ≥ X5, deep-reviewed, duplicates reused, low-confidence after review (`queue_size_at_compute`), cleared, taxonomy, umbrella set version, routed to model |
| `EVENTS` | clusters (umbrellas with X8, else sub-classifications) whose month count ≥ (1 + θ) × the previous month and ≥ the minimum |
| `BUNDLE` (X8) | counts and % of L per umbrella; carried umbrellas at zero included; `new` flags |
| `ROOT_CAUSE_TOP` (X8) | top-k causes; per umbrella top-n |
| `BUNDLE_BY_SERVICE` (X8) | main service × umbrella counts and row % |
| `NEAR_OVER_BY_BUNDLE` (X8) | share of near + over within each umbrella |
| `SERVICE_FOCUS` (X8) | per top-N service: count, share, months, peak, within-deadline (1 − over / count), sub-classes, umbrellas, phone and live-chat % |
| `DEFLECTABLE_PCT` (X8) | cases in deflectable umbrellas / \|L\| |
| `INQ_PER_100_TX` | \|L\| / Σ transactions (rows with `counts_in_denominator`) × 100; per main and sub service by join |
| `FAQ_COVERAGE` | share of how-to cases matching a catalogue FAQ (service + keywords), per service |
| `AGENT` (X9) | per non-queue owner: count, %, within-deadline %; alphabetical, never ranked |
| `COMPARISON` | deltas against the `history` snapshot X12 selects |
| `JOURNEY_MAP` | frictions: name AR/EN, root-cause category, remedy, case count = Σ of the case groups assigned to it |
| `NOTIFICATION_OPPORTUNITIES` | type, trigger, sample message, eliminable cases = Σ of their groups |
| `VALIDATED_FAQS` | question, answer, frequency = cases matched to it (each case to one FAQ; `faq_id` on the case), catalogue status |
| `GAP_TABLE` | per friction: guidebook status, excerpt, gap type, deterministic priority, recommendation, case count |
| `PATTERNS` | the largest case groups |
| `FRAMEWORKS` | every registry indicator: status, value, numerator / denominator, target, recommendation |
| `PARSE_LOG` | records received, artefact rows, duplicates, entity rows, scope exclusions, mapped / unmapped / present-but-empty / label / system / sensitive columns, unreadable dates |
| `METRIC_GAPS`, `DATA_NOTES` | fixed-wording recommendations for missing optional inputs; notes for present-but-empty columns |

**What the model decides, and what it never does.** It writes labels (contact type,
main service, sub-classification, root cause), names umbrellas, frictions, FAQs,
notification opportunities and gap assessments, and writes prose. It never writes a
count: every figure above is computed from labels and group assignments.

### `ClassificationSummary`

`taxonomy`, `llm_threshold`, `review_threshold`, `provenance` (D6 split), `mean_confidence`,
`deep_review` (`reviewed`, `low_confidence`, `duplicates_reused`, up to 500
`low_confidence_case_ids`, `truncated`), `umbrella_set_version`,
`umbrellas` — each `{ id, name_ar, name_en, meaning_ar, meaning_en, cases, new,
member_root_causes }` for the Domain Admin's confirmation.

### `narratives` — `ReportNarratives`

`report` is the Full Report Prompt §4 `InquiriesReportNarratives`, 29 fields:
`intro_statement`, `executive_summary`, `comparative_analysis`, `statistics_intro`,
`monthly_narrative`, `main_service_narrative`, `sub_service_narrative`,
`transactions_ratio_narrative`, `channel_narrative`, `recorded_vs_true_narrative`,
`timeliness_narrative`, `service_focus_narratives[]`, `root_causes_intro`,
`bundle_distribution_narrative`, `bundle_by_service_narrative`, `bundle_narratives[]`,
`top_root_causes_narrative`, `timeliness_by_bundle_narrative`,
`digital_opportunity_narrative`, `priority_faqs[]`, `roadmap_intro`, `initiatives[]`
(`title`, `horizon`, `bundle_ref`, `addresses_cases`, `description`), `key_findings[]`,
`recommendations[]`, `closing_statement`, `methodology_note`, `event_narratives[]`,
`friction_points[]`, `top_service_short`. Conditional fields are empty when their input
is absent. `addresses_cases` is the referenced item's engine count.

`sections` is `SectionNarratives`: `contact_type_narrative`,
`reclassification_narrative`, `out_of_scope_narrative`, `department_narrative`,
`journey_narrative`, `digital_gaps_narrative`, `gap_root_causes_narrative`,
`digital_transformation_narrative`, `ai_use_cases_intro`, `ai_use_cases[]` (`title`,
`function`, `source_ref`, `effort`, `impact_cases`).

### `report` — S0–S11 as data

`{ document_name, language, rtl, entity, period, cover, metadata, sections[] }`. `cover`
is S0 (`tiles` O1–O6, both totals labelled — R7). Each section has `id` (S1…S11), `key`
(`ReportSection`), `title`, and any of `content`, `bullets`, `tables` (`columns`, `rows`),
`charts`, `notes`, `subsections`.

| Id | `key` | Present |
|---|---|---|
| S1 | `executive_summary` | always |
| S2 | `methodology` | always — sources, parse log, method with X5/X6 and counts, fields from the confirmed schema, quality line (R1) |
| S3 | `classification_map` | always; subsections by available input |
| S4 | `customer_journey` | always (a note when no friction was found) |
| S5 | `digital_gaps` | always; the gap table needs the guidebook |
| S6 | `digital_transformation` | always |
| S7 | `ai_use_cases` | always; the comparison with `history` |
| S8 | `improvement_roadmap` | always |
| S9 | `conclusion` | always |
| S10 | `root_causes` | X8 on |
| S11 | `service_focus` | X8 on |

### `charts` — `ChartSpec[]`

`key`, `kind` (`bar` · `column` · `pie` · `doughnut` · `line` · `stacked_bar` · `heatmap`),
`output_id` (the Builder output, O1–O26), `title_ar/en`, `categories_ar/en`, `series[]`
(`name_ar`, `name_en`, `values`), `colors`.

Keys: `classification_mix` (O7), `actual_type_mix` (O8), `service_distribution` (O9),
`timeliness_donut` (O10, locked colours), `severity_mix` (O11), `channel_donut` (O12),
`sub_class_by_type` (O13), `department_distribution` (O14), `monthly_bar` (O19),
`period_comparison` / `channel_comparison_bar` (O20), `classification_quality` (O21),
`bundle_bar` (O22), `bundle_service_heatmap` (O23, data only — not drawn in Word),
`top_root_causes_bar` (O24), `near_over_by_bundle_bar` (O25), `inq_per_100_bar` (O26),
`main_service_bar`, `sub_service_bar`, `recorded_vs_true_stacked`, `faq_coverage_bar`,
`howto_by_service_bar`, `focus_{1–5}_monthly_bar`, `focus_{1–5}_subclass_donut`,
`focus_{1–5}_bundle_bar`.

### `documents` — `RunDocuments`

| Field | Notes |
|---|---|
| `report` | `{ ar, en? }` Word documents. |
| `report_data` | `{ ar, en? }` the report JSON they were drawn from. |
| `workbook` | The companion workbook (R10): summary · all cases · one sheet per actual contact type · reclassification · deep review · out of scope (Domain 02). Columns: the universal columns sent (by U-id), then D1, D1b, D2a, D2, D3, D4, D5, D6, D7, D8, deep-reviewed, low-confidence, copied-from-duplicate, FAQ link, corrections. No identity column; redacted text. |
| `labels` | Per-case labels JSON: `label_*` fields, `misclassified`, `deep_reviewed`, `low_confidence`, `duplicate_of`, `faq_id`, `corrections` — what the platform stores and sends back next period as frozen labels. |

`DocumentRef`: `container`, `key`, `filename`, `content_type`, `size_bytes`, `url`,
`expires_at`.

### `usage` — `RunUsage`

`tokens`, `cost` (`null` when unpriced, never `0.0`), `input_tokens`, `output_tokens`,
`calls`, `model`, `by_stage` — `classification`, `umbrella_discovery`, `journey`, `faqs`,
`gaps`, `narratives`.

---

## Job models

### `JobAccepted`

`job_id`, `status` (always `queued`), `poll_url`, `created_at`, `estimated_seconds`.

### `JobState`

`job_id`, `status`, `created_at`, `started_at`, `finished_at`, `stage`, `progress`
(0.0–1.0), `message` (display only), `result`, `error`.

### `JobError`

`code` — `missing_required_columns`, `unprocessable_records`, `upstream_error`,
`stage_failed`, `runtime_exceeded`, `worker_restarted`, `request_unavailable`,
`delivery_failed`, `cancelled`, `internal_error` — plus `message` and `stage`.

A run whose worker died is **abandoned, not resumed**: the steps are not checkpointed,
and a report whose figures came from two half-runs would be wrong. Retrying is safe.
