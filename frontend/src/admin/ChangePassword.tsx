import { useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, Field, Modal, toast } from "../ui";

export default function ChangePassword({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    if (next !== again) { setErr(t("pw_mismatch")); return; }
    try {
      await api("/api/auth/change-password", { body: { current_password: cur, new_password: next } });
      toast(t("pw_changed")); onClose();
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <Modal title={t("pw_title")} onClose={onClose}>
      <Field label={t("pw_current")}><input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
      <Field label={t("pw_new")}><input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
      <Field label={t("pw_again")}><input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} /></Field>
      <p className="muted">{t("pw_rule")}</p>
      <ErrorBox error={err} />
      <div className="actions"><button onClick={onClose}>{t("cancel")}</button>
        <button className="primary" disabled={!cur || next.length < 10} onClick={save}>{t("save")}</button></div>
    </Modal>
  );
}
