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
  DUAS, Align, textStyle,
} from "./render";
import { FONTS } from "./fonts";
import { MissingList, PlaqueActions, PlaqueRow, PlaqueStatusBadge, PlaqueWhatsApp } from "./flow";

type Kind = "well" | "sacrifice";
interface Saved { id: string; created_at: string; actor_label: string; filename: string; design: Design; version?: number; approved?: boolean; media_id?: number | null; }

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
      if (e.status === 409 && !replace) { setConfirm(() => () => approve(true)); return; }
      throw e;
    }
    toast(t("plaque_approved_ok")); refreshCounts();
    load();
  });
  const approveVersion = (s: Saved, replace = false) => run("v" + s.id, async () => {
    try { await api(`/api/projects/${id}/plaques/${s.id}/approve`, { method: "POST", query: { replace } }); }
    catch (e: any) {
      if (e.status === 409 && !replace) { setConfirm(() => () => approveVersion(s, true)); return; }
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
      <div className="plaque-layout">
        <div className="card plaque-preview">
          <canvas ref={canvas} aria-label={t("pl_preview")} style={{ aspectRatio: `${GRIDS[d.template][0]} / ${GRIDS[d.template][1]}` }} />
          <div className="actions" style={{ flexWrap: "wrap" }}>
            <select value={d.size} onChange={(e) => set("size", e.target.value as SizeKey)} aria-label={t("pl_size")}>
              {(Object.keys(SIZES) as SizeKey[]).map((k) => <option key={k} value={k}>{sizeLabel(k, d.template, lang)}</option>)}
            </select>
            <button onClick={downloadPng} disabled={!!busy}>{busy === "png" ? "…" : t("pl_download_png")}</button>
            <button onClick={downloadPdf} disabled={!!busy}>{busy === "pdf" ? "…" : t("pl_download_pdf")}</button>
            {id && record && can(...EDITORS) && kind === "well" && <>
              <button onClick={saveTo} disabled={!!busy}>{busy === "save" ? "…" : t("plaque_save_draft")}</button>
              <button className="primary" onClick={() => approve()} disabled={!!busy}>{busy === "approve" ? "…" : `✓ ${t("plaque_approve")}`}</button>
            </>}
            {id && record && can(...EDITORS) && kind === "sacrifice" && <>
              <button onClick={saveTo} disabled={!!busy}>{busy === "save" ? "…" : t("pl_save_sac")}</button>
              <button className="primary" onClick={() => approve(true)} disabled={!!busy || !!flow?.missing.length}>{busy === "approve" ? "…" : `✓ ${t("pl_approve_sac")}`}</button>
            </>}
          </div>
        </div>
        <div className="card">
          {d.template === "hayah_square" ? <WellFields d={d} set={set} input={input} flagSelect={flagSelect} duaSelect={duaSelect(WELL_DUA_KINDS)} upload={upload} L={L} />
            : <SacrificeFields d={d} setD={setD} set={set} input={input} flagSelect={flagSelect} duaSelect={duaSelect(SACRIFICE_DUA_KINDS)} upload={upload} L={L} />}
          {d.dua_sure === false && <div className="error" role="alert" style={{ marginTop: 12 }}>{t("pl_dua_unsure")}</div>}
          <TextControls d={d} set={set} />
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

/** The order this plaque belongs to: filled in automatically, shown so the designer can check it. */
function OrderBox({ p }: { p: Project }) {
  const { t, lang, fmtDate } = useI18n();
  const row = (k: string, v: any) => <div key={k}><span>{t(k)}</span>{v || "—"}</div>;
  return (
    <div className="card order-box" style={{ marginBottom: 14, background: p.contractor?.color || undefined }}>
      <div className="plaque-card-head"><h2 style={{ margin: 0 }}>{t("plaque_order_data")}</h2></div>
      <div className="dl">
        {row("well_id", <b className="well-no">{p.well_id}</b>)}{row("customer_name", p.customer_name)}{row("well_type", p.well_type)}
        {row("contractor", p.contractor ? `${p.contractor.name} (${p.contractor.code})` : null)}
        {row("country", p.contractor?.country ? countryLabel(p.contractor.country, lang) : p.country)}
        {row("order_date", fmtDate(p.order_date))}{row("shopify_order", p.shopify_order)}
        {row("construction_status", <Status v={p.construction_status} />)}
      </div>
      {p.dedication && <p style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}><span className="muted">{t("dedication")}: </span><b>{p.dedication}</b></p>}
      <p className="muted" style={{ marginBottom: 0, fontSize: 12.5 }}>{t("plaque_order_help")}</p>
    </div>
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

/** Font, size, line spacing, alignment and weight for the name and the prayer. Every font in the
 * list is shown in its own face; the files are bundled, so the export matches the preview. */
function TextControls({ d, set }: { d: Design; set: (k: string, v: any) => void }) {
  const { t, lang } = useI18n();
  const block = (which: "name" | "dua") => {
    const st = textStyle(d, which);
    const k = (f: string) => `${which}_${f}`;
    return (
      <fieldset className="text-controls" key={which}>
        <legend>{t(which === "name" ? "pl_text_name" : "pl_text_dua")}</legend>
        <div className="form-grid">
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
        <p className="font-sample" dir="rtl" style={{ fontFamily: `'${st.family}'`, fontWeight: st.weight }}>
          {which === "name" ? (d.name || "فاعل خير") : "اللهم تقبل منه واجعلها صدقة مباركة"}</p>
      </fieldset>
    );
  };
  return <div style={{ marginTop: 12 }}>{block("name")}{block("dua")}<p className="muted" style={{ fontSize: 12.5 }}>{t("pl_font_note")}</p></div>;
}
