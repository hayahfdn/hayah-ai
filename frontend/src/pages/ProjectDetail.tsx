import { useState } from "react";
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
import PlaqueBadge from "../plaque/PlaqueBadge";
import * as I from "../icons";
import DeliveryTrio from "./DeliveryTrio";

export default function ProjectDetail() {
  const { wellId } = useParams();
  const { t, fmtDate, money } = useI18n();
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
  // only filled-in details are shown; the empty ones are listed in one short line instead of empty boxes
  const rows: [string, I.IconC, any][] = [
    ["customer_phone", I.Phone, d.customer_phone && <span dir="ltr">{d.customer_phone_e164 || d.customer_phone}
      {d.customer_phone_e164 && d.customer_phone_e164 !== d.customer_phone && <span className="muted"> ({t("ph_original")}: {d.customer_phone})</span>}
      {d.customer_phone_status && d.customer_phone_status !== "valid" && <span className="badge warn" dir="auto"> {t(d.customer_phone_status === "invalid" ? "ph_invalid" : "ph_needs_country")}</span>}</span>],
    ["sales_source", I.TrendingUp, d.source_group || d.sales_source ? <>{d.source_group || d.sales_source}{d.sales_source && d.sales_source !== d.source_group && <span className="muted"> ({t("src_original")}: {d.sales_source})</span>}</> : null],
    ["addons", I.Package, d.extras ? <AddonChips value={d.extras} /> : null],
    ["addon_sacrifices", I.Sheep, d.addon_sacrifices?.length ? <span className="linked-sac">{d.addon_sacrifices.map((a) =>
      <span key={a.sacrifice_no} className="chip">{t("addon_sac_no")} <b className="mono">{a.sacrifice_no}</b>{a.animal_type ? ` · ${a.animal_type}` : ""}{a.sale_price ? ` · ${money(a.sale_price)}` : ""}</span>)}</span> : null],
    ["delivery_date", I.Truck, d.delivery_date ? <>{fmtDate(d.delivery_date)}{d.delivery_estimated && <span className="badge warn" style={{ marginInlineStart: 6 }}>{t("delivery_estimated")}</span>}</> : null],
    ["last_maintenance_date", I.Wrench, d.last_maintenance_date ? fmtDate(d.last_maintenance_date) : null],
    ["next_maintenance_date", I.CalendarDays, d.next_maintenance_date ? fmtDate(d.next_maintenance_date) : null],
    ["raw_media_folder", I.Images, d.raw_media_folder_url && <a href={d.raw_media_folder_url} target="_blank" rel="noreferrer">{t("open_link")}</a>],
    ["final_video_link", I.CirclePlay, d.final_video_link && <a href={d.final_video_link} target="_blank" rel="noreferrer">{t("open_link")}</a>],
  ];
  const filled = rows.filter(([, , v]) => v);
  const empty = rows.filter(([k, , v]) => !v && k !== "addon_sacrifices" && k !== "final_video_link");
  const phone = d.customer_phone_e164;
  return (
    <>
      <section className="card proj-head">
        <div className="ph-main">
          <Link to="/projects" className="crumb">‹ {t("nav_projects")}</Link>
          <h1><span className="ph-kind"><I.Droplets size={22} /></span>{t("well_id")} <span className="mono ph-no">{d.well_id}</span>
            {d.is_sample && <span className="badge">{t("sample")}</span>}{d.merged_into_id && <span className="badge warn">merged</span>}</h1>
          <div className="ph-who">{d.customer_name || "—"}</div>
          <div className="ph-chips">
            {d.well_type && <span className="pchip"><I.Droplets size={14} />{d.well_type}</span>}
            {d.contractor ? <span className="pchip"><span className="swatch" style={{ background: d.contractor.color || "#ccc" }} />{d.contractor.code} · {d.contractor.name}</span>
              : <span className="pchip warn"><I.HardHat size={14} />{t("ph_no_contractor")}</span>}
            {d.order_date && <span className="pchip"><I.CalendarDays size={14} />{fmtDate(d.order_date)}</span>}
            {d.shopify_order && <span className="pchip"><I.Hash size={14} />Shopify {d.shopify_order}</span>}
          </div>
        </div>
        <div className="ph-side">
          {d.sale_amount != null && <div className="ph-money"><span>{t("sale_amount")}</span><b>{money(d.sale_amount)}</b>
            <Status v={d.payment_status} /></div>}
          <div className="ph-actions">
            {can(...EDITORS) && <button className="primary" onClick={() => setEditing(true)}><I.Pencil size={16} /> {t("edit")}</button>}
            {can(...EDITORS) && phone && <Link className="btn icon-btn wa-soft" to={`/inbox?phone=${encodeURIComponent(phone)}`} title={t("wa_start")} aria-label={t("wa_start")}><I.MessageCircle size={18} /></Link>}
            {phone && <a className="btn icon-btn" href={`tel:${phone}`} title={t("ph_call")} aria-label={t("ph_call")}><I.Phone size={18} /></a>}
            {can(...MANAGERS) && <button className="icon-btn" onClick={() => setRenumbering(true)} title={t("num_change")} aria-label={t("num_change")}><I.Hash size={18} /></button>}
            {can(...MANAGERS) && <button className="icon-btn" onClick={() => setMerging(true)} title={t("request_merge")} aria-label={t("request_merge")}><I.GitMerge size={18} /></button>}
          </div>
        </div>
      </section>
      <StatusSteps d={d} />
      <div className="proj-grid">
        <section className="card proj-info">
          <div className="card-h"><h2>{t("ph_details")}</h2></div>
          {d.dedication && <div className="dedication"><span>{t("dedication")}</span><b>{d.dedication}</b></div>}
          <dl className="dl2">{filled.map(([k, C, v]) => <div key={k}><dt><C size={15} aria-hidden="true" />{t(k)}</dt><dd>{v}</dd></div>)}</dl>
          {d.notes && <p className="ph-notes"><span className="muted">{t("notes")}: </span>{d.notes}</p>}
          {empty.length > 0 && <p className="ph-empty"><I.TriangleAlert size={14} aria-hidden="true" /> {t("ph_not_filled")}: {empty.map(([k]) => t(k)).join("، ")}
            {can(...EDITORS) && <> · <button className="link-btn" onClick={() => setEditing(true)}>{t("ph_fill")}</button></>}</p>}
        </section>
        <DeliveryTrio p={d} />
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
            <tbody>{h.data.maintenance.map((m: any) => <tr key={m.id}><td className="mono">{m.maintenance_code}</td><td>{fmtDate(m.date)}</td><td>{m.problem_type}</td><td className="wrap">{m.description}</td><td><Status v={m.status} /></td><td className="num">{money(m.repair_cost)}</td></tr>)}</tbody></table></div> : <Empty />
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

type Step = { key: string; icon: I.IconC; state: "done" | "now" | "todo" | "warn"; value: React.ReactNode };

/** The order's road from order to delivery in one row, plus payment and maintenance, instead of five big boxes. */
function StatusSteps({ d }: { d: Project }) {
  const { t, st, fmtDate } = useI18n();
  const cs = d.construction_status;
  const steps: Step[] = [
    { key: "ph_step_order", icon: I.Inbox, state: "done", value: fmtDate(d.order_date) },
    { key: "plaque", icon: I.Image, state: d.plaque_status === "approved" ? "done" : d.plaque_status === "draft" ? "now" : "todo",
      value: d.plaque_status === "approved" ? t("plaque_approved") : d.plaque_status === "draft" ? t("plaque_draft") : t("plaque_none") },
    { key: "construction_status", icon: I.HardHat, state: cs === "completed" ? "done" : cs === "in_progress" || cs === "scheduled" ? "now"
      : cs === "on_hold" || cs === "cancelled" ? "warn" : "todo", value: st(cs) },
    { key: "video_status", icon: I.Clapperboard, state: d.video_status === "completed" ? "done" : d.video_status && d.video_status !== "none" ? "now" : "todo",
      value: st(d.video_status) },
    { key: "delivery_status", icon: I.Truck, state: d.delivery_status === "delivered" ? "done" : d.delivery_status === "pending" ? "now" : "todo",
      value: d.delivery_date ? `${st(d.delivery_status)} · ${fmtDate(d.delivery_date)}` : st(d.delivery_status) },
  ];
  const doneN = steps.filter((s) => s.state === "done").length;
  return (
    <section className="card steps-card" aria-label={t("ph_progress")}>
      <div className="steps-top"><b>{t("ph_progress")}</b><span className="steps-pct">{Math.round((100 * doneN) / steps.length)}%</span>
        <div className="steps-bar"><i style={{ width: `${(100 * doneN) / steps.length}%` }} /></div>
        <span className="steps-extra"><span className="muted">{t("payment_status")}:</span> <Status v={d.payment_status} />
          <span className="muted">{t("maintenance_status")}:</span> <Status v={d.maintenance_status} /></span></div>
      <ol className="steps">{steps.map((s) => (
        <li key={s.key} className={`step ${s.state}`}>
          <span className="step-ico" aria-hidden="true">{s.state === "done" ? <I.CircleCheck size={18} /> : <s.icon size={18} />}</span>
          <span className="step-txt"><b>{t(s.key)}</b><small>{s.value}</small></span></li>))}</ol>
    </section>);
}
