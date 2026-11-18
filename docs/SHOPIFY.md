# Shopify → HAYAH AI

Every paid order in the HAYAH Shopify store creates its wells and sacrifices in HAYAH AI by itself.

## What happens to an order

| In the order | In HAYAH AI |
|---|---|
| A product with **بئر / well** in its name | One **well** per unit, with the next Well ID |
| **خروف / ماعز / بقرة / عقيقة / أضحية …** | One **sacrifice** per unit, with the next sacrifice number |
| A line with the **للمشروع** property (extra water tank, إطعام, a sheep for a well) | Added to the **Extras** and the **selling price** of the well or sacrifice it was bought for |
| Anything else (gift, donation) | Shown on the order as "Nothing to import"; nothing is created |

Fields filled in: order date (store time zone), customer (or **اسم صاحب الطلب**), WhatsApp phone, **dedication (الإهداء)**, intention (**الغرض / نوع الطلب**), country if the donor chose one, well type (يدوي / متوسط / عميق / شمسي), animal, selling price after discounts, payment = Shopify, sales source (e.g. "Shopify (Instagram)"), and the Shopify order number.

## Rules

- **Never twice.** Shopify's order id and each line-item unit are unique in the database, so repeated notifications or re-checks do nothing. An order whose number is already typed in the workbook's **Shopify** column is linked, not created again.
- **Old orders are left alone.** Only orders from the "Only orders from this date" setting are imported. If you switch on the connection without a date, today's date is used.
- **Only paid orders** by default. An unpaid order waits and is imported when Shopify marks it paid.
- **Cancelled or refunded** orders are never deleted. Their wells are set to payment "Refunded" and get a note, so a manager decides.
- **Numbers:** the next number after the highest real one, or the start number you set. Never chosen by AI.
- **Who sees what:** the selling price is visible to managers and Team members (Reports > Shopify sales, Settings > Shopify orders). Costs never come from Shopify. Contractors don't see Shopify sales. Only the Super Admin can change the connection.
- Every new record is in the audit log and the project timeline ("shopify").

## Past orders (before the start date)

Settings → Shopify → **Past orders** → **Import past orders** (Super Admin; leave "From" empty for the store's first order).
The workbook rows have no Shopify order number, so past orders are **matched, not created**:

| Match | How | What changes on the workbook row |
|---|---|---|
| Matched | the row has this order number, or the donor / dedication name matches (within 7 days) | empty order number, dedication and phone are filled in |
| Matched | same kind and type within a day, and the only row that fits | same as above |
| Matched by date and type only | several identical rows fit (e.g. three hand wells that day) | nothing; it only stops the order being created again |
| Not in the workbook | nothing fits | nothing; listed under **Needs a look** |

Under **Needs a look** a manager can type the right Well ID / sacrifice number and press **Link**, or press **Add to HAYAH** (one order, or all of them) to create the missing records with the next numbers.
Running the import again is safe: linked items stay linked and nothing is created.
Old add-ons without the "للمشروع" property (إضافة سيراميك, خزان, دلو, إطعام) are still folded into their well or sacrifice.

Shopify gives apps only the last 60 days of orders unless the app has the **read_all_orders** scope (Dev Dashboard → app → Versions → scopes `read_orders,read_all_orders` → Release). The import checks this and warns if it is missing.

## Two ways orders arrive

1. **Order notifications (webhooks)**: Shopify tells the server the moment an order is created, paid or cancelled. Each one is checked against the app's secret.
2. **Automatic check every 15 minutes** (and the "Check for new orders now" button): catches anything a notification missed.

## Setup (Super Admin, about 10 minutes)

Shopify no longer lets you make new "custom apps" inside the store admin; new apps are made in the **Dev Dashboard**.

1. In the Shopify admin go to **Settings → Apps → Develop apps → Build apps in Dev Dashboard**. (Starting from the store keeps the app and the store in the same Shopify organization, which Shopify requires.)
2. Click **Create app** → **Start from Dev Dashboard**, name it `HAYAH AI`, click **Create**.
3. On the **Versions** page: App URL `https://77-42-84-83.sslip.io`, Webhooks API version = the newest, **Scopes** = `read_orders,read_all_orders`. Click **Release**.
4. If Shopify asks about **protected customer data**, allow **Name** and **Phone** (used for the donor's name and WhatsApp number).
5. Go to the app's **Home** → **Install app** → choose the HAYAH store → **Install**.
6. Open the app's **Settings** and copy the **Client ID** and **Client secret**.
7. In HAYAH AI: **Settings → Shopify**
   - Store address: `tcum1c-yt.myshopify.com`
   - Paste the Client ID and Client secret
   - Tick **Create wells and sacrifices from new orders**; leave the date as today (or the first day not yet in the workbook)
   - **Save** → **Test connection** (shows the store name) → **Connect order notifications** → **Check for new orders now**

If **Test connection** says `shop_not_permitted`, the app was made in a different Shopify organization than the store: delete it and make it again starting from step 1 inside the store admin.

An older custom app made in the store admin also works: paste its Admin API access token (`shpat_…`) and its API secret key instead.

## For developers

- Code: `backend/app/services/shopify.py`, `backend/app/integrations/shopify/`, `backend/app/api/shopify.py`, tests in `backend/tests/test_shopify.py`.
- Webhook URL: `POST /api/shopify/webhook` (HMAC `X-Shopify-Hmac-Sha256` with the client secret). Topics: `orders/create`, `orders/paid`, `orders/cancelled`.
- Auth: client credentials grant (24-hour token, cached encrypted) or a static `shpat_` token. Admin GraphQL API version `2026-10`.
- Tables: `shopify_orders`, `shopify_order_items` (`match` = sure/likely/guess/created/none for past orders, migration 0004); new column `dedication` on `projects` and `sacrifices` (migration 0003).
- Past orders: `backend/app/services/shopify_history.py`, API `GET/POST /api/shopify/history`, `POST /api/shopify/history/add`, `POST /api/shopify/history/link`.
- Property names and keywords are in `DEFAULTS` in the service and stored in the `shopify` app setting, so they can be changed without code.
