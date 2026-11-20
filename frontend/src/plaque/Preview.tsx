// The ready plaque of an order, drawn from what is recorded (Hayah, 2026-11-19): the approved plaque, else
// the latest saved version, else a fresh design from the order's details. The same drawing the designer uses,
// so it matches what the designer would show. Read-only here; "Edit plaque" opens the existing designer.
import { useEffect, useState } from "react";
import { api, Project } from "../api";
import { useI18n } from "../i18n";
import { defaultDesign, Design, renderCanvas } from "./render";
import { PlaqueRow } from "./flow";

export default function PlaquePreview({ p }: { p: Project }) {
  const { t } = useI18n();
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [saved, flow] = await Promise.all([
          api<{ approved: boolean; design: any }[]>(`/api/projects/${p.well_id}/plaques`).catch(() => []),
          api<PlaqueRow | null>(`/api/plaques/order/well/${p.well_id}`).catch(() => null)]);
        const ok = saved.find((x) => x.approved);
        const latest = !ok && flow?.design && !flow.design.auto && flow.design.template ? flow.design : null;
        const d = { ...defaultDesign(p as any), ...(ok ? ok.design : latest || {}) } as Design;
        const c = await renderCanvas(d, 540, 540);
        if (live) setUrl(c.toDataURL("image/png"));
      } catch { if (live) setFailed(true); }
    })();
    return () => { live = false; };
  }, [p.well_id, p.version, p.plaque_media_id]);
  if (failed) return <p className="muted">{t("plaque_none_yet")}</p>;
  return url ? <img className="plaque-thumb" src={url} alt={`${t("plaque")} ${p.well_id}`} /> : <div className="plaque-thumb empty">…</div>;
}
