// Connect the business WhatsApp number (Cloud API, Coexistence). Admins only.
// Keys go to the server, are stored encrypted and are never sent back (only where they are set).
import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, Field, toast, useApi } from "../ui";

export default function WhatsAppSettings() {
  const { t } = useI18n();
  const s = useApi<any>("/api/settings/whatsapp-inbox");
  const [f, setF] = useState({ phone_number_id: "", waba_id: "", display_number: "", access_token: "", app_secret: "", verify_token: "" });
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState<string | null>(null);
  useEffect(() => {
    if (s.data) setF((x) => ({ ...x, phone_number_id: s.data.phone_number_id || "", waba_id: s.data.waba_id || "", display_number: s.data.display_number || "" }));
  }, [s.data]);
  if (!s.data) return <ErrorBox error={s.error} />;
  const d = s.data;
  const save = async () => {
    setBusy(true);
    try {
      // empty secret fields keep what is stored
      await api("/api/settings/whatsapp-inbox", { method: "PUT", body: {
        phone_number_id: f.phone_number_id.trim(), waba_id: f.waba_id.trim() || null, display_number: f.display_number.trim() || null,
        access_token: f.access_token.trim() || null, app_secret: f.app_secret.trim() || null, verify_token: f.verify_token.trim() || null } });
      setF((x) => ({ ...x, access_token: "", app_secret: "", verify_token: "" }));
      toast(t("saved")); s.reload();
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const runTest = async () => {
    setTest(null);
    try { const r = await api<any>("/api/settings/whatsapp-inbox/test", { method: "POST" }); setTest(`✓ ${t("was_ok")}: ${r.phone.display_phone_number || ""} ${r.phone.verified_name || ""}`); }
    catch (e: any) { setTest(e.message); }
  };
  const hint = (x: any) => (x?.where === "server" ? t("was_server") : x?.where === "settings" ? t("was_keep") : undefined);
  const secret = (k: "access_token" | "app_secret" | "verify_token", label: string) => (
    <Field label={label} hint={hint(d[k])} tone={d[k]?.where ? "ok" : undefined}>
      <input type="password" dir="ltr" autoComplete="off" disabled={d[k]?.where === "server"} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </Field>);
  return (
    <div className="card">
      <h2>{t("was_title")} {d.enabled ? <span className="badge ok">{t("was_ok")}</span> : <span className="badge warn">{t("not_configured")}</span>}
        {d.mock && <span className="badge">{t("wa_mock")}</span>}</h2>
      <p className="muted">{t("was_help")}</p>
      <div className="form-grid">
        <Field label={t("was_phone_id")}><input dir="ltr" inputMode="numeric" value={f.phone_number_id} onChange={(e) => setF({ ...f, phone_number_id: e.target.value })} /></Field>
        <Field label={t("was_waba")}><input dir="ltr" inputMode="numeric" value={f.waba_id} onChange={(e) => setF({ ...f, waba_id: e.target.value })} /></Field>
        <Field label={t("was_display")}><input dir="ltr" value={f.display_number} onChange={(e) => setF({ ...f, display_number: e.target.value })} /></Field>
        {secret("access_token", t("was_token"))}
        {secret("app_secret", t("was_secret"))}
        {secret("verify_token", t("was_verify"))}
      </div>
      <div className="actions">
        <button className="primary" disabled={busy || !/^\d+$/.test(f.phone_number_id.trim())} onClick={save}>{t("was_save")}</button>
        <button disabled={!d.enabled} onClick={runTest}>{t("was_test")}</button>
        {test && <span className={test.startsWith("✓") ? "badge ok" : "badge bad"}>{test}</span>}
      </div>
      <div className="dl" style={{ marginTop: 12 }}>
        <div><span>{t("was_webhook")}</span><bdi dir="ltr" className="mono">{window.location.origin}{d.webhook_path}</bdi></div>
        <div><span>Webhook</span>{t("was_fields")}</div>
      </div>
    </div>
  );
}
