# NoveIntelligence — Customer Inquiries Analytics (Domain 03)

A headless FastAPI service that turns a period's customer-inquiry cases into an analysed
report. It implements the Business Owner's *Inquiries Analytics* handoff (spec v1.2):
the Domain Definition Sheet's universal columns, context fields and its report, the
Data Mapping's engine contract, the Full Report Prompt's classifier and narrative
prompts, the classification and root-cause codebooks, the TAMM framework registry, and
the Platformisation Requirements R1–R12.

It runs in three layers (Prerequisites §0):

1. **Parser + engine** (`engine/`) — cleans the cases and computes **every** number on
   frozen labels. Pure code.
2. **Classifier** (`classification/`) — labels each case under the tenant's taxonomy and
   the codebooks, with a confidence and a provenance; sends the uncertain ones through
   a deep AI review (a second, higher-effort pass — not a person). With root-cause
   extraction on, writes a root cause per case and groups them into umbrellas.
3. **Narrative writer** (`narratives/`) — receives the engine's numbers and writes prose
   only, in Arabic, checked against those numbers before it ships. The English report
   is a translation of the finished Arabic, made in the background while the Arabic
   documents are built.

> *The classifier may create labels; the engine alone creates numbers; the narrative
> writer creates neither.*

Self-contained: nothing here imports from the Streamlit application, which is no longer
on this branch.

---

## The one thing to know

**Runs are asynchronous.** `POST /v1/inquiries` answers `202` with a `job_id`; poll
`GET /v1/jobs/{job_id}` until `status` is terminal and read `result`. A run is dozens to
hundreds of model calls — minutes on a real export, far past the 230-second ceiling
Azure puts on an HTTP response (porting guide §5.6).

---

## Quick start

```bash
cd noveintel-inquiries
cp .env.example .env          # put your CORE42_API_KEY in it
uv sync --extra api --extra serve
uv run uvicorn noveintel_inquiries.api.app:app --reload    # http://localhost:8000/docs

uv run python scripts/make_fixtures.py path/to/export.xlsx --out fixtures/   # an export → request bodies
curl -s -X POST localhost:8000/v1/inquiries/validate -H 'content-type: application/json' -d @fixtures/happy.json | jq
uv run python scripts/smoke.py fixtures/happy.json           # a real run: spends money, takes minutes
uv run pytest                                                # 413 tests, no network
```

---

## The request

```json
{
  "records":   [ { "case_id": "260630-7987523", "description": "…", "resolution_text": "…",
                   "case_type": "Information - معلومات", "opened_datetime": "2026-06-30T23:37:48",
                   "channel": "Phone", "sla_status": "🟢 Green", "crm_service": "…" } ],
  "settings":  { "timeliness_target_working_days": 2, "timeliness_framework": "entity_process_kpi",
                 "case_type_scope": "inquiries_and_service_requests", "root_cause_extraction": true },
  "reference_lists": { "taxonomy": "adpf_codebook_v1" },
  "history":   { "previous_period": { "label_ar": "الربع الأول 2026", "total_cases": 11799, "within_deadline_pct": 98.8 } },
  "entity":    { "name_ar": "صندوق أبوظبي للتقاعد", "name_en": "Abu Dhabi Pension Fund" },
  "options":   { "include_english": true, "sections": ["executive_summary", "statistics", "improvement_roadmap", "conclusion"] }
}
```

- **`records`** — one object per case, keyed by the **universal columns** U1–U25
  (Definition Sheet §3). The platform's data home maps a tenant's headers onto these
  names before calling; a record keyed by a recognised export header (`Case Number`,
  «رقم الطلب») or by this API's earlier names is renamed on the way in, matching by
  *folded* spelling (ه/ة, hamza, spaces, underscores, case — R4). Records may also carry
  **frozen labels** (`label_main_service`, `label_root_cause`, …) settled by the review
  queue; the classifier never overwrites them.
- **`settings`** — the context fields X1–X12 with the Prerequisites §2.3 defaults.
- **`reference_lists`** — the taxonomy (required: a catalogue, or the preset
  `"adpf_codebook_v1"`), and optionally the FAQ catalogue, vocabulary overrides,
  transaction volumes, the service guidebook and the confirmed umbrella set.
- **`history`** — the stored snapshot of an earlier run, for the comparison (R9). Every
  bundle returns its own `snapshot` to store and send back next period.
- **`entity`** — identity and branding. Without `brand`, the report uses the documented
  NoveAI Navy `#201853` / Magenta `#7E2362`; the within/near/over status colours are
  locked.

**Required inputs** — the columns U1 `case_id`, U2 `description`, U3 `resolution_text`,
U4 `case_type`, U9 `opened_datetime`; the settings X2, X3, X4; and the taxonomy. A request
missing any of them is refused before a job starts:

```json
{ "error": { "code": "missing_required_columns",
  "message": "The following input field(s) were missing or unmapped: resolution_text (U3 · الحل / Resolution), settings.case_type_scope (X4 · …).",
  "detail": { "fields": [ { "field": "resolution_text", "id": "U3", "label": "الحل / Resolution" }, … ] } } }
```

A required column counts as present when any record carries it. A blank cell in it is
present-but-empty: a blank case id marks an export artefact row (dropped and counted), a
blank description or resolution degrades to «لم يُزوَّد». Optional inputs follow the
"graceful sections" rule: when one is absent its section or table is omitted with a data
note, and a missing metric field becomes a fixed-wording recommendation («تفعيل …»),
never a zero.

[`docs/api.md`](docs/api.md) is the route reference; [`docs/schema.md`](docs/schema.md)
lists every column, setting, reference list, engine key and bundle field.

---

## What a run produces

| Bundle field | Holds |
|---|---|
| `metrics` | The engine output — every Data Mapping §4 key: `KPI`, `MONTHLY`, `CHANNEL`, `CASE_TYPE_RECORDED`, `MAIN_SERVICE`, `SUB_CLASS`, `TIMELINESS`, `RECORDED_VS_TRUE`, `OUT_OF_SCOPE_DETECTED`, `CLASSIFICATION_QUALITY`, `EVENTS`, (X8) `BUNDLE`, `ROOT_CAUSE_TOP`, `BUNDLE_BY_SERVICE`, `SERVICE_FOCUS`, `NEAR_OVER_BY_BUNDLE`, `DEFLECTABLE_PCT`, (conditional) `INQ_PER_100_TX`, `FAQ_COVERAGE`, `FAQ_CATALOGUE_VOLUME`, `AGENT`, `COMPARISON`; the Fujairah-native `RECORDED_VS_ACTUAL`, `RECLASSIFICATION`, `ACTUAL_TYPE`, `SUB_CLASS_BY_TYPE`, `SLA`, `SEVERITY`, `CLOSED`, `DEPARTMENT`, `JOURNEY_MAP`, `GAP_TABLE`, `VALIDATED_FAQS`, `NOTIFICATION_OPPORTUNITIES`, `PATTERNS`; `FRAMEWORKS`, `PARSE_LOG`, `METRIC_GAPS`, `DATA_NOTES` |
| `narratives` | Per language: the 29 `InquiriesReportNarratives` fields (and `SectionNarratives`, the retired sections' prose, now always empty) |
| `classification` | Taxonomy, thresholds, provenance split, mean confidence, `deep_review` (cases reviewed, still low-confidence, duplicates reused), the umbrellas (new ones flagged for confirmation) |
| `report` | The report's sections as data, per language — what the Word documents are drawn from; only the sections in `options.sections` when it is sent |
| `charts` | Renderer-agnostic specs with Data Mapping §6 identities and Builder output ids (O1–O26) |
| `documents` | Word AR/EN, report JSON AR/EN, the companion workbook, and per-case `labels` JSON |
| `snapshot` | This run's comparable figures, for the next run's `history` |
| `warnings` | `low_confidence_after_review`, `umbrellas_pending_confirmation`, `narrative_unverified_figures`, `section_omitted`, `metric_gap`, `english_export_unavailable`, … |

The report has the sections of the ADPF Q2 2026 sample output, which the BO confirmed
(2026-10-14): the executive summary · **Section 01** general statistics and indicator
dashboard · **02** priority service focus and **03** root causes (with root-cause
extraction) · **04** targeted digital-content opportunities · **05** the improvement
roadmap by horizon · the conclusion · the appendices (methodology generated from run
data — R1, qualitative observations, journey friction points). Tenants choose sections
by name (`options.sections`). The Definition Sheet's other sections — the Fujairah
classification-map subsections, customer journey, guidebook digital gaps, digital
transformation, AI use cases — are retired: disabled entries in `sections.py`, kept as
code but never shown.

---

## Layout

```
noveintel_inquiries/
├── pipeline.py            entry points: validate_records, generate_report; the run's stages
├── sections.py            the section registry: what each section needs, prints and reads
├── models/                the contract: columns, records, settings, reference lists,
│                          narratives, bundle. Every layer builds on it
├── api/                   app, routes, deps, errors — the HTTP layer
├── engine/                LAYER 1 — parse (ingest rules, redaction), compute (every key),
│                          frameworks (TAMM registry, working time), taxonomy, wording, localize
├── classification/        LAYER 2 — rules (codebook), model (batched tool calls),
│                          rootcause (R1–R7), umbrellas (discovery), classify (routing)
├── analysis/              S4–S6 qualitative items, tied to case groups the engine counts;
│                          faqs — Section 04's questions and coverage (embeddings + judge)
├── narratives/            LAYER 3 — prompts (Full Report Prompt §1–2), rules, context, writer
├── report/                assemble (the report's sections), labels (static text), word, workbook;
│                          _docx/ — the vendored sword_word_builder that word renders with
├── resources/             taxonomy_adpf_codebook_v1.json — the codebook preset
├── core42/                the Core42 gateway integration
├── jobs/  storage/        the async job layer and document stores
fixtures/                  example request bodies; the Fujairah guidebook and catalogue
tests/                     447 tests; tests/fakes.py answers every model call locally
```

---

## How the handoff was applied

**Classification.** The codebook's golden rule is the classifier's first rule: read the
description and the resolution only, the resolution decides, the CRM title and tag are
context. Provenance is set by the pipeline, never the model (R11), and the ADPF words
are kept so a labelled master round-trips — but «يدوي - مُراجع» here means an AI deep
review, not a person:

| Provenance | Meaning |
|---|---|
| «آلي - موثوق» (`auto`) | Settled quickly: the keyword rules (the codebook's §4 signals and its service-request test) were confident, or the case repeats another case's description and its labels were copied |
| «نموذج» (`llm`) | Below X5: the model's first pass — batches of 40, with the classifier prompt, the taxonomy and its signals, the edge cases and up to 20 reviewed examples most similar to the batch. The model answers in a short schema (batch-local ids, sub-classification codes, a short reason naming the decisive fact in the reply, no `evidence`), mapped back to full labels in code: on 500 reviewed Q2 cases this cut classification cost 45% with accuracy unchanged |
| «آلي - مُصحّح» (`auto_corrected`) | A codebook rule corrected the label in code |
| «يدوي - مُراجع» (`deep_review`) | Below X6, or still breaking a rule: re-analysed with reasoning switched on (`LLM_DEEP_REASONING_EFFORT`, default low — gpt-5.1 does not reason unless asked), in smaller batches (10) with more examples (6 per case), told to weigh the two likeliest services before deciding |

A case still below X6 after the deep review is flagged `low_confidence`, counted with
its best labels, and listed in `classification.deep_review` — nothing waits for a person.
Duplicates (same folded description, at least 12 characters) are classified once.

**Root causes.** With X8 on, every case gets a root cause written to the root-cause
codebook; R1 case specifics are struck out in code, R1-length, R2 and R3 breaches are
sent back once, and a cause still breaking a rule goes to the deep review. Umbrella
discovery then clusters the distinct causes (by id, in chunks), reusing the carried set
first, while the qualitative analysis runs beside it; counts are the engine's.

**FAQs (Section 04).** The priority FAQs are the largest groups of cases asking the
same question — the BO's sample lists them as questions with their case counts — and
FAQ coverage is the share of procedures-umbrella cases a published FAQ answers. Both
come from `analysis/faqs.py`, after umbrella discovery: each case's root cause (else its
redacted description) is embedded and grouped by similarity; each group is shortlisted
against the catalogue by embedding and judged covered / partial / not covered by the
model, which also writes the customer's question for the largest groups; one more call
merges groups that ask the same question. Paraphrase is the reason: the Q2 master writes
10,628 root causes in 5,766 ways, so neither exact strings nor keywords count a question
reliably. The verdicts are per-case labels (`faq_id`, `faq_status`, `faq_match`) that the
engine sums. The tool writes FAQ questions, never answers (handoff scope). The embedding
model is `CORE42_MODEL_EMBED` — approved models only.

**Narratives.** The Full Report Prompt's Arabic system prompt, near verbatim, with its
hard rules and the tenant vocabulary. There is no English writing prompt: the
narrative is written in three groups side by side, and one translation call per group
takes that group's finished Arabic — started the moment it is final, while the others
are still being written — and returns English,
with a glossary of the English names the report already prints (taxonomy, umbrellas,
frictions, channels, entity, period) so the prose matches the tables. Fixed headings and
taxonomy names are never sent for translation; the English wording rules and figure
check apply to the translation as to any narrative. The pre-flight checklist (§6) is
enforced in code: banned words replaced, vocabulary applied, list items stripped of
leading symbols, conditional fields emptied when their input is absent, initiative and
use-case counts taken from the referenced item, and every figure checked against the
context with one corrective retry. Prompts across the service share one style block, so
none contradicts another.

**Deliberate adaptations** (each recorded where it is made):

- The classifier returns `main_service` always, not only with X8 — the codebook nests
  every sub-classification under a main service, so one cannot be chosen without the other.
- `intro_statement` summarises the sections in `REPORT_SECTIONS`, not "five sections".
- Umbrella case counts are computed from the assignment, not returned by the model
  (hard rule 10 overrides §0b's `cases` field).
- Root-cause R6 sends an out-of-remit case to «أخرى»; the ADPF reviewers kept such cases
  under the topic's main service (10 «أخرى» cases in 10,628). The taxonomy edge case
  follows the reviewers; the cause still states the reason.
- Coverage figures from the guidebook comparison are a status (Covered / Partially /
  Missing), not a percentage — the model never emits a number (R6).
- Severity in the gap table is a deterministic priority with ADPF wording («فرصة رقمية» not «فجوة حرجة»).

---

## Known limitations

- **Classifier agreement is below the 90% bar on its own.** On fresh samples of the ADPF
  Q2 reviewed cases, the defaults (X5 0.75 / X6 0.65) agree with the reviewers on the main
  service 76–80% of the time and on the sub-classification ~70%; 83% where the model is
  confident (≥ 0.85). The model is over-confident in the 0.65–0.85 band (57%). ADPF's own
  practice was a single 0.90 gate (X5 = X6 = 0.90), which sends that band to review.
  Growing `taxonomy.examples` from confirmed review-queue labels is the lever.
- **A large X8 run is long.** Every case goes to the model for its root cause: about
  one batch of 20 per 20 cases, five at a time. Size `NOVEINQ_JOB_MAX_RUNTIME_SEC` and
  `host.json`'s timeout for the tenant's volume.
- **Open spec items are configuration here, not answers.** The transactions denominator
  (open item 2) is a per-row `counts_in_denominator` flag; the recorded-vs-true crosswalk
  basis (item 4) is the catalogue's `crm_service_map` — the preset's learned crosswalk
  gives 79.3% on the Q2 master, not the delivered 71.7%.
- **The English report needs English catalogue names.** Without them it is withheld
  with `english_export_unavailable` (Domain 01 ruling).

---

## Deployment

[`docs/deployment.md`](docs/deployment.md) is the guide. Three settings choose where
things live — `NOVEINQ_STORAGE_BACKEND` (`local` | `blob`), `NOVEINQ_JOB_BACKEND`
(`local` | `table`), `NOVEINQ_JOB_DISPATCH` (`inprocess` | `queue`). On-prem installs no
Azure package. `host.json`'s `functionTimeout` must stay above
`NOVEINQ_JOB_MAX_RUNTIME_SEC`.
