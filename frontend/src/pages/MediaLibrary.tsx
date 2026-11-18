import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, Modal, toast, useApi } from "../ui";

const CATS = ["CONSTRUCTION", "DELIVERY", "FINAL", "MAINTENANCE", "MAINT_BEFORE", "MAINT_AFTER", "OTHER"];

export function MediaTable({ rows }: { rows: any[] }) {
  const { t, fmtDate } = useI18n();
  if (!rows.length) return <Empty />;
  return <div className="table-wrap"><table>
    <thead><tr><th>{t("file")}</th><th>{t("well_id")}</th><th>{t("category")}</th><th>{t("size")}</th><th>{t("sender")}</th><th>{t("date")}</th><th>{t("source")}</th><th></th></tr></thead>
    <tbody>{rows.map((m) => (
      <tr key={m.id}><td className="mono">{m.filename}</td>
        <td>{m.well_id ? <Link className="mono" to={`/projects/${m.well_id}`}>{m.well_id}</Link> : <span className="badge warn">{t("unassigned")}</span>}</td>
        <td>{t("cat_" + m.category)}</td><td className="num">{(m.size_bytes / 1048576).toFixed(2)} MB</td><td>{m.sender || "—"}</td>
        <td>{fmtDate(m.captured_at || m.created_at)}</td><td>{m.source}</td>
        <td>{m.drive_url?.startsWith("https://") ? <a href={m.drive_url} target="_blank" rel="noreferrer">{t("open_link")}</a> : <span className="muted mono" title={m.drive_file_id}>{m.drive_file_id?.slice(0, 18)}</span>}</td></tr>))}</tbody>
  </table></div>;
}

export default function MediaLibrary() {
  const { t } = useI18n();
  const { can } = useAuth();
  const [q, setQ] = useState<any>({});
  const { data, error, reload } = useApi<any[]>("/api/media", q);
  const [uploading, setUploading] = useState(false);
  return (
    <>
      <div className="topbar"><h1>{t("nav_media")}</h1>{can("super_admin", "operations_manager", "contractor", "maintenance") && <button className="primary" onClick={() => setUploading(true)}>+ {t("upload")}</button>}</div>
      <div className="toolbar">
        <input type="search" className="search" placeholder={t("file")} onBlur={(e) => setQ({ ...q, q: e.target.value })} onKeyDown={(e) => e.key === "Enter" && setQ({ ...q, q: (e.target as HTMLInputElement).value })} />
        <input type="number" placeholder={t("well_id")} style={{ width: 130 }} onBlur={(e) => setQ({ ...q, well_id: e.target.value })} />
        <select onChange={(e) => setQ({ ...q, category: e.target.value })}><option value="">{t("category")}: {t("all")}</option>{CATS.map((c) => <option key={c} value={c}>{t("cat_" + c)}</option>)}</select>
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" style={{ minHeight: 0 }} onChange={(e) => setQ({ ...q, unassigned: e.target.checked || undefined })} /> {t("unassigned")}</label>
      </div>
      <ErrorBox error={error} />
      {data && <MediaTable rows={data} />}
      {uploading && <Upload onClose={() => setUploading(false)} onDone={() => { setUploading(false); reload(); }} />}
    </>
  );
}

function Upload({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [well, setWell] = useState("");
  const [cat, setCat] = useState("CONSTRUCTION");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); if (!file) return;
    const form = new FormData(); form.append("file", file); form.append("category", cat); if (well) form.append("well_id", well);
    setBusy(true);
    try { const r = await api("/api/media/upload", { form }); toast(r.filename); onDone(); } catch (err: any) { setError(err.message); } finally { setBusy(false); }
  };
  return <Modal title={t("upload")} onClose={onClose}><form onSubmit={submit}>
    <div className="form-grid">
      <Field label={t("file")}><input type="file" required accept="image/*,video/*,audio/*,application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
      <Field label={t("well_id")} hint={!well ? t("unassigned") : undefined}><input type="number" value={well} onChange={(e) => setWell(e.target.value)} /></Field>
      <Field label={t("category")}><select value={cat} onChange={(e) => setCat(e.target.value)}>{CATS.map((c) => <option key={c} value={c}>{t("cat_" + c)}</option>)}</select></Field>
    </div>
    <ErrorBox error={error} /><div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary" disabled={busy}>{t("upload")}</button></div>
  </form></Modal>;
}
