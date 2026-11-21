# HAYAH AI: system guide

The in-app assistant answers from this guide. Keep it current when a page or a rule changes.
Each section is marked with who may read it. The server sends the assistant only the sections
the signed-in person's role may see. Sections marked `[managers]` never reach employees,
contractors, maintenance or viewers.

<!-- section: all -->
## What the system is
HAYAH AI is the HAYAH Foundation's operations system for water wells and sacrifices (ذبائح /
صدقات). It tracks every order from the moment it arrives (Shopify, WhatsApp or typed by the team)
through the plaque, the contractor, construction, delivery, the final video and maintenance.
The screen is in Arabic or English (switch at the top or in the menu). All money is in US dollars.

## Roles
- **Super admin / operations manager (المدير):** everything, including costs, profit, money and settings.
- **Employee (موظف):** adds and edits orders, the selling price, plaques, videos and WhatsApp chats.
  Never sees cost, contractor cost, profit, ads or the money workbook.
- **Contractor (المقاول):** sees only their own wells, updates construction and uploads photos and videos.
- **Maintenance:** records maintenance visits.
- **Viewer:** reads only.

## Main pages
- **لوحة التحكم / Dashboard (`/`):** «عمل اليوم» cards: new orders, plaques to confirm, waiting for the
  customer, plaques sent to contractors, waiting for the final video, videos ready, WhatsApp. Red needs
  action, orange is in progress, green is done.
- **الآبار / Wells (`/wells/<month>`, managers `/book/wells/<month>`):** the wells of one month, newest first. Switch month with the
  arrows. «بطاقات» shows cards (phone), «جدول» shows a sheet you can edit in place. «تراجع» undoes the last edit.
- **Project page (`/projects/<number>`):** everything about one well: details, plaque, timeline, photos,
  final video, delivery. «تعديل» opens the edit form.
- **The small open icon** (a square with an arrow) beside every project number opens that project's
  page directly in edit mode, with its plaque shown at the top. It is separate from clicking the row.
- **المشاريع / Projects (`/projects`):** search all wells by number, name or phone.
- **اللوحة / Plaque designer (`/plaque/<number>`, sacrifices `/plaque/sacrifice/<number>`):** design and
  save the plaque. Every save is a new version; nothing is overwritten.
- **طلبات تحتاج تأكيد اللوحة (`/plaques/confirm`):** plaques waiting for an employee or the customer.
- **الفيديوهات النهائية (`/videos`):** final delivery videos: waiting, uploaded, ready, sent.
- **واتساب (`/inbox`):** the WhatsApp inbox: chats, assigning, linking a chat to an order, sending the
  plaque or the final video.
- **الإنشاء / Construction, التسليم / Delivery, الصيانة / Maintenance, الوسائط / Media:** work lists.
  Delivery is confirmed on the Delivery page only.
- **المقاولون / Contractors:** the list of contractors by country, each with a colour.
- **التقارير / Reports:** counts by month, country, contractor and sales source.

## Team tasks «مهامي» (`/tasks`)
Each well order passes 8 stages. Each stage has one responsible person, set by a manager in
Settings → Users → «المسؤول عن كل مرحلة». Only that person (or a manager) can tick its steps. A task is
finished only when it is closed and documented: some steps need a short note saying what was done and how.
1. **استلام الطلب (غازي):** «تم استلام الطلب» → choose the country → choose the contractor.
2. **التواصل والتصميم (شذى):** «إرسال الرسالة الأولى» (WhatsApp) or «تم التواصل بطريقة أخرى» → «تصميم
   اللوحة» → send it to the customer with the green WhatsApp button (or «أُرسلت بطريقة أخرى») → wait.
3. **اعتماد اللوحة (شذى):** after the customer really approves, «تمت موافقة العميل» with how they approved.
   A manager can approve directly. An employee cannot approve before the plaque was sent to the customer.
4. **إرسال للمقاول (غازي):** send the approved plaque to the contractor → send the requirements list (note)
   → «وصل الفيديو من المقاول» when the contractor's video arrives.
5. **مراجعة ورفع الفيديو (غيداء):** check the order number and phone → «رفع الفيديو النهائي» → «جاهز للتسليم».
6. **تجهيز الشهادة (النظام):** the endowment certificate is prepared and saved to the order automatically.
7. **التسليم النهائي (شذى):** send the video and certificate on WhatsApp → «تأكيد التسليم» with a note.
8. **إغلاق المشروع (المديرة):** record the delivery date and close the order.
«لوحة الإدارة» (managers) lists every open order: its stage, who is responsible, the next step and how many
days it has waited (over 2 days shows red). A manager can move a task to another person from the board.
Every step is written to the order's timeline with the person's name. Orders before the start date are not listed.

## How an order moves
1. The order arrives (Shopify automatically, or «+ مشروع جديد»). It gets its number. Numbers are never
   changed or reused, and nothing is ever deleted.
2. A plaque draft is made automatically. Missing information (name, male/female, living/deceased,
   well type, animal, country) is listed in red and never guessed.
3. The employee confirms the plaque with the customer: «جاهزة للمراجعة» → «بانتظار موافقة العميل» →
   approved, or «تحتاج إلى تعديل» with the customer's note.
4. A manager sends the approved plaque to the contractor.
5. The contractor builds; construction status moves to completed.
6. The final video is uploaded (MP4 or MOV), marked ready and sent to the customer on WhatsApp.
7. Delivery is confirmed (WhatsApp delivery group message plus manager approval).

## Plaque states
قيد الإنشاء (draft with missing information) → جاهزة للمراجعة → بانتظار موافقة العميل →
تحتاج إلى تعديل / معتمدة وجاهزة للإرسال للمقاول → تم إرسال اللوحة للمقاول.

## Shopify add-ons
A sheep (خروف) bought together with a well becomes its own sacrifice: own number, 99 USD each, linked
to the same Shopify order, with the well's dedication and phone. Its amount is taken out of the well's
price. Other add-ons (extra tank, tiles, feeding) stay part of the well. This applies from order #1225.

## Sales sources
Every order keeps the source exactly as it was typed, and also shows one unified source: Insta Ads,
Referral, Instagram, Google, Lina, Facebook, ChatGPT, Influencer, TikTok, Other (a real source that
fits no group) or Unknown (empty). Hover the source to see the original text.

## Floating buttons
- **«عدّل بكتابة طلب» (managers):** type a change in plain words; the system shows a preview and
  changes nothing until you press Apply.
- **The assistant (this chat):** explains how to use the system. It only reads; it never changes data.
- Both buttons can be moved: press and hold for about half a second, then drag. A normal tap opens them.
  The place is remembered on this device. «إرجاع الزر لمكانه» puts it back.

## Phone numbers
The number is kept exactly as typed, plus a standard international copy. A number without a clear
country is marked and the form asks for the country. The well's country is never used for the phone.

## Safety rules
No deletes, no changing project numbers, no duplicates (re-syncing Shopify never adds an order twice),
every change is in the timeline and the audit log, and the database is backed up before every update.

<!-- section: managers -->
## [managers] Money
- **دفتر الحسابات / Book (`/book`):** the money summary: sales, cost, profit, margin, ads, cash in the
  bank, owed to contractors, by month.
- **Accounts (Wise and banks), partners (المسؤولون), contractor ledgers:** money rows. A wrong row is
  voided, never deleted; it stays in history.
- **الذبائح / Sacrifices (`/book/sac/<month>`):** sacrifices with cost and sale price.
- **Cost and profit** of a well are shown only to managers. Employees see the selling price only.

## [managers] Settings (`/settings`)
- **AI:** the Anthropic key and the monthly AI budget (20 USD a month, shared by the prompt box and the
  assistant). The key is stored on the server and never shown again.
- **Sales sources:** edit the groups and the values under each. Saving re-applies them to every order;
  the original text never changes.
- **Shopify, WhatsApp, Google, Import workbook, users and roles.**
- **Plaques approved and ready for the contractor (`/plaques/approved`)** and «إرسال للمقاول» are for
  managers. Employees do not see that list, so it does not distract them.
