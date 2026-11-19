# Connected order workflow (Hayah's request, 19 Nov 2026)

Order → automatic plaque draft → employee confirms with the customer → approved plaques
section → plaque sent to the contractor → final video → sent to the customer on WhatsApp.
Built in four phases, one pull request each.

## Phase 1 (this PR)

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
