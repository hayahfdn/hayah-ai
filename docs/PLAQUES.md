# Plaque designer

Menu: **Plaque designer** (`/plaque`), or **Design plaque** on a well's page (`/plaque/<WellID>`).
Managers and Team members can save; contractors cannot. Rule-based: the browser draws the plaque, no AI.

Layout matches HAYAH's current square plaque (1080 × 1080): HAYAH logo, country flag, Bismillah and
verse, project number pill, well type and "صدقة جارية عن:", month and year pill, the name in large red,
the well icon, a short prayer (حفظه الله …), the prayer paragraph and the footer.

Filled in from the well record (all editable):
- Name: `dedication` if set, otherwise `customer_name`, otherwise فاعل خير
- Project number: Well ID · Well type: `well_type`
- Month and year: completion date, else delivery date, else order date
- Flag: from the well's country (or the contractor's country); pick another or upload one
- Prayer: six variants (living or deceased; male, female or group), guessed from the name
  (e.g. المرحومة → deceased female). Pick another or edit the text.
- Well icon: built-in hand-pump well, an uploaded image, or none

Export: PNG (1080, 2160, or 20/30 cm at 300 dpi, with DPI written into the file) and a one-page PDF
at the physical size. **Save to well history** stores the PNG in Drive under `Plaques/<WellID>/`
(media category `PLAQUE`) and adds a `plaque_saved` event that keeps the design, so it can be
reopened and edited from the designer's "Saved plaques" list.

Code: `frontend/src/plaque/render.ts` (drawing and export), `frontend/src/plaque/PlaqueDesigner.tsx`,
`backend/app/services/plaques.py`. Flags are from flag-icons (MIT, `frontend/public/flags/`).

## Update: sacrifice plaques, well icons, flags (2026-11-18)

- **Sacrifice plaque** (tab "لوحة ذبيحة", `/plaque/sacrifice/<No>`): portrait 1024 × 1536, matching HAYAH's sacrifice
  plaques. Types: صدقة، عقيقة مولود، عقيقة مولودة، صدقة مع الإطعام، عقيقة مع الإطعام. Picking a type fills the header
  (Bismillah + Al Imran 92, the aqiqah hadith, or Al Insan 8), the title (e.g. "خروف عقيقة المولودة:"), the red line and
  the prayer (aqiqah prayers use the child's first name). All fields stay editable. Filled from the workbook: number,
  donor name (or `dedication`), animal, type (from the intention), month, flag and Arabic country name (contractor's country).
  `GET /api/plaques/sacrifices/<No>` returns only plaque fields (never cost or price), so Team members can use it.
  Saved PNGs go to Drive `Plaques/Sacrifices/<No>/`; the design is kept in the audit log (`plaque.saved`).
- **Well icons**: six HAYAH well types (hand pump, hand pump with tank, one or two tanks with 4 taps, one or two tanks
  with a tap wall) in `frontend/public/wells/`, background removed. Icon can sit left or right.
- **Flags**: Pakistan, Bangladesh, Nepal, India, Tanzania first, then all 22 Arab League countries, then others.

## Update: plaques from the order, with approval (2026-11-18)

- **Plaque button beside every well order**: in every month sheet, contractor sheet, the Master Sheet, Projects and the
  phone cards. No plaque yet → opens the designer filled in from the order (Well ID, owner/dedication, well type, contractor,
  country flag, month). Approved → shows the approved plaque.
- **Designer**: an order strip at the top (order, owner, type, contractor, plaque status, back to the order).
  "Save as draft" keeps a version; **"Approve plaque"** shows the exact final PNG first, then "Approve as final" saves it
  and links it to the order (`projects.plaque_media_id`, `plaque_approved_at`, `plaque_approved_by_id`; event `plaque_approved`).
- **Nothing is replaced silently**: if the order already has an approved plaque the server refuses (409) unless the user
  confirms (`replace_approved=true`). Every earlier version stays in "Saved plaques" and can be viewed or approved again.
- API: `POST /api/projects/<WellID>/plaques` (form fields `approve`, `replace_approved`),
  `POST /api/projects/<WellID>/plaques/approve` `{media_id, replace_approved}`, `GET /api/media/<id>/content` (the image).
- Plaque wording for the unified well types: يدوي → بئر سطحي يدوي · متوسط → بئر ارتوازي متوسط · عميق → بئر ارتوازي عميق ·
  شمسي → بئر بالطاقة الشمسية (editable on the plaque).
