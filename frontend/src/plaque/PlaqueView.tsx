// The plaque button next to every well order, and the viewer for an approved plaque.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { mediaUrl } from "../api";
import { EDITORS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Modal } from "../ui";

export function PlaqueIcon({ approved }: { approved?: boolean }) {
  return approved
    ? <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" /><path d="M8 12.5l2.6 2.6L16 9.6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
    : <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" /><path d="M12 8v8M8 12h8" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" /></svg>;
}

/** Shows the approved plaque image (fetched with the sign-in token). */
export function PlaqueImage({ mediaId, alt }: { mediaId: number; alt: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let u: string | null = null, live = true;
    setUrl(null); setErr(null);
    mediaUrl(mediaId).then((x) => { u = x; if (live) setUrl(x); else URL.revokeObjectURL(x); }).catch((e) => live && setErr(e.message));
    return () => { live = false; if (u) URL.revokeObjectURL(u); };
  }, [mediaId]);
  if (err) return <ErrorBox error={err} />;
  if (!url) return <div className="plaque-img loading" aria-busy="true" />;
  return <a href={url} target="_blank" rel="noreferrer"><img className="plaque-img" src={url} alt={alt} /></a>;
}

export function PlaqueModal({ wellId, mediaId, approvedAt, onClose }: { wellId: number; mediaId: number; approvedAt?: string | null; onClose: () => void }) {
  const { t, fmtDate } = useI18n();
  const nav = useNavigate();
  const { can } = useAuth();
  return (
    <Modal title={`${t("pl_approved")} · ${wellId}`} onClose={onClose}>
      <PlaqueImage mediaId={mediaId} alt={`${t("pl_section")} ${wellId}`} />
      {approvedAt && <p className="muted">{t("pl_approved_on")}: {fmtDate(approvedAt)}</p>}
      <div className="actions">
        <button onClick={() => nav(`/projects/${wellId}`)}>{t("details")}</button>
        {can(...EDITORS) && <button className="primary" onClick={() => nav(`/plaque/${wellId}`)}>{t("pl_new_version")}</button>}
      </div>
    </Modal>
  );
}

/** The button beside an order: opens the designer pre-filled, or shows the approved plaque. */
export function PlaqueButton({ wellId, mediaId, approvedAt, compact }: { wellId: number; mediaId?: number | null; approvedAt?: string | null; compact?: boolean }) {
  const { t } = useI18n();
  const nav = useNavigate();
  const { can } = useAuth();
  const [show, setShow] = useState(false);
  const approved = !!mediaId;
  if (!approved && !can(...EDITORS)) return null;
  const label = approved ? t("pl_view") : t("pl_create");
  return <>
    <button type="button" className={`plaque-btn ${approved ? "ok" : ""} ${compact ? "compact" : ""}`} title={label} aria-label={`${label} ${wellId}`}
      onClick={(e) => { e.stopPropagation(); approved ? setShow(true) : nav(`/plaque/${wellId}`); }}>
      <PlaqueIcon approved={approved} />{!compact && <span>{approved ? t("pl_badge_approved") : t("pl_create")}</span>}
    </button>
    {show && mediaId && <PlaqueModal wellId={wellId} mediaId={mediaId} approvedAt={approvedAt} onClose={() => setShow(false)} />}
  </>;
}
