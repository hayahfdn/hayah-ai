// Final delivery videos: the section on each order (wells and sacrifices) and the list page.
import OpenIcon from "../OpenIcon";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, getToken } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { Empty, ErrorBox, Field, Modal, toast } from "../ui";
import { WaChatButton } from "../plaque/flow";
import { CertificateSendInline } from "../certificate/Certificate";

type VState = "not_uploaded" | "uploaded" | "ready_for_delivery" | "sent_to_customer";
interface Version { media_id: number; filename: string; original_filename: string | null; mime_type: string; size_bytes: number; created_at: string; uploaded_by: string | null; current: boolean; }
interface VideoData {
  kind: "well" | "sacrifice"; number: number; status: VState; current_media_id: number | null;
  uploaded_at: string | null; uploaded_by: string | null; ready_at: string | null; ready_by: string | null;
  sent_at: string | null; sent_by: string | null; sent_note: string | null; customer_name: string | null;
  customer_phone_e164: string | null; customer_phone_status?: string | null; final_video_link: string | null; versions: Version[];
}
const TONE: Record<VState, string> = { not_uploaded: "bad", uploaded: "warn", ready_for_delivery: "info", sent_to_customer: "ok" };
const mb = (n: number) => `${(n / 1024 / 1024).toFixed(n > 100 * 1024 * 1024 ? 0 : 1)} MB`;

export function VideoBadge({ s }: { s: VState }) {
  const { t } = useI18n();
  return <span className={`badge ${TONE[s]}`}>{t("vid_st_" + s)}</span>;
}

/** A signed, short-lived link for one file (the player cannot send the login header). */
async function link(mediaId: number) {
  return api<{ url: string; download_url: string }>(`/api/videos/file/${mediaId}/link`);
}

function upload(kind: string, no: number, f: File, onProgress: (p: number) => void): Promise<VideoData> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", `/api/videos/order/${kind}/${no}`);
    x.setRequestHeader("Authorization", `Bearer ${getToken()}`);
    x.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    x.onload = () => {
      let j: any = null;
      try { j = JSON.parse(x.responseText); } catch { /* ignore */ }
      if (x.status >= 200 && x.status < 300) resolve(j);
      else reject(new Error((j && typeof j.detail === "string" && j.detail) || x.statusText || "Upload failed"));
    };
    x.onerror = () => reject(new Error("Network error"));
    const form = new FormData();
    form.append("file", f);
    x.send(form);
  });
}

/** «الفيديو النهائي للمشروع»: upload, play, download, share, replace, states. */
export function FinalVideoSection({ kind, no }: { kind: "well" | "sacrifice"; no: number }) {
  const { t, fmtDate } = useI18n();
  const { refreshCounts } = useAuth();
  const [d, setD] = useState<VideoData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [src, setSrc] = useState<{ url: string; download_url: string } | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [note, setNote] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const load = () => api<VideoData>(`/api/videos/order/${kind}/${no}`).then(setD).catch((e) => setError(e.message));
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [kind, no]);
  useEffect(() => {
    setSrc(null);
    if (d?.current_media_id) link(d.current_media_id).then(setSrc).catch(() => setSrc(null));
  }, [d?.current_media_id]);

  const pick = async (f: File | undefined) => {
    if (!f) return;
    setError(null); setProgress(0);
    try { setD(await upload(kind, no, f, setProgress)); toast(t("vid_st_uploaded")); refreshCounts(); }
    catch (e: any) { setError(e.message); }
    finally { setProgress(null); if (input.current) input.current.value = ""; }
  };
  const move = async (to: VState, n?: string) => {
    setBusy(true); setError(null);
    try { setD(await api<VideoData>(`/api/videos/order/${kind}/${no}/status`, { body: { to, note: n || null } })); refreshCounts(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const cur = d?.versions.find((v) => v.current);
  const fileName = cur ? `${kind === "well" ? "well" : "sacrifice"}-${no}-final${cur.filename.slice(cur.filename.lastIndexOf("."))}` : "";
  // On a phone the video itself goes to WhatsApp through the share sheet; elsewhere it downloads.
  const share = async () => {
    if (!src || !cur) return;
    const text = `${t("vid_share_text")} ${no}`;
    try {
      const nav: any = navigator;
      if (nav.canShare) {
        toast(t("vid_big"));
        const blob = await (await fetch(src.url)).blob();
        const file = new File([blob], fileName, { type: cur.mime_type });
        if (nav.canShare({ files: [file] })) { await nav.share({ files: [file], text }); return; }
      }
    } catch (e: any) { if (e?.name === "AbortError") return; }
    window.location.href = src.download_url;
  };
  if (!d) return <div className="card"><h2>{t("vid_title")}</h2><ErrorBox error={error} />{!error && <p className="muted">…</p>}</div>;
  return (
    <div className={`card final-video${d.status === "not_uploaded" ? "" : " has"}`}>
      <div className="plaque-card-head"><h2 style={{ margin: 0 }}>🎬 {t("vid_title")}</h2><VideoBadge s={d.status} /></div>
      <ErrorBox error={error} />
      {src && cur ? <video className="fv-player" controls preload="metadata" playsInline src={src.url} key={src.url} />
        : <p className="muted">{t("vid_none")}{d.final_video_link && <> · {t("vid_link_old")}: <a href={d.final_video_link} target="_blank" rel="noreferrer" dir="ltr">{d.final_video_link}</a></>}</p>}
      {cur && <p className="muted" style={{ fontSize: 13, margin: "6px 0" }}>
        {t("vid_uploaded_by")}: <b>{d.uploaded_by || cur.uploaded_by || "—"}</b> · {t("vid_on")} {fmtDate(d.uploaded_at || cur.created_at)} {new Date(d.uploaded_at || cur.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {mb(cur.size_bytes)}
        {d.sent_at && <> · {t("vid_st_sent_to_customer")} {fmtDate(d.sent_at)} ({d.sent_by}){d.sent_note ? ` · ${d.sent_note}` : ""}</>}
      </p>}
      {progress !== null && <div className="progress" aria-label={t("vid_uploading")}><div style={{ width: `${progress}%` }} /><span>{t("vid_uploading")} {progress}%</span></div>}
      <div className="actions" style={{ flexWrap: "wrap" }}>
        <input ref={input} type="file" accept="video/mp4,video/quicktime,.mp4,.mov" hidden onChange={(e) => pick(e.target.files?.[0])} />
        <button className={cur ? "" : "primary"} disabled={progress !== null} onClick={() => input.current?.click()}>⬆ {cur ? t("vid_replace") : t("vid_upload")}</button>
        <WaChatButton e164={d.customer_phone_e164} status={d.customer_phone_status} text={cur ? `${t("vid_share_text")} ${no}` : undefined} label />
        {kind === "well" && <CertificateSendInline no={no} key={`${d.current_media_id}-${d.status}`} />}
        {src && <a className="btn" href={src.download_url}>⬇ {t("vid_download")}</a>}
        {src && <button onClick={share}>↗ {t("vid_share")}</button>}
        {d.status === "uploaded" && <button className="primary" disabled={busy} onClick={() => move("ready_for_delivery")}>✓ {t("vid_ready")}</button>}
        {d.status === "ready_for_delivery" && <>
          <button className="primary" disabled={busy} onClick={() => setSending(true)}>✓ {t("vid_sent")}</button>
          <button disabled={busy} onClick={() => move("uploaded")}>{t("vid_back")}</button></>}
        {d.status === "sent_to_customer" && <button disabled={busy} onClick={() => move("ready_for_delivery")}>{t("vid_unsend")}</button>}
      </div>
      <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>{t("vid_help")}</p>
      {d.versions.length > 1 && <details style={{ marginTop: 8 }}><summary>{t("vid_versions")} ({d.versions.length})</summary>
        <ul className="timeline">{d.versions.map((v, i) => (
          <li key={v.media_id}><span className="muted">{fmtDate(v.created_at)}</span>
            <span><b>v{d.versions.length - i}</b> <bdi className="mono" dir="ltr">{v.filename}</bdi> · {mb(v.size_bytes)} · {v.uploaded_by || "—"}
              {v.current && <span className="badge ok"> {t("vid_current")}</span>}
              {!v.current && <button className="sm" onClick={async () => { const l = await link(v.media_id); window.location.href = l.download_url; }}>⬇</button>}</span></li>))}
        </ul></details>}
      {sending && <Modal title={t("vid_sent")} onClose={() => setSending(false)}>
        <Field label={t("vid_sent_note")}><input dir="auto" value={note} onChange={(e) => setNote(e.target.value)} autoFocus /></Field>
        <div className="actions"><button onClick={() => setSending(false)}>{t("cancel")}</button>
          <button className="primary" onClick={() => { setSending(false); move("sent_to_customer", note); setNote(""); }}>✓ {t("vid_sent")}</button></div>
      </Modal>}
    </div>
  );
}

/** One order's final video, for sacrifices (wells also show it on their order page). */
export function FinalVideoPage() {
  const { kind, no } = useParams();
  const { t } = useI18n();
  if (kind !== "well" && kind !== "sacrifice") return <Empty />;
  return <>
    <div className="topbar"><div><Link to="/videos" className="muted">‹ {t("nav_videos")}</Link>
      <h1>{kind === "well" ? t("pla_well") : t("pla_sac")} · <span className="mono">{no}</span></h1></div>
      {kind === "well" && <Link className="btn" to={`/projects/${no}`}>{t("vid_open")} {no}</Link>}</div>
    <FinalVideoSection kind={kind} no={Number(no)} />
  </>;
}

type Tab = "waiting" | "uploaded" | "ready_for_delivery" | "sent_to_customer";
export default function FinalVideos() {
  const { t, fmtDate } = useI18n();
  const { ops } = useAuth();
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>("ready_for_delivery");
  const [rows, setRows] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<"well" | "sacrifice">("well");
  const [no, setNo] = useState("");
  const v = ops.videos || {};
  useEffect(() => {
    setRows(null);
    api<any[]>("/api/videos", { query: { status: tab } }).then(setRows).catch((e) => setError(e.message));
  }, [tab, v.ready_for_delivery, v.uploaded, v.waiting_upload, v.sent_to_customer]);
  const tabs: [Tab, string, number | undefined][] = [["waiting", "vid_tab_waiting", v.waiting_upload], ["uploaded", "vid_tab_uploaded", v.uploaded],
    ["ready_for_delivery", "vid_tab_ready", v.ready_for_delivery], ["sent_to_customer", "vid_tab_sent", undefined]];
  return <>
    <div className="topbar">
      <div><h1>{t("nav_videos")}</h1><p className="muted" style={{ margin: 0 }}>{t("vid_list_help")}</p></div>
      <form className="toolbar" style={{ margin: 0 }} onSubmit={(e) => { e.preventDefault(); if (no.trim()) nav(`/videos/${kind}/${no.trim()}`); }}>
        <select value={kind} onChange={(e) => setKind(e.target.value as any)} aria-label={t("vid_open_order")}>
          <option value="well">{t("pla_well")}</option><option value="sacrifice">{t("pla_sac")}</option></select>
        <input type="number" placeholder={t("vid_open_order")} value={no} onChange={(e) => setNo(e.target.value)} style={{ width: 130 }} />
        <button>{t("vid_open")}</button>
      </form>
    </div>
    <div className="tabs">{tabs.map(([k, label, n]) => (
      <button type="button" key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t(label)}{n ? ` (${n})` : ""}</button>))}</div>
    <ErrorBox error={error} />
    {rows === null ? <p className="muted">…</p> : !rows.length ? <Empty /> : (
      <div className="table-wrap"><table>
        <thead><tr><th>{t("pla_well")} / {t("pla_sac")}</th><th>{t("customer_name")}</th><th>{t("pla_status")}</th><th>{t("vid_uploaded_by")}</th><th></th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.kind + r.number}>
            <td><b className="mono">{r.kind === "sacrifice" ? "S" : ""}{r.number}</b><OpenIcon kind={r.kind} no={r.number} /> <span className="muted">{r.kind === "well" ? t("pla_well") : t("pla_sac")}</span></td>
            <td>{r.customer_name || "—"}</td>
            <td><VideoBadge s={r.status} /></td>
            <td>{r.uploaded_by ? `${r.uploaded_by} · ${fmtDate(r.uploaded_at)}` : "—"}</td>
            <td><span className="row-actions"><Link className="btn sm" to={r.kind === "well" ? `/projects/${r.number}#final-video` : `/videos/sacrifice/${r.number}`}>{t("vid_open")}</Link>
              <WaChatButton e164={r.customer_phone_e164} status={r.customer_phone_status} /></span></td>
          </tr>))}</tbody>
      </table></div>)}
  </>;
}
