// The plaque workflow shared by the confirm list, the approved section and the designer:
// one plaque per order, its status, what is missing, and the moves an employee can make.
import { useEffect, useState } from "react";
import { api, fileUrl } from "../api";
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
export const waLink = (e164: string | null, text?: string) =>
  e164 ? `https://wa.me/${e164.replace(/\D/g, "")}${text ? `?text=${encodeURIComponent(text)}` : ""}` : null;
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
