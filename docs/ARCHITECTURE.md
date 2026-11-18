# Architecture

```
 WhatsApp groups A–D ──(team forwards, tagged #A/#B/#C/#D)──► Intake number (Meta Cloud API)
                                                                  │ webhook (signed)
 Dashboard (React, AR/EN) ──HTTPS──► nginx ──► FastAPI API ◄──────┘
                                                 │   │
                                    PostgreSQL ◄─┘   └─► jobs table ◄── Worker (Python)
                                 (source of truth)                     │  ├─ process_inbound → extraction (rules / Claude)
                                                                       │  ├─ whatsapp_media  → Google Drive
                                                                       │  ├─ sheets_sync     → Google Sheets
                                                                       │  └─ daily_health_check
```

## Components

| Component | Choice | Why |
| --- | --- | --- |
| Database | PostgreSQL 16, SQLAlchemy 2, Alembic | Transactions, constraints, JSONB for raw payloads |
| API | FastAPI | Typed validation on every endpoint, OpenAPI docs |
| Jobs | A `jobs` table + Python worker (`SELECT … FOR UPDATE SKIP LOCKED`) | Durable, retryable, idempotent, no extra service to run or pay for |
| Dashboard | React 18 + TypeScript + Vite, plain CSS with logical properties | RTL/LTR from one stylesheet; small bundle (74 KB gzipped) |
| Sheets/Drive | Google APIs via OAuth on HAYAH's own Google account | HAYAH owns the files |
| WhatsApp | Meta Cloud API, dedicated intake number | Official, does not touch the main business number |
| AI | Anthropic API behind an `Extraction` JSON contract; free rules engine as fallback | Cost cap and manual mode without losing function |
| Deploy | Docker Compose: db, api, worker, web (nginx), backup | One small VPS |

**n8n:** not used for Phases 1–4. The Python worker covers retries, schedules and
webhooks with fewer moving parts. n8n Community can be added later as an extra
container if HAYAH wants to build visual workflows on top of the API.

## Data model (17 tables)

`projects` (one row per Well ID) · `project_events` (immutable timeline) ·
`audit_log` (who changed what, before/after) · `inbound_messages` (raw WhatsApp
copies) · `review_cases` (Pending Review) · `delivery_confirmations` (pending →
approved/rejected) · `maintenance_records` (MNT-000001…) · `media_assets` (Drive
file id, SHA-256, sender, source message) · `contractors` · `users` · `jobs` ·
`sheet_row_state` + `sync_runs` + `sync_conflicts` (Sheets sync) ·
`app_settings` · `usage_records` (cost tracking) · `counters`.

## Key flows

**Message intake.** Webhook verifies Meta's signature → raw message stored once
(unique WhatsApp id) → job extracts a validated `Extraction` JSON
(docs/schemas/Extraction.json) → decision:
exactly one explicit, existing Well ID + high confidence + registered sender →
apply; delivery → *pending* confirmation only; anything else → Pending Review.

**Delivery.** Group B / dashboard → `delivery_confirmations` (pending) → manager
approves in the dashboard → project marked delivered, date recorded, timeline +
audit entry, Sheets sync queued.

**Sheets sync.** DB → "Master Projects" keyed by Well ID. Remembers what it last
wrote per row; a cell a person changed is kept and logged as a conflict until a
manager keeps the DB value or accepts the sheet value (accepted values go
through the normal validated update; delivery fields can't be accepted from the
sheet). Duplicate and unknown rows are reported, never deleted. Other tabs are
read-only reports rewritten each sync. Failures retry with backoff.

**Media.** SHA-256 duplicate check → Drive folder `Raw Footages/<WellID>/` etc.
→ name `<WellID>_<date>_<CATEGORY>_<NNN>.<ext>` → SHA stored in Drive
appProperties too, so a crash between upload and DB commit can't create a
second copy. No Well ID → `Unassigned Media/` + review case.

## Security

bcrypt passwords (10+ chars, upper + digit), JWT sessions revocable per user,
role checks on every endpoint (5 roles; contractors see only their projects),
login rate limiting (app + nginx), input validation, file type sniffing, size
limits, security headers + CSP, HMAC-verified webhooks, secrets only in env or
`secrets/`, non-root containers, `pg_dump` backup profile.
