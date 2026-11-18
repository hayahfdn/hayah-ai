import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Project } from "../api";
import { EDITORS, MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, Modal, Status, toast, useApi } from "../ui";
import ProjectForm from "./ProjectForm";
import { MediaTable } from "./MediaLibrary";

export default function ProjectDetail() {
  const { wellId } = useParams();
  const { t, fmtDate, num } = useI18n();
  const { can } = useAuth();
  const p = useApi<Project>(`/api/projects/${wellId}`);
  const h = useApi<any>(`/api/projects/${wellId}/history`);
  const [tab, setTab] = useState("timeline");
  const [editing, setEditing] = useState(false);
  const [merging, setMerging] = useState(false);
  if (p.error) return <ErrorBox error={p.error} />;
  if (!p.data) return <p className="muted">{t("loading")}</p>;
  const d = p.data;
  const item = (k: string, v: any) => <div key={k}><span>{t(k)}</span>{v ?? "—"}</div>;
  return (
    <>
      <div className="topbar">
        <div><Link to="/projects" className="muted">‹ {t("nav_projects")}</Link>
          <h1>{t("well_id")} <span className="mono">{d.well_id}</span> {d.is_sample && <span className="badge">{t("sample")}</span>}</h1>
          {d.merged_into_id && <span className="badge warn">merged</span>}</div>
        <div style={{ display: "flex", gap: 8 }}>
          {can(...MANAGERS) && <button onClick={() => setMerging(true)}>{t("request_merge")}</button>}
          {can(...EDITORS) && <Link className="btn" to={`/plaque/${d.well_id}`}>{t("pl_design")}</Link>}
          {can(...EDITORS) && <button className="primary" onClick={() => setEditing(true)}>{t("edit")}</button>}
        </div>
      </div>
      <div className="grid kpis" style={{ marginBottom: 14 }}>
        {[["construction_status", d.construction_status], ["delivery_status", d.delivery_status], ["video_status", d.video_status],
          ["maintenance_status", d.maintenance_status], ["payment_status", d.payment_status]].map(([k, v]) => (
          <div className="card kpi" key={k}><div className="label">{t(k)}</div><div style={{ marginTop: 6 }}><Status v={v} /></div></div>))}
      </div>
      <div className="card">
        <div className="dl">
          {item("customer_name", d.customer_name)}{item("customer_phone", d.customer_phone && <span dir="ltr">{d.customer_phone}</span>)}
          {item("country", d.country)}{item("city", d.city)}{item("village", d.village)}{item("well_type", d.well_type)}
          {item("sales_source", d.sales_source)}{item("contractor", d.contractor ? `${d.contractor.code} · ${d.contractor.name}` : null)}
          {item("sale_amount", d.sale_amount && `${num(d.sale_amount)} ${d.currency}`)}{item("order_date", fmtDate(d.order_date))}
          {item("construction_start_date", fmtDate(d.construction_start_date))}{item("completion_date", fmtDate(d.completion_date))}
          {item("delivery_date", fmtDate(d.delivery_date))}{item("last_maintenance_date", fmtDate(d.last_maintenance_date))}
          {item("next_maintenance_date", fmtDate(d.next_maintenance_date))}
          {item("raw_media_folder", d.raw_media_folder_url && <a href={d.raw_media_folder_url} target="_blank" rel="noreferrer">{t("open_link")}</a>)}
          {item("final_video_link", d.final_video_link && <a href={d.final_video_link} target="_blank" rel="noreferrer">{t("open_link")}</a>)}
          {item("last_updated", fmtDate(d.updated_at))}
        </div>
        {d.dedication && <p style={{ whiteSpace: "pre-wrap" }}><span className="muted">{t("dedication")}: </span><b>{d.dedication}</b>{d.shopify_order && <span className="muted"> · Shopify {d.shopify_order}</span>}</p>}
        {d.notes && <p style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}><span className="muted">{t("notes")}: </span>{d.notes}</p>}
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <div className="tabs">{["timeline", "media", "maintenance", "deliveries"].map((k) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t(k)} {h.data && k !== "timeline" ? `(${h.data[k].length})` : ""}</button>))}</div>
        {!h.data ? <p className="muted">{t("loading")}</p> : tab === "timeline" ? (
          h.data.events.length ? <ul className="timeline">{h.data.events.map((e: any) => (
            <li key={e.id}><span className="muted">{fmtDate(e.created_at)} {new Date(e.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
              <span><b>{e.event_type.replace(/_/g, " ")}</b> · {e.summary} <span className="muted">· {e.actor_label} · {e.source}</span></span></li>))}</ul> : <Empty />
        ) : tab === "media" ? <MediaTable rows={h.data.media} /> : tab === "maintenance" ? (
          h.data.maintenance.length ? <div className="table-wrap"><table><thead><tr><th>{t("maintenance_id")}</th><th>{t("date")}</th><th>{t("problem_type")}</th><th>{t("description")}</th><th>{t("status")}</th><th>{t("repair_cost")}</th></tr></thead>
            <tbody>{h.data.maintenance.map((m: any) => <tr key={m.id}><td className="mono">{m.maintenance_code}</td><td>{fmtDate(m.date)}</td><td>{m.problem_type}</td><td className="wrap">{m.description}</td><td><Status v={m.status} /></td><td className="num">{num(m.repair_cost)}</td></tr>)}</tbody></table></div> : <Empty />
        ) : (
          h.data.deliveries.length ? <div className="table-wrap"><table><thead><tr><th>{t("delivery_date")}</th><th>{t("status")}</th><th>{t("sender")}</th><th>{t("source")}</th><th>{t("decision_note")}</th></tr></thead>
            <tbody>{h.data.deliveries.map((x: any) => <tr key={x.id}><td>{fmtDate(x.delivery_date)}</td><td><Status v={x.status} /></td><td>{x.sender_name}</td><td>{x.source}</td><td className="wrap">{x.decision_note}</td></tr>)}</tbody></table></div> : <Empty />
        )}
      </div>
      {editing && <Modal title={`${t("edit")} · ${d.well_id}`} onClose={() => setEditing(false)}>
        <ProjectForm project={d} onCancel={() => setEditing(false)} onSaved={(np) => { p.setData(np); setEditing(false); h.reload(); toast(t("saved")); }} />
      </Modal>}
      {merging && <MergeModal source={d.well_id} onClose={() => setMerging(false)} />}
    </>
  );
}

function MergeModal({ source, onClose }: { source: number; onClose: () => void }) {
  const { t } = useI18n();
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try { await api("/api/projects/merge-requests", { body: { source_well_id: source, target_well_id: Number(target), reason } }); toast(t("saved")); onClose(); }
    catch (err: any) { setError(err.message); }
  };
  return <Modal title={t("request_merge")} onClose={onClose}><form onSubmit={submit}>
    <div className="form-grid"><Field label={t("merge_into")}><input type="number" required value={target} onChange={(e) => setTarget(e.target.value)} /></Field></div>
    <div style={{ marginTop: 12 }}><Field label={t("merge_reason")}><textarea required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field></div>
    <ErrorBox error={error} /><div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("request_merge")}</button></div>
  </form></Modal>;
}
