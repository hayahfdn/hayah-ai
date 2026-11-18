import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, Modal, Status, toast, useApi } from "../ui";

export default function Maintenance() {
  const { t, st, fmtDate, num } = useI18n();
  const { can, refreshCounts } = useAuth();
  const [well, setWell] = useState("");
  const [status, setStatus] = useState("");
  const { data, error, reload } = useApi<any[]>("/api/maintenance", { well_id: well || undefined, status });
  const [creating, setCreating] = useState(false);
  const canWrite = can("super_admin", "operations_manager", "maintenance");
  const setRec = async (code: string, s: string) => {
    try { await api(`/api/maintenance/${code}`, { method: "PATCH", body: { status: s } }); toast(t("saved")); reload(); refreshCounts(); } catch (e: any) { toast(e.message); }
  };
  return (
    <>
      <div className="topbar"><h1>{t("nav_maintenance")}</h1>{canWrite && <button className="primary" onClick={() => setCreating(true)}>+ {t("new_maintenance")}</button>}</div>
      <div className="toolbar">
        <input type="number" placeholder={t("well_id")} value={well} onChange={(e) => setWell(e.target.value)} style={{ width: 140 }} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">{t("status")}: {t("all")}</option>
          {["open", "in_progress", "resolved"].map((s) => <option key={s} value={s}>{st(s)}</option>)}</select>
      </div>
      <ErrorBox error={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("maintenance_id")}</th><th>{t("well_id")}</th><th>{t("date")}</th><th>{t("country")}</th><th>{t("problem_type")}</th>
          <th>{t("description")}</th><th>{t("technician")}</th><th>{t("repair_cost")}</th><th>{t("status")}</th><th>{t("next_maintenance_date")}</th></tr></thead>
        <tbody>{data?.map((m) => (
          <tr key={m.id}><td className="mono">{m.maintenance_code}</td><td><Link className="mono" to={`/projects/${m.well_id}`}>{m.well_id}</Link></td>
            <td>{fmtDate(m.date)}</td><td>{m.country || "—"}</td><td>{m.problem_type}</td><td className="wrap">{m.description || "—"}</td>
            <td>{m.technician || "—"}</td><td className="num">{num(m.repair_cost)}</td>
            <td>{canWrite ? <select value={m.status} onChange={(e) => setRec(m.maintenance_code, e.target.value)}>
              {["open", "in_progress", "resolved"].map((s) => <option key={s} value={s}>{st(s)}</option>)}</select> : <Status v={m.status} />}</td>
            <td>{fmtDate(m.next_maintenance_date)}</td></tr>))}</tbody>
      </table>{data && !data.length && <Empty />}</div>
      {creating && <NewMaintenance onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload(); refreshCounts(); }} />}
    </>
  );
}

function NewMaintenance({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState<any>({ date: new Date().toISOString().slice(0, 10), status: "open" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: any = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ""));
    body.well_id = Number(body.well_id);
    try { await api("/api/maintenance", { body }); onSaved(); } catch (err: any) { setError(err.message); }
  };
  return <Modal title={t("new_maintenance")} onClose={onClose}><form onSubmit={submit}>
    <div className="form-grid">
      <Field label={t("well_id")}><input type="number" required value={f.well_id || ""} onChange={set("well_id")} /></Field>
      <Field label={t("date")}><input type="date" required value={f.date} onChange={set("date")} /></Field>
      <Field label={t("problem_type")}><input required value={f.problem_type || ""} onChange={set("problem_type")} list="ptypes" />
        <datalist id="ptypes">{["pump_failure", "leak", "low_water", "water_quality", "handle_broken", "solar_panel", "other"].map((x) => <option key={x} value={x} />)}</datalist></Field>
      <Field label={t("location")}><input value={f.location || ""} onChange={set("location")} /></Field>
      <Field label={t("technician")}><input value={f.technician || ""} onChange={set("technician")} /></Field>
      <Field label={t("repair_cost")}><input type="number" min={0} step="0.01" value={f.repair_cost || ""} onChange={set("repair_cost")} /></Field>
      <Field label={t("next_maintenance_date")}><input type="date" value={f.next_maintenance_date || ""} onChange={set("next_maintenance_date")} /></Field>
    </div>
    <div style={{ marginTop: 12 }} className="grid">
      <Field label={t("description")}><textarea value={f.description || ""} onChange={set("description")} /></Field>
      <Field label={t("repair_action")}><textarea value={f.repair_action || ""} onChange={set("repair_action")} /></Field>
    </div>
    <ErrorBox error={error} /><div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("create")}</button></div>
  </form></Modal>;
}
