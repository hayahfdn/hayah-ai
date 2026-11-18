import { useEffect, useState } from "react";
import { api, User } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, Modal, Status, toast, useApi } from "../ui";
import { SyncPill } from "./Dashboard";
import ImportWorkbook from "../admin/ImportWorkbook";

export default function Settings() {
  const { t } = useI18n();
  const { can } = useAuth();
  const admin = can("super_admin");
  const [tab, setTab] = useState("integrations");
  const tabs = ["integrations", "sync_conflicts", "ai_settings", ...(admin ? ["users", "imp_tab"] : []), "jobs", "audit_log"];
  return (
    <>
      <div className="topbar"><h1>{t("nav_settings")}</h1></div>
      <div className="tabs">{tabs.map((k) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t(k)}</button>)}</div>
      {tab === "integrations" && <Integrations />}
      {tab === "sync_conflicts" && <Conflicts />}
      {tab === "ai_settings" && <AISettings admin={admin} />}
      {tab === "users" && <Users />}
      {tab === "imp_tab" && <ImportWorkbook />}
      {tab === "jobs" && <Jobs />}
      {tab === "audit_log" && <Audit />}
    </>
  );
}

function Integrations() {
  const { t } = useI18n();
  const s = useApi<any>("/api/settings");
  const sync = useApi<any>("/api/sync/status");
  const health = useApi<any>("/api/health/full");
  if (!s.data) return <ErrorBox error={s.error} />;
  const i = s.data.integrations;
  const row = (name: string, mode: string, ok: boolean, extra?: string) => (
    <tr key={name}><td><b>{name}</b></td><td>{mode === "mock" || mode === "rules" ? <span className="badge">{mode === "rules" ? "Rules (no AI cost)" : t("mock")}</span> : <span className="badge brand">{mode}</span>}</td>
      <td>{ok ? <span className="badge ok">{t("configured")}</span> : <span className="badge warn">{t("not_configured")}</span>}</td><td className="muted">{extra}</td></tr>);
  return (
    <div className="grid">
      {sync.data && <SyncPill s={sync.data} onSynced={sync.reload} />}
      <div className="table-wrap"><table>
        <thead><tr><th></th><th>{t("backend")}</th><th>{t("status")}</th><th></th></tr></thead>
        <tbody>
          {row("Google Sheets", i.sheets.backend, i.sheets.configured, sync.data?.spreadsheet_url || "")}
          {row("Google Drive", i.drive.backend, true, health.data?.drive?.usage_gb !== undefined ? `${health.data.drive.usage_gb} / ${health.data.drive.limit_gb ?? "?"} GB` : "")}
          {row("WhatsApp Cloud API", i.whatsapp.backend, i.whatsapp.verify_token_set && i.whatsapp.app_secret_set, "Intake number only")}
          {row("Anthropic Claude", i.ai.backend, i.ai.api_key_set, i.ai.model)}
        </tbody>
      </table></div>
      <ListEditor k="well_types" initial={s.data.well_types?.values || []} />
      <ListEditor k="countries" initial={s.data.countries?.values || []} />
    </div>
  );
}

function ListEditor({ k, initial }: { k: string; initial: string[] }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const [v, setV] = useState(initial.join("\n"));
  const save = async () => { try { await api(`/api/settings/lists/${k}`, { method: "PUT", body: v.split("\n") }); toast(t("saved")); } catch (e: any) { toast(e.message); } };
  return <div className="card"><h2>{t(k === "well_types" ? "well_type" : "country")}</h2>
    <textarea value={v} onChange={(e) => setV(e.target.value)} disabled={!can("super_admin")} />
    {can("super_admin") && <div className="actions"><button onClick={save}>{t("save")}</button></div>}</div>;
}

function Conflicts() {
  const { t, fmtDate } = useI18n();
  const { data, error, reload } = useApi<any[]>("/api/sync/conflicts");
  const resolve = async (id: number, keep: string) => {
    try { await api(`/api/sync/conflicts/${id}/resolve`, { body: { keep } }); toast(t("saved")); reload(); } catch (e: any) { toast(e.message); }
  };
  return <><ErrorBox error={error} /><div className="table-wrap"><table>
    <thead><tr><th>{t("well_id")}</th><th>{t("field")}</th><th>{t("status")}</th><th>{t("db_value")}</th><th>{t("sheet_value")}</th><th>{t("date")}</th><th></th></tr></thead>
    <tbody>{data?.map((c) => <tr key={c.id}><td className="mono">{c.row_key}</td><td>{c.field}</td><td><span className="badge warn">{c.kind}</span></td>
      <td className="wrap">{c.db_value || "—"}</td><td className="wrap">{c.sheet_value || "—"}</td><td>{fmtDate(c.detected_at)}</td>
      <td style={{ display: "flex", gap: 6 }}><button className="sm" onClick={() => resolve(c.id, "db")}>{t("keep_db")}</button>
        {c.kind === "manual_edit" && <button className="sm" onClick={() => resolve(c.id, "sheet")}>{t("keep_sheet")}</button>}</td></tr>)}</tbody>
  </table>{data && !data.length && <Empty />}</div></>;
}

function AISettings({ admin }: { admin: boolean }) {
  const { t, num } = useI18n();
  const s = useApi<any>("/api/settings");
  const [f, setF] = useState<any>(null);
  useEffect(() => { if (s.data) setF(s.data.ai); }, [s.data]);
  if (!f) return <ErrorBox error={s.error} />;
  const save = async () => {
    try { await api("/api/settings/ai", { method: "PUT", body: { ...f, monthly_budget_usd: Number(f.monthly_budget_usd), min_confidence: Number(f.min_confidence), manual_approval_over_usd: Number(f.manual_approval_over_usd) } }); toast(t("saved")); }
    catch (e: any) { toast(e.message); }
  };
  return <div className="card">
    <div className="banner info">Claude Pro does not include API credits. Production AI uses the Anthropic API, billed per token, capped by the monthly budget below. When AI is off or the budget is reached, the free rules engine and the AI Review queue keep everything working.</div>
    <div className="form-grid">
      <Field label={t("ai_enabled")}><input type="checkbox" disabled={!admin} checked={!!f.ai_enabled} onChange={(e) => setF({ ...f, ai_enabled: e.target.checked })} style={{ minHeight: 0, width: "auto" }} /></Field>
      <Field label={t("monthly_budget")}><input type="number" min={0} disabled={!admin} value={f.monthly_budget_usd} onChange={(e) => setF({ ...f, monthly_budget_usd: e.target.value })} /></Field>
      <Field label={t("min_confidence")}><input type="number" min={0.5} max={1} step={0.01} disabled={!admin} value={f.min_confidence} onChange={(e) => setF({ ...f, min_confidence: e.target.value })} /></Field>
      <Field label={t("manual_over")}><input type="number" min={0} step={0.01} disabled={!admin} value={f.manual_approval_over_usd} onChange={(e) => setF({ ...f, manual_approval_over_usd: e.target.value })} /></Field>
      <Field label={t("ai_cost_month")}><div className="num" style={{ fontSize: 20, fontWeight: 700 }}>${num(s.data.ai_cost_this_month_usd)}</div></Field>
    </div>
    {admin && <div className="actions"><button className="primary" onClick={save}>{t("save")}</button></div>}
  </div>;
}

function Users() {
  const { t, fmtDate } = useI18n();
  const { data, error, reload } = useApi<User[]>("/api/users");
  const [creating, setCreating] = useState(false);
  const toggle = async (u: User) => { try { await api(`/api/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }); reload(); } catch (e: any) { toast(e.message); } };
  return <><div className="toolbar"><button className="primary" onClick={() => setCreating(true)}>+ {t("new_user")}</button></div>
    <ErrorBox error={error} /><div className="table-wrap"><table>
      <thead><tr><th>{t("name")}</th><th>{t("email")}</th><th>{t("role")}</th><th>{t("phone")}</th><th>{t("active")}</th><th>{t("last_sync")}</th><th></th></tr></thead>
      <tbody>{data?.map((u) => <tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td>{t("role_" + u.role)}</td><td dir="ltr">{u.phone || "—"}</td>
        <td>{u.is_active ? "✓" : "—"}</td><td className="muted">{fmtDate(u.last_login_at)}</td><td><button className="sm" onClick={() => toggle(u)}>{u.is_active ? "Disable" : "Enable"}</button></td></tr>)}</tbody>
    </table></div>{creating && <NewUser onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload(); }} />}</>;
}

function NewUser({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const contractors = useApi<any[]>("/api/contractors");
  const [f, setF] = useState<any>({ role: "viewer", preferred_lang: "ar" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value || null });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try { await api("/api/users", { body: { ...f, contractor_id: f.contractor_id ? Number(f.contractor_id) : null } }); onSaved(); } catch (err: any) { setError(err.message); }
  };
  return <Modal title={t("new_user")} onClose={onClose}><form onSubmit={submit}><div className="form-grid">
    <Field label={t("name")}><input required onChange={set("full_name")} /></Field>
    <Field label={t("email")}><input type="email" required onChange={set("email")} /></Field>
    <Field label={t("password")} hint="10+ chars, uppercase and a digit"><input type="password" required minLength={10} onChange={set("password")} /></Field>
    <Field label={t("role")}><select value={f.role} onChange={set("role")}>{["super_admin", "operations_manager", "contractor", "maintenance", "viewer"].map((r) => <option key={r} value={r}>{t("role_" + r)}</option>)}</select></Field>
    <Field label={t("phone")} hint="WhatsApp number, used to recognise the sender"><input dir="ltr" onChange={set("phone")} /></Field>
    {f.role === "contractor" && <Field label={t("contractor")}><select required onChange={set("contractor_id")}><option value="">—</option>{contractors.data?.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}</select></Field>}
  </div><ErrorBox error={error} /><div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("create")}</button></div></form></Modal>;
}

function Jobs() {
  const { t, fmtDate } = useI18n();
  const { data, reload } = useApi<any[]>("/api/jobs");
  const retry = async (id: number) => { await api(`/api/jobs/${id}/retry`, { method: "POST" }); reload(); };
  return <div className="table-wrap"><table>
    <thead><tr><th>#</th><th>{t("event_type")}</th><th>{t("status")}</th><th>{t("attempts")}</th><th>{t("date")}</th><th>{t("error")}</th><th></th></tr></thead>
    <tbody>{data?.map((j) => <tr key={j.id}><td className="mono">{j.id}</td><td>{j.kind}</td><td><Status v={j.status} /></td><td className="num">{j.attempts}/{j.max_attempts}</td>
      <td>{fmtDate(j.created_at)}</td><td className="wrap mono" style={{ fontSize: 12 }}>{j.last_error?.split("\n")[0]}</td>
      <td>{j.status === "failed" && <button className="sm" onClick={() => retry(j.id)}>{t("retry")}</button>}</td></tr>)}</tbody>
  </table>{data && !data.length && <Empty />}</div>;
}

function Audit() {
  const { t } = useI18n();
  const { data } = useApi<any[]>("/api/audit", { limit: 300 });
  return <div className="table-wrap"><table>
    <thead><tr><th>{t("time")}</th><th>{t("by")}</th><th>{t("action")}</th><th>{t("details")}</th></tr></thead>
    <tbody>{data?.map((a) => <tr key={a.id}><td className="mono">{new Date(a.at).toLocaleString()}</td><td>{a.actor}</td><td>{a.action}</td>
      <td className="wrap mono" style={{ fontSize: 12 }}>{a.entity_type}:{a.entity_id} {a.after ? JSON.stringify(a.after).slice(0, 160) : ""}</td></tr>)}</tbody>
  </table></div>;
}
