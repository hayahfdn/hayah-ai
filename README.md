# HAYAH AI – Intelligent Operations System

One central platform for HAYAH Foundation well projects: every well has one
**Well ID** and a complete digital history, from order through construction,
delivery, final video and maintenance. Arabic (RTL) and English (LTR).

**Status: Phases 1–4 built and tested** (database, backend with roles, dashboard,
Google Sheets/Drive sync). WhatsApp, Claude AI, video and cost modules have
working interfaces and offline stand-ins, and get their live connections in
Phases 5–9. See [docs/PHASE_REPORT_1-4.md](docs/PHASE_REPORT_1-4.md).

## Quick start (Docker)

```bash
cp .env.example .env            # set POSTGRES_PASSWORD and HAYAH_JWT_SECRET
docker compose up -d --build
docker compose exec api python -m app.cli create-admin --email you@hayah.org --name "Your Name"
# optional: 12 clearly marked SAMPLE projects (Well IDs 9001–9012)
docker compose exec api python -m app.cli seed-demo
```

Open http://localhost:8080. Everything runs offline in **mock mode** until the
real Google, WhatsApp and Anthropic credentials are added (see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

## Development

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --reload
.venv/bin/pytest                # needs a PostgreSQL test database (see tests/conftest.py)
# frontend
cd frontend && npm install && npm run dev     # http://localhost:5173, proxies /api to :8000
```

## Repository layout

| Path | What it is |
| --- | --- |
| `backend/app/models.py` | PostgreSQL schema (source of truth) |
| `backend/alembic/` | Database migrations |
| `backend/app/api/` | REST endpoints (auth, projects, delivery, maintenance, media, review, intake, sync, settings) |
| `backend/app/services/` | Business rules: projects, delivery approval, maintenance IDs, media/Drive, Sheets sync, job queue, intake |
| `backend/app/integrations/` | Replaceable adapters: Google Sheets, Google Drive, WhatsApp Cloud API, AI extraction |
| `backend/app/worker.py` | Background worker: retries, scheduled sync, daily health check |
| `backend/tests/` | 49 automated tests |
| `frontend/` | React + TypeScript dashboard (Arabic RTL / English LTR) |
| `docs/` | Architecture, deployment, WhatsApp plan, costs, open questions, phase reports, JSON schemas |
| `scripts/` | Google authorization and live Google check |

## Non-negotiable rules built into the code

- Well IDs are unique (database constraint) and never guessed. Uncertain messages become **Pending Review** cases.
- Only an **approved delivery confirmation** marks a well delivered. Construction or video completion never does.
- Originals are never deleted: the Drive adapter has no delete function; history tables are append-only.
- Every change is written to the project timeline and the audit log, in the same transaction.
- No API keys in the frontend. Secrets come from `.env` and `secrets/` only.
- No unofficial WhatsApp automation. Only the official Cloud API on a dedicated intake number.


## Finance workbook
Excel-style pages for the Financial Summary, Wise, every contractor, partners and each month (wells and sacrifices), plus "Edit with a prompt". See [docs/WORKBOOK.md](docs/WORKBOOK.md).
