# Add-ons as projects, unified sales sources, newest first, employee lists (2026-11-19)

## Sheep bought with a well becomes its own sacrifice
- Rule in Shopify settings (`standalone_addons`): the sheep add-on (product 15429437489372, title "خروف",
  line property "للمشروع") becomes a normal sacrifice: next sacrifice number, 99 USD, own plaque draft and
  final video, same Shopify order number. Name, dedication, phone and donor come from the well it was bought
  with; intention "صدقة". One sacrifice per unit (2 sheep = 2 sacrifices).
- The well keeps its own price plus its other add-ons (tank, tiles); only the sheep's price moves out.
- Applies from order #1225 (`standalone_from_order`). Older orders keep the old behaviour.
- #1225 itself was imported before this change: every Shopify sync runs `split_imported_addons`, which
  creates its sacrifices once, takes 99 per sheep off the well and removes the sheep from the well's extras
  (audit `shopify.addon_split`). Re-syncing never creates a second copy (one row per line unit).
- Feeding (إطعام) and tiles/tank stay add-ons. More standalone products can be added to the list later.

## Unified sales sources
- Every well and sacrifice keeps `sales_source` exactly as received and gets `source_group`.
- Groups: Insta Ads, Referral, Instagram, Google, Lina, Facebook, ChatGPT, Influencer, TikTok, plus Other
  (a real source in no group) and Unknown (empty). Case and small typos are ignored; nothing is guessed.
- Settings → Sales sources (managers): edit groups and their values, move values out of Other. Saving
  re-applies to all records; the original text never changes.
- Shopify: an Instagram visit from an ad (campaign name, or Meta's unfilled `{{site_source_name}}`) is
  "Shopify (Insta Ads · campaign)"; the bio link (`link_in_bio`) is "Shopify (Instagram)".
- Reports: `/api/reports/summary` → `by_sales_source`; Shopify summary groups by the unified source.

## Newest first
Wells, sacrifices and contractor pages sort by order date (newest first), then the higher number; rows
without a date go last. Column sorting and filters still work as before.

## Employee lists
A well whose plaque is "approved and ready for the contractor" is the manager's step. Employees do not see
it in their lists, search, counters or the Approved plaques section; managers send it to the contractor.
Once a contractor is set, the employee sees it again (including the contractor's page). Opening it by
number still works. Nothing is deleted or changed.
