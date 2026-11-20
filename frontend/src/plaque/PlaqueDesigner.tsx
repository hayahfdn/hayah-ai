import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Project } from "../api";
import { EDITORS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Field, Modal, Status, toast } from "../ui";
import { countryLabel } from "../nav";
import { PlaqueViewer } from "./PlaqueBadge";
import {
  ANIMALS, applyOccasion, ARAB_FLAG_END, defaultDesign, defaultSacrificeDesign, Design, drawPlaque, DuaKind, duaText,
  exportPdf, exportPng, fileToSmallDataUrl, flagArabic, FLAGS, GRIDS, IconKey, loadAssets, MAIN_FLAG_COUNT, Occasion,
  OCCASIONS, SACRIFICE_DUA_KINDS, SacrificeDesign, sizeLabel, SIZES, SizeKey, WELL_DUA_KINDS, WELL_ICONS, WELL_TYPES, WellDesign,
  DUAS, Align, textStyle, Assets, imageBox, imageLibrary, LibraryImage,
} from "./render";
import { FONTS } from "./fonts";
import * as I from "../icons";
import { MissingList, PlaqueActions, PlaqueRow, PlaqueStatusBadge, PlaqueWhatsApp } from "./flow";

type Kind = "well" | "sacrifice";
interface Saved { id: string; created_at: string; actor_label: string; filename: string; design: Design; version?: number; approved?: boolean; media_id?: number | null; }

/** A small button that opens the file picker (instead of the wide browser file box). */
function UploadBtn({ label, accept = "image/*", onFile, disabled }: { label: string; accept?: string; onFile: (f: File | undefined) => void; disabled?: boolean }) {
  return (
    <label className={`btn sm upload-btn${disabled ? " disabled" : ""}`} title={label}>
      <I.Upload size={15} aria-hidden="true" /><span>{label}</span>
      <input type="file" accept={accept} disabled={disabled} onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} />
    </label>);
}

/** One button of the plaque's action bar: icon with a short word, all the same size, side by side. */
function ActBtn({ icon: C, label, onClick, disabled, busy, primary }: { icon: I.IconC; label: string; onClick: () => void; disabled?: boolean; busy?: boolean; primary?: boolean }) {
  return <button type="button" className={`act-btn${primary ? " primary" : ""}`} onClick={onClick} disabled={disabled} title={label} aria-label={label}>
    <C size={18} strokeWidth={2} aria-hidden="true" /><span>{busy ? "…" : label}</span></button>;
}

function saveBlob(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export default function PlaqueDesigner({ kind = "well" }: { kind?: Kind }) {
  const params = useParams();
  const id = kind === "well" ? params.wellId : params.no;
  const nav = useNavigate();
  const { t, lang, fmtDate } = useI18n();
  const { can } = useAuth();
  const [record, setRecord] = useState<any>(null);
  const [d, setD] = useState<Design>(() => (kind === "well" ? defaultDesign() : defaultSacrificeDesign()));
  const [saved, setSaved] = useState<Saved[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pick, setPick] = useState("");
  const [confirm, setConfirm] = useState<null | (() => void)>(null);
  const [viewing, setViewing] = useState<Saved | null>(null);
  const [flow, setFlow] = useState<PlaqueRow | null | undefined>(undefined);
  const canvas = useRef<HTMLCanvasElement>(null);

  const fresh = (rec: any) => (kind === "well" ? defaultDesign(rec || undefined) : defaultSacrificeDesign(rec || undefined));
  // first=true fills the design from the order (or from its approved plaque); after a save the design stays as it is.
  // The order's plaque in the workflow (status, missing information); null when it has none yet.
  const loadFlow = () => api<PlaqueRow | null>(`/api/plaques/order/${kind}/${id}`).then((f) => { setFlow(f); return f; }).catch(() => { setFlow(null); return null; });
  // The design to start from: the approved plaque, else the employee's latest saved version,
  // else a fresh design from the order (an automatic draft holds only what the order says).
  const startFrom = (rec: any, list: Saved[], f: PlaqueRow | null) => {
    const ok = list.find((x) => x.approved);
    const latest = !ok && f?.design && !f.design.auto && f.design.template ? f.design : null;
    setD((x) => ({ ...fresh(rec), ...(ok ? ok.design : latest || {}), size: x.size }) as Design);
  };
  const load = (first = false) => {
    if (!id) return;
    if (kind === "well") {
      Promise.all([api<Project>(`/api/projects/${id}`), api<Saved[]>(`/api/projects/${id}/plaques`).catch(() => [] as Saved[]), loadFlow()])
        .then(([p, list, f]) => {
          setRecord(p); setSaved(list);
          if (first) startFrom(p, list, f);
        }).catch((e) => setError(e.message));
    } else {
      Promise.all([api<{ sacrifice: any; saved: Saved[] }>(`/api/plaques/sacrifices/${id}`), loadFlow()]).then(([r, f]) => {
        setRecord(r.sacrifice); setSaved(r.saved);
        if (first) startFrom(r.sacrifice, [], f);
      }).catch((e) => setError(e.message));
    }
  };
  useEffect(() => {
    setError(null); setRecord(null); setSaved([]); setFlow(undefined);
    if (!id) setD(fresh(null)); else load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, kind]);

  // Live preview: the same drawing that gets exported, at screen size. A dashed frame shows the picture
  // that can be dragged (only on screen; it is never part of the PNG, PDF or saved image).
  const assets = useRef<Assets | null>(null);
  useEffect(() => {
    let live = true;
    loadAssets(d).then((a) => {
      const c = canvas.current;
      if (!live || !c) return;
      assets.current = a;
      const [gw, gh] = GRIDS[d.template];
      const px = Math.round(c.clientWidth * (window.devicePixelRatio || 1)) || gw;
      c.width = px; c.height = Math.round((px * gh) / gw);
      const ctx = c.getContext("2d")!;
      drawPlaque(ctx, d, a, px / gw);
      const box = imageBox(d, a.image);
      if (box) {
        const k = px / gw;
        ctx.save(); ctx.setLineDash([8, 6]); ctx.strokeStyle = "#0e7c86"; ctx.lineWidth = 2;
        ctx.strokeRect(box.x * k, box.y * k, box.w * k, box.h * k); ctx.restore();
      }
    });
    return () => { live = false; };
  }, [d]);

  // Drag the picture on the plaque (mouse, pen or finger). Positions are kept in plaque units.
  const drag = useRef<{ dx: number; dy: number; id: number } | null>(null);
  const toGrid = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const [gw, gh] = GRIDS[d.template];
    return { x: ((e.clientX - r.left) / r.width) * gw, y: ((e.clientY - r.top) / r.height) * gh };
  };
  const dragStart = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const box = imageBox(d, assets.current?.image);
    if (!box || !d.image) return;
    const g = toGrid(e);
    if (g.x < box.x || g.x > box.x + box.w || g.y < box.y || g.y > box.y + box.h) return;
    drag.current = { dx: g.x - d.image.x, dy: g.y - d.image.y, id: e.pointerId };
    e.currentTarget.setPointerCapture(e.pointerId); e.preventDefault();
  };
  const dragMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drag.current || drag.current.id !== e.pointerId) return;
    const g = toGrid(e); const [gw, gh] = GRIDS[d.template];
    const x = Math.max(0, Math.min(gw, g.x - drag.current.dx)), y = Math.max(0, Math.min(gh, g.y - drag.current.dy));
    setD((v) => (v.image ? { ...v, image: { ...v.image, x: Math.round(x), y: Math.round(y) } } : v) as Design);
  };
  const dragEnd = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (drag.current?.id === e.pointerId) { drag.current = null; try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* already released */ } }
  };

  const set = (k: string, v: any) => setD((x) => ({ ...x, [k]: v }) as Design);
  const setDua = (k: DuaKind) => setD((x) => {
    const dt = duaText(k, x.template, x.name);
    const short = x.template === "sacrifice_portrait" && (x as SacrificeDesign).occasion !== "sadaqa" ? x.short_dua : dt.short;
    return { ...x, dua_kind: k, dua_sure: true, short_dua: short, dua: dt.long } as Design;
  });
  const setFlag = (code: string) => setD((x) => x.template === "sacrifice_portrait"
    ? { ...x, flag: code, country_label: code === "custom" ? x.country_label : flagArabic(code) } : { ...x, flag: code });
  const upload = async (f: File | undefined, which: "flag" | "icon") => {
    if (!f) return;
    try {
      const url = await fileToSmallDataUrl(f);
      setD((x) => (which === "flag" ? { ...x, flag: "custom", flag_custom: url } : { ...x, icon: "custom", icon_custom: url }) as Design);
    } catch (e: any) { setError(e.message); }
  };
  const number = d.template === "hayah_square" ? d.well_id : d.sacrifice_no;
  const fileBase = `${kind === "well" ? "plaque" : "sacrifice-plaque"}-${number || "draft"}`;
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setError(null);
    try { await fn(); } catch (e: any) { setError(e.message || String(e)); } finally { setBusy(null); }
  };
  const downloadPng = () => run("png", async () => saveBlob(await exportPng(d), `${fileBase}.png`));
  const downloadPdf = () => run("pdf", async () => saveBlob(await exportPdf(d), `${fileBase}.pdf`));
  // «حفظ في معرض الصور»: the finished plaque image only (no designer controls), at its full size.
  // Phones get the share sheet ("Save Image" puts it in Photos); where sharing files is not possible
  // the same PNG is downloaded. It is prepared in advance so the share happens straight from the tap.
  const [photo, setPhoto] = useState<File | null>(null);
  useEffect(() => {
    setPhoto(null);
    const h = window.setTimeout(() => { exportPng(d).then((b) => setPhoto(new File([b], `${fileBase}.png`, { type: "image/png" }))).catch(() => {}); }, 700);
    return () => window.clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d]);
  const saveToPhotos = () => run("photos", async () => {
    const file = photo || new File([await exportPng(d)], `${fileBase}.png`, { type: "image/png" });
    const nav: any = navigator;
    if (nav.canShare && nav.canShare({ files: [file] })) {
      try { await nav.share({ files: [file], title: file.name }); toast(t("pl_photos_shared")); return; }
      catch (e: any) { if (e?.name === "AbortError") return; }
    }
    saveBlob(file, file.name); toast(t("pl_photos_downloaded"));
  });
  const [finalUrl, setFinalUrl] = useState<string | null>(null);
  const showFinal = () => run("final", async () => setFinalUrl(URL.createObjectURL(await exportPng(d))));
  // Every save is a new version of this order's plaque; nothing is overwritten.
  const send = async (approve: boolean, replace = false) => {
    const png = await exportPng(d);
    const form = new FormData();
    form.append("file", new File([png], `${fileBase}.png`, { type: "image/png" }));
    form.append("design", JSON.stringify(d));
    form.append("approve", String(approve));
    if (kind === "well") form.append("replace", String(replace));
    await api(kind === "well" ? `/api/projects/${id}/plaques` : `/api/plaques/sacrifices/${id}`, { form });
  };
  const { refreshCounts } = useAuth();
  const saveTo = () => run("save", async () => {
    await send(false); refreshCounts();
    toast(kind === "well" ? t("plaque_draft_ok") : t("pl_saved_sac"));
    load();
  });
  const approve = (replace = false) => run("approve", async () => {
    try { await send(true, replace); }
    catch (e: any) {
      if (e.status === 409 && !replace && /already has an approved plaque/i.test(e.message || "")) { setConfirm(() => () => approve(true)); return; }
      throw e;
    }
    toast(t("plaque_approved_ok")); refreshCounts();
    load();
  });
  const approveVersion = (s: Saved, replace = false) => run("v" + s.id, async () => {
    try { await api(`/api/projects/${id}/plaques/${s.id}/approve`, { method: "POST", query: { replace } }); }
    catch (e: any) {
      if (e.status === 409 && !replace && /already has an approved plaque/i.test(e.message || "")) { setConfirm(() => () => approveVersion(s, true)); return; }
      throw e;
    }
    toast(t("plaque_approved_ok"));
    load();
  });
  const L = (o: { en: string; ar: string }) => (lang === "ar" ? o.ar : o.en);
  const base = kind === "well" ? "/plaque" : "/plaque/sacrifice";
  const input = (k: string, v: string, dir: "rtl" | "ltr" = "rtl", list?: string) =>
    <input dir={dir} value={v} list={list} onChange={(e) => set(k, e.target.value)} />;

  const flagSelect = (
    <Field label={t("pl_flag")}>
      <select value={d.flag} onChange={(e) => setFlag(e.target.value)}>
        <option value="">{t("pl_none")}</option>
        <optgroup label={t("pl_flags_main")}>{FLAGS.slice(0, MAIN_FLAG_COUNT).map((f) => <option key={f.code} value={f.code}>{f.ar} · {f.en}</option>)}</optgroup>
        <optgroup label={t("pl_flags_arab")}>{FLAGS.slice(MAIN_FLAG_COUNT, ARAB_FLAG_END).map((f) => <option key={f.code} value={f.code}>{f.ar} · {f.en}</option>)}</optgroup>
        <optgroup label={t("pl_flags_other")}>{FLAGS.slice(ARAB_FLAG_END).map((f) => <option key={f.code} value={f.code}>{f.ar} · {f.en}</option>)}</optgroup>
        {d.flag_custom && <option value="custom">{t("pl_uploaded")}</option>}
      </select>
    </Field>
  );
  const duaSelect = (kinds: DuaKind[]) => (
    <Field label={t("pl_dua_kind")}>
      <select value={d.dua_kind} onChange={(e) => setDua(e.target.value as DuaKind)}>
        {kinds.map((k) => <option key={k} value={k}>{L(DUAS[k])}</option>)}
      </select>
    </Field>
  );

  return (
    <>
      <div className="topbar">
        <div>
          {id && kind === "well" ? <Link to={`/projects/${id}`} className="muted">‹ {t("plaque_back")} {id}</Link> : <span className="muted">{t("nav_plaque")}</span>}
          <h1>{kind === "well" ? t("pl_title") : t("pl_title_sac")}{id ? <> · <span className="mono">{id}</span></> : null}</h1>
        </div>
        <form style={{ display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (pick.trim()) nav(`${base}/${pick.trim()}`); }}>
          <input type="number" placeholder={kind === "well" ? t("pl_open_well") : t("pl_open_sac")} value={pick} onChange={(e) => setPick(e.target.value)} style={{ width: 170 }} />
          <button>{t("pl_open")}</button>
        </form>
      </div>
      <div className="tabs">
        <button type="button" className={kind === "well" ? "on" : ""} onClick={() => nav("/plaque")}>{t("pl_tab_well")}</button>
        <button type="button" className={kind === "sacrifice" ? "on" : ""} onClick={() => nav("/plaque/sacrifice")}>{t("pl_tab_sac")}</button>
      </div>
      <ErrorBox error={error} />
      {!id && <p className="muted">{kind === "well" ? t("pl_no_well") : t("pl_no_sac")}</p>}
      {id && kind === "well" && record && <OrderBox p={record} />}
      {id && record && flow !== undefined && can(...EDITORS) && <FlowPanel flow={flow} kind={kind} id={id} onChange={(f) => { setFlow(f); load(); }} />}
      <div className="card plaque-tools">
        <h2 style={{ marginBottom: 8 }}>{t("pl_tools")}</h2>
        {d.template === "hayah_square" ? <WellFields d={d} set={set} input={input} flagSelect={flagSelect} duaSelect={duaSelect(WELL_DUA_KINDS)} upload={upload} L={L} />
          : <SacrificeFields d={d} setD={setD} set={set} input={input} flagSelect={flagSelect} duaSelect={duaSelect(SACRIFICE_DUA_KINDS)} upload={upload} L={L} />}
        {d.dua_sure === false && <div className="error" role="alert" style={{ marginTop: 12 }}>{t("pl_dua_unsure")}</div>}
        <div className="tool-rows">
          <div className="field full"><label>{t("pl_dua")}</label>
            <textarea dir="rtl" rows={4} value={d.dua} onChange={(e) => set("dua", e.target.value)} aria-describedby="pl-nl-hint" />
            <span className="hint muted">{t("pl_dua_hint")}</span></div>
        </div>
        <p id="pl-nl-hint" className="muted" style={{ fontSize: 12.5, margin: "6px 0 0" }}>↵ {t("pl_newline_hint")}</p>
      </div>
      <div className="plaque-layout">
        <div className="card plaque-preview">
          <canvas ref={canvas} aria-label={t("pl_preview")} style={{ aspectRatio: `${GRIDS[d.template][0]} / ${GRIDS[d.template][1]}`, touchAction: d.image ? "none" : undefined, cursor: d.image ? "move" : undefined }}
            onPointerDown={dragStart} onPointerMove={dragMove} onPointerUp={dragEnd} onPointerCancel={dragEnd} />
          {d.image && <p className="muted" style={{ fontSize: 12, margin: "6px 0 0" }}>✥ {t("pl_solar_drag")}</p>}
          <div className="pl-actbar">
            <select value={d.size} onChange={(e) => set("size", e.target.value as SizeKey)} aria-label={t("pl_size")}>
              {(Object.keys(SIZES) as SizeKey[]).map((k) => <option key={k} value={k}>{sizeLabel(k, d.template, lang)}</option>)}
            </select>
            <ActBtn icon={I.Download} label={t("pl_download_png")} onClick={downloadPng} disabled={!!busy} busy={busy === "png"} />
            <ActBtn icon={I.Images} label={busy === "photos" ? t("pl_saving_photos") : t("pl_save_photos")} onClick={saveToPhotos} disabled={!!busy} />
            <ActBtn icon={I.ScrollText} label={t("pl_download_pdf")} onClick={downloadPdf} disabled={!!busy} busy={busy === "pdf"} />
            <ActBtn icon={I.Eye} label={t("pl_preview_final")} onClick={showFinal} disabled={!!busy} busy={busy === "final"} />
            {id && record && can(...EDITORS) && kind === "well" && <>
              <ActBtn icon={I.Pencil} label={t("plaque_save_draft")} onClick={saveTo} disabled={!!busy} busy={busy === "save"} />
              <ActBtn icon={I.CircleCheck} primary label={t("plaque_approve")} onClick={() => approve()} disabled={!!busy} busy={busy === "approve"} />
            </>}
            {id && record && can(...EDITORS) && kind === "sacrifice" && <>
              <ActBtn icon={I.Pencil} label={t("pl_save_sac")} onClick={saveTo} disabled={!!busy} busy={busy === "save"} />
              <ActBtn icon={I.CircleCheck} primary label={t("pl_approve_sac")} onClick={() => approve(true)} disabled={!!busy || !!flow?.missing.length} busy={busy === "approve"} />
            </>}
          </div>
        </div>
        <div className="card">
          {d.template === "hayah_square" && <WellIcons d={d} set={set} upload={upload} L={L} />}
          <TextControls d={d} set={set} />
          <details style={{ marginTop: 12 }} open={!!d.image || undefined}>
            <summary>{t("pl_more")}</summary>
            <ImageTool d={d} setD={setD} />
            <div className="form-grid" style={{ marginTop: 10 }}>
              {d.template === "hayah_square" ? <>
                <Field label={t("pl_bismillah")}>{input("bismillah", d.bismillah)}</Field>
                <Field label={t("pl_verse")}>{input("verse", d.verse)}</Field>
                <Field label={t("pl_project_label")}>{input("project_label", d.project_label)}</Field>
              </> : <>
                <Field label={t("pl_header1")}>{input("header1", d.header1)}</Field>
                <Field label={t("pl_quote")}>{input("quote", d.quote)}</Field>
                <Field label={t("pl_reference")}>{input("reference", d.reference)}</Field>
                <Field label={t("pl_number_label")}>{input("number_label", d.number_label)}</Field>
              </>}
              <Field label={t("pl_footer_org")}>{input("footer_org", d.footer_org)}</Field>
              <Field label={t("pl_footer_site")}>{input("footer_site", d.footer_site, "ltr")}</Field>
              <Field label={t("pl_color")}><input type="color" value={d.name_color} onChange={(e) => set("name_color", e.target.value)} /></Field>
            </div>
          </details>
          <div className="actions">
            <button type="button" onClick={() => setD({ ...fresh(record), size: d.size })}>{id ? t("pl_reset") : t("pl_reset_blank")}</button>
          </div>
          {id && <>
            <h3 style={{ marginBottom: 6, marginTop: 16 }}>{kind === "well" ? t("plaque_versions") : t("pl_history")}</h3>
            {saved.length ? <ul className="timeline versions">{saved.map((s) => (
              <li key={s.id} className={s.approved ? "is-approved" : ""}>
                <span className="muted">{s.version ? <b className="ver">{t("plaque_version")} {s.version}</b> : null} {fmtDate(s.created_at)} {new Date(s.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                <span>{s.approved && <span className="badge ok">✓ {t("plaque_approved")}</span>} <bdi className="mono" dir="ltr">{s.filename}</bdi> · {s.actor_label}
                  <span className="row-actions">
                    <button className="sm" onClick={() => { setD({ ...fresh(record), ...s.design } as Design); window.scrollTo({ top: 0, behavior: "smooth" }); }}>{t("pl_load")}</button>
                    {kind === "well" && s.media_id && <button className="sm" onClick={() => setViewing(s)}>{t("plaque_view")}</button>}
                    {kind === "well" && !s.approved && can(...EDITORS) && <button className="sm" disabled={!!busy} onClick={() => approveVersion(s)}>✓ {t("plaque_approve_this")}</button>}
                  </span></span></li>))}</ul>
              : <p className="muted">{t("pl_none_saved")}</p>}
          </>}
        </div>
      </div>
      {finalUrl && <Modal title={t("pl_preview_final")} onClose={() => { URL.revokeObjectURL(finalUrl); setFinalUrl(null); }}>
        <img src={finalUrl} alt={t("pl_preview_final")} className="final-preview" />
        <div className="actions"><button onClick={() => { URL.revokeObjectURL(finalUrl); setFinalUrl(null); }}>{t("close")}</button></div>
      </Modal>}
      {confirm && <Modal title={t("plaque_approve")} onClose={() => setConfirm(null)}>
        <p>{t("plaque_replace_q")}</p>
        <div className="actions"><button onClick={() => setConfirm(null)}>{t("cancel")}</button>
          <button className="primary" onClick={() => { const f = confirm; setConfirm(null); f(); }}>✓ {t("plaque_approve")}</button></div>
      </Modal>}
      {viewing && record && <PlaqueViewer p={{ ...record, plaque_media_id: viewing.media_id, plaque_status: "approved",
        plaque_approved_by: viewing.approved ? record.plaque_approved_by : null, plaque_approved_at: viewing.approved ? record.plaque_approved_at : null }}
        onClose={() => setViewing(null)} />}
    </>
  );
}

/** Where this order's plaque is in the workflow, what is missing, and the next steps. */
function FlowPanel({ flow, kind, id, onChange }: { flow: PlaqueRow | null; kind: Kind; id: string; onChange: (f: PlaqueRow) => void }) {
  const { t, fmtDate } = useI18n();
  const [busy, setBusy] = useState(false);
  if (!flow) return (
    <div className="card pl-flow" style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
      <span className="muted">{t("pla_none")}</span>
      <button className="sm" disabled={busy} onClick={async () => {
        setBusy(true);
        try { onChange(await api<PlaqueRow>(`/api/plaques/order/${kind}/${id}`, { method: "POST" })); } catch (e: any) { toast(e.message); } finally { setBusy(false); }
      }}>{t("pla_create")}</button>
    </div>);
  return (
    <div className={`card pl-flow${flow.missing.length || flow.status === "needs_changes" ? " alert" : ""}`}>
      <div className="pl-head"><b>{t("pla_status")}:</b> <PlaqueStatusBadge s={flow.status} />
        {flow.version ? <span className="muted">{t("pla_version")} {flow.version}</span> : null}
        {flow.sent_to_contractor_on && <span className="muted">{t("pla_sent_on")} {fmtDate(flow.sent_to_contractor_on)}{flow.contractor ? ` · ${flow.contractor.name}` : ""}</span>}</div>
      <MissingList missing={flow.missing} />
      {flow.customer_note && <div className="pl-note">{t("pla_customer_note")}: <b dir="auto">{flow.customer_note}</b></div>}
      <div className="actions" style={{ flexWrap: "wrap" }}><PlaqueWhatsApp p={flow} onDone={onChange} label /><PlaqueActions p={flow} onDone={onChange} /></div>
    </div>
  );
}

/** The order this plaque belongs to: filled in automatically, shown so the designer can check it.
 *  Only what the plaque needs, in one row of chips (Hayah, 21 Nov 2026). */
function OrderBox({ p }: { p: Project }) {
  const { t, lang } = useI18n();
  const country = p.contractor?.country ? countryLabel(p.contractor.country, lang) : p.country;
  return (
    <div className="card order-box compact" style={{ background: p.contractor?.color || undefined }} title={t("plaque_order_help")}>
      <div className="ob-row">
        <b className="well-no">{p.well_id}</b>
        {p.customer_name && <span className="ob-chip"><I.UserRound size={14} aria-hidden="true" />{p.customer_name}</span>}
        {p.well_type && <span className="ob-chip"><I.Droplets size={14} aria-hidden="true" />{p.well_type}</span>}
        {(p.contractor || country) && <span className="ob-chip"><I.MapPin size={14} aria-hidden="true" />{[p.contractor?.code, country].filter(Boolean).join(" · ")}</span>}
        <Status v={p.construction_status} />
      </div>
      {p.dedication && <p className="ob-ded" dir="auto"><span className="muted">{t("dedication")}: </span>{p.dedication}</p>}
    </div>
  );
}

type FieldProps = {
  set: (k: string, v: any) => void; input: (k: string, v: string, dir?: "rtl" | "ltr", list?: string) => JSX.Element;
  flagSelect: JSX.Element; duaSelect: JSX.Element; upload: (f: File | undefined, which: "flag" | "icon") => void;
  L: (o: { en: string; ar: string }) => string;
};

function WellFields({ d, set, input, flagSelect, duaSelect, upload }: FieldProps & { d: WellDesign }) {
  const { t } = useI18n();
  // Hayah's order (20 Nov 2026): flag, project number, well type, date, name, prayer form, prayer text.
  return <>
    <div className="tool-rows">
      {flagSelect}
      <div className="field upload-field"><label>&nbsp;</label><UploadBtn label={t("pl_flag_upload")} onFile={(f) => upload(f, "flag")} /></div>
      <Field label={t("pl_project_no")}>{input("well_id", d.well_id, "ltr")}</Field>
      <Field label={t("pl_well_type")}>{input("well_type", d.well_type, "rtl", "pl-well-types")}</Field>
      <Field label={t("pl_sadaqa_label")}>{input("sadaqa_label", d.sadaqa_label, "rtl", "pl-sadaqa-labels")}</Field>
      <Field label={t("pl_month")}>{input("month", d.month)}</Field>
    </div>
    <div className="tool-rows">
      <div className="field wide"><label>{t("pl_name")}</label><MultiLine value={d.name} onChange={(v) => set("name", v)} /></div>
      {duaSelect}
      <div className="field wide"><label>{t("pl_short_dua")}</label><MultiLine value={d.short_dua} onChange={(v) => set("short_dua", v)} /></div>
    </div>
    <datalist id="pl-well-types">{WELL_TYPES.map((w) => <option key={w} value={w} />)}</datalist>
    <datalist id="pl-sadaqa-labels">{["صدقة جارية عن:", "صدقة جارية إهداء إلى:", "صدقة جارية لروح:"].map((w) => <option key={w} value={w} />)}</datalist>
  </>;
}

function WellIcons({ d, set, upload, L }: { d: WellDesign; set: (k: string, v: any) => void; upload: FieldProps["upload"]; L: FieldProps["L"] }) {
  const { t } = useI18n();
  const icon = d.icon === "well" ? "hand_pump" : d.icon;
  return (
    <div>
      <div className="ic-head">
        <label className="muted">{t("pl_icon")}</label>
        <div className="seg sm" role="group" aria-label={t("pl_icon_side")} title={t("pl_icon_side")}>
          {(["left", "right"] as const).map((k) => <button type="button" key={k} className={(d.icon_side || "left") === k ? "on" : ""} onClick={() => set("icon_side", k)}>{t("pl_" + k)}</button>)}
        </div>
        <UploadBtn label={t("pl_icon_upload")} onFile={(f) => upload(f, "icon")} />
      </div>
      <div className="icon-picks compact">
        {WELL_ICONS.map((w) => (
          <button type="button" key={w.key} className={icon === w.key ? "on" : ""} onClick={() => set("icon", w.key as IconKey)} title={L(w)}>
            <img src={`/wells/${w.key}.png`} alt="" /><span>{L(w)}</span>
          </button>))}
        {d.icon_custom && <button type="button" className={icon === "custom" ? "on" : ""} onClick={() => set("icon", "custom")}><img src={d.icon_custom} alt="" /><span>{t("pl_uploaded")}</span></button>}
        <button type="button" className={icon === "none" ? "on" : ""} onClick={() => set("icon", "none")}><span>{t("pl_none")}</span></button>
      </div>
    </div>
  );
}

/** A text box where Enter starts a new line (and a button that does the same, for phones).
 *  The lines are saved as typed and drawn on the plaque exactly like that. */
function MultiLine({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useI18n();
  const ref = useRef<HTMLTextAreaElement>(null);
  const rows = Math.min(5, Math.max(1, value.split("\n").length));
  const newline = () => {
    const el = ref.current;
    const a = el ? el.selectionStart : value.length, b = el ? el.selectionEnd : value.length;
    onChange(value.slice(0, a) + "\n" + value.slice(b));
    requestAnimationFrame(() => { if (el) { el.focus(); el.selectionStart = el.selectionEnd = a + 1; } });
  };
  return <div className="multiline">
    <textarea ref={ref} dir="rtl" rows={rows} value={value} onChange={(e) => onChange(e.target.value)} aria-describedby="pl-nl-hint" />
    <button type="button" className="sm" onClick={newline} title={t("pl_newline_hint")} aria-label={t("pl_newline")}>↵ {t("pl_newline")}</button>
  </div>;
}

function SacrificeFields({ d, setD, set, input, flagSelect, duaSelect, upload, L }: FieldProps & { d: SacrificeDesign; setD: (fn: (x: Design) => Design) => void }) {
  const { t } = useI18n();
  return <>
    <div className="tool-rows">
      <Field label={t("pl_occasion")}>
        <select value={d.occasion} onChange={(e) => setD((x) => applyOccasion(x as SacrificeDesign, e.target.value as Occasion))}>
          {(Object.keys(OCCASIONS) as Occasion[]).map((k) => <option key={k} value={k}>{L(OCCASIONS[k])}</option>)}
        </select>
      </Field>
      {flagSelect}
      <div className="field upload-field"><label>&nbsp;</label><UploadBtn label={t("pl_flag_upload")} onFile={(f) => upload(f, "flag")} /></div>
      <Field label={t("pl_country_label")}>{input("country_label", d.country_label)}</Field>
      <Field label={t("pl_sac_no")}>{input("sacrifice_no", d.sacrifice_no, "ltr")}</Field>
      <Field label={t("pl_animal")}>
        <input dir="rtl" list="pl-animals" value={d.animal} onChange={(e) => {
          const animal = e.target.value;
          setD((x) => { const s = x as SacrificeDesign; return { ...s, animal, title: s.title.replace(s.animal || "\u0000", animal) }; });
        }} />
      </Field>
      <Field label={t("pl_month")}>{input("month", d.month)}</Field>
    </div>
    <div className="tool-rows">
      <Field label={t("pl_title_line")}>{input("title", d.title)}</Field>
      <Field label={t("pl_subtitle_line")}>{input("subtitle", d.subtitle)}</Field>
    </div>
    <div className="tool-rows">
      <div className="field wide"><label>{t("pl_name")}</label><MultiLine value={d.name} onChange={(v) => set("name", v)} /></div>
      {duaSelect}
      <div className="field wide"><label>{t("pl_short_dua")}</label><MultiLine value={d.short_dua} onChange={(v) => set("short_dua", v)} />
        <span className="hint muted">{t("pl_short_dua_hint")}</span></div>
    </div>
    <datalist id="pl-animals">{ANIMALS.map((w) => <option key={w} value={w} />)}</datalist>
    <p className="muted" style={{ marginBottom: 0 }}>{t("pl_occasion_hint")}</p>
  </>;
}

/** Font, size, line spacing, alignment and weight for the name and the prayer. Every font in the
 * list is shown in its own face; the files are bundled, so the export matches the preview. */
function TextControls({ d, set }: { d: Design; set: (k: string, v: any) => void }) {
  const { t, lang } = useI18n();
  const block = (which: "name" | "dua") => {
    const st = textStyle(d, which);
    const k = (f: string) => `${which}_${f}`;
    return (
      <fieldset className="text-controls compact" key={which}>
        <legend>{t(which === "name" ? "pl_text_name" : "pl_text_dua")}</legend>
        <div className="tc-row">
          <Field label={t("pl_font")}>
            <select value={st.family} onChange={(e) => set(k("font"), e.target.value)} style={{ fontFamily: `'${st.family}'` }}>
              {FONTS.map((f) => <option key={f.family} value={f.family} style={{ fontFamily: `'${f.family}'` }}>
                {lang === "ar" ? `${f.ar} · ${f.en}` : `${f.en} · ${f.ar}`}{f.standIn ? ` (${t("pl_font_standin")} ${f.standIn})` : ""}</option>)}
            </select>
          </Field>
          <Field label={`${t("pl_size_pct")} ${Math.round(st.k * 100)}%`}>
            <input type="range" min={50} max={150} step={5} value={Math.round(st.k * 100)} onChange={(e) => set(k("size"), Number(e.target.value))} />
          </Field>
          <Field label={`${t("pl_line")} ${st.line.toFixed(2)}`}>
            <input type="range" min={0.9} max={2.2} step={0.05} value={st.line} onChange={(e) => set(k("line"), Number(e.target.value))} />
          </Field>
          <Field label={t("pl_align")}>
            <div className="seg">{(["right", "center", "left"] as Align[]).map((a) =>
              <button type="button" key={a} className={st.align === a ? "on" : ""} onClick={() => set(k("align"), a)}>{t("pl_" + a)}</button>)}</div>
          </Field>
          <Field label={t("pl_weight")}>
            <div className="seg">{[true, false].map((b) =>
              <button type="button" key={String(b)} className={(st.weight > 400) === b ? "on" : ""} onClick={() => set(k("bold"), b)}>{t(b ? "pl_bold" : "pl_normal")}</button>)}</div>
          </Field>
        </div>
      </fieldset>
    );
  };
  return <div className="tc-wrap" title={t("pl_font_note")}>{block("name")}{block("dua")}</div>;
}

/** «صورة البئر الشمسي»: an optional picture on the plaque from the approved library (or a new upload).
 *  Move it by dragging on the preview or with the sliders; size keeps its proportions. */
function ImageTool({ d, setD }: { d: Design; setD: (fn: (x: Design) => Design) => void }) {
  const { t } = useI18n();
  const [lib, setLib] = useState<LibraryImage[]>([]);
  const [open, setOpen] = useState(!!d.image);
  const [busy, setBusy] = useState(false);
  const [gw, gh] = GRIDS[d.template];
  useEffect(() => { imageLibrary().then(setLib); }, []);
  useEffect(() => { if (d.image) setOpen(true); }, [d.image]);
  const place = (ref: string) => setD((x) => ({ ...x, image: x.image ? { ...x.image, ref } : { ref, x: Math.round(gw * 0.78), y: Math.round(gh * 0.55), w: Math.round(gw * 0.3) } }) as Design);
  const upd = (k: "x" | "y" | "w", v: number) => setD((x) => (x.image ? { ...x, image: { ...x.image, [k]: v } } : x) as Design);
  const add = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    try {
      const data_url = await fileToSmallDataUrl(f, 1200);
      const item = await api<LibraryImage>("/api/plaque-images", { body: { name: f.name.replace(/\.[^.]+$/, "").slice(0, 80) || "image", data_url } });
      setLib(await imageLibrary(true)); place(`lib:${item.id}`); toast(t("img_uploaded"));
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const cur = d.image?.ref;
  return (
    <fieldset className="text-controls image-tool">
      <legend>{t("pl_extra_img")}</legend>
      {!open && !d.image ? <button type="button" className="sm" onClick={() => setOpen(true)}><I.Image size={15} aria-hidden="true" /> {t("pl_extra_img_add")}</button> : <>
        <label className="muted" style={{ display: "block", marginBottom: 6 }}>{t("pl_solar_library")}</label>
        <div className="icon-picks">
          {lib.map((im) => (
            <button type="button" key={im.id} className={cur === `lib:${im.id}` ? "on" : ""} onClick={() => place(`lib:${im.id}`)} title={im.name}>
              <img src={im.src} alt="" /><span>{im.name}</span>
            </button>))}
        </div>
        <div className="actions" style={{ justifyContent: "flex-start", marginTop: 8 }}>
          <UploadBtn label={t("pl_solar_upload")} accept="image/png,image/jpeg,image/webp" disabled={busy} onFile={add} />
        </div>
        {d.image && <>
          <div className="tool-rows">
            <Field label={`${t("pl_solar_size")} ${Math.round((d.image.w / gw) * 100)}%`}>
              <input type="range" min={Math.round(gw * 0.08)} max={gw} step={2} value={d.image.w} onChange={(e) => upd("w", Number(e.target.value))} /></Field>
            <Field label={t("pl_solar_x")}><input type="range" min={0} max={gw} step={2} value={d.image.x} onChange={(e) => upd("x", Number(e.target.value))} /></Field>
            <Field label={t("pl_solar_y")}><input type="range" min={0} max={gh} step={2} value={d.image.y} onChange={(e) => upd("y", Number(e.target.value))} /></Field>
          </div>
          <div className="actions" style={{ justifyContent: "flex-start", flexWrap: "wrap" }}>
            <button type="button" className="sm" onClick={() => { upd("x", Math.round(gw / 2)); upd("y", Math.round(gh / 2)); }}>⊕ {t("pl_solar_center")}</button>
            <button type="button" className="sm danger" onClick={() => setD((x) => ({ ...x, image: null }) as Design)}>✕ {t("pl_solar_remove")}</button>
          </div>
          <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>{t("pl_solar_drag")}</p>
        </>}
      </>}
    </fieldset>
  );
}
