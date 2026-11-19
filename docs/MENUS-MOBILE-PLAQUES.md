# Menus, mobile layout, contractor colours, well types and plaques (2026-11-18)

## Side menu
- **الآبار** and **الأضاحي**: one drop-down each with every month; the current month is shown by default and marked "الشهر الحالي". Month pages keep their own data (filtered by order date). Each month page has previous / next month buttons.
- **المقاولون**: one drop-down per country (Pakistan, Nepal, Bangladesh, India, Tanzania, then others). Items link by contractor code, so equal names in two countries never mix.
- **المسؤولون**: محمد (MOHAMMED), هيا (CLIQ), غازي (GHAZI) partner ledgers.
- Managers open these inside the workbook (`/book/...`). Employees get `/wells/<month>` and `/contractor/<code>` (wells only, no cost). Sacrifices, ledgers and partners stay managers-only (server-side, `GET /api/nav`).
- The old tab strip at the bottom of the workbook was removed.

## Hidden fields
Country, city, village, construction start, received date, last updated and completion date are no longer shown or edited in the forms, sheets and order page. The columns and their data stay in the database, Sheets sync and CSV export. A well's country now follows its contractor (so reports by country keep working); the build dates still fill in from the construction status.

## Contractor colours
`contractors.color` (migration 0005). Every existing contractor got a colour; a new contractor gets the next unused one; managers change it on the Contractors page. Rows on every month, contractor and master sheet use it.

## Well types
Only يدوي، متوسط، عميق، شمسي (plus كهربائي, kept for the one old well and never offered). Every write is normalised (`app/services/well_types.py`, model validator + API validation). Migration 0005 unified the existing rows after the pre-update backup, logged as `well_types.normalized` in the audit log (with each well's old name). Settings → Integrations → أنواع الآبار shows counts, anything left, and an **Undo** per run. "يدوي مع سيراميك" also adds "سيراميك" to extras (put back on undo).

## Plaques from an order
- Every well row (sheets, cards, projects list, order page) has a plaque chip: **＋ لوحة** (none), **مسودة** (draft), **✓ معتمدة** (approved; opens the image).
- The designer opens filled from the order: number, name (dedication, then customer), plaque wording of the type, flag from the contractor's country; an "بيانات الطلب" box shows the order and contractor.
- **حفظ كمسودة** saves a new version; **اعتماد اللوحة** saves and approves. Approving when another plaque is already approved asks first. Every version stays (Versions list: load, view, approve this version).
- Stored on the order: `projects.plaque_status`, `plaque_media_id`, `plaque_approved_at`, `plaque_approved_by`; versions are the existing `plaque_saved` events and PLAQUE media. API: `POST /api/projects/{id}/plaques` (`approve`, `replace`), `POST /api/projects/{id}/plaques/{event}/approve`, `GET /api/projects/{id}/plaques/file/{media}`.

## Font and phone
IBM Plex Sans Arabic (served from the site, weights 400–700). On phones: cards instead of grids (with a Table switch that keeps every grid feature), plain tables become one card per row, a bottom bar (home, wells this month, sacrifices / projects, plaques, menu), 44px touch targets, 16px inputs (no iOS zoom), full-height bottom-sheet dialogs.
