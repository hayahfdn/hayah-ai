# Mark old projects as delivered (2026-11-20)

Settings → «تسليم المشاريع القديمة» (managers only).

1. **Preview.** Wells and sacrifices ordered before the current month that are not marked
   delivered, counted by order month and type, split into "real date" (a delivery date was already
   typed) and "estimated date". Cancelled wells, records without an order date and sample rows are
   left out and counted. Nothing changes.
2. **Apply.** Tick "I checked the numbers" and press the button. The server recomputes and refuses
   if the totals moved since the preview. Only `delivery_status`, an empty `delivery_date` and
   `delivery_estimated` change. Numbers, names and prices are never touched. A well's timeline gets
   a «delivery.bulk_marked» entry. An estimated date is the last day of the order month, shown in
   orange with "~" in the sheet and as «تاريخ تقديري» on the project page.
3. **Undo.** Each run is kept in `bulk_changes` with every record's before/after. Undo restores them
   exactly; a record that someone changed since is left as it is and listed.

Sacrifices now have a delivery status too (migration 0012): those with a delivery date are
delivered. Typing a delivery date on a sacrifice, or approving a well's delivery, sets a real date
and clears the estimated flag.

API: `GET /api/bulk/old-delivered/preview`, `POST /api/bulk/old-delivered/apply`
(`{wells, sacrifices, confirm: true}`), `POST /api/bulk/old-delivered/{id}/undo`.
