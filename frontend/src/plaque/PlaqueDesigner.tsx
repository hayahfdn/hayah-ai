import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Project } from "../api";
import { EDITORS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Field, toast } from "../ui";
import {
  defaultDesign, Design, DuaKind, DUAS, exportPdf, exportPng, fileToSmallDataUrl, FLAGS, GRID, loadAssets, drawPlaque,
  SIZES, SizeKey,
} from "./render";

interface Saved { id: string; created_at: string; actor_label: string; filename: string; design: Design; }

function saveBlob(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export default function PlaqueDesigner() {
  const { wellId } = useParams();
  const nav = useNavigate();
  const { t, lang, fmtDate } = useI18n();
  const { can } = useAuth();
  const [project, setProject] = useState<Project | null>(null);
  const [d, setD] = useState<Design>(() => defaultDesign());
  const [saved, setSaved] = useState<Saved[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pick, setPick] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);

  const loadSaved = () => wellId && api<Saved[]>(`/api/projects/${wellId}/plaques`).then(setSaved).catch(() => setSaved([]));

  useEffect(() => {
    setError(null); setProject(null); setSaved([]);
    if (!wellId) { setD(defaultDesign()); return; }
    api<Project>(`/api/projects/${wellId}`).then((p) => {
      setProject(p);
      setD({ ...defaultDesign(p as any), size: d.size });
    }).catch((e) => setError(e.message));
    loadSaved();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wellId]);

  // Live preview: draw the same canvas that gets exported, at screen size.
  useEffect(() => {
    let live = true;
    loadAssets(d).then((a) => {
      const c = canvas.current;
      if (!live || !c) return;
      const px = Math.round(c.clientWidth * (window.devicePixelRatio || 1)) || GRID;
      c.width = px; c.height = px;
      drawPlaque(c.getContext("2d")!, d, a, px / GRID);
    });
    return () => { live = false; };
  }, [d]);

  const set = <K extends keyof Design>(k: K, v: Design[K]) => setD((x) => ({ ...x, [k]: v }));
  const setDua = (k: DuaKind) => setD((x) => ({ ...x, dua_kind: k, short_dua: DUAS[k].short, dua: DUAS[k].long }));
  const upload = async (f: File | undefined, which: "flag" | "icon") => {
    if (!f) return;
    try {
      const url = await fileToSmallDataUrl(f);
      setD((x) => which === "flag" ? { ...x, flag: "custom", flag_custom: url } : { ...x, icon: "custom", icon_custom: url });
    } catch (e: any) { setError(e.message); }
  };
  const fileBase = `plaque-${d.well_id || "draft"}`;
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setError(null);
    try { await fn(); } catch (e: any) { setError(e.message || String(e)); } finally { setBusy(null); }
  };
  const downloadPng = () => run("png", async () => saveBlob(await exportPng(d), `${fileBase}-${SIZES[d.size].px}px.png`));
  const downloadPdf = () => run("pdf", async () => saveBlob(await exportPdf(d), `${fileBase}.pdf`));
  const saveToWell = () => run("save", async () => {
    const png = await exportPng(d);
    const form = new FormData();
    form.append("file", new File([png], `${fileBase}.png`, { type: "image/png" }));
    form.append("design", JSON.stringify(d));
    await api(`/api/projects/${wellId}/plaques`, { form });
    toast(t("pl_saved")); loadSaved();
  });
  const L = (o: { label_en: string; label_ar: string }) => (lang === "ar" ? o.label_ar : o.label_en);

  return (
    <>
      <div className="topbar">
        <div>
          {wellId ? <Link to={`/projects/${wellId}`} className="muted">‹ {t("well_id")} {wellId}</Link> : <span className="muted">{t("nav_plaque")}</span>}
          <h1>{t("pl_title")}{wellId ? <> · <span className="mono">{wellId}</span></> : null}</h1>
        </div>
        <form style={{ display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (pick) nav(`/plaque/${pick.trim()}`); }}>
          <input type="number" placeholder={t("pl_open_well")} value={pick} onChange={(e) => setPick(e.target.value)} style={{ width: 170 }} />
          <button>{t("pl_open")}</button>
        </form>
      </div>
      <ErrorBox error={error} />
      {!wellId && <p className="muted">{t("pl_no_well")}</p>}
      <div className="plaque-layout">
        <div className="card plaque-preview">
          <canvas ref={canvas} aria-label={t("pl_preview")} />
          <div className="actions" style={{ flexWrap: "wrap" }}>
            <select value={d.size} onChange={(e) => set("size", e.target.value as SizeKey)} aria-label={t("pl_size")}>
              {Object.entries(SIZES).map(([k, s]) => <option key={k} value={k}>{L(s)}</option>)}
            </select>
            <button onClick={downloadPng} disabled={!!busy}>{busy === "png" ? "…" : t("pl_download_png")}</button>
            <button onClick={downloadPdf} disabled={!!busy}>{busy === "pdf" ? "…" : t("pl_download_pdf")}</button>
            {wellId && project && can(...EDITORS) && <button className="primary" onClick={saveToWell} disabled={!!busy}>{busy === "save" ? "…" : t("pl_save")}</button>}
          </div>
        </div>
        <div className="card">
          <div className="form-grid">
            <Field label={t("pl_name")}><input dir="rtl" value={d.name} onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label={t("pl_project_no")}><input dir="ltr" value={d.well_id} onChange={(e) => set("well_id", e.target.value)} /></Field>
            <Field label={t("pl_well_type")}><input dir="rtl" value={d.well_type} onChange={(e) => set("well_type", e.target.value)} /></Field>
            <Field label={t("pl_month")}><input dir="rtl" value={d.month} onChange={(e) => set("month", e.target.value)} /></Field>
            <Field label={t("pl_flag")}>
              <select value={d.flag} onChange={(e) => set("flag", e.target.value)}>
                <option value="">{t("pl_none")}</option>
                {FLAGS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                {d.flag_custom && <option value="custom">{t("pl_uploaded")}</option>}
              </select>
            </Field>
            <Field label={t("pl_flag_upload")}><input type="file" accept="image/*" onChange={(e) => upload(e.target.files?.[0], "flag")} /></Field>
            <Field label={t("pl_icon")}>
              <select value={d.icon} onChange={(e) => set("icon", e.target.value as Design["icon"])}>
                <option value="well">{t("pl_icon_well")}</option>
                {d.icon_custom && <option value="custom">{t("pl_uploaded")}</option>}
                <option value="none">{t("pl_none")}</option>
              </select>
            </Field>
            <Field label={t("pl_icon_upload")}><input type="file" accept="image/*" onChange={(e) => upload(e.target.files?.[0], "icon")} /></Field>
            <Field label={t("pl_dua_kind")}>
              <select value={d.dua_kind} onChange={(e) => setDua(e.target.value as DuaKind)}>
                {(Object.keys(DUAS) as DuaKind[]).map((k) => <option key={k} value={k}>{L(DUAS[k])}</option>)}
              </select>
            </Field>
            <Field label={t("pl_short_dua")}><input dir="rtl" value={d.short_dua} onChange={(e) => set("short_dua", e.target.value)} /></Field>
          </div>
          <div style={{ marginTop: 12 }}>
            <Field label={t("pl_dua")} hint={t("pl_dua_hint")}><textarea dir="rtl" rows={5} value={d.dua} onChange={(e) => set("dua", e.target.value)} /></Field>
          </div>
          <details style={{ marginTop: 12 }}>
            <summary>{t("pl_more")}</summary>
            <div className="form-grid" style={{ marginTop: 10 }}>
              <Field label={t("pl_bismillah")}><input dir="rtl" value={d.bismillah} onChange={(e) => set("bismillah", e.target.value)} /></Field>
              <Field label={t("pl_verse")}><input dir="rtl" value={d.verse} onChange={(e) => set("verse", e.target.value)} /></Field>
              <Field label={t("pl_project_label")}><input dir="rtl" value={d.project_label} onChange={(e) => set("project_label", e.target.value)} /></Field>
              <Field label={t("pl_sadaqa_label")}><input dir="rtl" value={d.sadaqa_label} onChange={(e) => set("sadaqa_label", e.target.value)} /></Field>
              <Field label={t("pl_footer_org")}><input dir="rtl" value={d.footer_org} onChange={(e) => set("footer_org", e.target.value)} /></Field>
              <Field label={t("pl_footer_site")}><input dir="ltr" value={d.footer_site} onChange={(e) => set("footer_site", e.target.value)} /></Field>
              <Field label={t("pl_name_font")}>
                <select value={d.name_font} onChange={(e) => set("name_font", e.target.value as Design["name_font"])}>
                  <option value="Cairo">Cairo</option><option value="Amiri">Amiri</option><option value="Noto Naskh Arabic">Noto Naskh</option>
                </select>
              </Field>
              <Field label={t("pl_color")}><input type="color" value={d.name_color} onChange={(e) => set("name_color", e.target.value)} /></Field>
            </div>
          </details>
          <div className="actions">
            <button type="button" onClick={() => setD({ ...defaultDesign((project as any) || undefined), size: d.size })}>{t("pl_reset")}</button>
          </div>
          {wellId && <>
            <h3 style={{ marginBottom: 6 }}>{t("pl_history")}</h3>
            {saved.length ? <ul className="timeline">{saved.map((s) => (
              <li key={s.id}><span className="muted">{fmtDate(s.created_at)} {new Date(s.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                <span><bdi className="mono" dir="ltr">{s.filename}</bdi> · {s.actor_label}{" "}
                  <button className="sm" onClick={() => { setD({ ...defaultDesign(), ...s.design }); window.scrollTo({ top: 0, behavior: "smooth" }); }}>{t("pl_load")}</button></span></li>))}</ul>
              : <p className="muted">{t("pl_none_saved")}</p>}
          </>}
        </div>
      </div>
    </>
  );
}
