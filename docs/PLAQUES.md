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
