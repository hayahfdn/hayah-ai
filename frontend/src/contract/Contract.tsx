// «صيغة عقد» page: /plaque/contract/:kind/:no — the official contract and invoice for a well or a
// sacrifice, filled from the order, every line editable, live preview, save, PNG, PDF, photos and
// WhatsApp. The invoice number is given by the server on the first save and never changes.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { EDITORS, MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Field, toast } from "../ui";
import { FONTS } from "../plaque/fonts";
import DesignerTabs from "../plaque/DesignerTabs";
import { downloadBlob, saveToPhotos } from "../plaque/photos";
import { isPhoneDevice, waLink, WaIcon } from "../plaque/flow";
import * as I from "../icons";
import { ContractData, ContractDesign, contractPdf, contractPng, defaultContract, drawContract, KH, KW, loadContractAssets } from "./render";

type Kind = "well" | "sacrifice";

function Preview({ d, invoice }: { d: ContractDesign; invoice: string | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let live = true;
    loadContractAssets(d).then((a) => {
      const c = ref.current;
      if (!live || !c) return;
      const s = Math.max(1, Math.min(2, (c.clientWidth * (window.devicePixelRatio || 1)) / KW));
      c.width = Math.round(KW * s); c.height = Math.round(KH * s);
      drawContract(c.getContext("2d")!, d, { invoice }, a, s);
    });
    return () => { live = false; };
  }, [d, invoice]);
  return <canvas ref={ref} className="contract-canvas" aria-label="صيغة عقد" />;
}

const FIELDS: [keyof ContractDesign, string, "text" | "area" | "ltr"][] = [
  ["project_no", "ct_f_no", "ltr"], ["project_type", "ct_f_type", "text"], ["owner", "ct_f_owner", "text"],
  ["contract_date", "ct_f_date", "text"], ["expected_delivery", "ct_f_delivery", "text"], ["delivery_note", "ct_f_delivery_note", "area"],
  ["amount", "ct_f_amount", "ltr"], ["currency", "ct_f_currency", "ltr"], ["amount_words", "ct_f_words", "text"],
  ["specs", "ct_f_specs", "area"], ["hayah_phone", "ct_f_phone", "ltr"], ["site", "ct_f_site", "ltr"],
  ["title", "ct_f_title", "text"], ["subtitle", "ct_f_subtitle", "text"], ["terms", "ct_f_terms", "area"],
];

export default function ContractPage() {
  const { kind: rawKind, no } = useParams();
  const kind: Kind = rawKind === "sacrifice" ? "sacrifice" : "well";
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const nav = useNavigate();
  const [data, setData] = useState<ContractData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [d, setD] = useState<ContractDesign | null>(null);
  const [savedJson, setSavedJson] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [pickKind, setPickKind] = useState<Kind>(kind);
  const [pick, setPick] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);

  const fill = (c: ContractData) => {
    const full = { ...defaultContract(c), ...(c.design || {}) } as ContractDesign;
    if (!full.hayah_phone) full.hayah_phone = c.hayah_phone || "";  // Settings fills it once it is set
    setData(c); setD(full); setSavedJson(c.design ? JSON.stringify(full) : "");
  };
  useEffect(() => {
    setData(null); setD(null); setError(null);
    if (!no) return;
    api<ContractData>(`/api/contracts/${kind}/${no}`).then(fill).catch((e) => setError(e.message));
  }, [kind, no]);

  const dirty = useMemo(() => !!d && (!data?.invoice_no || JSON.stringify(d) !== savedJson), [d, data, savedJson]);
  const invoice = data?.invoice_no || null;
  const fileBase = `contract-${kind === "well" ? "well" : "sacrifice"}-${no}`;
  // The image for «حفظ في معرض الصور», made in advance once the contract is saved (so the share opens from the tap).
  useEffect(() => {
    setPhoto(null);
    if (!d || dirty) return;
    const h = window.setTimeout(() => contractPng(d, { invoice }).then((b) => setPhoto(new File([b], `${fileBase}.png`, { type: "image/png" }))).catch(() => {}), 500);
    return () => window.clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, dirty, invoice]);

  if (!can(...EDITORS)) return <ErrorBox error="403" />;
  const opener = (
    <form style={{ display: "flex", gap: 8, flexWrap: "wrap" }} onSubmit={(e) => { e.preventDefault(); if (pick.trim()) nav(`/plaque/contract/${pickKind}/${pick.trim()}`); }}>
      <select value={pickKind} onChange={(e) => setPickKind(e.target.value as Kind)} aria-label={t("ct_kind")}>
        <option value="well">{t("ct_kind_well")}</option><option value="sacrifice">{t("ct_kind_sac")}</option></select>
      <input type="number" placeholder={pickKind === "well" ? t("pl_open_well") : t("pl_open_sac")} value={pick} onChange={(e) => setPick(e.target.value)} style={{ width: 150 }} />
      <button>{t("pl_open")}</button>
    </form>);
  const tabs = <DesignerTabs on="contract" wellId={kind === "well" ? no : undefined} sacNo={kind === "sacrifice" ? no : undefined} />;
  if (!no) return <>
    <div className="topbar"><div><span className="muted">{t("nav_plaque")}</span><h1>📄 {t("ct_title")}</h1></div>{opener}</div>
    {tabs}<p className="muted">{t("ct_pick")}</p></>;
  if (error) return <>{tabs}<ErrorBox error={error} /></>;
  if (!data || !d) return <>{tabs}<p className="muted">{t("loading")}</p></>;

  const set = (k: keyof ContractDesign, v: any) => setD({ ...d, [k]: v });
  /** Saves when something changed (the first save gives the invoice number). Returns the invoice. */
  const ensure = async (): Promise<string | null> => {
    if (!dirty) return invoice;
    const r = await api<ContractData>(`/api/contracts/${kind}/${no}`, { method: "PUT", body: { design: d } });
    setData(r); setSavedJson(JSON.stringify(d));
    return r.invoice_no;
  };
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try { await fn(); } catch (e: any) { toast(e.message || String(e)); } finally { setBusy(null); }
  };
  const save = () => run("save", async () => { const inv = await ensure(); toast(`${t("ct_saved")} ${inv || ""}`); });
  const png = () => run("png", async () => { const inv = await ensure(); downloadBlob(await contractPng(d, { invoice: inv }), `${fileBase}.png`); });
  const pdf = () => run("pdf", async () => { const inv = await ensure(); downloadBlob(await contractPdf(d, { invoice: inv }), `${fileBase}.pdf`); });
  const photos = () => run("photos", async () => {
    const inv = await ensure();
    const f = photo || new File([await contractPng(d, { invoice: inv })], `${fileBase}.png`, { type: "image/png" });
    const r = await saveToPhotos(f);
    if (r === "shared") toast(t("pl_photos_shared"));
    else if (r === "downloaded") toast(t("pl_photos_downloaded"));
    else if (r === "tap_again") { setPhoto(f); toast(t("cert_tap_again")); }
  });
  const phone = data.facts.owner_phone;
  const text = `${t("ct_msg")} ${d.project_no}\n${t("cert_msg_end")}`;
  const whatsapp = () => run("wa", async () => {
    const link = waLink(phone && phone.startsWith("+") ? phone : null, text);
    const onPhone = isPhoneDevice() && !!(navigator as any).canShare;
    if (!onPhone && link) window.open(link, "_blank", "noopener");
    const inv = await ensure();
    const f = new File([await contractPdf(d, { invoice: inv })], `${fileBase}.pdf`, { type: "application/pdf" });
    if (onPhone && (navigator as any).canShare({ files: [f] })) {
      try { await (navigator as any).share({ files: [f], text }); return; }
      catch (e: any) { if (e?.name === "AbortError") return; toast(t("cert_tap_again")); return; }
    }
    downloadBlob(f, f.name); toast(t("cert_done_dl"));
  });

  return <>
    <div className="topbar">
      <div>
        {kind === "well" ? <Link to={`/projects/${no}`} className="muted">‹ {t("well_id")} {no}</Link> : <span className="muted">{t("ct_kind_sac")} {no}</span>}
        <h1>📄 {t("ct_title")} · <span className="mono">{no}</span></h1>
      </div>
      {opener}
    </div>
    {tabs}
    <div className="cert-editor contract-editor">
      <div className="card cert-preview-card">
        <Preview d={d} invoice={invoice} />
        <div className="pl-actbar">
          <button type="button" className="act-btn primary" onClick={save} disabled={!!busy}><I.CircleCheck size={18} aria-hidden="true" /><span>{busy === "save" ? "…" : t("save")}</span></button>
          <button type="button" className="act-btn" onClick={pdf} disabled={!!busy}><I.ScrollText size={18} aria-hidden="true" /><span>{busy === "pdf" ? "…" : "PDF"}</span></button>
          <button type="button" className="act-btn" onClick={png} disabled={!!busy}><I.Download size={18} aria-hidden="true" /><span>{busy === "png" ? "…" : "PNG"}</span></button>
          <button type="button" className="act-btn" onClick={photos} disabled={!!busy}><I.Images size={18} aria-hidden="true" /><span>{busy === "photos" ? "…" : t("pl_save_photos")}</span></button>
          <button type="button" className="act-btn wa" onClick={whatsapp} disabled={!!busy} title={t("ct_wa_help")}><WaIcon /><span>{busy === "wa" ? "…" : t("tile_wa")}</span></button>
        </div>
      </div>
      <div className="card">
        <div className="ct-meta">
          <span className={`badge ${invoice ? "ok" : "info"}`}>{t("ct_invoice")}: <b dir="ltr">{invoice || t("ct_invoice_new")}</b></span>
          {dirty && invoice && <span className="badge warn">{t("ct_unsaved")}</span>}
        </div>
        <p className="muted" style={{ marginTop: 6 }}>{t("ct_help")}</p>
        {!d.hayah_phone && <p className="missing">⚠ {t("ct_no_phone")} {can(...MANAGERS) && <Link to="/settings#contract">{t("ct_to_settings")}</Link>}</p>}
        {!d.expected_delivery.trim() && <p className="missing">⚠ {t("ct_delivery_empty")}</p>}
        {!data.facts.amount && <p className="missing">⚠ {t("ct_no_amount")}</p>}
        <div className="cert-form">
          {FIELDS.map(([k, label, type]) => (
            <Field key={k} label={t(label)}>{type === "area"
              ? <textarea dir="rtl" rows={k === "terms" ? 5 : k === "delivery_note" ? 2 : 4} value={String(d[k] ?? "")} onChange={(e) => set(k, e.target.value)} />
              : <input dir={type === "ltr" ? "ltr" : "rtl"} value={String(d[k] ?? "")} onChange={(e) => set(k, e.target.value)} />}</Field>))}
          <Field label={t("ct_f_font")}>
            <select value={d.names_font} onChange={(e) => set("names_font", e.target.value)} style={{ fontFamily: `'${d.names_font}'` }}>
              {FONTS.map((f) => <option key={f.family} value={f.family} style={{ fontFamily: `'${f.family}'` }}>{lang === "ar" ? `${f.ar} · ${f.en}` : `${f.en} · ${f.ar}`}</option>)}
            </select></Field>
          <Field label={`${t("ct_f_size")} (${d.names_size}%)`}>
            <input type="range" min={60} max={140} step={5} value={d.names_size} onChange={(e) => set("names_size", Number(e.target.value))} /></Field>
          <label className="check"><input type="checkbox" checked={d.show_terms} onChange={(e) => set("show_terms", e.target.checked)} /> {t("ct_f_show_terms")}</label>
          <label className="check"><input type="checkbox" checked={d.show_stamp} onChange={(e) => set("show_stamp", e.target.checked)} /> {t("cert_f_stamp")}</label>
        </div>
        <div className="actions" style={{ justifyContent: "flex-start" }}>
          <button onClick={() => setD(defaultContract(data))}>↺ {t("cert_reset")}</button>
        </div>
      </div>
    </div>
  </>;
}
