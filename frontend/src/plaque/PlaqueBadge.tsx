// The plaque icon next to every well order: create one, open the draft, or view the approved plaque.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fileUrl, Project } from "../api";
import { EDITORS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Modal } from "../ui";

type P = Pick<Project, "well_id" | "plaque_status" | "plaque_media_id" | "plaque_approved_by" | "plaque_approved_at">;

export default function PlaqueBadge({ p, compact }: { p: P; compact?: boolean }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const go = useNavigate();
  const [viewing, setViewing] = useState(false);
  const editor = can(...EDITORS);
  const stop = (e: React.SyntheticEvent) => e.stopPropagation();
  if (p.plaque_status === "approved" && p.plaque_media_id) {
    return <>
      <button type="button" className="plaque-chip ok" onClick={(e) => { stop(e); setViewing(true); }}
        onDoubleClick={stop} title={t("plaque_view")}>
        <span aria-hidden="true">✓</span>{compact ? t("plaque_approved") : `${t("plaque")} · ${t("plaque_approved")}`}
      </button>
      {viewing && <PlaqueViewer p={p} onClose={() => setViewing(false)} />}
    </>;
  }
  if (!editor) return <span className="muted">{p.plaque_status === "draft" ? t("plaque_draft") : "—"}</span>;
  const draft = p.plaque_status === "draft";
  return (
    <button type="button" className={`plaque-chip ${draft ? "draft" : "new"}`} title={t("plaque_create")}
      onClick={(e) => { stop(e); go(`/plaque/${p.well_id}`); }} onDoubleClick={stop}>
      <span aria-hidden="true">{draft ? "✎" : "＋"}</span>{draft ? t("plaque_draft") : compact ? t("plaque") : t("plaque_create")}
    </button>
  );
}

export function PlaqueViewer({ p, onClose }: { p: P; onClose: () => void }) {
  const { t, fmtDate } = useI18n();
  const { can } = useAuth();
  const go = useNavigate();
  const src = usePlaqueImage(p.well_id, p.plaque_media_id);
  return (
    <Modal title={`${t("plaque")} · ${p.well_id}`} onClose={onClose}>
      {src.error ? <ErrorBox error={src.error} /> : src.url
        ? <img className="plaque-img" src={src.url} alt={`${t("plaque")} ${p.well_id}`} /> : <p className="muted">{t("plaque_loading")}</p>}
      <p className="muted" style={{ marginBottom: 0 }}>
        <span className="badge ok">✓ {t("plaque_approved")}</span>{" "}
        {p.plaque_approved_by && <>{t("plaque_approved_by")}: {p.plaque_approved_by} · </>}{fmtDate(p.plaque_approved_at)}
      </p>
      <div className="actions" style={{ flexWrap: "wrap" }}>
        {src.url && <a className="btn" href={src.url} download={`plaque-${p.well_id}.png`}>{t("pl_download_png")}</a>}
        {can(...EDITORS) && <button className="primary" onClick={() => go(`/plaque/${p.well_id}`)}>{t("plaque_versions")} · {t("plaque_new_version")}</button>}
      </div>
    </Modal>
  );
}

/** Loads a plaque image that needs the login token, as an object URL. */
export function usePlaqueImage(wellId: number | string, mediaId: number | null | undefined) {
  const [state, setState] = useState<{ url: string | null; error: string | null }>({ url: null, error: null });
  useEffect(() => {
    if (!mediaId) { setState({ url: null, error: null }); return; }
    let url: string | null = null, live = true;
    fileUrl(`/api/projects/${wellId}/plaques/file/${mediaId}`)
      .then((u) => { url = u; if (live) setState({ url: u, error: null }); else URL.revokeObjectURL(u); })
      .catch((e) => live && setState({ url: null, error: e.message }));
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [wellId, mediaId]);
  return state;
}
