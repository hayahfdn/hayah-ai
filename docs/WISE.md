# Wise, read only (2026-11-20)

Settings → Wise (managers; the token itself only the super admin).

- **Read only.** The server only sends GET requests to Wise (profiles and the activity feed). There is
  no code that sends, funds or cancels money. A test checks that the module never uses POST/PUT/DELETE.
- **Token.** A Wise *read only* personal API token for the business account, pasted in Settings → Wise.
  It is checked (the business profile is found) before saving, stored encrypted with the other keys,
  and never sent back to the browser (only its last 4 characters).
- **Sync.** Hourly from the worker, or «مزامنة الآن». The first sync reads the last 120 days; later ones
  read from 3 days before the newest stored activity. Each activity is stored once (unique Wise id),
  so syncing again never duplicates. Cancelled activities are skipped. Moves between own balances
  (conversions) are stored as ignored.
- **Classification.** Money in from SHOPIFY = Shopify payout (Shopify pays out in batches, not one
  payment per order). Money out to a recipient in the "recipients who are contractors" list = contractor
  payment for that contractor. Facebook / Meta / Google ads words = ads. Hetzner, Anthropic, Shopify
  plan, etc. = tools. Other transfers out = "transfer out" until a person maps the recipient.
- **Matching.** Automatic only when exactly one Wise ledger row has the same direction, the same USD
  amount to the cent and a date within 5 days. For GBP/PKR/EGP transfers the USD amount Wise shows is
  used. Everything else stays in «غير مطابقة»: match it to a ledger row (closest suggestions shown),
  add it to the ledger in one click (kind from the classification; never twice), or ignore it. All
  reversible (unmatch, un-ignore) and written to the audit log.

Table `wise_transactions` (migration 0013). API under `/api/wise`. Tests: `backend/tests/test_wise.py`.
