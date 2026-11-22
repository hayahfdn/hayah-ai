import { useEffect, useState } from "react";
import { api, User } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, Modal, Status, toast, useApi } from "../ui";
import { SyncPill } from "./Dashboard";
import RecentChanges from "../admin/RecentChanges";
import ImportWorkbook from "../admin/ImportWorkbook";
import ShopifySettings from "../admin/ShopifySettings";
import WhatsAppSettings from "../admin/WhatsAppSettings";
import SalesSources from "../admin/SalesSources";
import RenumberSacrifices from "../admin/RenumberSacrifices";
import OldDelivered from "../admin/OldDelivered";
import WiseSettings from "../admin/WiseSettings";

export default function Settings() {
  const { t } = useI18n();
  const { can } = useAuth();
  const admin = can("super_admin");
  const [tab, setTab] = useState(() => (window.location.hash === "#contract" ? "ct_settings" : "integrations"));
  const manager = can("super_admin", "operations_manager");
  const tabs = ["integrations", "shopify_tab", ...(manager ? ["ct_settings", "src_tab", "ren_tab", "wise_tab", "od_tab"] : []), "sync_conflicts", "ai_settings", "undo_tab", ...(admin ? ["was_tab", "users", "imp_tab"] : []), "jobs", "audit_log"];
  return (
    <>
      <div className="topbar"><h1>{t("nav_settings")}</h1></div>
      <div className="tabs">{tabs.map((k) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t(k)}</button>)}</div>
      {tab === "integrations" && <Integrations />}
      {tab === "shopify_tab" && <ShopifySettings />}
      {tab === "was_tab" && <WhatsAppSettings />}
      {tab === "src_tab" && <SalesSources />}
      {tab === "ren_tab" && <RenumberSacrifices />}
      {tab === "od_tab" && <OldDelivered />}
      {tab === "wise_tab" && <WiseSettings />}
      {tab === "ct_settings" && <ContractSettings />}
      {tab === "sync_conflicts" && <Conflicts />}
      {tab === "ai_settings" && <AISettings admin={admin} />}
      {tab === "users" && <Users />}
      {tab === "imp_tab" && <ImportWorkbook />}
      {tab === "undo_tab" && <RecentChanges />}
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
      <WellTypes />
      <ListEditor k="countries" initial={s.data.countries?.values || []} />
    </div>
  );
}

/** The four well types: counts, anything left to unify, and the reversible unification runs. */
function WellTypes() {
  const { t, num, fmtDate } = useI18n();
  const { can } = useAuth();
  const admin = can("super_admin");
  const w = useApi<{ types: string[]; legacy: string; counts: { value: string | null; count: number }[];
    pending: { from: string; to: string; count: number }[]; unknown: { value: string; count: number }[];
    runs: { id: number; at: string; by: string; count: number; undone: boolean }[] }>("/api/admin/well-types");
  const [ask, setAsk] = useState<null | { text: string; go: () => Promise<void> }>(null);
  if (!w.data) return <ErrorBox error={w.error} />;
  const d = w.data;
  const act = (text: string, path: string) => setAsk({ text, go: async () => {
    try { const r = await api(path, { method: "POST" }); toast(`${t("saved")} (${r.changed ?? r.restored ?? 0})`); w.reload(); }
    catch (e: any) { toast(e.message); }
  } });
  return <div className="card">
    <h2>{t("wt_title")}</h2>
    <p className="muted" style={{ marginTop: -6 }}>{t("wt_help")}</p>
    <div className="chips" style={{ marginBottom: 10 }}>
      {d.types.map((x) => <span key={x} className="chip strong">{x}</span>)}
      <span className="chip muted">{d.legacy} · {t("wt_legacy")}</span>
    </div>
    <h3>{t("wt_now")}</h3>
    <div className="chips">{d.counts.map((c) => <span key={c.value ?? "-"} className="chip">{c.value ?? "—"}: <b>{num(c.count)}</b></span>)}</div>
    <h3 style={{ marginTop: 14 }}>{t("wt_pending")}</h3>
    {d.pending.length ? <>
      <div className="table-wrap"><table><thead><tr><th>{t("well_type")}</th><th>→</th><th>{t("count")}</th></tr></thead>
        <tbody>{d.pending.map((p) => <tr key={p.from}><td>{p.from}</td><td><b>{p.to}</b></td><td className="num">{num(p.count)}</td></tr>)}</tbody></table></div>
      {admin && <div className="actions"><button className="primary" onClick={() => act(t("wt_confirm"), "/api/admin/well-types/normalize")}>{t("wt_apply")}</button></div>}
    </> : <p className="muted">{t("wt_none_pending")}</p>}
    {d.unknown.length > 0 && <><h3 style={{ marginTop: 14 }}>{t("wt_unknown")}</h3>
      <div className="chips">{d.unknown.map((u) => <span key={u.value} className="chip warn-t">{u.value}: {num(u.count)}</span>)}</div></>}
    {d.runs.length > 0 && <><h3 style={{ marginTop: 14 }}>{t("wt_runs")}</h3>
      <ul className="timeline">{d.runs.map((r) => <li key={r.id}><span className="muted">{fmtDate(r.at)}</span>
        <span>{r.by} · {num(r.count)} {t("wells")} {r.undone ? <span className="badge">{t("wt_undone")}</span>
          : admin && <button className="sm" onClick={() => act(t("wt_undo_confirm"), `/api/admin/well-types/undo/${r.id}`)}>↶ {t("wt_undo")}</button>}</span></li>)}</ul></>}
    {ask && <Modal title={t("wt_title")} onClose={() => setAsk(null)}>
      <p>{ask.text}</p>
      <div className="actions"><button onClick={() => setAsk(null)}>{t("cancel")}</button>
        <button className="primary" onClick={async () => { const a = ask; setAsk(null); await a.go(); }}>{t("save")}</button></div>
    </Modal>}
  </div>;
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
  const { t, money } = useI18n();
  const s = useApi<any>("/api/settings");
  const [f, setF] = useState<any>(null);
  const [key, setKey] = useState("");
  useEffect(() => { if (s.data) setF(s.data.ai); }, [s.data]);
  const saveKey = async (value: string) => {
    try { await api("/api/settings/ai-key", { method: "PUT", body: { api_key: value } }); setKey(""); toast(t("saved")); s.reload(); }
    catch (e: any) { toast(e.message); }
  };
  const hint = s.data?.integrations?.ai?.api_key;
  if (!f) return <ErrorBox error={s.error} />;
  const save = async () => {
    try { await api("/api/settings/ai", { method: "PUT", body: { ...f, monthly_budget_usd: Number(f.monthly_budget_usd), min_confidence: Number(f.min_confidence), manual_approval_over_usd: Number(f.manual_approval_over_usd) } }); toast(t("saved")); }
    catch (e: any) { toast(e.message); }
  };
  return <div className="card">
    <div className="banner info">Claude Pro does not include API credits. Production AI uses the Anthropic API, billed per token, capped by the monthly budget below (never more than $20 a month). When AI is off or the budget is reached, the free rules engine and the AI Review queue keep everything working.</div>
    {admin && <div className="form-grid" style={{ marginBottom: 12 }}>
      <Field label={t("ai_key")} hint={hint?.set ? t("ai_key_saved") + " …" + hint.last4 : t("ai_key_help")} tone={hint?.set ? "ok" : undefined}>
        <input type="password" dir="ltr" autoComplete="off" placeholder="sk-ant-…" value={key} onChange={(e) => setKey(e.target.value)} />
      </Field>
      <div className="actions" style={{ alignSelf: "end" }}>
        <button className="primary" disabled={!key.trim()} onClick={() => saveKey(key)}>{t("ai_key_save")}</button>
        {hint?.where === "settings" && <button onClick={() => saveKey("")}>{t("ai_key_remove")}</button>}
      </div>
    </div>}
    <div className="form-grid">
      <Field label={t("ai_enabled")}><input type="checkbox" disabled={!admin} checked={!!f.ai_enabled} onChange={(e) => setF({ ...f, ai_enabled: e.target.checked })} style={{ minHeight: 0, width: "auto" }} /></Field>
      <Field label={t("monthly_budget")}><input type="number" min={0} max={20} disabled={!admin} value={f.monthly_budget_usd} onChange={(e) => setF({ ...f, monthly_budget_usd: e.target.value })} /></Field>
      <Field label={t("min_confidence")}><input type="number" min={0.5} max={1} step={0.01} disabled={!admin} value={f.min_confidence} onChange={(e) => setF({ ...f, min_confidence: e.target.value })} /></Field>
      <Field label={t("manual_over")}><input type="number" min={0} step={0.01} disabled={!admin} value={f.manual_approval_over_usd} onChange={(e) => setF({ ...f, manual_approval_over_usd: e.target.value })} /></Field>
      <Field label={t("ai_cost_month")}><div className="num" style={{ fontSize: 20, fontWeight: 700 }}>{money(s.data.ai_cost_this_month_usd)}</div></Field>
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
    <TeamOwners />
    <ErrorBox error={error} /><div className="table-wrap"><table>
      <thead><tr><th>{t("name")}</th><th>{t("email")}</th><th>{t("role")}</th><th>{t("phone")}</th><th>{t("active")}</th><th>{t("last_sync")}</th><th></th></tr></thead>
      <tbody>{data?.map((u) => <tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td>{t("role_" + u.role)}</td>
        <td dir="ltr">{u.phone || "—"}</td>
        <td>{u.is_active ? "✓" : "—"}</td><td className="muted">{fmtDate(u.last_login_at)}</td><td><button className="sm" onClick={() => toggle(u)}>{u.is_active ? "Disable" : "Enable"}</button></td></tr>)}</tbody>
    </table></div>{creating && <NewUser onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload(); }} />}</>;
}

/** One responsible person for each stage of the order workflow, and the date the task lists start from. */
function TeamOwners() {
  const { t } = useI18n();
  const [d, setD] = useState<any>(null);
  useEffect(() => { api<any>("/api/team/tasks", { query: { view: "mine" } }).then(setD).catch(() => {}); }, []);
  const save = (body: any) => api<any>("/api/team/settings", { method: "PUT", body }).then((r) => { setD((x: any) => ({ ...x, ...r })); toast(t("saved")); }).catch((e) => toast(e.message));
  if (!d) return null;
  return <div className="card tk-owners" style={{ marginBottom: 14 }}>
    <h3 style={{ marginTop: 0 }}>{t("tk_owners")}</h3>
    <p className="muted" style={{ marginTop: 0 }}>{t("tk_owners_help")}</p>
    <div className="tk-owners-grid">{d.stages.map((s: any, i: number) => <label key={s.key} className="tk-owner-row" data-stage={s.key}>
      <span className="tk-stage-no sm">{i + 1}</span><b>{s.label}</b>
      {s.kind === "system" ? <span className="muted">{t("tk_system")}</span>
        : <select value={s.owner?.id ?? ""} onChange={(e) => save({ owners: { [s.key]: e.target.value ? Number(e.target.value) : null } })}>
          <option value="">{s.kind === "manager" ? t("tk_manager") : t("tk_unassigned")}</option>
          {d.people.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>}
      {s.kind === "person" && <select className="tk-helper" title={t("tk_helper_help")} value={s.helpers?.[0]?.id ?? ""}
        onChange={(e) => save({ helpers: { [s.key]: e.target.value ? [Number(e.target.value)] : [] } })}>
        <option value="">{t("tk_no_helper")}</option>
        {d.people.filter((p: any) => p.id !== s.owner?.id).map((p: any) => <option key={p.id} value={p.id}>{t("tk_with")} {p.name}</option>)}</select>}
    </label>)}</div>
    <label className="tk-inline" title={t("tk_start_help")} style={{ marginTop: 10 }}>{t("tk_start")} <input type="date" defaultValue={d.settings.start_date} onChange={(e) => e.target.value && save({ start_date: e.target.value })} /></label>
  </div>;
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
    <Field label={t("role")}><select value={f.role} onChange={set("role")}>{["super_admin", "operations_manager", "staff", "contractor", "maintenance", "viewer"].map((r) => <option key={r} value={r}>{t("role_" + r)}</option>)}</select></Field>
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

/** «صيغة عقد» settings (managers): HAYAH's phone on every contract
 *  and the invoice number prefix. The expected delivery date is typed on each contract. */
function ContractSettings() {
  const { t } = useI18n();
  const [v, setV] = useState<{ hayah_phone: string; invoice_prefix: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<any>("/api/contracts/settings").then(setV).catch((e) => toast(e.message)); }, []);
  if (!v) return <p className="muted">{t("loading")}</p>;
  const save = async () => {
    setBusy(true);
    try { setV(await api<any>("/api/contracts/settings", { method: "PUT", body: v })); toast(t("saved")); }
    catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  return <div className="card" id="contract">
    <h2>📄 {t("ct_title")}</h2>
    <p className="muted">{t("ct_settings_help")}</p>
    <div className="form-grid">
      <Field label={t("ct_f_phone")}><input dir="ltr" value={v.hayah_phone} placeholder="+962 …" onChange={(e) => setV({ ...v, hayah_phone: e.target.value })} /></Field>
      <Field label={t("ct_prefix")}><input dir="ltr" value={v.invoice_prefix} maxLength={8} onChange={(e) => setV({ ...v, invoice_prefix: e.target.value.replace(/[^A-Za-z0-9]/g, "") })} /></Field>
    </div>
    <p className="muted" style={{ fontSize: 13 }}>{t("ct_prefix_help")} <b dir="ltr">{(v.invoice_prefix || "HF")}-{new Date().getFullYear()}-0001</b></p>
    <div className="actions"><button className="primary" disabled={busy} onClick={save}>{t("save")}</button></div>
  </div>;
}
