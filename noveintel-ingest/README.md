# NoveIntelligence — document ingestion

Excel workbooks → one chunk per row, every value carried with its column name →
Core42 embeddings → pgvector. Usable on its own, and by the analytics services
through what it exports: `faq-catalogue` writes the inquiries service's
`reference.faq_catalogue`. It imports nothing from either service.

```bash
cd noveintel-ingest
cp .env.example .env                 # set CORE42_API_KEY
uv sync --extra local                # Python 3.12; the extra is the embedded Postgres
uv run noveintel-ingest inspect  "الاسئلة الشائعة.xlsx"          # what would be embedded — no model call
uv run noveintel-ingest ingest   "الاسئلة الشائعة.xlsx" --collection adpf_faq_te3l
uv run noveintel-ingest search   "كيف أتابع طلبي" --collection adpf_faq_te3l --skip-hidden
uv run noveintel-ingest faq-catalogue "الاسئلة الشائعة.xlsx" -o faq_catalogue.json
uv run pytest                        # no network
```

As a library: `ingest_workbook(path, collection=…)`, `search(query, collection=…)`,
`read_workbook(path)`, `faq_catalogue(path)`.

## What a chunk is

One spreadsheet row, serialised with its column names, after the document and sheet
names:

```
Document: الاسئلة الشائعة | Sheet: FAQs | CA Reviewed Arabic Question: ما هو نظام الخصم المباشر؟ | الصيغة المقترحة: نظام يهدف إلى … | الإدارة المعنية: التحصيل والمتابعة | الخدمة: تسجيل جهة عمل | صنف المتعامل: جهات العمل
```

- **Every sheet is read, hidden ones too**, flagged `sheet_hidden`; `--skip-hidden`
  leaves them out at ingest or at search.
- **The header row is found**, not assumed: a title or a blank row above the table is
  skipped, and a title merged across the table is not taken for a header. Merged cells
  are filled from their top-left value, blank headers become `Column C`, repeated ones
  `Notes (2)`. Empty rows, and rows that repeat the header, are dropped.
- **Empty cells are left out** of the text. `--exclude-column` keeps a column (a row
  number, a reviewer's note) out of the embedded text; it is still stored.
- **A row too long for one embedding** (over 6,000 characters) is split on its longest
  field; every part repeats the row's other fields, so no part loses its context.
- **Stored per chunk:** the embedded text, the original cells exactly as read (line
  breaks included) in sheet order, document, sheet, Excel row number, part.

## Incremental re-ingest

Chunk ids are content-addressed. Re-ingesting a document embeds only new or edited
rows; unchanged rows keep their vector (their row number is updated if they moved),
and rows gone from the file are deleted. All in one transaction: a failed embedding
call changes nothing. Several documents can share a collection; `drop <collection>
--document-id <id>` removes one.

## Embedding model

Only the two approved embedding models are accepted; anything else (the gateway also
serves `embed-v-4-0`) is refused.

| `CORE42_MODEL_EMBED` | Approved name | Native size |
|---|---|---|
| `text-embedding-3-large` (default) | Embeddings 3 Large | 3072 |
| `qwen3-embedding` | Qwen3 Embedding 8B | 4096 |

Embeddings 3 Large is the default, measured on the ADPF FAQ workbook
(`scripts/compare_models.py`, 2026-10-16) at the stored 1024 dimensions:

| Task | Result |
|---|---|
| Each FAQ's question → its answer (142 queries) | right row first 71%, in the top 5 94% |
| Customer phrasing, Emirati colloquial (60 queries) | right row first 80%, top 3 93%, top 5 98% |
| Telling answerable from unanswerable by the top score (12 unanswerable) | AUC 0.94; best threshold 0.45 → 92% correct |

Cutting 3072 → 1024 dimensions cost nothing measurable. Qwen3 Embedding could not be
measured: on Core42 it answered mostly 429 "Model is overloaded", the rest after
~50 s or with "no healthy upstream". It stays selectable (`--model qwen3-embedding`);
re-run the comparison before switching. It is instruction-aware: a search query is
sent as `Instruct: … Query: …`, a document as-is.

Both models are Matryoshka-trained: vectors are cut to `NOVEINGEST_EMBED_DIMENSIONS`
(default 1024) and re-normalised here, which needs no gateway support and keeps
pgvector's HNSW index available (it indexes up to 2000 dimensions).

A collection is bound to the model and size that created it: vectors from two models
are not comparable, so a mismatched embedder is refused rather than mixed in. Change
model → new collection.

`--model local-hash` is a deterministic, offline stand-in (character n-gram hashing)
for tests and for trying the flow without gateway access. It matches wording, not
meaning.

## Vector store

pgvector, one table per collection (`ingest_<collection>`) and a registry,
`ingest_collections`.

| `NOVEINGEST_PG_DSN` | Where |
|---|---|
| `postgresql://<you>@localhost:5432/noveintel` | A local Postgres — the working setup on a Mac (below). |
| any Postgres with the `vector` extension | Production (Azure Database for PostgreSQL offers pgvector). |
| unset | An embedded Postgres 16 + pgvector 0.6 started in `NOVEINGEST_PG_DATA_DIR` (`.pgdata/`) — `pgserver`, the `local` extra. A test convenience: wheels up to Python 3.12 only; the test suite uses it. |

Local Postgres on macOS, once:

```bash
brew install postgresql@17 pgvector        # pgvector 0.8 is bottled for 17 and 18
brew services start postgresql@17          # runs at login; `brew services stop postgresql@17` to stop
/opt/homebrew/opt/postgresql@17/bin/createdb noveintel
echo "NOVEINGEST_PG_DSN=postgresql://$USER@localhost:5432/noveintel" >> .env
```

The store runs `CREATE EXTENSION IF NOT EXISTS vector` itself. Inspect it with
`/opt/homebrew/opt/postgresql@17/bin/psql noveintel` (`\dt ingest_*`).

## With the inquiries service

`faq-catalogue` turns a FAQ sheet into `reference.faq_catalogue` — the visible sheet
with an Arabic question column, columns found by header (`--question-ar`,
`--answer-ar`, `--service-column` override). Nothing else is needed: the pipeline's
FAQ detection embeds the catalogue itself on each run (same approved models) and does
not query the vector store.

Identity redaction (R3) is the inquiries service's, at its ingest. This package
embeds what it is given: use it for reference content (FAQs, guidebooks,
catalogues), not for case exports.

## Settings

| Variable | Default | What it does |
|---|---|---|
| `CORE42_API_KEY` | — | Required to embed (not for `inspect` / `faq-catalogue`). |
| `CORE42_BASE_URL` | `https://api.core42.ai/v1` | A trailing `/chat/completions` or `/embeddings` is stripped. |
| `CORE42_MODEL_EMBED` | `text-embedding-3-large` | See above. |
| `NOVEINGEST_EMBED_DIMENSIONS` | `1024` | Stored vector size. |
| `NOVEINGEST_EMBED_BATCH` | `64` | Texts per embeddings request. |
| `LLM_MAX_RETRIES` / `LLM_RETRY_DELAY` | `2` / `2` | 429 (10 s floor), 5xx, timeouts. A 400 is not retried. |
| `CORE42_REQUEST_TIMEOUT` | `120` | Seconds per request. |
| `NOVEINGEST_PG_DSN` / `NOVEINGEST_PG_DATA_DIR` | — / `.pgdata` | See *Vector store*. |
