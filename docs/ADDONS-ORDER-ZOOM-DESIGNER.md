# Add-ons, project order, WhatsApp, plaque designer, zoom (20 Nov 2026)

## Add-ons (الإضافات)
- Wells: multi-select «الإضافات» (Settings list `well_addons`, default خزان، سيراميك، خروف), stored in `projects.extras`, separate from the well type.
- A sheep add-on (خروف, or «خروف ×2») creates its own sacrifice per sheep: 99 USD, animal خروف, linked by `sacrifices.parent_project_id`. It is created when a well is made or edited in the system (not on workbook/Shopify import, which already split sheep). Linked sacrifices are never deleted automatically and are edited on the sacrifices page. The well price excludes the sheep's 99, so revenue is counted once.
- Sacrifices: «الإضافات» (Settings list `sacrifice_addons`, default إطعام).

## Project order
- `projects.listed_at` fixes the list order: newest created first; editing or status changes never move a row.
- «⇅ إعادة ترتيب المشاريع» (`POST /api/projects/resort`) recomputes the order from creation time (system projects) or order date (workbook imports). Audited.

## WhatsApp (wa.me only, no Cloud API)
- Chat icon beside the final-video upload and in the lists: wa.me on phones, WhatsApp Web on computers.
- «إرسال للعميل على واتساب» was disabled with «ناقص: الدولة» because the plaque's missing list wanted a country from the contractor, and new orders have no contractor yet, and the list was never recomputed. Now the design's flag counts as the country, the list is recomputed on every read, and phone problems are explained in words (no number / needs country code / invalid), with an inline country picker.
- Phone numbers: digits-only international numbers are accepted; Shopify billing country code is used as a fallback for local numbers.

## Plaque designer
- Tools in rows: العلم، رقم المشروع، نوع البئر، التاريخ، الاسم، صيغة الدعاء، نص الدعاء (wrap on small screens).
- Line breaks in the name, short prayer and prayer text are kept in save, PNG, PDF and photos export.
- «إضافة صورة البئر الشمسي»: library (built-in solar well + uploads stored in app setting `plaque_images`), upload, drag, resize with aspect ratio kept, centre, remove/replace. Stored in the design as `image: {ref, x, y, w}`.
- «معاينة التصميم النهائي» and «حفظ في معرض الصور» (share sheet on phones, download otherwise).

## Interface zoom
- 80/90/100/110/125/150 %, in the top bar. Saved per user (`users.ui_zoom`) and in the browser. Shortcuts Ctrl+Alt+= / Ctrl+Alt+- / Ctrl+Alt+0.

## Migration
- `20261120_0011_addons_order_zoom`: projects.listed_at (backfilled), sacrifices.parent_project_id (backfilled from notes), users.ui_zoom.
