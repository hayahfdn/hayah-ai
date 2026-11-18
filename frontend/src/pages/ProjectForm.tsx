import { useEffect, useState } from "react";
import { api, Contractor, Project } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { countryName, sortContractors, wellTypeOptions } from "../look";
import { ErrorBox, Field, useApi } from "../ui";

const CONSTRUCTION = ["new_order", "scheduled", "in_progress", "completed", "on_hold", "cancelled"];
const PAYMENT = ["unpaid", "partial", "paid", "refunded"];
const VIDEO = ["none", "raw_received", "processing", "in_review", "completed"];
// Country, city, village, construction start, received, completion and last-updated are no longer
// entered or shown: the data already stored stays in the database, and country follows the contractor.
const CONTRACTOR_FIELDS = new Set(["construction_status", "notes"]);

export default function ProjectForm({ project, defaults, onSaved, onCancel }: {
  project?: Project; defaults?: Partial<Record<string, any>>; onSaved: (p: Project) => void; onCancel: () => void;
}) {
  const { t, st, lang } = useI18n();
  const { can, user } = useAuth();
  const manager = can(...MANAGERS);
  const isContractor = user.role === "contractor";
  const contractors = useApi<Contractor[]>("/api/contractors");
  const [f, setF] = useState<any>(() => project ? { ...project } : {
    construction_status: "new_order", payment_status: "unpaid", video_status: "none", currency: "USD",
    order_date: new Date().toISOString().slice(0, 10),
    ...Object.fromEntries(Object.entries(defaults || {}).filter(([, v]) => v !== undefined && v !== null)),
  });
  const [check, setCheck] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  useEffect(() => {
    if (project || !f.well_id) { setCheck(null); return; }
    const h = setTimeout(() => api(`/api/projects/well-id-check/${f.well_id}`).then(setCheck).catch(() => setCheck(null)), 300);
    return () => clearTimeout(h);
  }, [f.well_id, project]);
  const fields = ["order_date", "customer_name", "customer_phone", "well_type", "sales_source", "contractor_id",
    "sale_amount", ...(manager ? ["cost"] : []), "currency", "payment_status", "payment_method", "extras", "shopify_order",
    "construction_status", "final_video_link", "video_status", "next_maintenance_date", "dedication", "notes"]
    .filter((k) => !isContractor || CONTRACTOR_FIELDS.has(k));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(null);
    const body: any = {};
    for (const k of fields) {
      let v = f[k];
      if (v === "" || v === undefined) v = null;
      if (k === "contractor_id" && v !== null) v = Number(v);
      if ((k === "sale_amount" || k === "cost") && v !== null) v = Number(v).toFixed(2);
      const old = project ? (project as any)[k] : null;
      const same = v === old || (v === null && old === null) || ((k === "sale_amount" || k === "cost") && v !== null && old !== null && Number(v) === Number(old));
      if (project ? !same : v !== null) body[k] = v;
    }
    if (!Object.keys(body).length && project) { onCancel(); return; }
    setBusy(true);
    try {
      const p = project
        ? await api<Project>(`/api/projects/${project.well_id}`, { method: "PATCH", body: { ...body, expected_version: project.version } })
        : await api<Project>("/api/projects", { body: { ...body, well_id: Number(f.well_id) } });
      onSaved(p);
    } catch (err: any) { setError(err.message); } finally { setBusy(false); }
  };
  const date = (k: string) => <Field label={t(k)} key={k}><input type="date" value={f[k] || ""} onChange={set(k)} /></Field>;
  const text = (k: string, extra: any = {}) => <Field label={t(k)} key={k}><input value={f[k] ?? ""} onChange={set(k)} {...extra} /></Field>;
  const sel = (k: string, opts: string[], label = (o: string) => st(o)) => (
    <Field label={t(k)} key={k}><select value={f[k] ?? ""} onChange={set(k)}>{opts.map((o) => <option key={o} value={o}>{label(o)}</option>)}</select></Field>);
  const money = { type: "number", min: 0, step: "0.01", inputMode: "decimal", className: "num" };
  const byCountry = sortContractors(contractors.data || []).reduce<Record<string, Contractor[]>>((a, c) => ((a[c.country || ""] ||= []).push(c), a), {});
  if (isContractor) return (
    <form onSubmit={submit}>
      <div className="form-grid">{sel("construction_status", CONSTRUCTION)}</div>
      <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes ?? ""} onChange={set("notes")} /></Field></div>
      <ErrorBox error={error} />
      <div className="actions"><button type="button" onClick={onCancel}>{t("cancel")}</button><button className="primary" disabled={busy}>{t("save")}</button></div>
    </form>);
  return (
    <form onSubmit={submit}>
      <div className="form-grid">
        {!project && <Field label={t("well_id")} tone={check?.exists ? "bad" : "ok"}
          hint={check ? (check.exists ? t("well_exists") : `${t("well_free")} · ${t("highest_well")}: ${check.highest_existing ?? "—"}`) : undefined}>
          <input type="number" inputMode="numeric" min={1} required value={f.well_id || ""} onChange={set("well_id")} className="wid-input" /></Field>}
        {date("order_date")}{text("customer_name")}{text("customer_phone", { dir: "ltr", inputMode: "tel" })}
        <Field label={t("well_type")}>
          <select value={f.well_type ?? ""} onChange={set("well_type")}>
            <option value="">—</option>
            {wellTypeOptions(project?.well_type).map((w) => <option key={w} value={w}>{w}</option>)}
          </select>
        </Field>
        <Field label={t("contractor")}><select value={f.contractor_id ?? ""} onChange={set("contractor_id")}><option value="">—</option>
          {Object.entries(byCountry).map(([country, list]) => <optgroup key={country} label={countryName(country, lang)}>
            {list.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}</optgroup>)}</select></Field>
        {text("sales_source")}
        {text("sale_amount", money)}{manager && text("cost", money)}{text("currency", { maxLength: 3 })}
        {sel("payment_status", PAYMENT)}{text("payment_method")}{text("extras")}{text("shopify_order", { dir: "ltr" })}
        {sel("construction_status", CONSTRUCTION)}
        {text("final_video_link", { type: "url", dir: "ltr", placeholder: "https://" })}{sel("video_status", VIDEO)}{date("next_maintenance_date")}
      </div>
      <div style={{ marginTop: 12 }}><Field label={t("dedication")}><textarea value={f.dedication ?? ""} onChange={set("dedication")} /></Field></div>
      <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes ?? ""} onChange={set("notes")} /></Field></div>
      <p className="muted" style={{ fontSize: 12.5 }}>{t("delivery_rule")}</p>
      <ErrorBox error={error} />
      <div className="actions"><button type="button" onClick={onCancel}>{t("cancel")}</button>
        <button className="primary" disabled={busy || (!project && check?.exists)}>{project ? t("save") : t("create")}</button></div>
    </form>
  );
}
