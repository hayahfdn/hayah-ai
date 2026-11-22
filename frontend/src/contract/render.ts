// «صيغة عقد»: HAYAH's official contract and invoice for a well or a sacrifice, on one A4 page
// (1240 × 1754 grid = 150 dpi; exported at 2× for print). Drawn on a canvas, rule-based, like the
// plaques and the certificate. Shows only what the customer should see: the amount received is the
// selling price; cost and profit are never part of it.
import { cssFamily, ensureFont, weightFor } from "../plaque/fonts";
import { canvasPdf, flagArabic, flagFor, loadImage, MONTHS_AR, plaqueName, plaqueTypeLabel } from "../plaque/render";

export const KW = 1240, KH = 1754;

export interface ContractFacts {
  number: number; owner: string | null; dedication: string | null; amount: string | null; currency: string;
  country: string | null; order_date: string | null; owner_phone: string | null;
  extras: string | null; well_type?: string | null; animal_type?: string | null; intention?: string | null;
}
export interface ContractData {
  kind: "well" | "sacrifice"; facts: ContractFacts; hayah_phone: string; invoice_no: string | null; issued_at: string | null;
  design: Partial<ContractDesign> | null; saved_at: string | null; saved_by: string | null;
}
export interface ContractDesign {
  title: string; subtitle: string; project_no: string; project_type: string; owner: string; owner_phone: string;
  specs: string; amount: string; currency: string; amount_words: string; contract_date: string; expected_delivery: string; delivery_note: string;
  terms: string; hayah_phone: string; site: string; names_font: string; names_size: number; show_stamp: boolean; show_terms: boolean;
}

export function dateAr(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  if (isNaN(d.getTime())) return iso;
  return `${d.getDate()} ${MONTHS_AR[d.getMonth()]} ${d.getFullYear()}`;
}
const money = (v: string | null) => {
  const n = Number(v);
  return v == null || v === "" || isNaN(n) ? "" : n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const TERMS = [
  "تلتزم مؤسسة حياة بتنفيذ المشروع وفق المواصفات المذكورة أعلاه، بإشراف فريقها في بلد التنفيذ.",
  "يُزوَّد صاحب المشروع بصور ومقطع فيديو للتنفيذ عند الانتهاء، عبر رقم الهاتف المسجل لدينا.",
  "التاريخ المتوقع للتسليم تقديري، وقد يتأخر لظروف خارجة عن الإرادة (الطقس، تصاريح الجهات الرسمية، طبيعة الأرض)، مع إبلاغ صاحب المشروع بذلك.",
  "تُعد هذه الوثيقة إثباتاً رسمياً لاستلام المبلغ المذكور أعلاه.",
].join("\n");

// Hayah's wording (22 Nov 2026), printed under the expected delivery date.
export const DELIVERY_NOTE = "قد تزيد مدة التنفيذ حسب الظروف الجوية والأوضاع السياسية في مناطق التنفيذ وهذا التاريخ تقديري بناءاً على مشاريعنا السابقة.";

export function defaultContract(c: ContractData): ContractDesign {
  const f = c.facts;
  const country = flagArabic(flagFor(f.country)) || f.country || "";
  const specs: string[] = [];
  let type: string;
  if (c.kind === "well") {
    const wt = plaqueTypeLabel(f.well_type) || "بئر مياه";
    type = `حفر ${wt}`;
    specs.push(`نوع البئر: ${wt}`);
    if (country) specs.push(`بلد التنفيذ: ${country}`);
    if (f.extras) specs.push(`الإضافات: ${f.extras.replace(/\s*,\s*/g, "، ")}`);
    const nm = plaqueName(f.dedication || f.owner);
    specs.push(nm ? `لوحة تذكارية باسم: ${nm.replace(/\n/g, " و ")}` : "لوحة تذكارية باسم المتبرع");
    specs.push("توثيق التنفيذ بالصور والفيديو، وشهادة وقفية باسم المتبرع");
  } else {
    const animal = f.animal_type || "خروف";
    const intent = (f.intention || "صدقة").trim();
    type = `ذبيحة ${intent} (${animal})`;
    specs.push(`نوع الذبيحة: ${animal}`, `النية: ${intent}`);
    if (f.extras) specs.push(`الإضافات: ${f.extras.replace(/\s*,\s*/g, "، ")}`);
    specs.push(country ? `الذبح وتوزيع اللحم على المستحقين في ${country}` : "الذبح وتوزيع اللحم على المستحقين");
    specs.push("توثيق الذبح بالصور والفيديو، ولوحة باسم صاحب الذبيحة");
  }
  return {
    title: "عقد تنفيذ مشروع خيري", subtitle: "وفاتورة استلام مبلغ", project_no: String(f.number), project_type: type,
    owner: (f.owner || "").trim() || "فاعل خير", owner_phone: f.owner_phone || "", specs: specs.join("\n"),
    amount: money(f.amount), currency: f.currency || "USD", amount_words: "",
    contract_date: dateAr(c.issued_at || new Date().toISOString().slice(0, 10)), expected_delivery: "", delivery_note: DELIVERY_NOTE,
    terms: TERMS, hayah_phone: c.hayah_phone || "", site: "HayahFoundation.com", names_font: "Cairo", names_size: 100,
    show_stamp: true, show_terms: true,
  };
}

const BLUE = "#2f6fb0", BLUE_D = "#1f4f86", INK = "#1d2b3a", MUTED = "#6b7a8c", GOLD = "#b48a46", LINE = "#d6e2ef", SOFT = "#f3f7fb", FONT = "Cairo";
type Ctx = CanvasRenderingContext2D;
const font = (ctx: Ctx, w: number, px: number, fam = FONT) => { ctx.font = `${w} ${px}px ${cssFamily(fam)}`; };

export interface ContractAssets { logo: HTMLImageElement | null; stamp: HTMLImageElement | null }
export async function loadContractAssets(d: ContractDesign): Promise<ContractAssets> {
  await Promise.all([400, 600, 700, 800].map((w) => ensureFont(FONT, w)));
  if (d.names_font && d.names_font !== FONT) await ensureFont(d.names_font, weightFor(d.names_font, true));
  const [logo, stamp] = await Promise.all([loadImage("/hayah-logo.png"), loadImage("/certificate-stamp.png")]);
  return { logo, stamp };
}

function rr(ctx: Ctx, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function fitPx(ctx: Ctx, s: string, w: number, max: number, width: number, fam = FONT, min = 16) {
  let px = max;
  for (; px > min; px -= 1) { font(ctx, w, px, fam); if (ctx.measureText(s).width <= width) break; }
  return px;
}
function wrap(ctx: Ctx, text: string, maxW: number): string[] {
  const out: string[] = [];
  for (const para of text.split(/\n/)) {
    let line = "";
    for (const w of para.split(/\s+/).filter(Boolean)) {
      const t = line ? `${line} ${w}` : w;
      if (ctx.measureText(t).width > maxW && line) { out.push(line); line = w; } else line = t;
    }
    if (line) out.push(line);
  }
  return out;
}

/** meta: the invoice number and issue date given by the server on the first save. */
export function drawContract(ctx: Ctx, d: ContractDesign, meta: { invoice: string | null }, a: ContractAssets, scale = 1) {
  ctx.save(); ctx.scale(scale, scale);
  ctx.textBaseline = "alphabetic"; (ctx as any).direction = "rtl";
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, KW, KH);
  const M = 70, R = KW - M, L = M, W = R - L;

  // top band and frame
  const g = ctx.createLinearGradient(0, 0, KW, 0); g.addColorStop(0, BLUE_D); g.addColorStop(1, BLUE);
  ctx.fillStyle = g; ctx.fillRect(0, 0, KW, 16);
  ctx.strokeStyle = LINE; ctx.lineWidth = 2; rr(ctx, 30, 40, KW - 60, KH - 80, 14); ctx.stroke();

  // header: logo and organisation (right), invoice box (left)
  let lw = 0;
  if (a.logo) { const h = 150; lw = (a.logo.width / a.logo.height) * h; ctx.drawImage(a.logo, R - lw, 62, lw, h); }
  ctx.textAlign = "right"; ctx.fillStyle = INK;
  const ox = R - lw - 24;
  font(ctx, 800, 40); ctx.fillText("مؤسسة حياة للمشاريع التنموية", ox, 125);
  ctx.fillStyle = MUTED; (ctx as any).direction = "ltr"; ctx.textAlign = "right"; font(ctx, 600, 24);
  ctx.fillText("Hayah Foundation for Development Projects", ox, 165);
  (ctx as any).direction = "rtl";
  const bw = 330, bh = 150, bx = L, by = 62;
  ctx.fillStyle = SOFT; rr(ctx, bx, by, bw, bh, 16); ctx.fill(); ctx.strokeStyle = BLUE; ctx.lineWidth = 2; ctx.stroke();
  ctx.textAlign = "center"; ctx.fillStyle = BLUE; font(ctx, 800, 30); ctx.fillText("فاتورة رقم", bx + bw / 2, by + 44);
  ctx.fillStyle = INK; (ctx as any).direction = "ltr";
  const inv = meta.invoice || "—";
  font(ctx, 800, fitPx(ctx, inv, 800, 40, bw - 30)); ctx.fillText(inv, bx + bw / 2, by + 92);
  (ctx as any).direction = "rtl"; ctx.fillStyle = MUTED; font(ctx, 600, 22); ctx.fillText(`بتاريخ ${d.contract_date}`, bx + bw / 2, by + 130);

  // title
  ctx.strokeStyle = GOLD; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(L, 245); ctx.lineTo(R, 245); ctx.stroke();
  ctx.textAlign = "center"; ctx.fillStyle = BLUE_D; font(ctx, 800, fitPx(ctx, d.title, 800, 60, W)); ctx.fillText(d.title, KW / 2, 322);
  if (d.subtitle) { ctx.fillStyle = GOLD; font(ctx, 700, 30); ctx.fillText(d.subtitle, KW / 2, 368); }

  // info grid
  let y = 400;
  const cell = (x: number, w: number, label: string, value: string, opts: { fam?: string; px?: number; color?: string; ltr?: boolean } = {}) => {
    ctx.fillStyle = "#fff"; rr(ctx, x, y, w, 108, 12); ctx.fill(); ctx.strokeStyle = LINE; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = BLUE; ctx.fillRect(x + w - 6, y + 18, 6, 72);
    ctx.textAlign = "right"; ctx.fillStyle = MUTED; font(ctx, 600, 22); ctx.fillText(label, x + w - 24, y + 38);
    const fam = opts.fam || FONT, wt = fam === FONT ? 800 : weightFor(fam, true);
    ctx.fillStyle = opts.color || INK;
    const v = value || "—";
    font(ctx, wt, fitPx(ctx, v, wt, opts.px || 34, w - 48, fam), fam);
    if (opts.ltr) { (ctx as any).direction = "ltr"; ctx.textAlign = "right"; }
    ctx.fillText(v, x + w - 24, y + 86);
    (ctx as any).direction = "rtl";
  };
  const half = (W - 20) / 2;
  cell(R - half, half, "رقم المشروع", d.project_no, { ltr: true, px: 38 });
  cell(L, half, "نوع المشروع", d.project_type);
  y += 124;
  cell(L, W, "اسم صاحب المشروع", d.owner.replace(/\n/g, " و "), { fam: d.names_font || FONT, px: Math.round(44 * (d.names_size || 100) / 100), color: BLUE_D });
  y += 124;
  cell(R - half, half, "تاريخ العقد", d.contract_date);
  cell(L, half, "التاريخ المتوقع للتسليم", d.expected_delivery);
  y += 108;
  if (d.delivery_note?.trim()) {
    // the note under the expected delivery date, across the page, small and muted
    ctx.textAlign = "center"; ctx.fillStyle = MUTED;
    const note = `* ${d.delivery_note.trim()}`;
    font(ctx, 600, 21);
    const nl = wrap(ctx, note, W - 40).slice(0, 3);
    nl.forEach((l, i) => ctx.fillText(l, KW / 2, y + 34 + i * 32));
    y += 32 * (nl.length - 1);
  }
  y += 92;

  // section heading
  const heading = (s: string) => {
    ctx.fillStyle = BLUE; rr(ctx, R - 10, y - 30, 10, 38, 4); ctx.fill();
    ctx.textAlign = "right"; ctx.fillStyle = INK; font(ctx, 800, 32); ctx.fillText(s, R - 26, y);
    ctx.strokeStyle = LINE; ctx.lineWidth = 2; ctx.beginPath();
    const tw = ctx.measureText(s).width; ctx.moveTo(L, y - 10); ctx.lineTo(R - 46 - tw, y - 10); ctx.stroke();
    y += 22;
  };

  // body sizes shrink a little when the text is long, so everything stays on one page
  const specLines = d.specs.split("\n").map((s) => s.trim()).filter(Boolean);
  const termLines = d.show_terms ? d.terms.split("\n").map((s) => s.trim()).filter(Boolean) : [];
  const bottomLimit = KH - 330;
  let sp = 28, tp = 21;
  const measure = () => {
    let h = 0;
    font(ctx, 600, sp); for (const s of specLines) h += wrap(ctx, s, W - 60).length * sp * 1.6 + 6;
    h += 52 + 150 + 40;
    if (termLines.length) { h += 52; font(ctx, 400, tp); termLines.forEach((s) => { h += wrap(ctx, `${s}`, W - 60).length * tp * 1.6 + 4; }); }
    return h;
  };
  while (y + measure() > bottomLimit && sp > 20) { sp -= 1; tp = Math.max(16, tp - 0.6); }

  heading("مواصفات التنفيذ");
  y += 12;
  for (const s of specLines) {
    font(ctx, 600, sp);
    const lines = wrap(ctx, s, W - 60);
    ctx.fillStyle = GOLD; ctx.beginPath(); ctx.arc(R - 14, y + sp * 0.75, 6, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = INK; ctx.textAlign = "right";
    lines.forEach((l) => { ctx.fillText(l, R - 34, y + sp * 1.05); y += sp * 1.6; });
    y += 6;
  }
  y += 24;

  // amount band
  const ah = d.amount_words ? 150 : 124;
  const ag = ctx.createLinearGradient(0, y, 0, y + ah); ag.addColorStop(0, "#3f86cc"); ag.addColorStop(1, BLUE_D);
  ctx.fillStyle = ag; rr(ctx, L, y, W, ah, 18); ctx.fill();
  ctx.textAlign = "right"; ctx.fillStyle = "#fff"; font(ctx, 700, 26); ctx.fillText("المبلغ المستلم", R - 34, y + 50);
  font(ctx, 600, 20); ctx.fillStyle = "rgba(255,255,255,.85)"; ctx.fillText("من صاحب المشروع", R - 34, y + 86);
  (ctx as any).direction = "ltr"; ctx.textAlign = "left"; ctx.fillStyle = "#fff";
  const cur = (d.currency || "USD").toUpperCase(), sym = cur === "USD" ? "$" : "";
  const amt = d.amount ? `${sym}${d.amount}` : "—";
  font(ctx, 800, 64); ctx.fillText(amt, L + 34, y + 84);
  const aw = ctx.measureText(amt).width; font(ctx, 700, 28); ctx.fillText(cur, L + 44 + aw, y + 84);
  (ctx as any).direction = "rtl";
  if (d.amount_words) { ctx.textAlign = "center"; font(ctx, 600, 22); ctx.fillStyle = "#fff"; ctx.fillText(d.amount_words, KW / 2, y + ah - 22); }
  y += ah + 52;

  if (termLines.length) {
    heading("الشروط والالتزامات");
    y += 8;
    termLines.forEach((s, i) => {
      font(ctx, 700, tp); ctx.fillStyle = BLUE; ctx.textAlign = "right"; ctx.fillText(`${(i + 1).toLocaleString("ar-EG")}.`, R - 6, y + tp * 1.05);
      font(ctx, 400, tp); ctx.fillStyle = INK;
      wrap(ctx, s, W - 60).forEach((l) => { ctx.fillText(l, R - 40, y + tp * 1.05); y += tp * 1.6; });
      y += 4;
    });
  }

  // signatures and contact
  const sy = KH - 300;
  ctx.strokeStyle = LINE; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(L, sy); ctx.lineTo(R, sy); ctx.stroke();
  ctx.textAlign = "center"; ctx.fillStyle = MUTED; font(ctx, 600, 22);
  const rx = R - 200, lx = L + 200;
  ctx.fillText("ختم وتوقيع المؤسسة", rx, sy + 40);
  if (d.show_stamp && a.stamp) { const s = 150, h = (a.stamp.height / a.stamp.width) * s; ctx.globalAlpha = 0.92; ctx.drawImage(a.stamp, rx - s / 2, sy + 52, s, h); ctx.globalAlpha = 1; }
  ctx.fillText("للتواصل والاستفسار", lx, sy + 40);
  ctx.fillStyle = INK; font(ctx, 800, 34); (ctx as any).direction = "ltr";
  ctx.fillText(d.hayah_phone || "—", lx, sy + 100);
  ctx.fillStyle = BLUE; font(ctx, 700, 28); ctx.fillText(d.site, lx, sy + 150);
  (ctx as any).direction = "rtl";

  // footer band
  ctx.fillStyle = g; ctx.fillRect(0, KH - 70, KW, 70);
  ctx.fillStyle = "#fff"; ctx.textAlign = "center"; font(ctx, 600, 22);
  ctx.fillText(`صدر هذا العقد إلكترونياً من نظام مؤسسة حياة · ${meta.invoice || ""}`.trim(), KW / 2, KH - 28);
  ctx.restore();
}

export async function contractCanvas(d: ContractDesign, meta: { invoice: string | null }, scale = 2): Promise<HTMLCanvasElement> {
  const a = await loadContractAssets(d);
  const c = document.createElement("canvas");
  c.width = KW * scale; c.height = KH * scale;
  drawContract(c.getContext("2d")!, d, meta, a, scale);
  return c;
}
export async function contractPng(d: ContractDesign, meta: { invoice: string | null }): Promise<Blob> {
  const c = await contractCanvas(d, meta, 2);
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("PNG failed"))), "image/png"));
}
/** A4 PDF (210 × 297 mm) at 300 dpi. */
export async function contractPdf(d: ContractDesign, meta: { invoice: string | null }): Promise<Blob> {
  return canvasPdf(await contractCanvas(d, meta, 2), 210, 297);
}
