import { useState } from "react";
import { api } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, toast, useApi } from "../ui";

const EVENTS = ["construction_update", "delivery_confirmation", "final_video", "maintenance_report", "general_note"];

export default function Review() {
  const { t, fmtDate } = useI18n();
  const { can, refreshCounts } = useAuth();
  const { data, error, reload } = useApi<any[]>(can(...MANAGERS) ? "/api/review" : null);
  return (
    <>
      <div className="topbar"><h1>{t("nav_review")}</h1></div>
      <p className="muted">{t("review_intro")}</p>
      <PasteMessage onDone={() => { reload(); refreshCounts(); }} />
      <ErrorBox error={error} />
      <div className="grid" style={{ marginTop: 14 }}>
        {data?.map((c) => <Case key={c.id} c={c} onDone={() => { reload(); refreshCounts(); }} />)}
        {data && !data.length && <div className="card"><Empty /></div>}
      </div>
      <p className="muted" style={{ fontSize: 12 }}>{data?.length ? fmtDate(new Date().toISOString()) : ""}</p>
    </>
  );
}

function Case({ c, onDone }: { c: any; onDone: () => void }) {
  const { t, fmtDate } = useI18n();
  const p = c.proposed || {};
  const [well, setWell] = useState<string>(p.well_id ? String(p.well_id) : p.well_ids?.length === 1 ? String(p.well_ids[0]) : "");
  const [event, setEvent] = useState<string>(p.event_type && p.event_type !== "unknown" ? p.event_type : "general_note");
  const [error, setError] = useState<string | null>(null);
  const decide = async (approve: boolean) => {
    try {
      await api(`/api/review/${c.id}/decision`, { body: { approve, well_id: well ? Number(well) : null, event_type: c.inbound_message_id ? event : null } });
      toast(t("saved")); onDone();
    } catch (e: any) { setError(e.message); }
  };
  const merge = c.kind === "merge_request";
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <div><span className="badge warn">{t("k_" + c.kind)}</span> <span className="muted">#{c.id} · {fmtDate(c.created_at)}</span>
          {c.message_group && <span className="badge" style={{ marginInlineStart: 6 }}>{t("group")} {c.message_group}</span>}</div>
        <span className="muted">{c.message_sender}</span>
      </div>
      {c.message_text && <p style={{ whiteSpace: "pre-wrap", background: "var(--surface-2)", padding: 10, borderRadius: 8 }}>{c.message_text}</p>}
      {merge && <p>{p.source_well_id} → {p.target_well_id}</p>}
      {c.kind === "unassigned_media" && <p className="mono">{p.filename}</p>}
      <p className="muted" style={{ margin: "4px 0" }}><b>{t("reason")}:</b> {c.reason}</p>
      {p.engine && <p className="muted" style={{ margin: "4px 0", fontSize: 12.5 }}><b>{t("extracted")}:</b> {t("ev_" + p.event_type)} · {t("well_id")}: {p.well_ids?.join(", ") || "—"} · {Math.round((p.confidence || 0) * 100)}% ({p.engine})</p>}
      {!merge && <div className="form-grid" style={{ marginTop: 10 }}>
        <Field label={t("choose_well")}><input type="number" value={well} onChange={(e) => setWell(e.target.value)} /></Field>
        {c.inbound_message_id && <Field label={t("event_type")}><select value={event} onChange={(e) => setEvent(e.target.value)}>
          {EVENTS.map((x) => <option key={x} value={x}>{t("ev_" + x)}</option>)}</select></Field>}
      </div>}
      <ErrorBox error={error} />
      <div className="actions"><button className="danger" onClick={() => decide(false)}>{t("reject")}</button>
        <button className="primary" onClick={() => decide(true)} disabled={!merge && !well}>{t("approve")}</button></div>
    </div>
  );
}

function PasteMessage({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [group, setGroup] = useState("A");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(null);
    try { const r = await api("/api/intake/manual", { body: { text, group_label: group } }); setResult(r); setText(""); onDone(); }
    catch (err: any) { setError(err.message); }
  };
  return (
    <form className="card" onSubmit={submit}>
      <h2>{t("paste_message")}</h2><p className="muted" style={{ marginTop: -6 }}>{t("paste_help")}</p>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start", flexWrap: "wrap" }}>
        <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label={t("group")}>
          {["A", "B", "C", "D"].map((g) => <option key={g} value={g}>{t("group")} {g}</option>)}</select>
        <textarea style={{ flex: 1, minWidth: 220, minHeight: 60 }} required value={text} onChange={(e) => setText(e.target.value)} placeholder="1339 تم التسليم للعائلة" />
        <button className="primary">{t("process")}</button>
      </div>
      <ErrorBox error={error} />
      {result && <p className="muted" style={{ marginBottom: 0 }}>→ <b>{result.status}</b> · {t("ev_" + result.extraction?.event_type)} · {t("well_id")}: {result.extraction?.well_id ?? "—"}</p>}
    </form>
  );
}
