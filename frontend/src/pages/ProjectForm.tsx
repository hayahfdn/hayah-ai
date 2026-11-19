import { useEffect, useState } from "react";
import { api, Contractor, Project } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, Field, useApi } from "../ui";
import { PhoneField } from "../PhoneField";

const CONSTRUCTION = ["new_order", "scheduled", "in_progress", "completed", "on_hold", "cancelled"];
const PAYMENT = ["unpaid", "partial", "paid", "refunded"];
const VIDEO = ["none", "raw_received", "processing", "in_review", "completed"];

export default function ProjectForm({ project, onSaved, onCancel }: { project?: Project; onSaved: (p: Project) => void; onCancel: () => void }) {
  const { t, st } = useI18n();
  const contractors = useApi<Contractor[]>("/api/contractors");
  const [f, setF] = useState<any>(() => project ? { ...project } : { construction_status: "new_order", payment_status: "unpaid", video_status: "none", currency: "USD" });
  const [check, setCheck] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  useEffect(() => {
    if (project || !f.well_id) { setCheck(null); return; }
    const h = setTimeout(() => api(`/api/projects/well-id-check/${f.well_id}`).then(setCheck).catch(() => setCheck(null)), 300);
    return () => clearTimeout(h);
  }, [f.well_id, project]);
  // Country, city, village and the build dates are no longer typed here (Hayah, 2026-11-18). Their old
  // values stay in the database; the country follows the contractor and the dates fill in from the status.
  const fields = ["order_date", "customer_name", "customer_phone", "customer_phone_country", "well_type", "sales_source",
    "contractor_id", "sale_amount", "currency", "payment_status", "construction_status",
    "final_video_link", "video_status", "next_maintenance_date", "dedication", "notes"];
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(null);
    const body: any = {};
    for (const k of fields) {
      let v = f[k];
      if (v === "" || v === undefined) v = null;
      if (k === "contractor_id" && v !== null) v = Number(v);
      if (project ? v !== (project as any)[k] && !(v === null && (project as any)[k] === null) : v !== null) body[k] = v;
    }
    if (k_isEmpty(body) && project) { onCancel(); return; }
    try {
      const p = project
        ? await api<Project>(`/api/projects/${project.well_id}`, { method: "PATCH", body: { ...body, expected_version: project.version } })
        : await api<Project>("/api/projects", { body: { ...body, well_id: Number(f.well_id) } });
      onSaved(p);
    } catch (err: any) { setError(err.message); }
  };
  const lists = useApi<Record<string, string[]>>("/api/settings/lists");
  const types: string[] = lists.data?.well_types || ["يدوي", "متوسط", "عميق", "شمسي"];
  // The old electric type stays visible only on the one well that already has it.
  const typeOpts = f.well_type && !types.includes(f.well_type) ? [...types, f.well_type] : types;
  const date = (k: string) => <Field label={t(k)} key={k}><input type="date" value={f[k] || ""} onChange={set(k)} /></Field>;
  const text = (k: string, extra: any = {}) => <Field label={t(k)} key={k}><input value={f[k] ?? ""} onChange={set(k)} {...extra} /></Field>;
  const sel = (k: string, opts: string[], label = (o: string) => st(o)) => (
    <Field label={t(k)} key={k}><select value={f[k] ?? ""} onChange={set(k)}>{opts.map((o) => <option key={o} value={o}>{label(o)}</option>)}</select></Field>);
  return (
    <form onSubmit={submit}>
      <div className="form-grid">
        {!project && <Field label={t("well_id")} tone={check?.exists ? "bad" : "ok"}
          hint={check ? (check.exists ? t("well_exists") : `${t("well_free")} · ${t("highest_well")}: ${check.highest_existing ?? "—"}`) : undefined}>
          <input type="number" min={1} required value={f.well_id || ""} onChange={set("well_id")} className="mono" /></Field>}
        {date("order_date")}{text("customer_name")}
        <PhoneField phone={f.customer_phone ?? ""} country={f.customer_phone_country ?? ""}
          onPhone={(v) => setF({ ...f, customer_phone: v })} onCountry={(v) => setF({ ...f, customer_phone_country: v })} />
        <Field label={t("well_type")}><select value={f.well_type ?? ""} onChange={set("well_type")}><option value="">—</option>
          {typeOpts.map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
        {text("sales_source")}
        <Field label={t("contractor")}><select value={f.contractor_id ?? ""} onChange={set("contractor_id")}><option value="">—</option>
          {(contractors.data || []).map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}</select></Field>
        {text("sale_amount", { type: "number", min: 0, step: "0.01", className: "num" })}{text("currency", { maxLength: 3 })}
        {sel("payment_status", PAYMENT)}{sel("construction_status", CONSTRUCTION)}
        {text("final_video_link", { type: "url", dir: "ltr", placeholder: "https://" })}{sel("video_status", VIDEO)}{date("next_maintenance_date")}
      </div>
      <div style={{ marginTop: 12 }}><Field label={t("dedication")}><textarea value={f.dedication ?? ""} onChange={set("dedication")} /></Field></div>
      <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes ?? ""} onChange={set("notes")} /></Field></div>
      <p className="muted" style={{ fontSize: 12.5 }}>{t("delivery_rule")}</p>
      <ErrorBox error={error} />
      <div className="actions"><button type="button" onClick={onCancel}>{t("cancel")}</button>
        <button className="primary" disabled={!project && check?.exists}>{project ? t("save") : t("create")}</button></div>
    </form>
  );
}

function k_isEmpty(o: object) { return Object.keys(o).length === 0; }
