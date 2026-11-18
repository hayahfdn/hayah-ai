import { useState } from "react";
import { api, Contractor, dataChanged } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Field, Modal, useApi } from "../ui";
import { countryLabel } from "../nav";
import { COUNTRY_AR } from "../i18n-ui";

const PALETTE = ["#CFE3FA", "#D3F0D9", "#FFE2C2", "#E6D9F7", "#FAD4DE", "#CDEFEA", "#FFF0B8", "#EBDDCB",
  "#DDEFC2", "#F9D3C9", "#C9DDF0", "#F2D6EC", "#D5E8E0", "#E4E4E4", "#D9D3F5", "#C8EAF5"];

export default function Contractors() {
  const { t, num, lang } = useI18n();
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
        <thead><tr><th>{t("color")}</th><th>{t("code")}</th><th>{t("name")}</th><th>{t("country")}</th><th>{t("phone")}</th><th>{t("active")}</th>
          <th>{t("projects")}</th><th>{t("in_progress")}</th><th>{t("completed")}</th><th>{t("delivered")}</th><th>{t("avg_build_days")}</th><th></th></tr></thead>
        <tbody>{list.data?.map((c) => { const p = byId[c.id] || {}; return (
          <tr key={c.id} style={{ background: c.color || undefined }}><td><span className="swatch lg" style={{ background: c.color || "#fff" }} title={c.color || ""} /></td>
            <td className="row-head"><b>{c.code}</b></td><td className="strong">{c.name}</td><td>{countryLabel(c.country || "", lang) || "—"}</td><td dir="ltr">{c.phone || "—"}</td>
            <td>{c.is_active ? "✓" : "—"}</td><td className="num">{num(p.projects)}</td><td className="num">{num(p.in_progress)}</td>
            <td className="num">{num(p.completed)}</td><td className="num">{num(p.delivered)}</td><td className="num">{p.avg_build_days ?? "—"}</td>
            <td>{can(...MANAGERS) && <button className="sm" onClick={() => setEditing(c)}>{t("edit")}</button>}</td></tr>); })}</tbody>
      </table></div>
      {editing && <ContractorForm c={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); perf.reload(); dataChanged(); }} />}
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
      <Field label={t("country")}><input list="con-countries" value={f.country || ""} onChange={set("country")} />
        <datalist id="con-countries">{Object.keys(COUNTRY_AR).map((c) => <option key={c} value={c}>{COUNTRY_AR[c]}</option>)}</datalist></Field>
      <Field label={t("phone")}><input dir="ltr" value={f.phone || ""} onChange={set("phone")} /></Field>
      <Field label={t("active")}><input type="checkbox" checked={!!f.is_active} onChange={set("is_active")} style={{ minHeight: 0, width: "auto" }} /></Field>
    </div>
    <div style={{ marginTop: 12 }}>
      <Field label={t("color")} hint={t("color_help")}>
        <div className="color-picks">
          {PALETTE.map((p) => <button type="button" key={p} className={(f.color || "").toUpperCase() === p ? "on" : ""} style={{ background: p }}
            aria-label={p} onClick={() => setF({ ...f, color: p })} />)}
          <input type="color" value={f.color || "#ffffff"} onChange={(e) => setF({ ...f, color: e.target.value.toUpperCase() })} aria-label={t("color")} />
        </div>
      </Field>
    </div>
    <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes || ""} onChange={set("notes")} /></Field></div>
    <ErrorBox error={error} /><div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("save")}</button></div>
  </form></Modal>;
}
