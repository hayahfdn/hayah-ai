// «سقيا الماء في الحرم» (Hayah, 27 Nov 2026): the list of سقيا orders with HAYAH numbers, a short form for a
// new one (the next number is filled in), and the plaque editor: live preview, every line editable,
// Haram background or an uploaded one, PNG download, save to photos and one-tap WhatsApp to the customer.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { EDITORS, MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Field, toast } from "../ui";
import { PhoneField } from "../PhoneField";
import DesignerTabs from "../plaque/DesignerTabs";
import { FONTS } from "../plaque/fonts";
import { isPhoneDevice, waLink, waProblem, WaIcon } from "../plaque/flow";
import { downloadBlob, saveToPhotos } from "../plaque/photos";
import * as I from "../icons";
import { designFor, designToSave, drawSuqya, loadSuqyaAssets, SH, SuqyaDesign, SuqyaOrder, suqyaPng, SW } from "./render";

export const DUAS = ["حفظه الله", "حفظها الله", "حفظهم الله", "رحمه الله", "رحمها الله", "رحمهم الله", "تقبل الله منه", "تقبل الله منها", "تقبل الله منهم"];
type Bg = { id: string; name: string; src: string; builtin: boolean };
type OrderForm = Pick<SuqyaOrder, "order_date" | "quantity" | "donor_name" | "dua" | "customer_name" | "customer_phone" | "customer_phone_country" | "sale_price" | "notes">;
const pickForm = (o: SuqyaOrder): OrderForm => ({ order_date: o.order_date, quantity: o.quantity, donor_name: o.donor_name, dua: o.dua,
  customer_name: o.customer_name, customer_phone: o.customer_phone, customer_phone_country: o.customer_phone_country, sale_price: o.sale_price, notes: o.notes });
const AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
const monthText = (d: string | null) => { const x = d ? new Date(d + "T00:00:00") : new Date(); return `${AR_MONTHS[x.getMonth()]} ${x.getFullYear()}`; };
const fileName = (no: number | string) => `suqya-${no}.png`;

/** Draws the plaque into a canvas that fills its box. */
export function SuqyaPreview({ d, className }: { d: SuqyaDesign; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let live = true;
    loadSuqyaAssets(d).then((a) => {
      const c = ref.current;
      if (!live || !c) return;
      c.width = SW * 1.5; c.height = SH * 1.5;
      drawSuqya(c.getContext("2d")!, d, a, 1.5);
    });
    return () => { live = false; };
  }, [d]);
  return <canvas ref={ref} className={className || "suqya-canvas"} aria-label="لوحة سقيا الماء" />;
}

/** The order fields, shared by "new" and the editor. */
function OrderFields({ f, set, no, setNo }: { f: OrderForm; set: (k: keyof OrderForm, v: any) => void; no?: number | ""; setNo?: (v: number | "") => void }) {
  const { t } = useI18n();
  const custom = !!f.dua && !DUAS.includes(f.dua);
  return (
    <div className="suqya-form">
      {setNo ? <Field label={t("sq_no")} hint={t("sq_no_hint")}><input type="number" min={1} value={no} onChange={(e) => setNo(e.target.value ? Number(e.target.value) : "")} /></Field>
        : <Field label={t("sq_no")}><input value={no} disabled /></Field>}
      <Field label={t("sq_date")}><input type="date" value={f.order_date || ""} onChange={(e) => set("order_date", e.target.value || null)} /></Field>
      <Field label={t("sq_qty")}><input type="number" min={1} value={f.quantity || ""} onChange={(e) => set("quantity", Number(e.target.value) || 0)} /></Field>
      <Field label={t("sq_price")}><input type="number" min={0} step="0.01" value={f.sale_price ?? ""} onChange={(e) => set("sale_price", e.target.value === "" ? null : Number(e.target.value))} /></Field>
      <div className="span2"><Field label={t("sq_name")} hint={t("sq_name_hint")}>
        <textarea dir="rtl" rows={2} value={f.donor_name || ""} onChange={(e) => set("donor_name", e.target.value)} /></Field></div>
      <div className="span2"><Field label={t("sq_dua")}>
        <div className="chips">
          {DUAS.map((x) => <button type="button" key={x} className={`chip${f.dua === x ? " on" : ""}`} onClick={() => set("dua", x)}>{x}</button>)}
          <button type="button" className={`chip${!f.dua ? " on" : ""}`} onClick={() => set("dua", "")}>{t("pl_none")}</button>
          <input dir="rtl" className="chip-input" placeholder={t("sq_dua_custom")} value={custom ? f.dua! : ""} onChange={(e) => set("dua", e.target.value)} />
        </div></Field></div>
      <Field label={t("sq_customer")}><input dir="rtl" value={f.customer_name || ""} onChange={(e) => set("customer_name", e.target.value)} /></Field>
      <PhoneField phone={f.customer_phone ?? ""} country={f.customer_phone_country ?? ""}
        onPhone={(v) => set("customer_phone", v)} onCountry={(v) => set("customer_phone_country", v)} />
      <div className="span2"><Field label={t("sq_notes")}><input dir="rtl" value={f.notes || ""} onChange={(e) => set("notes", e.target.value)} /></Field></div>
    </div>);
}

const EMPTY: OrderForm = { order_date: new Date().toISOString().slice(0, 10), quantity: 100, donor_name: "", dua: "حفظه الله", customer_name: "",
  customer_phone: "", customer_phone_country: "", sale_price: null, notes: "" };

/** /plaque/suqya and /plaque/suqya/:no */
export default function SuqyaPage() {
  const { no } = useParams();
  const { can } = useAuth();
  if (!can(...EDITORS)) return <ErrorBox error="403" />;
  return no ? <Editor no={no} key={no} /> : <ListAndNew />;
}

function Opener() {
  const { t } = useI18n();
  const nav = useNavigate();
  const [pick, setPick] = useState("");
  return (
    <form style={{ display: "flex", gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (pick.trim()) nav(`/plaque/suqya/${pick.trim()}`); }}>
      <input type="number" placeholder={t("sq_open")} value={pick} onChange={(e) => setPick(e.target.value)} style={{ width: 150 }} />
      <button>{t("pl_open")}</button>
    </form>);
}

function ListAndNew() {
  const { t, fmtDate, money } = useI18n();
  const nav = useNavigate();
  const [data, setData] = useState<{ items: SuqyaOrder[]; next_no: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState<OrderForm>(EMPTY);
  const [no, setNo] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const load = () => api<{ items: SuqyaOrder[]; next_no: number }>("/api/suqya", { query: { q } }).then((r) => { setData(r); setNo((n) => n || r.next_no); }).catch((e) => setError(e.message));
  useEffect(() => { const h = setTimeout(load, q ? 300 : 0); return () => clearTimeout(h); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [q]);
  useEffect(() => { if (data && !data.items.length && !q) setShowNew(true); }, [data, q]);
  const create = async () => {
    setBusy(true);
    try {
      const r = await api<SuqyaOrder>("/api/suqya", { body: { ...f, suqya_no: no || null } });
      toast(`${t("sq_created")} ${r.suqya_no}`); nav(`/plaque/suqya/${r.suqya_no}`);
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  return <>
    <div className="topbar">
      <div><span className="muted">{t("nav_plaque")}</span><h1>💧 {t("sq_title")}</h1></div>
      <div className="actions" style={{ margin: 0, flexWrap: "wrap" }}>
        <Opener />
        <button className="primary" onClick={() => setShowNew((v) => !v)}><I.Plus size={16} aria-hidden="true" /> {t("sq_new")}</button>
      </div>
    </div>
    <DesignerTabs on="suqya" />
    <ErrorBox error={error} />
    {showNew && <div className="card" style={{ marginBottom: 14 }}>
      <h2 style={{ marginTop: 0 }}>＋ {t("sq_new")}</h2>
      <OrderFields f={f} set={(k, v) => setF({ ...f, [k]: v })} no={no} setNo={setNo} />
      <div className="actions" style={{ justifyContent: "flex-start" }}>
        <button className="primary" disabled={busy || !f.donor_name?.trim()} onClick={create}>💾 {t("sq_create")}</button>
        <span className="muted" style={{ fontSize: 13 }}>{t("sq_create_help")}</span>
      </div>
    </div>}
    <div className="card">
      <div className="plaque-card-head"><h2 style={{ margin: 0 }}>{t("sq_list")}</h2>
        <input placeholder={t("sq_search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} /></div>
      {!data ? <p className="muted">{t("loading")}</p> : !data.items.length ? <p className="muted">{t("sq_empty")}</p> :
        <div className="table-wrap"><table className="table">
          <thead><tr><th>{t("sq_no")}</th><th>{t("sq_date")}</th><th>{t("sq_name")}</th><th>{t("sq_qty")}</th><th>{t("sq_customer")}</th><th>{t("sq_price")}</th><th>{t("sq_plaque")}</th></tr></thead>
          <tbody>{data.items.map((o) => (
            <tr key={o.suqya_no} className="clickable" onClick={() => nav(`/plaque/suqya/${o.suqya_no}`)}>
              <td className="mono"><Link to={`/plaque/suqya/${o.suqya_no}`}>{o.suqya_no}</Link></td>
              <td>{fmtDate(o.order_date)}</td><td>{o.donor_name || "—"}{o.dua ? <span className="muted"> · {o.dua}</span> : null}</td>
              <td>{o.quantity}</td><td>{o.customer_name || o.customer_phone || "—"}</td>
              <td>{o.sale_price != null ? money(o.sale_price) : "—"}</td>
              <td>{o.sent_at ? <span className="badge ok">✓ {t("sq_sent")}</span> : o.plaque_saved_at ? <span className="badge">{t("sq_saved_badge")}</span> : <span className="muted">—</span>}</td>
            </tr>))}</tbody>
        </table></div>}
    </div>
  </>;
}

/** Shrinks a picked image in the browser before it is stored (long side 1600 px, JPEG). */
async function shrink(file: File): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const im = await new Promise<HTMLImageElement>((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
    const r = Math.min(1, 1600 / Math.max(im.width, im.height));
    const c = document.createElement("canvas"); c.width = Math.round(im.width * r); c.height = Math.round(im.height * r);
    c.getContext("2d")!.drawImage(im, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.88);
  } finally { URL.revokeObjectURL(url); }
}

function Editor({ no }: { no: string }) {
  const { t, lang, fmtDate } = useI18n();
  const { can } = useAuth();
  const nav = useNavigate();
  const [o, setO] = useState<SuqyaOrder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [f, setF] = useState<OrderForm | null>(null);
  const [ds, setDs] = useState<Partial<SuqyaDesign>>({});
  const [bgs, setBgs] = useState<Bg[]>([]);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [more, setMore] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const take = (r: SuqyaOrder) => { setO(r); setF(pickForm(r)); setDs(r.design || {}); setDirty(false); };
  useEffect(() => { api<SuqyaOrder>(`/api/suqya/${no}`).then(take).catch((e) => setError(e.message)); }, [no]);
  useEffect(() => { api<Bg[]>("/api/suqya/backgrounds").then(setBgs).catch(() => {}); }, []);
  const design = useMemo<SuqyaDesign | null>(() => {
    if (!o || !f) return null;
    const d = designFor({ ...o, ...f, quantity: f.quantity || o.quantity, design: ds, month_text: monthText(f.order_date) });
    const bg = bgs.find((b) => b.id === d.bg);
    return { ...d, month_text: ds.month_text ?? monthText(f.order_date), bg_src: bg?.src };
  }, [o, f, ds, bgs]);
  if (error) return <><DesignerTabs on="suqya" /><ErrorBox error={error} /></>;
  if (!o || !f || !design) return <p className="muted">{t("loading")}</p>;
  const setOrder = (k: keyof OrderForm, v: any) => { setF({ ...f, [k]: v }); setDirty(true); };
  const setD = (k: keyof SuqyaDesign, v: any) => { setDs({ ...ds, [k]: v }); setDirty(true); };
  const save = async (quiet = false) => {
    setSaving(true);
    try {
      await api(`/api/suqya/${no}`, { method: "PATCH", body: f });
      take(await api<SuqyaOrder>(`/api/suqya/${no}/design`, { method: "PUT", body: { design: designToSave(design) } }));
      if (!quiet) toast(t("sq_saved"));
      return true;
    } catch (e: any) { toast(e.message); return false; } finally { setSaving(false); }
  };
  const upload = async (file: File) => {
    try {
      const data_url = await shrink(file);
      const item = await api<Bg>("/api/suqya/backgrounds", { body: { name: file.name.replace(/\.[^.]+$/, "").slice(0, 80) || "background", data_url } });
      setBgs([...bgs, item]); setD("bg", item.id); toast(t("sq_bg_added"));
    } catch (e: any) { toast(e.message); }
  };
  const del = async () => {
    if (!window.confirm(t("sq_delete_q"))) return;
    try { await api(`/api/suqya/${no}`, { method: "DELETE" }); nav("/plaque/suqya"); } catch (e: any) { toast(e.message); }
  };
  const txt = (k: keyof SuqyaDesign, label: string, dir: "rtl" | "ltr" = "rtl") => (
    <Field key={k} label={label}><input dir={dir} value={String(design[k] ?? "")} onChange={(e) => setD(k, e.target.value)} /></Field>);
  return <>
    <div className="topbar">
      <div><Link to="/plaque/suqya" className="muted">‹ {t("sq_title")}</Link><h1>💧 {t("sq_plaque")} · <span className="mono">{no}</span></h1></div>
      <div className="actions" style={{ margin: 0, flexWrap: "wrap" }}>
        <Opener />
        <SuqyaSend o={o} f={f} design={design} before={() => (dirty ? save(true) : Promise.resolve(true))} onSent={take} />
        <button onClick={async () => downloadBlob(await suqyaPng(design, 2), fileName(no))}>⬇ {t("pl_download_png")}</button>
        <PhotosBtn design={design} no={no} />
        <button className="primary" disabled={saving} onClick={() => save()}>💾 {t("save")}</button>
      </div>
    </div>
    <DesignerTabs on="suqya" />
    <div className="suqya-editor">
      <div className="card suqya-preview-card"><SuqyaPreview d={design} />
        <p className="muted" style={{ fontSize: 12.5, margin: "8px 2px 0" }}>
          {o.plaque_saved_at ? `${t("sq_saved_badge")}: ${fmtDate(o.plaque_saved_at)} · ${o.plaque_saved_by || ""}` : t("sq_not_saved")}
          {o.sent_at && <> · ✓ {t("sq_sent")} {fmtDate(o.sent_at)}</>}
          {dirty && <> · <b>{t("ct_unsaved")}</b></>}</p>
      </div>
      <div>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>{t("sq_order")}</h2>
          <OrderFields f={f} set={setOrder} no={o.suqya_no} />
        </div>
        <div className="card" style={{ marginTop: 14 }}>
          <h2 style={{ marginTop: 0 }}>{t("sq_bg")}</h2>
          <div className="suqya-bgs">
            {bgs.map((b) => <button type="button" key={b.id} className={`suqya-bg${design.bg === b.id ? " on" : ""}`} onClick={() => setD("bg", b.id)} title={b.name}>
              <img src={b.src} alt="" /><span>{b.name}</span></button>)}
            <button type="button" className="suqya-bg add" onClick={() => fileRef.current?.click()}><I.Upload size={22} aria-hidden="true" /><span>{t("sq_bg_upload")}</span></button>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => { const x = e.target.files?.[0]; if (x) upload(x); e.target.value = ""; }} />
          </div>
          <p className="muted" style={{ fontSize: 12.5 }}>{t("sq_bg_help")}</p>
          <div className="suqya-form">
            <Field label={t("pl_name_font")}>
              <select value={design.name_font} onChange={(e) => setD("name_font", e.target.value)} style={{ fontFamily: `'${design.name_font}'` }}>
                {FONTS.map((x) => <option key={x.family} value={x.family} style={{ fontFamily: `'${x.family}'` }}>{lang === "ar" ? `${x.ar} · ${x.en}` : `${x.en} · ${x.ar}`}</option>)}
              </select></Field>
            <Field label={`${t("cert_f_names_size")} (${design.name_size}%)`}>
              <input type="range" min={60} max={130} step={5} value={design.name_size} onChange={(e) => setD("name_size", Number(e.target.value))} /></Field>
          </div>
          <button type="button" className="sm" onClick={() => setMore(!more)}>{more ? "▾" : "▸"} {t("pl_more")}</button>
          {more && <div className="suqya-form" style={{ marginTop: 10 }}>
            {txt("intro", t("sq_f_intro"))}{txt("hadith", t("sq_f_hadith"))}{txt("number_label", t("pl_number_label"))}{txt("month_text", t("pl_month"))}
            {txt("qty_before", t("sq_f_qty_before"))}{txt("qty_after", t("sq_f_qty_after"))}{txt("sadaqa_label", t("pl_sadaqa_label"))}
            {txt("footer", t("pl_footer_org"))}{txt("site", t("pl_footer_site"), "ltr")}
            <label className="check"><input type="checkbox" checked={design.show_logo} onChange={(e) => setD("show_logo", e.target.checked)} /> {t("sq_f_logo")}</label>
            <div className="span2"><button type="button" className="sm" onClick={() => { setDs({ bg: ds.bg }); setDirty(true); }}>↺ {t("sq_reset")}</button></div>
          </div>}
        </div>
        <p className="muted" style={{ fontSize: 12.5 }}>{t("sq_send_help")}</p>
        {can(...MANAGERS) && <button type="button" className="sm danger" onClick={del}>🗑 {t("sq_delete")}</button>}
      </div>
    </div>
  </>;
}

function PhotosBtn({ design, no }: { design: SuqyaDesign; no: string }) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setFile(null);
    const h = window.setTimeout(() => suqyaPng(design, 2).then((b) => setFile(new File([b], fileName(no), { type: "image/png" }))).catch(() => {}), 600);
    return () => window.clearTimeout(h);
  }, [design, no]);
  const go = async () => {
    setBusy(true);
    try {
      const fl = file || new File([await suqyaPng(design, 2)], fileName(no), { type: "image/png" });
      const r = await saveToPhotos(fl);
      if (r === "shared") toast(t("pl_photos_shared")); else if (r === "downloaded") toast(t("pl_photos_downloaded"));
      else if (r === "tap_again") { setFile(fl); toast(t("cert_tap_again")); }
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  return <button type="button" onClick={go} disabled={busy} title={t("pl_save_photos")}><I.Images size={16} aria-hidden="true" /> {busy ? t("pl_saving_photos") : t("pl_save_photos")}</button>;
}

/** One tap: the plaque to the customer's WhatsApp. Phone: share sheet with the PNG. Computer: WhatsApp Web
 *  opens on the customer's chat and the PNG downloads to attach. Nothing is sent automatically. */
function SuqyaSend({ o, f, design, before, onSent }: { o: SuqyaOrder; f: OrderForm; design: SuqyaDesign; before: () => Promise<boolean>; onSent: (o: SuqyaOrder) => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState<File | null>(null);
  useEffect(() => setReady(null), [design]);
  const phoneChanged = (f.customer_phone || "") !== (o.customer_phone || "") || (f.customer_phone_country || "") !== (o.customer_phone_country || "");
  const why = phoneChanged ? t("sq_save_phone_first") : waProblem(t, o.customer_phone_e164, o.customer_phone_status);
  const text = `${t("sq_msg")} ${o.suqya_no}\n${t("sq_msg_end")}`;
  const logged = (method: "share" | "download") => api<SuqyaOrder>(`/api/suqya/${o.suqya_no}/sent`, { body: { method } }).then(onSent).catch(() => {});
  const go = async () => {
    const nav: any = navigator;
    const phone = isPhoneDevice() && !!nav.canShare;
    if (phone && ready) {
      try { await nav.share({ files: [ready], text }); setReady(null); logged("share"); } catch (e: any) { if (e?.name !== "AbortError") toast(e.message); }
      return;
    }
    const link = waLink(o.customer_phone_e164, text);
    if (!phone && link) window.open(link, "_blank", "noopener");
    setBusy(true);
    try {
      if (!(await before())) return;
      const fl = new File([await suqyaPng(design, 2)], fileName(o.suqya_no), { type: "image/png" });
      if (phone && nav.canShare({ files: [fl] })) {
        try { await nav.share({ files: [fl], text }); logged("share"); }
        catch (e: any) { if (e?.name !== "AbortError") { setReady(fl); toast(t("cert_tap_again")); } }
        return;
      }
      if (phone && link) window.location.href = link;
      downloadBlob(fl, fl.name); toast(t("cert_done_dl")); logged("download");
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const label = busy ? t("cert_preparing") : ready ? t("cert_tap_again") : t("sq_send");
  return (
    <span className="wa-wrap">
      <button type="button" className={`wa-btn${ready ? " primary" : ""}`} disabled={!!why || busy} onClick={go} title={why || t("sq_send_help")} aria-label={label}>
        <WaIcon /><span>{label}</span></button>
      {why && <span className="wa-why">⚠ {why}</span>}
    </span>);
}
