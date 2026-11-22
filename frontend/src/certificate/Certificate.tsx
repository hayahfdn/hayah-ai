// «شهادة وقفية» for each well: the card on the project page, the editor page, and the one-tap
// WhatsApp send of the certificate together with the final video.
// Nothing is sent automatically: the person's own WhatsApp sends it (share sheet on a phone,
// WhatsApp Web + downloaded files on a computer). No unofficial automation.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Project } from "../api";
import { EDITORS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Field, toast } from "../ui";
import { isPhoneDevice, waLink, waProblem, WaIcon } from "../plaque/flow";
import { WELL_ICONS } from "../plaque/render";
import { FONTS } from "../plaque/fonts";
import DesignerTabs from "../plaque/DesignerTabs";
import { saveToPhotos } from "../plaque/photos";
import * as I from "../icons";
import { CertDefaults, CertDesign, CH, CW, certificatePng, defaultCert, drawCertificate, loadCertAssets } from "./render";

export interface CertData {
  number: number; defaults: CertDefaults; design: Partial<CertDesign> | null; saved_at: string | null; saved_by: string | null;
  sent_at: string | null; sent_by: string | null; customer_name: string | null; customer_phone_e164: string | null;
  customer_phone_status: string | null;
  video: { status: string; media_id: number | null; mime_type: string | null; filename: string | null; size_bytes: number | null };
}

export function useCertificate(no: number | string | undefined) {
  const [data, setData] = useState<CertData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => (no ? api<CertData>(`/api/certificates/well/${no}`).then(setData).catch((e) => setError(e.message)) : Promise.resolve());
  useEffect(() => { setData(null); load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [no]);
  const design = useMemo<CertDesign | null>(() => data && { ...defaultCert(data.defaults), ...(data.design || {}) } as CertDesign,
    [data]);
  return { data, setData, design, error, reload: load };
}

/** Draws the certificate into a canvas that fills its box. */
export function CertificatePreview({ d, className }: { d: CertDesign; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let live = true;
    loadCertAssets(d).then((a) => {
      const c = ref.current;
      if (!live || !c) return;
      const s = 2;
      c.width = CW * s; c.height = CH * s;
      drawCertificate(c.getContext("2d")!, d, a, s);
    });
    return () => { live = false; };
  }, [d]);
  return <canvas ref={ref} className={className || "cert-canvas"} aria-label="شهادة وقفية" />;
}

export function saveBlob(b: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
const ext = (mime: string | null, name: string | null) => (name && name.includes(".") ? name.slice(name.lastIndexOf(".")) : mime === "video/quicktime" ? ".mov" : ".mp4");

/** The one-tap WhatsApp button: certificate + final video (when there is one) to the customer.
 *  Phone: the files go into the share sheet (WhatsApp → the customer). Large videos take a moment to
 *  fetch; if the phone then refuses to open the share sheet without a new tap, the button says
 *  "tap again" and the second tap opens it straight away with the files already prepared. */
export function CertificateSend({ data, design, onSent, compact, tile }: { data: CertData; design: CertDesign; onSent?: (d: CertData) => void; compact?: boolean; tile?: boolean }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState<File[] | null>(null);
  const why = waProblem(t, data.customer_phone_e164, data.customer_phone_status);
  const hasVideo = !!data.video.media_id;
  const no = data.number;
  const text = `${t("cert_msg")} ${no}\n${t("cert_msg_end")}`;
  useEffect(() => setReady(null), [design, data.video.media_id]);

  const files = async (): Promise<File[]> => {
    const out = [new File([await certificatePng(design, 2)], `certificate-${no}.png`, { type: "image/png" })];
    if (data.video.media_id) {
      const l = await api<{ url: string }>(`/api/videos/file/${data.video.media_id}/link`);
      const b = await (await fetch(l.url)).blob();
      out.push(new File([b], `well-${no}-final${ext(data.video.mime_type, data.video.filename)}`, { type: data.video.mime_type || "video/mp4" }));
    }
    return out;
  };
  const logged = async (method: "share" | "download") => {
    try {
      let r = await api<CertData>(`/api/certificates/well/${no}/sent`, { body: { with_video: hasVideo, method } });
      if (method === "share" && data.video.status === "ready_for_delivery") {
        await api(`/api/videos/order/well/${no}/status`, { body: { to: "sent_to_customer", note: t("cert_title") } }).catch(() => null);
        r = await api<CertData>(`/api/certificates/well/${no}`);
      }
      onSent?.(r);
    } catch (e: any) { toast(e.message); }
  };
  const share = async (fs: File[]) => {
    await (navigator as any).share({ files: fs, text });
    setReady(null); toast(t("cert_done_share")); logged("share");
  };
  const go = async () => {
    const nav: any = navigator;
    const phone = isPhoneDevice() && !!nav.canShare;
    if (phone && ready) {
      try { await share(ready); } catch (e: any) { if (e?.name !== "AbortError") toast(e.message); }
      return;
    }
    // computer (or a phone that cannot share files): open the customer's chat now, inside the tap
    const link = waLink(data.customer_phone_e164, text);
    if (!phone && link) window.open(link, "_blank", "noopener");
    setBusy(true);
    try {
      if (hasVideo && phone) toast(t("vid_big"));
      const fs = await files();
      if (phone && nav.canShare({ files: fs })) {
        try { await share(fs); }
        catch (e: any) {
          if (e?.name === "AbortError") return;
          setReady(fs); toast(t("cert_tap_again")); // the tap expired while the video was loading
        }
        return;
      }
      if (phone && link) window.location.href = link;
      fs.forEach((f) => saveBlob(f, f.name));
      toast(t("cert_done_dl")); logged("download");
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const label = busy ? t("cert_preparing") : ready ? t("cert_tap_again") : hasVideo ? t("cert_send") : t("cert_send_only");
  if (tile) return <button type="button" className={`tile-btn wa${ready ? " ready" : ""}`} disabled={!!why || busy} onClick={go}
    title={why || `${label} · ${t("cert_send_help")}`} aria-label={label}><WaIcon /><span>{busy ? "…" : ready ? t("cert_tap_again") : t("tile_wa")}</span></button>;
  return (
    <span className="wa-wrap">
      <button type="button" className={`sm wa-btn${compact ? " icon" : ""}${ready ? " primary" : ""}`} disabled={!!why || busy} onClick={go}
        title={why || t("cert_send_help")} aria-label={label}>
        <WaIcon />{!compact && <span>{label}</span>}
      </button>
      {why && !compact && <span className="wa-why">⚠ {why}</span>}
    </span>);
}

/** «حفظ في معرض الصور»: the certificate image straight into the phone's photos (download on a computer).
 *  The PNG is made in advance, so the phone's share sheet opens straight from the tap. */
export function CertificatePhotos({ design, no, className = "sm", tile }: { design: CertDesign; no: number | string; className?: string; tile?: boolean }) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setFile(null);
    const h = window.setTimeout(() => certificatePng(design, 2).then((b) => setFile(new File([b], `certificate-${no}.png`, { type: "image/png" }))).catch(() => {}), 500);
    return () => window.clearTimeout(h);
  }, [design, no]);
  const go = async () => {
    setBusy(true);
    try {
      const f = file || new File([await certificatePng(design, 2)], `certificate-${no}.png`, { type: "image/png" });
      const r = await saveToPhotos(f);
      if (r === "shared") toast(t("pl_photos_shared"));
      else if (r === "downloaded") toast(t("pl_photos_downloaded"));
      else if (r === "tap_again") { setFile(f); toast(t("cert_tap_again")); }
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  if (tile) return <button type="button" className="tile-btn" onClick={go} disabled={busy} title={t("pl_save_photos")} aria-label={t("pl_save_photos")}>
    <I.Images size={19} strokeWidth={2} aria-hidden="true" /><span>{busy ? "…" : t("tile_photos")}</span></button>;
  return <button type="button" className={className} onClick={go} disabled={busy} title={t("pl_save_photos")}><I.Images size={16} aria-hidden="true" /> {busy ? t("pl_saving_photos") : t("pl_save_photos")}</button>;
}

/** The certificate on the project page: preview, edit, download, send. */
export function CertificateCard({ p }: { p: Project }) {
  const { t, fmtDate } = useI18n();
  const c = useCertificate(p.well_id);
  if (c.error) return <div className="card" style={{ marginTop: 14 }}><h2>📜 {t("cert_title")}</h2><ErrorBox error={c.error} /></div>;
  if (!c.data || !c.design) return null;
  return (
    <div className="card cert-card" id="certificate" style={{ marginTop: 14 }}>
      <div className="plaque-card-head"><h2 style={{ margin: 0 }}>📜 {t("cert_title")}</h2>
        {c.data.sent_at && <span className="badge ok">✓ {t("cert_sent_log")} {fmtDate(c.data.sent_at)}</span>}</div>
      <div className="plaque-card-body">
        <CertificatePreview d={c.design} className="cert-thumb" />
        <div>
          <p className="muted" style={{ marginTop: 0 }}>{t("cert_help")}</p>
          {c.data.defaults.date_guessed && !c.data.design?.month && <p className="missing">⚠ {t("cert_date_guess")}</p>}
          {!c.data.video.media_id && <p className="muted" style={{ fontSize: 13 }}>{t("cert_no_video")}</p>}
          <div className="actions" style={{ flexWrap: "wrap", justifyContent: "flex-start" }}>
            <CertificateSend data={c.data} design={c.design} onSent={c.setData} />
            <Link className="btn sm" to={`/plaque/certificate/${p.well_id}`}>✏️ {t("cert_edit")}</Link>
            <button className="sm" onClick={async () => saveBlob(await certificatePng(c.design!, 2), `certificate-${p.well_id}.png`)}>⬇ {t("cert_download")}</button>
            <CertificatePhotos design={c.design} no={p.well_id} />
          </div>
        </div>
      </div>
    </div>);
}

const FIELDS: [keyof CertDesign, string, "text" | "area"][] = [
  ["names", "cert_f_names", "area"], ["project_type", "cert_f_type", "text"], ["month", "cert_f_month", "text"], ["year", "cert_f_year", "text"],
  ["number", "cert_f_number", "text"], ["country", "cert_f_country", "text"],
  ["title", "cert_f_title", "text"], ["intro", "cert_f_intro", "area"], ["sadaqa_line", "cert_f_sadaqa", "text"], ["opened_prefix", "cert_f_opened", "text"],
  ["number_label", "cert_f_number_label", "text"], ["country_label", "cert_f_country_label", "text"], ["dua", "cert_f_dua", "text"], ["site", "cert_f_site", "text"],
];

/** /certificate/:wellId — edit every line, see it live, save, download and send. */
export default function CertificatePage() {
  const { wellId } = useParams();
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const c = useCertificate(wellId);
  const nav = useNavigate();
  const [pick, setPick] = useState("");
  const [d, setD] = useState<CertDesign | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (c.design) setD(c.design); }, [c.design]);
  if (!can(...EDITORS)) return <ErrorBox error="403" />;
  const opener = (
    <form style={{ display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (pick.trim()) nav(`/plaque/certificate/${pick.trim()}`); }}>
      <input type="number" placeholder={t("pl_open_well")} value={pick} onChange={(e) => setPick(e.target.value)} style={{ width: 170 }} />
      <button>{t("pl_open")}</button>
    </form>);
  if (!wellId) return <>
    <div className="topbar"><div><span className="muted">{t("nav_plaque")}</span><h1>📜 {t("cert_title")}</h1></div>{opener}</div>
    <DesignerTabs on="certificate" />
    <p className="muted">{t("cert_pick")}</p>
  </>;
  if (c.error) return <><DesignerTabs on="certificate" wellId={wellId} /><ErrorBox error={c.error} /></>;
  if (!c.data || !d) return <p className="muted">{t("loading")}</p>;
  const set = (k: keyof CertDesign, v: any) => setD({ ...d, [k]: v });
  const save = async () => {
    setSaving(true);
    try { c.setData(await api<CertData>(`/api/certificates/well/${wellId}`, { method: "PUT", body: { design: d } })); toast(t("cert_saved")); }
    catch (e: any) { toast(e.message); } finally { setSaving(false); }
  };
  return <>
    <div className="topbar">
      <div><Link to={`/projects/${wellId}`} className="muted">‹ {t("well_id")} {wellId}</Link><h1>📜 {t("cert_title")} · <span className="mono">{wellId}</span></h1></div>
      <div className="actions" style={{ margin: 0, flexWrap: "wrap" }}>
        {opener}
        <CertificateSend data={c.data} design={d} onSent={c.setData} />
        <button onClick={async () => saveBlob(await certificatePng(d, 2), `certificate-${wellId}.png`)}>⬇ {t("cert_download")}</button>
        <CertificatePhotos design={d} no={wellId!} className="" />
        <button className="primary" disabled={saving} onClick={save}>💾 {t("save")}</button>
      </div>
    </div>
    <DesignerTabs on="certificate" wellId={wellId} />
    <div className="cert-editor">
      <div className="card cert-preview-card"><CertificatePreview d={d} /></div>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>{t("cert_help")}</p>
        {c.data.defaults.date_guessed && !c.data.design?.month && <p className="missing">⚠ {t("cert_date_guess")}</p>}
        <div className="cert-form">
          {FIELDS.map(([k, label, kind]) => (
            <Field key={k} label={t(label)}>{kind === "area"
              ? <textarea dir="rtl" rows={k === "names" ? 3 : 2} value={String(d[k] ?? "")} onChange={(e) => set(k, e.target.value)} />
              : <input dir={k === "site" ? "ltr" : "rtl"} value={String(d[k] ?? "")} onChange={(e) => set(k, e.target.value)} />}</Field>))}
          <Field label={t("cert_f_names_font")}>
            <select value={d.names_font || "Cairo"} onChange={(e) => set("names_font", e.target.value)} style={{ fontFamily: `'${d.names_font || "Cairo"}'` }}>
              {FONTS.map((f) => <option key={f.family} value={f.family} style={{ fontFamily: `'${f.family}'` }}>{lang === "ar" ? `${f.ar} · ${f.en}` : `${f.en} · ${f.ar}`}</option>)}
            </select></Field>
          <Field label={`${t("cert_f_names_size")} (${d.names_size}%)`}>
            <input type="range" min={60} max={130} step={5} value={d.names_size} onChange={(e) => set("names_size", Number(e.target.value))} /></Field>
          <Field label={t("cert_f_icon")}>
            <select value={d.icon} onChange={(e) => set("icon", e.target.value)}>
              <option value="pump">{lang === "ar" ? "مضخة (رسم بسيط)" : "Pump (simple drawing)"}</option>
              {WELL_ICONS.map((i) => <option key={i.key} value={i.key}>{lang === "ar" ? i.ar : i.en}</option>)}
              <option value="none">{t("pl_none")}</option></select></Field>
          <label className="check"><input type="checkbox" checked={d.show_stamp} onChange={(e) => set("show_stamp", e.target.checked)} /> {t("cert_f_stamp")}</label>
        </div>
        <div className="actions" style={{ justifyContent: "flex-start" }}>
          <button onClick={() => setD(defaultCert(c.data!.defaults))}>↺ {t("cert_reset")}</button>
        </div>
        <p className="muted" style={{ fontSize: 12.5 }}>{t("cert_send_help")}</p>
      </div>
    </div>
  </>;
}

/** The same one-tap send inside the final-video section of a well. */
export function CertificateSendInline({ no }: { no: number }) {
  const c = useCertificate(no);
  if (!c.data || !c.design) return null;
  return <CertificateSend data={c.data} design={c.design} onSent={c.setData} />;
}

/** The certificate as a PNG at full print size (the same file the editor downloads). */
export const certificatePngFor = (d: CertDesign) => certificatePng(d, 2);
