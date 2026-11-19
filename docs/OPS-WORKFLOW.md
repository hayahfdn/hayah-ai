# Connected order workflow (Hayah's request, 19 Nov 2026)

Order → automatic plaque draft → employee confirms with the customer → approved plaques
section → plaque sent to the contractor → final video → sent to the customer on WhatsApp.
Built in four phases, one pull request each.

## Phase 1

**Employee role.** The staff role is now called "موظف / Employee". Its permissions did not change:
cost, contractor cost, profit, ads and the finance workbook stay managers-only and are removed by
the API (tests in `tests/test_staff_visibility.py`).

**Phone numbers** (`backend/app/services/phones.py`, Google libphonenumber via `phonenumbers`).
`customer_phone` keeps the number exactly as typed. Three new columns hold the standard copy:
`customer_phone_e164` (e.g. `+962791234567`), `customer_phone_country` (ISO code) and
`customer_phone_status` (`valid`, `needs_country`, `invalid`, `empty`). Same columns on
sacrifices, which now also keep the customer's phone.
- `+44 07712345678` → `+447712345678` (the extra local 0 is dropped; nothing else is removed).
- `0791234567` + Jordan → `+962791234567`. Without a known country the number is marked
  `needs_country` and the order form asks the employee to choose. The well's country is never
  used: it is where the well is built, not where the customer lives.
- A Shopify line-item number written locally takes the country of the checkout phone only when
  both are the same number.
- Invalid numbers are flagged, never "fixed" by guessing. `POST /api/phones/check` gives the
  live preview in the form.

**Prayers.** Sacrifice plaques show the name on its own line and the prayer under it, using
Hayah's six texts word for word; the name is never repeated inside the prayer (the aqiqa prayers
now say بارك فيه / فيها). The prayer is picked from clear words in the dedication only
(المرحوم/المرحومة، أرواح/موتانا، فاعل خير، أم/أبو، عائلة ...). When gender or living/deceased is
not clear, a neutral prayer is used and a red note asks the employee to confirm. The prayer text
can always be edited.

**Fonts.** Bundled with the app (SIL Open Font Licence): Cairo, Tajawal, Kufam, Alexandria,
IBM Plex Sans Arabic, Amiri, Noto Naskh Arabic, Aref Ruqaa. Media Pro and Niloofar are not
installed (no free licence could be confirmed); El Messiri and Reem Kufi are listed as their
stand-ins. The name and the prayer each have font, size, line spacing, alignment and
bold/regular. Preview and export draw on the same canvas with the same font files.

**Well plaque middle text.** The text between the project number and the month (well type +
"صدقة جارية عن:") now grows when short and shrinks when long, measured per font so it never
leaves its space, and is always centred across and down. Older saved plaques redraw the same way.

## Phase 2: automatic plaque, its states and versions, approved plaques section

**One plaque per order** (`plaques`, `plaque_versions`; migration 0007, new tables only).
A new order from Shopify, the dashboard or WhatsApp intake gets version 1 automatically: a
draft made from the order (name, well type or animal, project number, month, prayer from clear
words only). Seeded sample orders and imported old orders get no automatic draft; open them in
the designer and use «إنشاء مسودة لوحة». The automatic draft is kept unchanged; every save in
the designer adds a new version, nothing is overwritten.

**Missing information is listed, never guessed** (`services/plaque_flow.py: compute_missing`):
name, male/female + living/deceased, well type, animal type, country. A plaque with missing
information cannot go to the customer or be approved (the server refuses, HTTP 409).

**States** (Arabic labels as shown in the app):

| State | Meaning |
|---|---|
| قيد الإنشاء | automatic draft with missing information |
| جاهزة للمراجعة | complete, waiting for an employee |
| بانتظار موافقة العميل | sent to the customer |
| تحتاج إلى تعديل | the customer asked for changes (their note is kept) |
| تم اعتمادها من العميل → معتمدة وجاهزة للإرسال للمقاول | customer approval moves it straight to the approved section |
| تم إرسال اللوحة للمقاول | sending recorded with contractor, country and date |

Each move is checked on the server and written to the order's timeline (wells) or the audit log
(sacrifices). A saved PNG version is needed before sending to the customer or approving.

**Pages.** «طلبات تحتاج تأكيد اللوحة» (`/plaques/confirm`) and «اللوحات المعتمدة – جاهزة للإرسال
للمقاول» (`/plaques/approved`), both with a red live count in the menu (re-read every 10 seconds;
on a phone the count is on the menu button). The approved section shows the plaque images, single
download, ZIP of the selected plaques, sharing (on a phone the image goes straight to WhatsApp
through the share sheet), and «تم إرسال اللوحة للمقاول» with contractor, contractor's country and
date. A plaque leaves the list only when sending is recorded; the «تم الإرسال» tab keeps the history.
The designer shows the plaque's state, what is missing and the same buttons.

**API** (employees and managers only; contractors and viewers get 403; no money fields):
`GET /api/plaques?group=confirm|approved|sent`, `GET /api/plaques/counts`, `GET /api/ops/counts`,
`GET|POST /api/plaques/order/{well|sacrifice}/{number}`, `GET /api/plaques/{id}`,
`POST /api/plaques/{id}/status`, `POST /api/plaques/{id}/send-to-contractor`,
`GET /api/plaques/{id}/file`, `POST /api/plaques/zip`.

**Existing plaques** are carried over by the migration as versions: approved well plaques land in
the approved section (so the team can record which were already sent), the rest are «جاهزة للمراجعة».
