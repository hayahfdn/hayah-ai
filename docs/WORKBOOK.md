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

## Update: menu, colours, well types, phones (2026-11-18)

- **Side menu**: «الآبار» and «الأضاحي» are drop-down lists of every month (current month shown by default and listed first);
  «المقاولون» has one list per country (from the contractor's country); «المسؤولون» lists محمد، هيا، غازي (accounts MOHAMMED,
  CLIQ, GHAZI). The Excel tabs at the bottom stay on computers; on phones a sheet picker at the top replaces them.
- **Hidden fields**: country, city, village, construction start, received date, last updated and completion date are no longer
  entered or shown. Their stored values stay in the database, exports and Google Sheets. Country now follows the contractor
  automatically, so reports by country keep working.
- **Contractor colours**: `contractors.color`. Every well row (and phone card) uses its contractor's colour in every month;
  changing the contractor changes the colour. New contractors get an unused calm colour automatically; managers can change it
  in Contractors. Delivery state is shown as a stripe on the Well ID (green delivered, amber finished and waiting).
- **Well types**: only يدوي، متوسط، عميق، شمسي. Every spelling is unified on save (`app/services/well_types.py`) and migration
  0005 unified the existing data, logging each old value in audit_log (`project.well_type_normalized`). The one old
  "سطحي كهربائي" project is now "كهربائي", kept on that project only and never offered for new wells. Values matching no rule
  are left untouched for a manager to review.
- **Phones**: wells and sacrifices appear as cards with every action (edit, details, record delivery, plaque), tables become
  stacked cards, touch-size buttons, 16 px inputs (no iOS zoom). A Table / Cards switch is on every sheet.
- **Font**: IBM Plex Sans Arabic (self-hosted), one family for Arabic, Latin and digits.
