// Two working lists of the plaque workflow:
// - confirm: orders whose plaque is not approved yet (draft → customer's answer);
// - approved: «اللوحات المعتمدة – جاهزة للإرسال للمقاول», until sending to the contractor is recorded.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, Contractor, download, getToken } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { countryLabel } from "../nav";
import { Empty, ErrorBox, Field, Modal, toast } from "../ui";
import {
  designerLink, MissingList, PlaqueActions, PlaqueWhatsApp, plaqueFile, PlaqueRow, PlaqueStatusBadge, PlaqueThumb, waLink,
} from "../plaque/flow";

type Mode = "confirm" | "approved";

export default function PlaqueLists({ mode }: { mode: Mode }) {
  const { t } = useI18n();
  const { counts } = useAuth();
  const [tab, setTab] = useState<"pending" | "sent">("pending");
  const [kind, setKind] = useState<"" | "well" | "sacrifice">("");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<PlaqueRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const group = mode === "confirm" ? "confirm" : tab === "pending" ? "approved" : "sent";
  const load = () => api<PlaqueRow[]>("/api/plaques", { query: { group, kind, q: q.trim() } })
    .then((r) => { setRows(r); setError(null); }).catch((e) => setError(e.message));
  useEffect(() => { setRows(null); load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [group, kind]);
  // follow the live counts: when a number in the menu changes, the list is read again
  const live = mode === "confirm" ? counts.pl_confirm : counts.pl_ready;
  useEffect(() => { if (rows) load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [live]);
  const replace = (r: PlaqueRow) => setRows((xs) => {
    if (!xs) return xs;
    const stays = mode === "confirm" ? !["approved_for_contractor", "sent_to_contractor"].includes(r.status)
      : (tab === "pending" ? r.status === "approved_for_contractor" : r.status === "sent_to_contractor");
    return stays ? xs.map((x) => (x.id === r.id ? r : x)) : xs.filter((x) => x.id !== r.id);
  });

  return (
    <>
      <div className="topbar">
        <div><h1>{mode === "confirm" ? t("nav_pl_confirm") : t("nav_pl_approved")}
          {live ? <span className="count-pill">{live}</span> : null}</h1>
          <p className="muted" style={{ margin: 0 }}>{mode === "confirm" ? t("pla_confirm_help") : t("pla_approved_help")}</p></div>
      </div>
      {mode === "approved" && <div className="tabs">
        <button type="button" className={tab === "pending" ? "on" : ""} onClick={() => setTab("pending")}>{t("pla_pending")}{counts.pl_ready ? ` (${counts.pl_ready})` : ""}</button>
        <button type="button" className={tab === "sent" ? "on" : ""} onClick={() => setTab("sent")}>{t("pla_sent")}</button>
      </div>}
      <form className="toolbar" onSubmit={(e) => { e.preventDefault(); load(); }}>
        <select value={kind} onChange={(e) => setKind(e.target.value as any)} aria-label={t("pla_all")}>
          <option value="">{t("pla_all")}</option><option value="well">{t("pla_well")}</option><option value="sacrifice">{t("pla_sac")}</option>
        </select>
        <input type="search" placeholder={t("pla_search")} value={q} onChange={(e) => setQ(e.target.value)} />
        <button>🔍</button>
      </form>
      <ErrorBox error={error} />
      {rows === null ? <p className="muted">…</p> : !rows.length ? <Empty />
        : mode === "confirm" ? <ConfirmList rows={rows} onChange={replace} />
          : <ApprovedList rows={rows} sent={tab === "sent"} onChange={replace} />}
    </>
  );
}

function Order({ p }: { p: PlaqueRow }) {
  const { t } = useI18n();
  return <>
    <b className="well-no mono">{p.kind === "well" ? "" : "S"}{p.number}</b>{" "}
    <span className="muted">{p.kind === "well" ? t("pla_well") : t("pla_sac")}{p.type ? ` · ${p.type}` : ""}</span>
  </>;
}

function Phone({ p }: { p: PlaqueRow }) {
  const { t } = useI18n();
  const wa = waLink(p.customer_phone_e164);
  if (!p.customer_phone) return <span className="muted">—</span>;
  return <span><bdi dir="ltr" className="mono">{p.customer_phone_e164 || p.customer_phone}</bdi>
    {wa && <> · <a href={wa} target="_blank" rel="noreferrer">{t("pla_whatsapp")}</a></>}
    {p.customer_phone_status && p.customer_phone_status !== "valid" && <> <span className="badge warn">{t("ph_" + p.customer_phone_status)}</span></>}</span>;
}

function ConfirmList({ rows, onChange }: { rows: PlaqueRow[]; onChange: (r: PlaqueRow) => void }) {
  const { t, fmtDate } = useI18n();
  return (
    <div className="pl-list">
      {rows.map((p) => (
        <div key={p.id} className={`card pl-item${p.missing.length || p.status === "needs_changes" ? " alert" : ""}`}>
          <PlaqueThumb p={p} />
          <div className="pl-body">
            <div className="pl-head"><Order p={p} /> <PlaqueStatusBadge s={p.status} />
              {p.design?.auto && <span className="badge">{t("pla_draft_auto")}</span>}
              {p.version ? <span className="muted">{t("pla_version")} {p.version}</span> : null}</div>
            <div className="pl-name" dir="rtl">{p.name || <span className="muted">—</span>}</div>
            <div className="muted">{p.customer_name || "—"} · <Phone p={p} /> · {fmtDate(p.order_date)}</div>
            <MissingList missing={p.missing} />
            {p.customer_note && <div className="pl-note">{t("pla_customer_note")}: <b dir="auto">{p.customer_note}</b></div>}
            <div className="actions">
              <Link className="btn sm" to={designerLink(p)}>{t("pla_open")}</Link>
              <PlaqueWhatsApp p={p} onDone={onChange} label />
              <PlaqueActions p={p} onDone={onChange} compact />
            </div>
          </div>
        </div>))}
    </div>
  );
}

function ApprovedList({ rows, sent, onChange }: { rows: PlaqueRow[]; sent: boolean; onChange: (r: PlaqueRow) => void }) {
  const { t, lang, fmtDate } = useI18n();
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [sendFor, setSendFor] = useState<PlaqueRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<PlaqueRow | null>(null);
  useEffect(() => setSel(new Set()), [sent]);
  const all = rows.length > 0 && rows.every((r) => sel.has(r.id));
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const fileName = (p: PlaqueRow) => `${p.kind === "well" ? "plaque" : "sacrifice-plaque"}-${p.number}.png`;
  const zip = async () => {
    setBusy(true);
    try {
      const res = await fetch("/api/plaques/zip", { method: "POST", headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [...sel] }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob()); a.download = `plaques-${new Date().toISOString().slice(0, 10)}.zip`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  // Phones share the image itself (e.g. to the contractor's WhatsApp); elsewhere it downloads and opens WhatsApp.
  const share = async (p: PlaqueRow) => {
    const text = `${t("pla_share_text")} ${p.number}${p.name ? ` · ${p.name}` : ""}`;
    try {
      const res = await fetch(plaqueFile(p), { headers: { Authorization: `Bearer ${getToken()}` } });
      const file = new File([await res.blob()], fileName(p), { type: "image/png" });
      const nav: any = navigator;
      if (nav.canShare?.({ files: [file] })) { await nav.share({ files: [file], text }); return; }
    } catch (e: any) { if (e?.name === "AbortError") return; }
    await download(plaqueFile(p, true), fileName(p));
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
  };
  return <>
    {!sent && <div className="actions" style={{ marginBottom: 10 }}>
      <label className="inline-check"><input type="checkbox" checked={all} onChange={() => setSel(all ? new Set() : new Set(rows.map((r) => r.id)))} /> {t("pla_select_all")}</label>
      <button disabled={!sel.size || busy} onClick={zip}>{busy ? "…" : `⬇ ${t("pla_zip")}`}{sel.size ? ` (${sel.size})` : ""}</button>
    </div>}
    <div className="pl-grid">
      {rows.map((p) => (
        <div key={p.id} className={`card pl-card${sel.has(p.id) ? " on" : ""}`}>
          <PlaqueThumb p={p} onClick={() => setView(p)} />
          <div className="pl-head">
            {!sent && <input type="checkbox" checked={sel.has(p.id)} onChange={() => toggle(p.id)} aria-label={`${p.number}`} />}
            <Order p={p} /></div>
          <div className="pl-name" dir="rtl">{p.name || "—"}</div>
          <div className="muted" style={{ fontSize: 12.5 }}>{p.customer_decision_by ? `✓ ${p.customer_decision_by} · ` : ""}{fmtDate(p.customer_decision_at)}</div>
          {sent && <div style={{ fontSize: 13 }}>{t("pla_sent_on")} {fmtDate(p.sent_to_contractor_on)} · <b>{p.contractor?.name || "—"}</b>
            {p.contractor_country ? ` · ${countryLabel(p.contractor_country, lang)}` : ""}{p.sent_to_contractor_by ? ` · ${t("pla_by")} ${p.sent_to_contractor_by}` : ""}</div>}
          <div className="actions">
            {p.file_version_id && <>
              <button className="sm" onClick={() => download(plaqueFile(p, true), fileName(p))}>⬇ {t("pla_download")}</button>
              <button className="sm" onClick={() => share(p)}>↗ {t("pla_share")}</button>
            </>}
            {!sent && <button className="sm primary" onClick={() => setSendFor(p)}>✓ {t("pla_send")}</button>}
            {sent && <PlaqueActions p={p} onDone={onChange} compact />}
          </div>
        </div>))}
    </div>
    {sendFor && <SendModal p={sendFor} onClose={() => setSendFor(null)} onDone={(r) => { setSendFor(null); onChange(r); }} />}
    {view && <Modal title={`${view.number} · ${view.name || ""}`} onClose={() => setView(null)}><BigImage p={view} /></Modal>}
  </>;
}

function BigImage({ p }: { p: PlaqueRow }) {
  return <div className="pl-big"><PlaqueThumb p={p} /></div>;
}

function SendModal({ p, onClose, onDone }: { p: PlaqueRow; onClose: () => void; onDone: (r: PlaqueRow) => void }) {
  const { t, lang } = useI18n();
  const { refreshCounts } = useAuth();
  const [cons, setCons] = useState<Contractor[]>([]);
  const [cid, setCid] = useState<number | "">(p.order_contractor_id || "");
  const [country, setCountry] = useState(p.order_country || "");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Contractor[]>("/api/contractors").then((c) => setCons(c.filter((x) => x.is_active))).catch((e) => setError(e.message)); }, []);
  const countries = useMemo(() => [...new Set(cons.map((c) => c.country).filter(Boolean) as string[])].sort(), [cons]);
  const pickCon = (v: string) => {
    const id = v ? Number(v) : "";
    setCid(id);
    const c = cons.find((x) => x.id === id);
    if (c?.country) setCountry(c.country);
  };
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api<PlaqueRow>(`/api/plaques/${p.id}/send-to-contractor`, { body: { contractor_id: cid, country, sent_on: date, note: note || null } });
      toast(t("pla_sent_ok")); refreshCounts(); onDone(r);
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal title={`${t("pla_send_title")} · ${p.number}`} onClose={onClose}>
      <ErrorBox error={error} />
      <div className="form-grid">
        <Field label={t("pla_contractor")}>
          <select value={cid} onChange={(e) => pickCon(e.target.value)}>
            <option value="">—</option>
            {cons.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code}){c.country ? ` · ${countryLabel(c.country, lang)}` : ""}</option>)}
          </select>
        </Field>
        <Field label={t("pla_country")}>
          <input list="pl-countries" value={country} onChange={(e) => setCountry(e.target.value)} />
          <datalist id="pl-countries">{countries.map((c) => <option key={c} value={c}>{countryLabel(c, lang)}</option>)}</datalist>
        </Field>
        <Field label={t("pla_date")}><input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        <Field label={t("pla_note_opt")}><input dir="auto" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </div>
      <div className="actions"><button onClick={onClose}>{t("cancel")}</button>
        <button className="primary" disabled={busy || !cid || !country.trim() || !date} onClick={save}>{busy ? "…" : `✓ ${t("pla_send")}`}</button></div>
    </Modal>
  );
}
