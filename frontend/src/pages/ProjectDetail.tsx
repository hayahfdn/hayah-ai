import { lazy, Suspense, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChangeNumber } from "../Renumber";
import PlaquePreview from "../plaque/Preview";
import { api, Project } from "../api";
import { EDITORS, MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, Modal, Status, toast, useApi } from "../ui";
import ProjectForm from "./ProjectForm";
import { AddonChips } from "../AddonPicker";
import { MediaTable } from "./MediaLibrary";
import PlaqueBadge, { usePlaqueImage } from "../plaque/PlaqueBadge";
import { PlaqueRow, PlaqueWhatsApp } from "../plaque/flow";
const FinalVideoSection = lazy(() => import("./FinalVideos").then((m) => ({ default: m.FinalVideoSection })));

export default function ProjectDetail() {
  const { wellId } = useParams();
  const { t, fmtDate, num } = useI18n();
  const { can } = useAuth();
  const p = useApi<Project>(`/api/projects/${wellId}`);
  const h = useApi<any>(`/api/projects/${wellId}/history`);
  const [tab, setTab] = useState("timeline");
  // ?edit=1 (the open icon beside a project number): open straight in the usual edit form
  const [search, setSearch] = useSearchParams();
  const [editing, setEditing] = useState(() => search.get("edit") === "1" && can(...EDITORS));
  const [merging, setMerging] = useState(false);
  const [renumbering, setRenumbering] = useState(false);
  const go = useNavigate();
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
          {can(...MANAGERS) && <button onClick={() => setRenumbering(true)}>🔢 {t("num_change")}</button>}
          {can(...MANAGERS) && <button onClick={() => setMerging(true)}>{t("request_merge")}</button>}
          {can(...EDITORS) && <Link className="btn" to={`/plaque/${d.well_id}`}>🖼 {d.plaque_status ? t("plaque_new_version") : t("plaque_create")}</Link>}
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
          {item("customer_name", d.customer_name)}{item("customer_phone", d.customer_phone && <span dir="ltr">{d.customer_phone_e164 || d.customer_phone}
            {d.customer_phone_e164 && d.customer_phone_e164 !== d.customer_phone && <span className="muted"> ({t("ph_original")}: {d.customer_phone})</span>}
            {d.customer_phone_status && d.customer_phone_status !== "valid" && <span className="badge warn" dir="auto"> {t(d.customer_phone_status === "invalid" ? "ph_invalid" : "ph_needs_country")}</span>}</span>)}
          {item("well_type", d.well_type)}
          {item("addons", <AddonChips value={d.extras} />)}
          {!!d.addon_sacrifices?.length && item("addon_sacrifices", <span className="linked-sac">{d.addon_sacrifices.map((a) =>
            <span key={a.sacrifice_no} className="chip">{t("addon_sac_no")} <b className="mono">{a.sacrifice_no}</b>{a.animal_type ? ` · ${a.animal_type}` : ""}{a.sale_price ? ` · ${num(a.sale_price)} ${a.currency}` : ""}</span>)}</span>)}
          {item("sales_source", d.source_group || d.sales_source ? <>{d.source_group || d.sales_source}{d.sales_source && d.sales_source !== d.source_group && <span className="muted"> ({t("src_original")}: {d.sales_source})</span>}</> : null)}{item("contractor", d.contractor ? `${d.contractor.code} · ${d.contractor.name}` : null)}
          {item("sale_amount", d.sale_amount && `${num(d.sale_amount)} ${d.currency}`)}{item("order_date", fmtDate(d.order_date))}
          {item("delivery_date", fmtDate(d.delivery_date))}{item("last_maintenance_date", fmtDate(d.last_maintenance_date))}
          {item("next_maintenance_date", fmtDate(d.next_maintenance_date))}
          {item("raw_media_folder", d.raw_media_folder_url && <a href={d.raw_media_folder_url} target="_blank" rel="noreferrer">{t("open_link")}</a>)}
          {item("final_video_link", d.final_video_link && <a href={d.final_video_link} target="_blank" rel="noreferrer">{t("open_link")}</a>)}
        </div>
        {d.dedication && <p style={{ whiteSpace: "pre-wrap" }}><span className="muted">{t("dedication")}: </span><b>{d.dedication}</b>{d.shopify_order && <span className="muted"> · Shopify {d.shopify_order}</span>}</p>}
        {d.notes && <p style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}><span className="muted">{t("notes")}: </span>{d.notes}</p>}
      </div>
      <PlaqueCard p={d} />
      {can(...EDITORS) && d.customer_phone_e164 && <div className="actions" style={{ marginTop: 10 }}><Link className="btn" to={`/inbox?phone=${encodeURIComponent(d.customer_phone_e164)}`}>🟢 {t("wa_start")}</Link></div>}
      {can(...EDITORS) && <div id="final-video" style={{ marginTop: 14 }}><Suspense fallback={null}><FinalVideoSection kind="well" no={d.well_id} /></Suspense></div>}
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
      {editing && <Modal title={`${t("edit")} · ${d.well_id}`} onClose={() => { setEditing(false); setSearch({}, { replace: true }); }}>
        <div className="edit-plaque"><PlaquePreview p={d} />
          <div><b>{t("plaque")}</b> <PlaqueBadge p={d} /><p className="muted">{t("plaque_auto_preview")}</p>
            <Link className="btn" to={`/plaque/${d.well_id}`}>🖼 {t("plaque_edit")}</Link></div></div>
        <ProjectForm project={d} onCancel={() => { setEditing(false); setSearch({}, { replace: true }); }}
          onSaved={(np) => { p.setData(np); setEditing(false); setSearch({}, { replace: true }); h.reload(); toast(t("saved")); }} />
      </Modal>}
      {renumbering && <ChangeNumber kind="project" current={d.well_id} onClose={() => setRenumbering(false)}
        onDone={(n) => { setRenumbering(false); go(`/projects/${n}`, { replace: true }); }} />}
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

/** The order's plaque: the approved image (or a clear way to create one), linked to the designer. */
function PlaqueCard({ p }: { p: Project }) {
  const { t, fmtDate } = useI18n();
  const { can } = useAuth();
  const img = usePlaqueImage(p.well_id, p.plaque_status === "approved" ? p.plaque_media_id : null);
  const flow = useApi<PlaqueRow | null>(can(...EDITORS) ? `/api/plaques/order/well/${p.well_id}` : null);
  return (
    <div className="card plaque-card" style={{ marginTop: 14 }}>
      <div className="plaque-card-head">
        <h2 style={{ margin: 0 }}>{t("plaque")}</h2>
        <PlaqueBadge p={p} />
        {flow.data && <PlaqueWhatsApp p={flow.data} label onDone={() => flow.reload()} />}
      </div>
      {p.plaque_status === "approved" ? <div className="plaque-card-body">
        {img.url ? <img className="plaque-thumb" src={img.url} alt={`${t("plaque")} ${p.well_id}`} /> : <ErrorBox error={img.error} />}
        <div>
          <p style={{ marginTop: 0 }}><span className="badge ok">✓ {t("plaque_approved")}</span></p>
          <p className="muted">{t("plaque_approved_by")}: {p.plaque_approved_by || "—"} · {fmtDate(p.plaque_approved_at)}</p>
          {can(...EDITORS) && <Link className="btn" to={`/plaque/${p.well_id}`}>{t("plaque_versions")} · {t("plaque_new_version")}</Link>}
        </div>
      </div> : <div className="plaque-card-body">
        <PlaquePreview p={p} />
        <div>
          <p className="muted" style={{ marginTop: 0 }}>{t("plaque_auto_preview")}</p>
          {can(...EDITORS) && <Link className="btn primary" to={`/plaque/${p.well_id}`}>🖼 {t("plaque_edit")}</Link>}
        </div>
      </div>}
    </div>
  );
}
