import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, toast, useApi } from "../ui";
import ShopifyHistory from "./ShopifyHistory";

/** Settings > Shopify. The super admin pastes the app keys; managers can see orders and run a check. */
export default function ShopifySettings() {
  const { t, fmtDate, num, money } = useI18n();
  const { can } = useAuth();
  const admin = can("super_admin");
  const s = useApi<any>("/api/shopify/settings");
  const orders = useApi<any[]>("/api/shopify/orders");
  const [f, setF] = useState<any>(null);
  const [secret, setSecret] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { if (s.data) setF({ ...s.data }); }, [s.data]);
  if (!f) return <ErrorBox error={s.error} />;
  const d = s.data;
  const run = async (name: string, fn: () => Promise<any>) => {
    setBusy(name);
    try { await fn(); } catch (e: any) { toast(e.message); } finally { setBusy(null); s.reload(); orders.reload(); }
  };
  const save = () => run("save", async () => {
    const body: any = { store_domain: f.store_domain || "", client_id: f.client_id || "", enabled: !!f.enabled, only_paid: !!f.only_paid,
      import_from: f.import_from || null, well_id_start: f.well_id_start ? Number(f.well_id_start) : null,
      sacrifice_no_start: f.sacrifice_no_start ? Number(f.sacrifice_no_start) : null };
    if (secret.trim()) body.client_secret = secret.trim();
    if (token.trim()) body.access_token = token.trim();
    await api("/api/shopify/settings", { method: "PUT", body });
    setSecret(""); setToken(""); toast(t("saved"));
  });
  const test = () => run("test", async () => { const r = await api("/api/shopify/test", { method: "POST" }); toast(`${t("shop_connected")} ${r.shop.name}`); });
  const hooks = () => run("hooks", async () => {
    const r = await api("/api/shopify/register-webhooks", { body: { base_url: window.location.origin } });
    toast(r.errors?.length ? r.errors.join("; ") : t("shop_hooks_on"));
  });
  const sync = (full: boolean) => run("sync", async () => {
    const r = await api("/api/shopify/sync", { method: "POST", query: { full } });
    toast(t("shop_sync_done").replace("{w}", r.created_wells).replace("{s}", r.created_sacrifices) + (r.errors?.length ? ` · ${r.errors.join("; ")}` : ""));
  });
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const check = { minHeight: 0, width: "auto" };
  return <div className="grid">
    <div className="card">
      <div className="banner info">{t("shop_help")}</div>
      <p>{d.configured && d.shop_name ? <span className="badge ok">{t("shop_connected")} {d.shop_name}</span> : <span className="badge warn">{t("shop_not_set")}</span>}
        {" "}{d.webhooks?.active?.length ? <span className="badge ok">{t("shop_hooks_on")}</span> : null}
        <span className="muted"> · {t("shop_last_sync")}: {d.last_sync_at ? fmtDate(d.last_sync_at) : t("never")} · {t("shop_last_hook")}: {d.last_webhook_at ? fmtDate(d.last_webhook_at) : t("never")}</span></p>
      <div className="form-grid">
        <Field label={t("shop_store")} hint={t("shop_store_hint")}><input dir="ltr" disabled={!admin} placeholder="your-store.myshopify.com" value={f.store_domain || ""} onChange={set("store_domain")} /></Field>
        <Field label={t("shop_client_id")}><input dir="ltr" disabled={!admin} autoComplete="off" value={f.client_id || ""} onChange={set("client_id")} /></Field>
        {admin && <Field label={t("shop_client_secret")} tone={d.client_secret?.set ? "ok" : undefined}
          hint={d.client_secret?.set ? `${t("ai_key_saved")} …${d.client_secret.last4}` : t("shop_secret_hint")}>
          <input type="password" dir="ltr" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} /></Field>}
        {admin && <Field label={t("shop_token")} tone={d.access_token?.set ? "ok" : undefined}
          hint={d.access_token?.set ? `${t("ai_key_saved")} …${d.access_token.last4}` : t("shop_token_hint")}>
          <input type="password" dir="ltr" autoComplete="off" placeholder="shpat_…" value={token} onChange={(e) => setToken(e.target.value)} /></Field>}
        <Field label={t("shop_import_from")} hint={t("shop_import_from_hint")}><input type="date" disabled={!admin} value={f.import_from || ""} onChange={set("import_from")} /></Field>
        <Field label={t("shop_well_start")} hint={t("shop_start_hint")}><input type="number" min={1} disabled={!admin} value={f.well_id_start || ""} onChange={set("well_id_start")} /></Field>
        <Field label={t("shop_sac_start")} hint={t("shop_start_hint")}><input type="number" min={1} disabled={!admin} value={f.sacrifice_no_start || ""} onChange={set("sacrifice_no_start")} /></Field>
        <Field label={t("shop_enabled")}><input type="checkbox" disabled={!admin} checked={!!f.enabled} onChange={set("enabled")} style={check} /></Field>
        <Field label={t("shop_only_paid")}><input type="checkbox" disabled={!admin} checked={!!f.only_paid} onChange={set("only_paid")} style={check} /></Field>
      </div>
      <div className="actions">
        {admin && <button className="primary" disabled={!!busy} onClick={save}>{t("shop_save")}</button>}
        {admin && <button disabled={!!busy || !d.configured} onClick={test}>{t("shop_test")}</button>}
        {admin && <button disabled={!!busy || !d.configured} onClick={hooks}>{t("shop_hook")}</button>}
        <button disabled={!!busy || !d.configured} onClick={() => sync(false)}>{busy === "sync" ? t("loading") : t("shop_sync")}</button>
        {admin && <button disabled={!!busy || !d.configured} onClick={() => sync(true)}>{t("shop_sync_all")}</button>}
      </div>
    </div>
    <ShopifyHistory configured={!!d.configured} onDone={() => orders.reload()} />
    <div className="card"><h2>{t("shop_orders")}</h2>
      <ErrorBox error={orders.error} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("shop_order")}</th><th>{t("date")}</th><th>{t("customer_name")}</th><th>{t("amount")}</th><th>{t("shop_result")}</th><th>{t("shop_records")}</th></tr></thead>
        <tbody>{orders.data?.map((o) => <tr key={o.name}>
          <td className="mono">{o.name}</td><td>{fmtDate(o.created_at)}</td><td>{o.customer_name || "—"}</td>
          <td className="num">{o.currency === "USD" || !o.currency ? money(o.total) : `${num(o.total)} ${o.currency}`}</td>
          <td><span className={`badge ${["imported", "already_in_workbook", "matched"].includes(o.status) ? "ok" : ["needs_review", "cancelled", "check", "not_in_workbook"].includes(o.status) ? "warn" : ""}`}>{t("shop_st_" + o.status)}</span></td>
          <td className="wrap">{[...o.well_ids.map((w: number) => `${t("well_id")} ${w}`), ...o.sacrifice_nos.map((n: number) => `${t("sacrifice_no")} ${n}`)].join(", ") || "—"}
            {o.message && o.status !== "imported" && <div className="muted" style={{ fontSize: 12 }}>{o.message}</div>}</td>
        </tr>)}</tbody>
      </table>{orders.data && !orders.data.length && <Empty />}</div>
    </div>
  </div>;
}
