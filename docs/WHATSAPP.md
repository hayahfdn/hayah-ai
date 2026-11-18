# WhatsApp plan (decided: hybrid)

**Decision (2026-11-17):** keep the four existing groups (A Orders & Construction,
B Delivery, C Final Videos, D Maintenance) exactly as they are, and add a new,
dedicated WhatsApp number on Meta's official Cloud API that the team forwards
operational messages to. No unofficial automation, no WhatsApp Web scraping,
and the main business number is never connected to the system.

## Why

The Cloud API cannot read groups that were created in the WhatsApp app, so the
existing groups cannot be connected directly. Meta's newer Groups API (for groups
created through the API) will be checked in Phase 5 for eligibility, limits and
charges before anything changes. Until then the hybrid flow works with no
change to how the groups are used.

## How the team uses it

Forward (or type) the message to the intake number, starting with the group tag:

| Tag | Meaning | What the system does |
| --- | --- | --- |
| `#A 1339 اكتمل الحفر` | Construction update | Updates construction status if sender is registered and Well ID is clear |
| `#B 1339 تم التسليم` | Delivery | Creates a **pending** confirmation; a manager approves in the dashboard |
| `#C 1339 https://…` | Final video link | Saves the link, video status completed (never marks delivered) |
| `#D 1339 الطلمبة معطلة` | Maintenance | Opens a maintenance record with its own Maintenance ID |

Photos and videos with a caption that contains the Well ID go to that well's
Drive folder. Without a clear Well ID, everything lands in **AI Review**.
Arabic tags work too (`#ب`), and Arabic-Indic digits (١٣٣٩) are understood.

The dashboard's **AI Review → Paste a WhatsApp message** box runs the same
pipeline by hand, so the system is usable before the intake number exists.

## Setup checklist (Phase 5, needs HAYAH)

1. A new phone number that is not on any WhatsApp account.
2. Meta Business Manager (HAYAH's), WhatsApp Business Account, add the number, verify the business.
3. Create a Meta app, add WhatsApp product, get Phone Number ID and a permanent system-user token.
4. Webhook: `https://<domain>/webhooks/whatsapp`, verify token = `HAYAH_WHATSAPP_VERIFY_TOKEN`,
   subscribe to `messages`. Set `HAYAH_WHATSAPP_APP_SECRET` so every webhook is signature-checked.
5. Register each team member's phone in Settings → Users so the system recognises senders.

**Cost:** receiving messages from the team is free on the Cloud API; Meta
charges only for business-initiated template messages (notifications), priced
per country. Exact rates are confirmed with HAYAH before any notifications are turned on.
