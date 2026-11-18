import { useState } from "react";
import { api, Contractor } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Field, Modal, useApi } from "../ui";

export default function Contractors() {
  const { t, num } = useI18n();
  const { can } = useAuth();
  const list = useApi<Contractor[]>("/api/contractors");
  const perf = useApi<any[]>("/api/contractors/performance");
  const [editing, setEditing] = useState<Contractor | "new" | null>(null);
  const byId = Object.fromEntries((perf.data || []).map((p) => [p.id, p]));
  return (
    <>
      <div className="topbar"><h1>{t("nav_contractors")}</h1>{can(...MANAGERS) && <button className="primary" onClick={() => setEditing("new")}>+ {t("new_contractor")}</button>}</div>
      <ErrorBox error={list.error} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("code")}</th><th>{t("name")}</th><th>{t("country")}</th><th>{t("phone")}</th><th>{t("active")}</th>
          <th>{t("projects")}</th><th>{t("in_progress")}</th><th>{t("completed")}</th><th>{t("delivered")}</th><th>{t("avg_build_days")}</th><th></th></tr></thead>
        <tbody>{list.data?.map((c) => { const p = byId[c.id] || {}; return (
          <tr key={c.id}><td className="mono"><b>{c.code}</b></td><td>{c.name}</td><td>{c.country || "—"}</td><td dir="ltr">{c.phone || "—"}</td>
            <td>{c.is_active ? "✓" : "—"}</td><td className="num">{num(p.projects)}</td><td className="num">{num(p.in_progress)}</td>
            <td className="num">{num(p.completed)}</td><td className="num">{num(p.delivered)}</td><td className="num">{p.avg_build_days ?? "—"}</td>
            <td>{can(...MANAGERS) && <button className="sm" onClick={() => setEditing(c)}>{t("edit")}</button>}</td></tr>); })}</tbody>
      </table></div>
      {editing && <ContractorForm c={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); perf.reload(); }} />}
    </>
  );
}

function ContractorForm({ c, onClose, onSaved }: { c: Contractor | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState<any>(c || { is_active: true });
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value || null });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const { id, code, ...rest } = f;
    try { c ? await api(`/api/contractors/${c.id}`, { method: "PATCH", body: rest }) : await api("/api/contractors", { body: { code, ...rest } }); onSaved(); }
    catch (err: any) { setError(err.message); }
  };
  return <Modal title={c ? `${t("edit")} · ${c.code}` : t("new_contractor")} onClose={onClose}><form onSubmit={submit}>
    <div className="form-grid">
      <Field label={t("code")}><input required disabled={!!c} value={f.code || ""} onChange={set("code")} pattern="[A-Za-z0-9_\-]+" /></Field>
      <Field label={t("name")}><input required value={f.name || ""} onChange={set("name")} /></Field>
      <Field label={t("country")}><input value={f.country || ""} onChange={set("country")} /></Field>
      <Field label={t("phone")}><input dir="ltr" value={f.phone || ""} onChange={set("phone")} /></Field>
      <Field label={t("active")}><input type="checkbox" checked={!!f.is_active} onChange={set("is_active")} style={{ minHeight: 0, width: "auto" }} /></Field>
    </div>
    <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes || ""} onChange={set("notes")} /></Field></div>
    <ErrorBox error={error} /><div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("save")}</button></div>
  </form></Modal>;
}
