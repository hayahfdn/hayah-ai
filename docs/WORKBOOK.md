# Finance workbook and "Edit with a prompt"

## Pages (menu: Workbook / دفتر الحسابات, managers only)
Tabs at the bottom, like the Excel file:
Financial Summary · Wise · Pak 1–5 · Nepal 1–3 · Bangladesh 1 · Mohammed · Ghazi · Haya Cliq · one tab per month of wells · Tanzania 1 · one tab per month of sacrifices.

- **Financial Summary** – headline numbers, monthly chart, sales/profit by month (wells and sacrifices), contractor payments (invoiced / paid / owed / % paid, subtotal per country), ads by channel, operating expenses, bank and partner accounts, this month vs last month to the same day. Everything is calculated from the database.
- **Contractor tab** – the contractor's wells and sacrifices (editable), its payments, and invoiced/paid/owed. Invoiced = sum of the *cost* of its wells and sacrifices.
- **Wise** – every money row with a running balance.
- **Partner tabs** – taken from company, spent on company, withdrawn, start-up loans, and "still with partner" (= taken − spent).
- **Month tabs** – wells or sacrifices whose order date is in that month, with a totals row. Green = delivered, pink = not yet.

New tabs appear by themselves: add a contractor in Contractors, or add a row with a new month.
`python -m app.cli setup-workbook` creates the standard tabs (safe to repeat; the migration does not insert data).

## Rules
- Money rows are never deleted. A wrong row is **voided** with a reason and stays in history.
- Every edit is validated, versioned (two people can't overwrite each other) and written to the audit log.
- Delivery: a manager typing a delivery date in a sheet records a delivery confirmation and approves it in their name (audited). Construction completion never sets delivery.
- Contractors, maintenance staff and viewers cannot see the finance pages.

## Edit with a prompt (Ctrl+K, managers only)
1. Type what to change, in Arabic or English.
2. Claude proposes changes. The server checks each one with the same validation as the pages and shows before → after. **Nothing is saved yet.**
3. Press Apply. All changes are saved together (all or nothing) through the normal audited code. If someone changed the same row in the meantime, nothing is applied.

Guard rails enforced by the server, not by the AI: only edit/add/void operations exist (no delete); delivery can't be changed by a prompt; a new Well ID or sacrifice number must be written in the prompt itself; contractors/accounts must match an existing code.

**Setup (needs approval – paid API):** set `HAYAH_ANTHROPIC_API_KEY` on the server and turn AI on in Settings. Model `claude-opus-5-5` (change with `HAYAH_ANTHROPIC_MODEL`). Each request is costed (`HAYAH_ANTHROPIC_INPUT_USD_PER_MTOK`/`_OUTPUT_`, default $4/$20 per million tokens; a typical request is about $0.02) and stops when the monthly AI budget (default $100) is reached. Until the key is added the button explains what is missing and the sheets work normally.

## Replace all imported data with a new workbook (Settings → Import workbook, super admin only)

For loading a newer copy of the Excel workbook over the data earlier imports loaded
(`POST /api/admin/import-workbook/replace`, `app/services/workbook_replace.py`).

1. **Preview** (saves nothing): counts of what is updated, deleted, kept and added, the wells and
   sacrifices kept and why, the hand edits the new file will overwrite, and renumbering to check.
2. **Apply**: type `REPLACE` (or `استبدال`). A database backup is written first
   (`app/services/backup.py`: `pg_dump` file plus a JSON copy of every table, in `<data>/backups`,
   downloadable from the page). If no backup can be written, nothing changes.

Rules:
* Only rows that came from a workbook import are touched (wells: their "created" timeline event says
  `workbook_import`; sacrifices: their latest create record carries the import note; money rows: the ids
  each import listed). Hand-typed, Shopify, WhatsApp and sample rows are never changed.
* Same number in the new file → **updated in place** (same record, so plaque, certificate, contract and
  invoice number, final video, tasks, chats, Shopify link, photos and history stay linked). An empty cell
  never wipes a value; notes typed in the system are kept; a new delivery date is recorded as approved.
* Not in the new file → deleted, **unless work was added in the system** (any table linking to it, a
  timeline event or delivery confirmation not from the import, a saved contract or plaque, a hand edit).
  Those are kept and listed.
* Money rows from earlier imports are replaced by the new file's money rows. A row matched to a Wise payment
  moves its match to the identical new row (same date, kind, direction, account, amount, reference), or is kept.
* The earlier imports are marked removed (`workbook.import_removed` with `replaced_by`), and the replace is
  logged as a new `workbook.import`, so it can itself be removed or replaced later. Full copies of deleted
  rows are in the audit log (`workbook.replace_deleted`).

Restore a backup on the server if ever needed:
`docker compose exec -T db pg_restore --clean --if-exists -U hayah -d hayah < hayah-…-before-replace.dump`
