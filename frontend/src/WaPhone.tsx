// The small green WhatsApp icon shown beside a customer's phone number (Hayah, 2026-11-22).
// Tapping it opens the customer's chat in the WhatsApp app (wa.me), in a new tab or the app.
// It uses the cleaned international number (E.164, from services/phones.py); when the number
// is missing or needs its country, the icon is greyed out with the reason.
import { useI18n } from "./i18n";
import { WaIcon, waProblem } from "./plaque/flow";
import "./wa-phone.css";

/** wa.me link for an E.164 number ("+962 79…" → https://wa.me/96279…), or null if it is too short. */
export const waMe = (e164: string | null | undefined) => {
  const digits = (e164 || "").replace(/\D/g, "");
  return digits.length >= 8 ? `https://wa.me/${digits}` : null;
};

export function WaPhoneIcon({ e164, status }: { e164: string | null | undefined; status?: string | null }) {
  const { t } = useI18n();
  const link = waMe(e164);
  if (!link) {
    const why = waProblem(t, e164, status) || t("wa_chat_missing");
    return <span className="wa-phone off" title={why} aria-label={why}><WaIcon /></span>;
  }
  return <a className="wa-phone" href={link} target="_blank" rel="noopener noreferrer"
    title={`${t("wa_chat")} · ${e164}`} aria-label={t("wa_chat")}
    onClick={(e) => e.stopPropagation()}><WaIcon /></a>;
}

/** A phone number with the WhatsApp icon beside it. Shows "—" when there is no number at all. */
export function PhoneWithWa({ phone, e164, status }: { phone: string | null | undefined; e164: string | null | undefined; status?: string | null }) {
  if (!phone && !e164) return <span className="muted">—</span>;
  return <span className="phone-wa"><bdi dir="ltr" className="mono">{e164 || phone}</bdi><WaPhoneIcon e164={e164} status={status} /></span>;
}
