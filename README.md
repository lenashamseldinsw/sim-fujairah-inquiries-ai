# NoveIntelligence analytics services

Two headless FastAPI services for the NoveIntelligence platform, deployable to Azure
Functions or on-prem:

| Service | Domain | What it does |
|---|---|---|
| [`noveintel-inquiries/`](noveintel-inquiries/README.md) | 03 — Customer Inquiries Analytics | Classifies a period's CRM cases under the tenant's taxonomy and the codebooks, computes every figure deterministically, and writes the S0–S11 report in Arabic and English, with a companion workbook and per-case labels the platform stores for the next run. |
| [`noveintel-complaints/`](noveintel-complaints/README.md) | 02 — Complaints Analytics | The Fujairah Pulse complaints pipeline behind the same API shape. |

Each folder is self-contained — its own `pyproject.toml`, `.env.example`, tests, and
four documents: `README.md`, `docs/api.md`, `docs/schema.md`, `docs/deployment.md`.

Beside them, [`noveintel-ingest/`](noveintel-ingest/README.md) is a library and CLI,
not a service: it reads every sheet of an Excel workbook, embeds each row with its
column names (Core42, approved embedding models only) into pgvector, and exports a
FAQ sheet as the inquiries service's `reference.faq_catalogue`.

```bash
cd noveintel-inquiries            # or noveintel-complaints
cp .env.example .env              # set CORE42_API_KEY
uv sync --extra api --extra serve
uv run uvicorn noveintel_inquiries.api.app:app --reload    # http://localhost:8000/docs
uv run pytest
```

Runs are asynchronous: `POST /v1/<domain>` returns a job to poll at
`GET /v1/jobs/{job_id}`.

This is the `noveintel` branch. The Fujairah Pulse Streamlit application the services
were ported from is on the `main` and `real` branches and is not part of this branch.
[`CLAUDE.md`](CLAUDE.md) is the development guide.
