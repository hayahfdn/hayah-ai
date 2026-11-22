// The three things a donor receives, side by side on the project page (Hayah, 21 Nov 2026):
// the plaque, the final video and the endowment certificate. Each has the same three buttons in the
// same order: Edit, Send on WhatsApp, Download. Every button uses the feature that already exists
// (the plaque designer, the final-video upload/states, the certificate editor and its one-tap send);
// nothing here is a second copy of those features.
import { useState } from "react";
import { Link } from "react-router-dom";
import { getToken, Project } from "../api";
import { EDITORS, useAuth } from "../App";
import { useI18n } from "../i18n";
import * as I from "../icons";
import { Modal, toast, useApi } from "../ui";
import PlaquePreview from "../plaque/Preview";
import { usePlaqueImage } from "../plaque/PlaqueBadge";
import { isPhoneDevice, PlaqueRow, PlaqueStatusBadge, PlaqueWhatsApp, plaqueFile, plaqueWaWhy, waLink, waProblem, WaIcon } from "../plaque/flow";
import { CertificatePhotos, CertificatePreview, CertificateSend, certificatePngFor, saveBlob, useCertificate } from "../certificate/Certificate";
import { FinalVideoSection, useFinalVideo, VideoBadge } from "./FinalVideos";

type BtnProps = { icon: I.IconC; label: string; onClick?: () => void; to?: string; href?: string; download?: string;
  disabled?: boolean; title?: string; primary?: boolean };

/** One of the three tile buttons: icon on top, short word under it, same size everywhere. */
function TileBtn({ icon: C, label, onClick, to, href, download, disabled, title, primary }: BtnProps) {
  const inner = <><C size={19} strokeWidth={2} aria-hidden="true" /><span>{label}</span></>;
  const cls = `tile-btn${primary ? " primary" : ""}`;
  if (to && !disabled) return <Link className={cls} to={to} title={title || label}>{inner}</Link>;
  if (href && !disabled) return <a className={cls} href={href} download={download} title={title || label}>{inner}</a>;
  return <button type="button" className={cls} onClick={onClick} disabled={disabled} title={title || label} aria-label={title || label}>{inner}</button>;
}

function Tile({ icon: C, title, badge, thumb, buttons, foot, tone }: { icon: I.IconC; title: string; badge?: React.ReactNode;
  thumb: React.ReactNode; buttons: React.ReactNode; foot?: React.ReactNode; tone: string }) {
  return (
    <section className="dtile">
      <header><span className={`kpi-ico xs tone-${tone}`} aria-hidden="true"><C size={15} /></span><h3>{title}</h3></header>
      <div className="dtile-badge">{badge}</div>
      <div className="dtile-thumb">{thumb}</div>
      <div className="dtile-btns">{buttons}</div>
      {foot && <div className="dtile-foot">{foot}</div>}
    </section>);
}

async function downloadAuthed(url: string, name: string) {
  const r = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!r.ok) throw new Error(r.statusText);
  saveBlob(await r.blob(), name);
}

function PlaqueTile({ p }: { p: Project }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const editor = can(...EDITORS);
  const approved = p.plaque_status === "approved";
  const img = usePlaqueImage(p.well_id, approved ? p.plaque_media_id : null);
  const flow = useApi<PlaqueRow | null>(editor ? `/api/plaques/order/well/${p.well_id}` : null);
  const [preview, setPreview] = useState<string | null>(null);
  const name = `plaque-${p.well_id}.png`;
  const download = async () => {
    try {
      if (img.url) { const a = document.createElement("a"); a.href = img.url; a.download = name; a.click(); return; }
      if (flow.data?.file_version_id) { await downloadAuthed(plaqueFile(flow.data, true), name); return; }
      if (preview) { const a = document.createElement("a"); a.href = preview; a.download = name; a.click(); }
    } catch (e: any) { toast(e.message); }
  };
  const why = flow.data ? plaqueWaWhy(t, flow.data) : "";
  return (
    <Tile icon={I.Image} tone="violet" title={t("plaque")}
      badge={flow.data ? <PlaqueStatusBadge s={flow.data.status} /> : approved ? <span className="badge ok">✓ {t("plaque_approved")}</span>
        : <span className="badge">{p.plaque_status === "draft" ? t("plaque_draft") : t("plaque_none")}</span>}
      thumb={img.url ? <img src={img.url} alt={`${t("plaque")} ${p.well_id}`} /> : <PlaquePreview p={p} onReady={setPreview} />}
      buttons={<>
        <TileBtn icon={I.Pencil} label={t("tile_edit")} to={`/plaque/${p.well_id}`} disabled={!editor} title={t("plaque_edit")} />
        {flow.data ? <PlaqueWhatsApp p={flow.data} tile onDone={() => flow.reload()} />
          : <button type="button" className="tile-btn wa" disabled title={t("plwa_no_file")}><WaIcon /><span>{t("tile_wa")}</span></button>}
        <TileBtn icon={I.Download} label={t("tile_download")} onClick={download} disabled={!img.url && !flow.data?.file_version_id && !preview} title={t("pl_download_png")} />
      </>}
      foot={why ? <span className="tile-why" title={why}>⚠ {why}</span> : null} />);
}

function VideoTile({ no }: { no: number }) {
  const { t } = useI18n();
  const v = useFinalVideo("well", no);
  const [open, setOpen] = useState(false);
  const d = v.d;
  const has = !!(v.src && v.cur);
  const why = !has ? t("tile_no_video") : waProblem(t, d?.customer_phone_e164, d?.customer_phone_status);
  // phone: the video file goes into the share sheet (WhatsApp → the customer); computer: the customer's chat opens and the video downloads
  const send = () => {
    if (!d || !v.src) return;
    if (isPhoneDevice() && (navigator as any).canShare) { v.share(); return; }
    const l = waLink(d.customer_phone_e164, `${t("vid_share_text")} ${no}`);
    if (l) window.open(l, "_blank", "noopener");
    window.location.href = v.src.download_url;
  };
  return <>
    <Tile icon={I.Clapperboard} tone="pink" title={t("tile_video")}
      badge={d ? <VideoBadge s={d.status} /> : <span className="badge">…</span>}
      thumb={has ? <video src={v.src!.url} preload="metadata" muted playsInline controls />
        : <button type="button" className="dtile-empty" onClick={() => setOpen(true)}><I.Upload size={26} /><span>{t("vid_upload")}</span></button>}
      buttons={<>
        <TileBtn icon={I.Pencil} label={t("tile_edit")} onClick={() => setOpen(true)} title={t("tile_video_edit")} />
        <button type="button" className="tile-btn wa" disabled={!!why || !d} onClick={send} title={why || t("vid_share")}><WaIcon /><span>{t("tile_wa")}</span></button>
        <TileBtn icon={I.Download} label={t("tile_download")} href={v.src?.download_url} disabled={!has} title={t("vid_download")} />
      </>}
      foot={d && d.status === "uploaded" ? <button className="sm primary" disabled={v.busy} onClick={() => v.move("ready_for_delivery")}>✓ {t("vid_ready")}</button>
        : d && d.status === "ready_for_delivery" ? <button className="sm primary" disabled={v.busy} onClick={() => v.move("sent_to_customer")}>✓ {t("vid_sent")}</button>
        : v.error ? <span className="tile-why">{v.error}</span> : null} />
    {open && <Modal title={`${t("vid_title")} · ${no}`} onClose={() => { setOpen(false); v.load(); }}>
      <FinalVideoSection kind="well" no={no} />
    </Modal>}
  </>;
}

function CertificateTile({ p }: { p: Project }) {
  const { t, fmtDate } = useI18n();
  const c = useCertificate(p.well_id);
  return (
    <Tile icon={I.ScrollText} tone="teal" title={t("cert_title")}
      badge={c.data?.sent_at ? <span className="badge ok">✓ {t("cert_sent_log")} {fmtDate(c.data.sent_at)}</span>
        : <span className="badge info">{t("tile_ready")}</span>}
      thumb={c.design ? <CertificatePreview d={c.design} className="cert-thumb" /> : <div className="dtile-empty">{c.error || "…"}</div>}
      buttons={<>
        <TileBtn icon={I.Pencil} label={t("tile_edit")} to={`/plaque/certificate/${p.well_id}`} title={t("cert_edit")} />
        {c.data && c.design ? <CertificateSend data={c.data} design={c.design} onSent={c.setData} tile />
          : <button type="button" className="tile-btn wa" disabled><WaIcon /><span>{t("tile_wa")}</span></button>}
        <TileBtn icon={I.Download} label={t("tile_download")} disabled={!c.design} title={t("cert_download")}
          onClick={async () => c.design && saveBlob(await certificatePngFor(c.design), `certificate-${p.well_id}.png`)} />
        {c.design && <CertificatePhotos design={c.design} no={p.well_id} tile />}
      </>}
      foot={c.data?.defaults.date_guessed && !c.data?.design?.month ? <span className="tile-why" title={t("cert_date_guess")}>⚠ {t("tile_cert_date")}</span>
        : c.data && !c.data.video.media_id ? <span className="muted tile-note">{t("tile_cert_no_video")}</span> : null} />);
}

export default function DeliveryTrio({ p }: { p: Project }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const editor = can(...EDITORS);
  return (
    <div className="card dtrio-card" id="final-video">
      <div className="card-h"><h2>{t("tile_heading")}</h2><span className="muted">{t("tile_sub")}</span></div>
      <div className={`dtrio${editor ? "" : " one"}`}>
        <PlaqueTile p={p} />
        {editor && <VideoTile no={p.well_id} />}
        {editor && <CertificateTile p={p} />}
      </div>
    </div>);
}
