# Plaque designer

Menu: **Plaque designer** (`/plaque`), or **Design plaque** on a well's page (`/plaque/<WellID>`).
Managers and Employees can save; contractors cannot. Rule-based: the browser draws the plaque, no AI.

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
  `GET /api/plaques/sacrifices/<No>` returns only plaque fields (never cost or price), so Employees can use it.
  Saved PNGs go to Drive `Plaques/Sacrifices/<No>/`; the design is kept in the audit log (`plaque.saved`).
- **Well icons**: six HAYAH well types (hand pump, hand pump with tank, one or two tanks with 4 taps, one or two tanks
  with a tap wall) in `frontend/public/wells/`, background removed. Icon can sit left or right.
- **Flags**: Pakistan, Bangladesh, Nepal, India, Tanzania first, then all 22 Arab League countries, then others.

## «شهادة وقفية» (endowment certificate)
Every well has a certificate card on its project page and an editor at `/certificate/<well>`.
- Filled from the order: donor names (the plaque's name, else the dedication, else the customer), cleaned to the names only, one per line: titles (السيد، الحاج، المرحوم…), kinship words (والدي، أمي، أخي…) and prayers (رحمه الله…) are removed (`clean_names`). Project type
  ("حفر بئر مياه", solar adds "بالطاقة الشمسية"), opening month/year (delivery date, then completion date, else this
  month with a warning), well number, country (in Arabic). Every line is editable; Save keeps the design as a
  `certificate_saved` timeline event (no new table).
- Layout matches HAYAH's sample (1080 × 1640, exported at 2×). The stamp at `frontend/public/certificate-stamp.png`
  was cut from that sample with its background removed.
- One-tap WhatsApp ("إرسال الشهادة والفيديو"), on the card, the editor and the well's final-video section. Phone: the share
  sheet opens with the certificate PNG and the final video; the employee picks WhatsApp and the customer. If the phone
  needs a fresh tap after a large video loads, the button says "tap again". Computer: WhatsApp Web opens on the customer's
  chat and both files download. Each send is logged (`certificate_sent`); after a phone share, a video that was
  "ready for delivery" becomes "sent to customer". Nothing is sent automatically or by unofficial tools.
