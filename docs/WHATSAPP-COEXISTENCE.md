# Connect the current WhatsApp Business number (Coexistence), 2026-11-20

Hayah chose to become a Meta Tech Provider so the number now used in the WhatsApp Business app can
also be used by the inbox, without moving it.

## In the app (super admin): Settings → WhatsApp → «ربط رقم واتساب للأعمال الحالي»
1. Enter the Meta app ID and the Embedded Signup configuration ID (public IDs, not secrets). The app
   secret goes in the WhatsApp settings above it (stored encrypted).
2. Read the impact list, tick the box, press «الربط عبر فيسبوك», log in, choose the business, and scan
   the QR code shown in the WhatsApp Business app on the phone.
3. The server then: exchanges the one-time code for a business token (encrypted), subscribes the app
   to the WABA's webhooks, saves the phone number ID and WABA ID as the inbox number, and asks Meta to
   sync contacts (`smb_app_state_sync`) and then chat history (`history`, up to 6 months). The sync
   must be asked within 24 hours; «إعادة محاولة المزامنة» repeats a failed step.
4. No `/register` call is made (that would move the number off the phone app). Nothing is sent to
   customers.

Webhook fields to subscribe in the Meta app: `messages`, `history`, `smb_app_state_sync`,
`smb_message_echoes`. History messages are stored once each (`source = history`); contacts give chats
their names; echoes (sent from the phone) show as «أُرسلت من الهاتف».

## In Meta (done together, on Hayah's device)
1. Business verification of the Meta Business portfolio (company documents).
2. In the Meta app (Business type): add the WhatsApp product, set the webhook URL
   `https://<server>/webhooks/whatsapp` and the verify token from Settings → WhatsApp.
3. Facebook Login for Business → create an Embedded Signup configuration for WhatsApp
   (permissions `whatsapp_business_management`, `whatsapp_business_messaging`); copy its configuration ID.
4. Add the server's domain to the allowed domains for the JavaScript SDK.
5. App review for advanced access to those two permissions, then Tech Provider onboarding.
6. Switch the app to Live, then press the button in the HAYAH app.

API: `GET|PUT /api/settings/whatsapp-coexistence`, `POST .../finish`, `POST .../sync`.
Tests: `backend/tests/test_wa_coexistence.py`.
