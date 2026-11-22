import OpenIcon from "../OpenIcon";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, download, Project } from "../api";
import { EDITORS, MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Modal, Status, toast, useApi } from "../ui";
import ProjectForm from "./ProjectForm";
import PlaqueBadge from "../plaque/PlaqueBadge";
import { AddonChips } from "../AddonPicker";
import { WaPhoneIcon } from "../WaPhone";

export default function Projects() {
  const { t, st, fmtDate, num } = useI18n();
  const { can, refreshCounts } = useAuth();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  // ?new=1&phone=…&name=… (from a WhatsApp chat): open the new-order form already filled in
  const [creating, setCreating] = useState(() => params.get("new") === "1");
  const prefill = params.get("new") === "1" ? { customer_phone: params.get("phone") || "", customer_name: params.get("name") || "", sales_source: "WhatsApp" } : undefined;
  const q = Object.fromEntries(params.entries());
  const page = Number(q.page || 1);
  const { data, error, reload } = useApi<{ items: Project[]; total: number; page_size: number }>("/api/projects", { ...q, page, page_size: 50 });
  const setQ = (k: string, v: string) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); n.delete("page"); setParams(n); };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  return (
    <>
      <div className="topbar"><h1>{t("nav_projects")}</h1>
        <div style={{ display: "flex", gap: 8 }}>
          {can(...MANAGERS) && <button onClick={() => download("/api/projects/export.csv", "hayah-projects.csv")}>{t("export_csv")}</button>}
          {can(...EDITORS) && <button title={t("resort_help")} onClick={async () => {
            try { await api("/api/projects/resort", { method: "POST" }); const n = new URLSearchParams(params); n.delete("page"); n.delete("sort"); setParams(n); reload(); toast(t("resort_done")); }
            catch (e: any) { toast(e.message); } }}>⇅ {t("resort")}</button>}
          {can(...EDITORS) && <button className="primary" onClick={() => setCreating(true)}>+ {t("new_project")}</button>}
        </div>
      </div>
      {data?.items.some((p) => p.is_sample) && <div className="banner">{t("sample_banner")}</div>}
      <div className="toolbar">
        <input className="search" type="search" placeholder={t("search")} defaultValue={q.q || ""} onKeyDown={(e) => e.key === "Enter" && setQ("q", (e.target as HTMLInputElement).value)} onBlur={(e) => setQ("q", e.target.value)} />
        <select value={q.construction_status || ""} onChange={(e) => setQ("construction_status", e.target.value)} aria-label={t("construction_status")}>
          <option value="">{t("construction_status")}: {t("all")}</option>
          {["new_order", "scheduled", "in_progress", "completed", "on_hold", "cancelled"].map((s) => <option key={s} value={s}>{st(s)}</option>)}
        </select>
        <select value={q.delivery_status || ""} onChange={(e) => setQ("delivery_status", e.target.value)} aria-label={t("delivery_status")}>
          <option value="">{t("delivery_status")}: {t("all")}</option>
          {["not_ready", "pending", "delivered"].map((s) => <option key={s} value={s}>{st(s)}</option>)}
        </select>
        <span className="muted">{data ? `${num(data.total)} ${t("projects")}` : ""}</span>
      </div>
      <ErrorBox error={error} />
      <div className="table-wrap">
        <table>
          <thead><tr>
            <th>{t("well_id")}</th><th>{t("plaque")}</th><th>{t("customer_name")}</th><th>{t("well_type")}</th><th>{t("addons")}</th>
            <th>{t("contractor")}</th><th>{t("construction_status")}</th><th>{t("delivery_status")}</th><th>{t("video_status")}</th>
            <th>{t("payment_status")}</th><th>{t("order_date")}</th>
          </tr></thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.id} onClick={() => nav(`/projects/${p.well_id}`)} style={{ cursor: "pointer", background: p.contractor?.color || undefined }}>
                <td className="row-head"><Link to={`/projects/${p.well_id}`} className="well-no">{p.well_id}</Link><OpenIcon no={p.well_id} /> {p.is_sample && <span className="badge">{t("sample")}</span>}</td>
                <td><PlaqueBadge p={p} compact /></td>
                <td className="strong"><span className="phone-wa">{p.customer_name || "—"}{p.customer_phone && <WaPhoneIcon e164={p.customer_phone_e164} status={p.customer_phone_status} />}</span></td><td>{p.well_type || "—"}</td><td><AddonChips value={p.extras} /></td>
                <td>{p.contractor?.name || "—"}</td><td><Status v={p.construction_status} /></td><td><Status v={p.delivery_status} /></td>
                <td><Status v={p.video_status} /></td><td><Status v={p.payment_status} /></td><td className="muted">{fmtDate(p.order_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.items.length && <Empty />}
      </div>
      <div className="pager">
        <button className="sm" disabled={page <= 1} onClick={() => setParams({ ...q, page: String(page - 1) })}>‹</button>
        <span className="muted">{t("page")} {page} {t("of")} {pages}</span>
        <button className="sm" disabled={page >= pages} onClick={() => setParams({ ...q, page: String(page + 1) })}>›</button>
      </div>
      {creating && <Modal title={t("new_project")} onClose={() => setCreating(false)}>
        <ProjectForm prefill={prefill} onCancel={() => setCreating(false)} onSaved={(p) => { setCreating(false); reload(); refreshCounts(); nav(`/projects/${p.well_id}`); }} />
      </Modal>}
    </>
  );
}
