// Connect the CURRENT WhatsApp Business app number (Meta Coexistence, Embedded Signup). Super admin only.
// The phone app keeps working; chats sent from the phone show in the inbox too. Nothing is sent to customers.
import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, Field, toast, useApi } from "../ui";

interface St {
  app_id: string | null; config_id: string | null; graph_version: string; onboarded_at: string | null; phone_number_id: string | null;
  contacts_sync_at: string | null; history_sync_at: string | null; history_progress: number | null; sync_deadline: string | null;
  last_error: string | null; app_secret_set: boolean; mock: boolean;
}
declare global { interface Window { FB?: any; fbAsyncInit?: () => void } }

function loadSdk(appId: string, version: string): Promise<any> {
  return new Promise((resolve, reject) => {
    if (window.FB) { window.FB.init({ appId, autoLogAppEvents: true, xfbml: false, version }); return resolve(window.FB); }
    window.fbAsyncInit = () => { window.FB.init({ appId, autoLogAppEvents: true, xfbml: false, version }); resolve(window.FB); };
    const s = document.createElement("script");
    s.src = "https://connect.facebook.net/en_US/sdk.js"; s.async = true; s.crossOrigin = "anonymous";
    s.onerror = () => reject(new Error("Could not load Facebook login"));
    document.body.appendChild(s);
  });
}

export default function WaCoexistence() {
  const { t } = useI18n();
  const s = useApi<St>("/api/settings/whatsapp-coexistence");
  const [ids, setIds] = useState({ app_id: "", config_id: "" });
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (s.data) setIds({ app_id: s.data.app_id || "", config_id: s.data.config_id || "" }); }, [s.data]);
  if (!s.data) return <ErrorBox error={s.error} />;
  const d = s.data;

  const saveIds = async () => {
    setBusy(true);
    try { await api("/api/settings/whatsapp-coexistence", { method: "PUT", body: ids }); toast(t("saved")); s.reload(); }
    catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const connect = async () => {
    setBusy(true);
    let session: { phone_number_id?: string; waba_id?: string } = {};
    const onMsg = (ev: MessageEvent) => {
      if (!/facebook\.com$/.test(new URL(ev.origin).hostname)) return;
      try {
        const data = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data;
        if (data?.type === "WA_EMBEDDED_SIGNUP" && data.data) session = { ...session, ...data.data };
      } catch { /* other messages */ }
    };
    window.addEventListener("message", onMsg);
    try {
      const FB = await loadSdk(d.app_id!, d.graph_version);
      const code: string | null = await new Promise((resolve) => FB.login((r: any) => resolve(r?.authResponse?.code || null), {
        config_id: d.config_id, response_type: "code", override_default_response_type: true,
        extras: { setup: {}, featureType: "whatsapp_business_app_onboarding", sessionInfoVersion: "3" },
      }));
      await new Promise((r) => setTimeout(r, 800));  // the session message can arrive just after the login callback
      if (!code || !session.phone_number_id || !session.waba_id) throw new Error(t("coex_cancelled"));
      await api("/api/settings/whatsapp-coexistence/finish", { body: { code, phone_number_id: session.phone_number_id, waba_id: session.waba_id } });
      toast(t("coex_done")); s.reload();
    } catch (e: any) { toast(e.message); } finally { window.removeEventListener("message", onMsg); setBusy(false); }
  };
  const retry = async () => {
    setBusy(true);
    try { await api("/api/settings/whatsapp-coexistence/sync", { body: {} }); s.reload(); }
    catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const when = (x: string | null) => (x ? new Date(x).toLocaleString() : "—");

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h2 style={{ marginTop: 0 }}>{t("coex_title")} {d.onboarded_at ? <span className="badge ok">{t("coex_connected")}</span> : null}</h2>
      <p className="muted">{t("coex_intro")}</p>
      <ul className="muted" style={{ fontSize: 13.5 }}>
        <li>{t("coex_i1")}</li><li>{t("coex_i2")}</li><li>{t("coex_i3")}</li><li>{t("coex_i4")}</li><li>{t("coex_i5")}</li>
      </ul>
      <div className="form-grid">
        <Field label={t("coex_app_id")}><input dir="ltr" inputMode="numeric" value={ids.app_id} onChange={(e) => setIds({ ...ids, app_id: e.target.value })} /></Field>
        <Field label={t("coex_config_id")}><input dir="ltr" inputMode="numeric" value={ids.config_id} onChange={(e) => setIds({ ...ids, config_id: e.target.value })} /></Field>
      </div>
      <div className="actions">
        <button disabled={busy || !/^\d{5,}$/.test(ids.app_id) || !/^\d{5,}$/.test(ids.config_id)} onClick={saveIds}>{t("save")}</button>
      </div>
      {!d.app_secret_set && !d.mock && <div className="banner">{t("coex_need_secret")}</div>}
      {d.app_id && d.config_id && <>
        <label style={{ display: "flex", gap: 8, alignItems: "flex-start", margin: "12px 0" }}>
          <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />{t("coex_agree")}
        </label>
        <button className="primary" disabled={busy || !agree || (!d.app_secret_set && !d.mock)} onClick={connect}>{t("coex_button")}</button>
      </>}
      {d.onboarded_at && <div className="dl" style={{ marginTop: 12 }}>
        <div><span>{t("coex_connected")}</span>{when(d.onboarded_at)} · {d.phone_number_id}</div>
        <div><span>{t("coex_contacts")}</span>{when(d.contacts_sync_at)}</div>
        <div><span>{t("coex_history")}</span>{when(d.history_sync_at)}{d.history_progress != null ? ` · ${d.history_progress}%` : ""}</div>
        {d.sync_deadline && <div><span>{t("coex_deadline")}</span>{when(d.sync_deadline)}</div>}
      </div>}
      {d.last_error && <div className="banner">{d.last_error} <button className="sm" disabled={busy} onClick={retry}>{t("coex_retry")}</button></div>}
    </div>
  );
}
