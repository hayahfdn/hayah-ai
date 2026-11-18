import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, Modal, Status, toast, useApi } from "../ui";

export default function Delivery() {
  const { t, fmtDate } = useI18n();
  const { can, refreshCounts } = useAuth();
  const [filter, setFilter] = useState("pending");
  const { data, error, reload } = useApi<any[]>("/api/delivery", { status: filter });
  const [creating, setCreating] = useState(false);
  const decide = async (id: number, approve: boolean) => {
    const note = approve ? null : window.prompt(t("decision_note")) ;
    try { await api(`/api/delivery/${id}/decision`, { body: { approve, note } }); toast(t("saved")); reload(); refreshCounts(); }
    catch (e: any) { toast(e.message); }
  };
  return (
    <>
      <div className="topbar"><h1>{t("nav_delivery")}</h1>
        {can("super_admin", "operations_manager", "contractor") && <button className="primary" onClick={() => setCreating(true)}>+ {t("new_confirmation")}</button>}</div>
      <div className="banner info">{t("delivery_rule")}</div>
      <div className="tabs">{[["pending", "awaiting_approval"], ["approved", "approved"], ["rejected", "rejected"], ["", "all"]].map(([v, k]) => (
        <button key={k} className={filter === v ? "on" : ""} onClick={() => setFilter(v)}>{t(k)}</button>))}</div>
      <ErrorBox error={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("well_id")}</th><th>{t("delivery_date")}</th><th>{t("status")}</th><th>{t("sender")}</th><th>{t("source")}</th><th>{t("notes")}</th><th></th></tr></thead>
        <tbody>{data?.map((d) => (
          <tr key={d.id}>
            <td><Link className="mono" to={`/projects/${d.well_id}`}><b>{d.well_id}</b></Link></td><td>{fmtDate(d.delivery_date)}</td>
            <td><Status v={d.status} /></td><td>{d.sender_name || d.sender_phone || "—"}</td><td>{d.source}</td>
            <td className="wrap">{d.notes || d.decision_note || "—"}</td>
            <td>{d.status === "pending" && can(...MANAGERS) && <div style={{ display: "flex", gap: 6 }}>
              <button className="sm primary" onClick={() => decide(d.id, true)}>{t("approve")}</button>
              <button className="sm danger" onClick={() => decide(d.id, false)}>{t("reject")}</button></div>}</td>
          </tr>))}</tbody>
      </table>{data && !data.length && <Empty />}</div>
      {creating && <NewDelivery onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload(); refreshCounts(); }} />}
    </>
  );
}

function NewDelivery({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState<any>({ delivery_date: new Date().toISOString().slice(0, 10) });
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try { await api("/api/delivery", { body: { ...f, well_id: Number(f.well_id) } }); onSaved(); } catch (err: any) { setError(err.message); }
  };
  return <Modal title={t("new_confirmation")} onClose={onClose}><form onSubmit={submit}>
    <div className="form-grid">
      <Field label={t("well_id")}><input type="number" required value={f.well_id || ""} onChange={(e) => setF({ ...f, well_id: e.target.value })} /></Field>
      <Field label={t("delivery_date")}><input type="date" required value={f.delivery_date} onChange={(e) => setF({ ...f, delivery_date: e.target.value })} /></Field>
    </div>
    <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes || ""} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field></div>
    <ErrorBox error={error} /><div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("create")}</button></div>
  </form></Modal>;
}
