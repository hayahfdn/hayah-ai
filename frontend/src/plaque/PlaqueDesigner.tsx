import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Project } from "../api";
import { EDITORS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Field, toast } from "../ui";
import {
  ANIMALS, applyOccasion, ARAB_FLAG_END, defaultDesign, defaultSacrificeDesign, Design, drawPlaque, DuaKind, duaText,
  exportPdf, exportPng, fileToSmallDataUrl, flagArabic, FLAGS, GRIDS, IconKey, loadAssets, MAIN_FLAG_COUNT, Occasion,
  OCCASIONS, SACRIFICE_DUA_KINDS, SacrificeDesign, sizeLabel, SIZES, SizeKey, WELL_DUA_KINDS, WELL_ICONS, WELL_TYPES, WellDesign,
  DUAS,
} from "./render";

type Kind = "well" | "sacrifice";
interface Saved { id: string; created_at: string; actor_label: string; filename: string; design: Design; }

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
  const canvas = useRef<HTMLCanvasElement>(null);

  const fresh = (rec: any) => (kind === "well" ? defaultDesign(rec || undefined) : defaultSacrificeDesign(rec || undefined));
  const load = () => {
    if (!id) return;
    if (kind === "well") {
      api<Project>(`/api/projects/${id}`).then((p) => { setRecord(p); setD((x) => ({ ...fresh(p), size: x.size })); }).catch((e) => setError(e.message));
      api<Saved[]>(`/api/projects/${id}/plaques`).then(setSaved).catch(() => setSaved([]));
    } else {
      api<{ sacrifice: any; saved: Saved[] }>(`/api/plaques/sacrifices/${id}`).then((r) => {
        setRecord(r.sacrifice); setSaved(r.saved); setD((x) => ({ ...fresh(r.sacrifice), size: x.size }));
      }).catch((e) => setError(e.message));
    }
  };
  useEffect(() => {
    setError(null); setRecord(null); setSaved([]);
    if (!id) setD(fresh(null)); else load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, kind]);

  // Live preview: the same drawing that gets exported, at screen size.
  useEffect(() => {
    let live = true;
    loadAssets(d).then((a) => {
      const c = canvas.current;
      if (!live || !c) return;
      const [gw, gh] = GRIDS[d.template];
      const px = Math.round(c.clientWidth * (window.devicePixelRatio || 1)) || gw;
      c.width = px; c.height = Math.round((px * gh) / gw);
      drawPlaque(c.getContext("2d")!, d, a, px / gw);
    });
    return () => { live = false; };
  }, [d]);

  const set = (k: string, v: any) => setD((x) => ({ ...x, [k]: v }) as Design);
  const setDua = (k: DuaKind) => setD((x) => {
    const dt = duaText(k, x.template, x.name);
    const short = x.template === "sacrifice_portrait" && (x as SacrificeDesign).occasion !== "sadaqa" ? x.short_dua : dt.short;
    return { ...x, dua_kind: k, short_dua: short, dua: dt.long } as Design;
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
  const saveTo = () => run("save", async () => {
    const png = await exportPng(d);
    const form = new FormData();
    form.append("file", new File([png], `${fileBase}.png`, { type: "image/png" }));
    form.append("design", JSON.stringify(d));
    await api(kind === "well" ? `/api/projects/${id}/plaques` : `/api/plaques/sacrifices/${id}`, { form });
    toast(kind === "well" ? t("pl_saved") : t("pl_saved_sac"));
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
          {id && kind === "well" ? <Link to={`/projects/${id}`} className="muted">‹ {t("well_id")} {id}</Link> : <span className="muted">{t("nav_plaque")}</span>}
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
      <div className="plaque-layout">
        <div className="card plaque-preview">
          <canvas ref={canvas} aria-label={t("pl_preview")} style={{ aspectRatio: `${GRIDS[d.template][0]} / ${GRIDS[d.template][1]}` }} />
          <div className="actions" style={{ flexWrap: "wrap" }}>
            <select value={d.size} onChange={(e) => set("size", e.target.value as SizeKey)} aria-label={t("pl_size")}>
              {(Object.keys(SIZES) as SizeKey[]).map((k) => <option key={k} value={k}>{sizeLabel(k, d.template, lang)}</option>)}
            </select>
            <button onClick={downloadPng} disabled={!!busy}>{busy === "png" ? "…" : t("pl_download_png")}</button>
            <button onClick={downloadPdf} disabled={!!busy}>{busy === "pdf" ? "…" : t("pl_download_pdf")}</button>
            {id && record && can(...EDITORS) && <button className="primary" onClick={saveTo} disabled={!!busy}>{busy === "save" ? "…" : kind === "well" ? t("pl_save") : t("pl_save_sac")}</button>}
          </div>
        </div>
        <div className="card">
          {d.template === "hayah_square" ? <WellFields d={d} set={set} input={input} flagSelect={flagSelect} duaSelect={duaSelect(WELL_DUA_KINDS)} upload={upload} L={L} />
            : <SacrificeFields d={d} setD={setD} set={set} input={input} flagSelect={flagSelect} duaSelect={duaSelect(SACRIFICE_DUA_KINDS)} upload={upload} L={L} />}
          <div style={{ marginTop: 12 }}>
            <Field label={t("pl_dua")} hint={t("pl_dua_hint")}><textarea dir="rtl" rows={5} value={d.dua} onChange={(e) => set("dua", e.target.value)} /></Field>
          </div>
          <details style={{ marginTop: 12 }}>
            <summary>{t("pl_more")}</summary>
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
              <Field label={t("pl_name_font")}>
                <select value={d.name_font} onChange={(e) => set("name_font", e.target.value)}>
                  <option value="Cairo">Cairo</option><option value="Amiri">Amiri</option><option value="Noto Naskh Arabic">Noto Naskh</option>
                </select>
              </Field>
              <Field label={t("pl_color")}><input type="color" value={d.name_color} onChange={(e) => set("name_color", e.target.value)} /></Field>
            </div>
          </details>
          <div className="actions">
            <button type="button" onClick={() => setD({ ...fresh(record), size: d.size })}>{id ? t("pl_reset") : t("pl_reset_blank")}</button>
          </div>
          {id && <>
            <h3 style={{ marginBottom: 6 }}>{t("pl_history")}</h3>
            {saved.length ? <ul className="timeline">{saved.map((s) => (
              <li key={s.id}><span className="muted">{fmtDate(s.created_at)} {new Date(s.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                <span><bdi className="mono" dir="ltr">{s.filename}</bdi> · {s.actor_label}{" "}
                  <button className="sm" onClick={() => { setD({ ...fresh(record), ...s.design } as Design); window.scrollTo({ top: 0, behavior: "smooth" }); }}>{t("pl_load")}</button></span></li>))}</ul>
              : <p className="muted">{t("pl_none_saved")}</p>}
          </>}
        </div>
      </div>
    </>
  );
}

type FieldProps = {
  set: (k: string, v: any) => void; input: (k: string, v: string, dir?: "rtl" | "ltr", list?: string) => JSX.Element;
  flagSelect: JSX.Element; duaSelect: JSX.Element; upload: (f: File | undefined, which: "flag" | "icon") => void;
  L: (o: { en: string; ar: string }) => string;
};

function WellFields({ d, set, input, flagSelect, duaSelect, upload, L }: FieldProps & { d: WellDesign }) {
  const { t } = useI18n();
  const icon = d.icon === "well" ? "hand_pump" : d.icon;
  return <>
    <div className="form-grid">
      <Field label={t("pl_name")}>{input("name", d.name)}</Field>
      <Field label={t("pl_project_no")}>{input("well_id", d.well_id, "ltr")}</Field>
      <Field label={t("pl_well_type")}>{input("well_type", d.well_type, "rtl", "pl-well-types")}</Field>
      <Field label={t("pl_sadaqa_label")}>{input("sadaqa_label", d.sadaqa_label, "rtl", "pl-sadaqa-labels")}</Field>
      <Field label={t("pl_month")}>{input("month", d.month)}</Field>
      {flagSelect}
      <Field label={t("pl_flag_upload")}><input type="file" accept="image/*" onChange={(e) => upload(e.target.files?.[0], "flag")} /></Field>
      {duaSelect}
      <Field label={t("pl_short_dua")}>{input("short_dua", d.short_dua)}</Field>
    </div>
    <datalist id="pl-well-types">{WELL_TYPES.map((w) => <option key={w} value={w} />)}</datalist>
    <datalist id="pl-sadaqa-labels">{["صدقة جارية عن:", "صدقة جارية إهداء إلى:", "صدقة جارية لروح:"].map((w) => <option key={w} value={w} />)}</datalist>
    <div style={{ marginTop: 12 }}>
      <label className="muted" style={{ display: "block", marginBottom: 6 }}>{t("pl_icon")}</label>
      <div className="icon-picks">
        {WELL_ICONS.map((w) => (
          <button type="button" key={w.key} className={icon === w.key ? "on" : ""} onClick={() => set("icon", w.key as IconKey)} title={L(w)}>
            <img src={`/wells/${w.key}.png`} alt="" /><span>{L(w)}</span>
          </button>))}
        {d.icon_custom && <button type="button" className={icon === "custom" ? "on" : ""} onClick={() => set("icon", "custom")}><img src={d.icon_custom} alt="" /><span>{t("pl_uploaded")}</span></button>}
        <button type="button" className={icon === "none" ? "on" : ""} onClick={() => set("icon", "none")}><span>{t("pl_none")}</span></button>
      </div>
      <div className="form-grid" style={{ marginTop: 10 }}>
        <Field label={t("pl_icon_upload")}><input type="file" accept="image/*" onChange={(e) => upload(e.target.files?.[0], "icon")} /></Field>
        <Field label={t("pl_icon_side")}>
          <select value={d.icon_side || "left"} onChange={(e) => set("icon_side", e.target.value)}>
            <option value="left">{t("pl_left")}</option><option value="right">{t("pl_right")}</option>
          </select>
        </Field>
      </div>
    </div>
  </>;
}

function SacrificeFields({ d, setD, input, flagSelect, duaSelect, upload, L }: FieldProps & { d: SacrificeDesign; setD: (fn: (x: Design) => Design) => void }) {
  const { t } = useI18n();
  return <>
    <div className="form-grid">
      <Field label={t("pl_occasion")}>
        <select value={d.occasion} onChange={(e) => setD((x) => applyOccasion(x as SacrificeDesign, e.target.value as Occasion))}>
          {(Object.keys(OCCASIONS) as Occasion[]).map((k) => <option key={k} value={k}>{L(OCCASIONS[k])}</option>)}
        </select>
      </Field>
      <Field label={t("pl_animal")}>
        <input dir="rtl" list="pl-animals" value={d.animal} onChange={(e) => {
          const animal = e.target.value;
          setD((x) => { const s = x as SacrificeDesign; return { ...s, animal, title: s.title.replace(s.animal || "\u0000", animal) }; });
        }} />
      </Field>
      <Field label={t("pl_name")}>{input("name", d.name)}</Field>
      <Field label={t("pl_sac_no")}>{input("sacrifice_no", d.sacrifice_no, "ltr")}</Field>
      <Field label={t("pl_title_line")}>{input("title", d.title)}</Field>
      <Field label={t("pl_subtitle_line")}>{input("subtitle", d.subtitle)}</Field>
      <Field label={t("pl_month")}>{input("month", d.month)}</Field>
      {flagSelect}
      <Field label={t("pl_flag_upload")}><input type="file" accept="image/*" onChange={(e) => upload(e.target.files?.[0], "flag")} /></Field>
      <Field label={t("pl_country_label")}>{input("country_label", d.country_label)}</Field>
      {duaSelect}
      <Field label={t("pl_short_dua")} hint={t("pl_short_dua_hint")}>{input("short_dua", d.short_dua)}</Field>
    </div>
    <datalist id="pl-animals">{ANIMALS.map((w) => <option key={w} value={w} />)}</datalist>
    <p className="muted" style={{ marginBottom: 0 }}>{t("pl_occasion_hint")}</p>
  </>;
}
