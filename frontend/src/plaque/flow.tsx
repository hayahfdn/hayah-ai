// The plaque workflow shared by the confirm list, the approved section and the designer:
// one plaque per order, its status, what is missing, and the moves an employee can make.
import { useEffect, useState } from "react";
import { api, fileUrl, getToken } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { Field, Modal, toast } from "../ui";

export type PlaqueState = "draft" | "ready_for_review" | "awaiting_customer" | "needs_changes" | "customer_approved"
  | "approved_for_contractor" | "sent_to_contractor";
export interface PlaqueRow {
  id: number; kind: "well" | "sacrifice"; number: number; status: PlaqueState; status_ar: string; missing: string[];
  name: string | null; customer_name: string | null; customer_phone: string | null; customer_phone_e164: string | null;
  customer_phone_status: string | null; order_date: string | null; shopify_order: string | null; type: string | null;
  order_country: string | null; order_contractor_id: number | null; honoree_gender: string | null; honoree_state: string | null;
  anonymous: boolean; dua_kind: string | null; version: number | null; file_version_id: number | null; design: Record<string, any>;
  sent_to_customer_at: string | null; customer_decision_at: string | null; customer_decision_by: string | null; customer_note: string | null;
  contractor: { id: number; code: string; name: string; color: string | null } | null; contractor_country: string | null;
  sent_to_contractor_on: string | null; sent_to_contractor_by: string | null; updated_at: string; created_at: string;
  whatsapp?: { text: string | null; time: string | null; phone: string | null; problems: string[] };
  versions?: { id: number; version: number; source: string; actor_label: string | null; created_at: string; has_file: boolean; approved: boolean; design: any }[];
}

const TONE: Record<PlaqueState, string> = {
  draft: "bad", ready_for_review: "warn", awaiting_customer: "info", needs_changes: "bad", customer_approved: "ok",
  approved_for_contractor: "ok", sent_to_contractor: "brand",
};
// The same moves the server allows (services/plaque_flow.py MOVES); the server checks them again.
const NEXT: Record<PlaqueState, PlaqueState[]> = {
  draft: ["ready_for_review"],
  ready_for_review: ["awaiting_customer", "customer_approved", "needs_changes"],
  awaiting_customer: ["customer_approved", "needs_changes"],
  needs_changes: ["awaiting_customer", "customer_approved"],
  customer_approved: ["needs_changes"],
  approved_for_contractor: ["needs_changes"],
  sent_to_contractor: ["needs_changes"],
};
const BTN: Partial<Record<PlaqueState, string>> = {
  ready_for_review: "pla_to_review", awaiting_customer: "pla_to_customer", customer_approved: "pla_approved", needs_changes: "pla_changes",
};

export const designerLink = (p: { kind: string; number: number }) => (p.kind === "well" ? `/plaque/${p.number}` : `/plaque/sacrifice/${p.number}`);
/** Phones and tablets open the WhatsApp app (wa.me); a computer opens WhatsApp Web straight on the chat.
 *  The number is the customer's international number (E.164) without "+", as WhatsApp expects. */
export const isPhoneDevice = () => /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)
  || (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent));
export const waLink = (e164: string | null, text?: string) => {
  const digits = (e164 || "").replace(/\D/g, "");
  if (digits.length < 8) return null;
  const q = text ? encodeURIComponent(text) : "";
  return isPhoneDevice() ? `https://wa.me/${digits}${q ? `?text=${q}` : ""}`
    : `https://web.whatsapp.com/send?phone=${digits}${q ? `&text=${q}` : ""}`;
};
/** Why a WhatsApp chat cannot open yet, in words for the person (null when it can). */
export const waProblem = (t: (k: string) => string, e164: string | null | undefined, status: string | null | undefined) =>
  e164 ? null : status === "needs_country" ? t("plwa_phone_country") : status === "invalid" ? t("plwa_phone_invalid") : t("wa_chat_missing");
export const plaqueFile = (p: PlaqueRow, download = false) =>
  `/api/plaques/${p.id}/file?version_id=${p.file_version_id}${download ? "&download=true" : ""}`;

export function PlaqueStatusBadge({ s }: { s: PlaqueState }) {
  const { t } = useI18n();
  return <span className={`badge ${TONE[s]}`}>{t("plst_" + s)}</span>;
}

export function MissingList({ missing }: { missing: string[] }) {
  const { t } = useI18n();
  if (!missing.length) return null;
  return <span className="missing">⚠ {t("pla_missing")}: {missing.map((m) => t("miss_" + m)).join("، ")}</span>;
}

/** Buttons for the next steps of one plaque. "Customer wants changes" asks for the customer's note. */
export function PlaqueActions({ p, onDone, compact }: { p: PlaqueRow; onDone: (p: PlaqueRow) => void; compact?: boolean }) {
  const { t } = useI18n();
  const { refreshCounts } = useAuth();
  const [busy, setBusy] = useState(false);
  const [noteFor, setNoteFor] = useState(false);
  const [note, setNote] = useState("");
  const move = async (to: PlaqueState, n?: string) => {
    setBusy(true);
    try {
      const r = await api<PlaqueRow>(`/api/plaques/${p.id}/status`, { body: { to, note: n || null } });
      toast(t("pla_moved")); refreshCounts(); onDone(r);
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const blocked = (to: PlaqueState) => (to !== "needs_changes" && p.missing.length > 0)
    || ((to === "awaiting_customer" || to === "customer_approved") && !p.file_version_id);
  return <>
    <span className="row-actions">
      {NEXT[p.status].map((to) => (
        <button key={to} className={`sm${to === "customer_approved" ? " primary" : ""}`} disabled={busy || blocked(to)}
          title={blocked(to) ? (p.missing.length ? t("pla_missing") + ": " + p.missing.map((m) => t("miss_" + m)).join("، ") : t("pla_save_first")) : undefined}
          onClick={() => (to === "needs_changes" ? setNoteFor(true) : move(to))}>
          {to === "customer_approved" ? "✓ " : ""}{t(BTN[to] || "plst_" + to)}
        </button>))}
      {!compact && !p.file_version_id && <span className="muted" style={{ fontSize: 12 }}>{t("pla_save_first")}</span>}
    </span>
    {noteFor && <Modal title={t("pla_changes")} onClose={() => setNoteFor(false)}>
      <Field label={t("pla_note")}><textarea dir="auto" rows={3} value={note} onChange={(e) => setNote(e.target.value)} autoFocus /></Field>
      <div className="actions"><button onClick={() => setNoteFor(false)}>{t("cancel")}</button>
        <button className="primary" disabled={busy} onClick={() => { setNoteFor(false); move("needs_changes", note); setNote(""); }}>{t("pla_changes")}</button></div>
    </Modal>}
  </>;
}

/** A thumbnail of the plaque file (it needs the login token, so it is fetched, not linked). */
export function PlaqueThumb({ p, onClick }: { p: PlaqueRow; onClick?: () => void }) {
  const { t } = useI18n();
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!p.file_version_id || failed) return;
    let url: string | null = null, live = true;
    fileUrl(plaqueFile(p)).then((u) => { url = u; if (live) setSrc(u); else URL.revokeObjectURL(u); }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.id, p.file_version_id]);
  if (!p.file_version_id || failed) return <div className="pl-thumb empty">{t("pla_no_file")}</div>;
  return <button type="button" className="pl-thumb" onClick={onClick} aria-label={`${p.number}`}>{src ? <img src={src} alt="" /> : "…"}</button>;
}

/** WhatsApp's colour; a plain chat-bubble drawing (not the WhatsApp logo). */
export const WaIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="currentColor" d="M12 2a10 10 0 0 0-8.7 14.9L2 22l5.3-1.3A10 10 0 1 0 12 2zm0 2a8 8 0 1 1-4.1 14.9l-.3-.2-3 .8.8-2.9-.2-.3A8 8 0 0 1 12 4z" />
    <path fill="currentColor" d="M8.6 7.5c.2-.4.4-.4.7-.4h.5c.2 0 .4 0 .6.5l.8 1.9c.1.2 0 .5-.1.6l-.5.6c-.1.2-.2.3 0 .6.6 1 1.4 1.8 2.5 2.4.3.2.5.1.6 0l.7-.8c.2-.2.4-.2.6-.1l1.8.9c.3.1.4.3.4.5 0 .6-.3 1.3-.8 1.6-.6.4-1.4.5-2.5.1a9.4 9.4 0 0 1-4.6-4.1c-.7-1.2-.9-2.3-.4-3.2z" />
  </svg>);

/** The WhatsApp icon on a prepared plaque. Nothing is sent automatically: it opens WhatsApp on the
 *  customer's number with Hayah's message ready (delivery time by order type) and downloads the plaque
 *  image so the employee can attach it. The tap is logged and the plaque moves to "waiting for the customer". */
export function PlaqueWhatsApp({ p, onDone, label }: { p: PlaqueRow; onDone?: (p: PlaqueRow) => void; label?: boolean }) {
  const { t } = useI18n();
  const { refreshCounts } = useAuth();
  const w = p.whatsapp;
  if (!w) return null;
  const why = w.problems.includes("missing") ? `${t("pla_missing")}: ${p.missing.map((m) => t("miss_" + m)).join("، ")}`
    : w.problems.includes("no_file") ? t("plwa_no_file") : w.problems.includes("no_phone") ? t("plwa_no_phone")
    : w.problems.includes("phone_country") ? t("plwa_phone_country") : w.problems.includes("phone_invalid") ? t("plwa_phone_invalid")
    : w.problems.includes("no_time") ? t("plwa_no_time") : "";
  const go = () => {
    const link = waLink(w.phone, w.text || undefined);
    if (!link) return;
    // the image first starts downloading, then WhatsApp opens in the same tap (so it is not blocked)
    const img = fetch(plaqueFile(p, true), { headers: { Authorization: `Bearer ${getToken()}` } }).then((r) => (r.ok ? r.blob() : null)).catch(() => null);
    window.open(link, "_blank", "noopener");
    img.then((b) => {
      if (!b) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b); a.download = `${p.kind === "well" ? "plaque" : "sacrifice-plaque"}-${p.number}.png`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    });
    api<PlaqueRow>(`/api/plaques/${p.id}/whatsapp-opened`, { method: "POST" })
      .then((r) => { toast(t("plwa_done")); refreshCounts(); onDone?.(r); }).catch((e) => toast(e.message));
  };
  return (
    <span className="wa-wrap">
      <button type="button" className={`sm wa-btn${label ? "" : " icon"}`} disabled={!!why} onClick={go}
        title={why || t("plwa_help")} aria-label={t("plwa_send")} aria-describedby={why ? `wa-why-${p.id}` : undefined}>
        <WaIcon />{label && <span>{t("plwa_send")}</span>}
      </button>
      {why && label && <span className="wa-why" id={`wa-why-${p.id}`}>⚠ {why}</span>}
      {w.problems.includes("phone_country") && <PhoneCountryFix p={p} onDone={onDone} />}
    </span>);
}

/** A local customer number without its country: choose the country here and the button works straight away. */
function PhoneCountryFix({ p, onDone }: { p: PlaqueRow; onDone?: (p: PlaqueRow) => void }) {
  const { t, lang } = useI18n();
  const [list, setList] = useState<{ code: string; dial: string; ar: string | null; en: string | null }[]>([]);
  useEffect(() => { api<any[]>("/api/phones/countries").then(setList).catch(() => {}); }, []);
  const save = async (code: string) => {
    if (!code) return;
    try {
      const url = p.kind === "well" ? `/api/projects/${p.number}` : `/api/sacrifices/${p.number}`;
      await api(url, { method: "PATCH", body: { customer_phone_country: code } });
      onDone?.(await api<PlaqueRow>(`/api/plaques/${p.id}`)); toast(t("plwa_country_saved"));
    } catch (e: any) { toast(e.message); }
  };
  return <select className="sm wa-country" defaultValue="" onChange={(e) => save(e.target.value)} aria-label={t("plwa_pick_country")}>
    <option value="">{t("plwa_pick_country")}…</option>
    {list.map((c) => <option key={c.code} value={c.code}>{(lang === "ar" ? c.ar : c.en) || c.code} {c.dial}</option>)}
  </select>;
}

/** The WhatsApp icon beside the final-video upload: opens the customer's chat (app on a phone, WhatsApp Web on a
 *  computer). Disabled with the reason when the number is missing, has no country, or is not valid. */
export function WaChatButton({ e164, status, text, label }: { e164: string | null | undefined; status?: string | null; text?: string; label?: boolean }) {
  const { t } = useI18n();
  const why = waProblem(t, e164, status);
  const link = why ? null : waLink(e164 || null, text);
  return link
    ? <a className={`btn sm wa-btn${label ? "" : " icon"}`} href={link} target="_blank" rel="noopener noreferrer"
        title={`${t("wa_chat")} · ${e164}`} aria-label={t("wa_chat")}><WaIcon />{label && <span>{t("wa_chat")}</span>}</a>
    : <span className="wa-wrap"><button type="button" className={`sm wa-btn${label ? "" : " icon"}`} disabled title={why || ""} aria-label={t("wa_chat")}>
        <WaIcon />{label && <span>{t("wa_chat")}</span>}</button>{label && <span className="wa-why">⚠ {why}</span>}</span>;
}
