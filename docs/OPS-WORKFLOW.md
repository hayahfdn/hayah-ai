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

## Phase 3: final delivery video, dashboard cards

**«الفيديو النهائي للمشروع»** is on every well's order page and, for sacrifices, on
`/videos/sacrifice/<number>`. MP4 and MOV only. Upload shows progress; the video plays in the page
(with seeking), downloads, shares (on a phone the file goes to WhatsApp through the share sheet) and
opens the customer's WhatsApp chat. Every upload is kept as a file of that one order (category
`final_video`); a newer upload becomes the current one and goes back to «تم رفع الفيديو». The same
file cannot be attached to two orders, so videos never mix. Uploader and date are recorded; every
step is on the order's timeline and in the audit log.

States: «لم يتم رفع الفيديو» → «تم رفع الفيديو» → «جاهز للتسليم» → «تم إرساله للعميل».

New table `final_videos` (migration 0008). Wells that already had a final video file get a row
with «تم رفع الفيديو»; final video links typed earlier stay as they are.

Playing and downloading use a signed link that works for 2 hours and only for that file, made for a
logged-in employee or manager (a video player cannot send the login header). Files are streamed from
disk, not read into memory.

**«الفيديوهات النهائية»** page: waiting for video (orders whose plaque was sent to the contractor and
have no final video yet), uploaded, ready for delivery, sent.

**Dashboard «عمل اليوم»** (employees and managers, live every 10 seconds, no money): new orders,
waiting for plaque confirmation, waiting for the customer, approved plaques to send to the
contractor, plaques sent to contractors, waiting for the final video, videos ready for delivery.
Red needs action, orange is in progress, green is done (a red card with nothing waiting turns green).
The two WhatsApp cards (unread messages, chats waiting for a reply) come with phase 4.

**Storage note.** Videos are stored on the server disk (the `appdata` volume), like the other
media. The nightly backup copies the database, not the files.

## Phase 4: WhatsApp inbox (official WhatsApp Business Platform, Cloud API)

**Number.** Hayah chose to connect the current WhatsApp Business number with Meta's
Coexistence onboarding, so the WhatsApp Business app on the phone keeps working. Replies typed on
the phone arrive as `smb_message_echoes` and show in the same chat as «أُرسلت من الهاتف». The
team's intake number and its stored messages are unchanged; webhook messages are routed by the
receiving `phone_number_id`.

**Page «واتساب»** (`/inbox`, employees and managers):
- chat list with name, number, last message and time, unread count, status, assignee, linked
  order and a red «اللوحة غير مؤكدة» tag; search by name, number or order number; boxes: all,
  mine, unassigned, unread, waiting for a reply, follow-up, closed;
- chat view: full history, new messages every 4 seconds, send text, files from the device
  (images, PDF, video, documents, audio files), the linked order's plaque and final video;
  delivery ticks (sent, delivered, read, failed with the reason and «إعادة الإرسال»);
- orders with the same number are listed; one order is linked automatically, several are picked
  by the employee; link to any order by number or open a new order with the number filled in;
- assign, transfer, follow-up, close (a customer writing again reopens the chat). Employees can
  take unassigned chats or hand over their own; managers can assign any chat;
- every sent message records who sent it; sending a plaque or final video is written on the
  order's timeline, and sending the final video marks it «تم إرساله للعميل».

**Meta rules.** Free replies only within 24 hours of the customer's last message; after that the
chat offers the approved templates (read from the WhatsApp Business Account) with their values.
Files follow WhatsApp's limits: images 5 MB, video and audio 16 MB, documents 100 MB (a bigger
final video is sent as a document up to 100 MB). Profile photos are not available through the
Cloud API, so chats show initials.

**Reliability and security.**
- Webhook signatures (`X-Hub-Signature-256`) are checked with the app secret; Meta re-sends are
  stored once (unique WhatsApp id).
- Each outgoing message carries a `client_ref` made once by the browser: a double click or a
  retried request never sends twice. A message WhatsApp did not accept because it could not be
  reached is retried by the worker; a refusal from Meta is shown with its reason.
- Incoming media is downloaded by the worker into `WhatsApp Inbox/<number>/`. Files are served
  through 2-hour signed links; programs are refused; only images, audio and video open in the page.
- Access token, app secret and verify token come from the server environment or are pasted in
  Settings → WhatsApp (admins), stored encrypted, never sent to the browser.

**To connect (Hayah, in Meta):**
1. Meta Business Suite / developers.facebook.com: create (or use) a Meta app of type Business with
   the WhatsApp product, and onboard the current number with the "WhatsApp Business app"
   (Coexistence) option. The phone must run a recent WhatsApp Business app version.
2. Create a system user with a permanent access token (permissions `whatsapp_business_messaging`,
   `whatsapp_business_management`).
3. In the app's WhatsApp → Configuration, set the webhook URL `https://<site>/webhooks/whatsapp`,
   the verify token, and subscribe to `messages` and `smb_message_echoes`.
4. In HAYAH Settings → WhatsApp: phone number ID, WhatsApp Business Account ID, the token, the app
   secret and the verify token; then «اختبار الاتصال».
5. Create the message templates you want for messages after 24 hours (Meta approves them).
