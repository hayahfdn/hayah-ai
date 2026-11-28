// «سقيا الماء في الحرم» plaque (Hayah, 27 Nov 2026): portrait poster on a Haram background with a gold
// arch, laid out to match HAYAH's own poster. The background is a picture (built-in or uploaded); every
// line of text is drawn on top, so numbers, month, quantity, name and prayer are always editable.
import { cssFamily, ensureFont, weightFor } from "../plaque/fonts";
import { loadImage } from "../plaque/render";

export const SW = 1055, SH = 1491;
const NAVY = "#14275e", RED = "#d3121c", GOLD = "#d6a52a", FONT = "Cairo";

export interface SuqyaDesign {
  intro: string; hadith: string; number_label: string; number: string; month_text: string;
  qty_before: string; quantity: string; qty_after: string; sadaqa_label: string;
  name: string; name_size: number; name_font: string; dua: string;
  site: string; footer: string; bg: string; bg_src?: string; show_logo: boolean;
  /** The whole plaque wording, one line per plaque line (Hayah, 28 Nov 2026). Missing = the standard wording. */
  template?: string;
  /** Size of the prayer line («حفظه الله») and of any lines written under it, in % of the standard. */
  dua_size: number; extra_size: number;
}
export interface SuqyaOrder {
  suqya_no: number; order_date: string | null; quantity: number; donor_name: string | null; dua: string | null;
  customer_name: string | null; customer_phone: string | null; customer_phone_country: string | null;
  customer_phone_e164: string | null; customer_phone_status: string | null; sale_price: number | null; currency: string;
  notes: string | null; shopify_order?: string | null; sales_source?: string | null; dedication?: string | null; design: Partial<SuqyaDesign> | null; plaque_saved_at: string | null; plaque_saved_by: string | null;
  sent_at: string | null; sent_by: string | null; created_by: string | null; created_at: string; month_text: string;
}

/** The plaque filled from the order, with the saved design (text the person changed) on top. */
export function designFor(o: SuqyaOrder): SuqyaDesign {
  const saved = o.design || {};
  return {
    intro: "قال رسول الله ﷺ", hadith: "أفضل الصدقة سقي الماء", number_label: "سقيا رقم", month_text: o.month_text,
    qty_before: "توزيع", qty_after: "عبوة مياه لضيوف الرحمن", sadaqa_label: "صدقة عن",
    name_size: 100, dua_size: 100, extra_size: 100, name_font: FONT, site: "HayahFoundation.com", footer: "تنفيذ مؤسسة حياة", bg: "haram", show_logo: true,
    ...saved,
    // these always follow the order (edit them in the order fields)
    number: String(o.suqya_no), quantity: String(o.quantity), name: o.donor_name || "", dua: o.dua || "",
  } as SuqyaDesign;
}
/** Only what differs from the order goes into the saved design. */
export function designToSave(d: SuqyaDesign): Partial<SuqyaDesign> {
  const { number: _n, quantity: _q, bg_src: _s, name: _name, dua: _d, ...rest } = d;
  return rest;
}

/** Words in braces are filled from the order, so the wording can change while numbers and names stay automatic. */
export const PH = { no: "{رقم}", date: "{التاريخ}", qty: "{العدد}", name: "{الاسم}", dua: "{الدعاء}" } as const;

/** The standard wording, built from the line fields (so wording changed before 28 Nov 2026 carries over). */
export function defaultTemplate(d: SuqyaDesign): string {
  return [d.intro, d.hadith, `${d.number_label} ${PH.no} | ${PH.date}`, `${d.qty_before} ${PH.qty} ${d.qty_after}`, d.sadaqa_label, PH.name, PH.dua]
    .map((s) => s.replace(/\s+/g, " ").trim()).join("\n");
}
export const templateOf = (d: SuqyaDesign) => (d.template ?? defaultTemplate(d));

type Kind = "intro" | "hadith" | "text" | "name" | "dua" | "extra" | "gap";
type Block = { kind: Kind; text: string; px: number; y: number; lines?: string[] };

const fill = (s: string, d: SuqyaDesign) => s.split(PH.no).join(d.number).split(PH.qty).join(d.quantity)
  .split(PH.date).join(d.month_text).split(PH.name).join(d.name.replace(/\s*\n\s*/g, " ")).split(PH.dua).join(d.dua);

/** Turns the wording into plaque lines and places them top to bottom. The standard wording lands exactly
 *  where it did before; extra or fewer lines shift the rest, and a long text is squeezed to fit. */
function layout(d: SuqyaDesign): Block[] {
  const out: Block[] = [];
  let afterDua = false;
  for (const raw of templateOf(d).split("\n")) {
    const line = raw.trim();
    const prev = out.filter((b) => b.kind !== "gap").slice(-1)[0];
    if (!line) { if (out.length) out.push({ kind: "gap", text: "", px: 0, y: 0 }); continue; }
    if (line.includes(PH.name)) {
      const names = d.name.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 3);
      if (!names.length && line === PH.name) continue;
      const lines = line === PH.name ? names : [fill(line, d)];
      out.push({ kind: "name", text: "", lines, px: (lines.length > 1 ? 82 : 112) * (d.name_size / 100), y: 0 });
    } else if (line.includes(PH.dua)) {
      const t = fill(line, d).trim();
      afterDua = true;
      if (t) out.push({ kind: "dua", text: t, px: 48 * ((d.dua_size || 100) / 100), y: 0 });
    } else if (afterDua) out.push({ kind: "extra", text: fill(line, d), px: 44 * ((d.extra_size || 100) / 100), y: 0 });
    else if (/ﷺ|صلى الله عليه وسلم/.test(line)) out.push({ kind: "intro", text: fill(line, d), px: 44, y: 0 });
    else if (prev?.kind === "intro") out.push({ kind: "hadith", text: line, px: 74, y: 0 });
    else out.push({ kind: "text", text: line, px: /\{(رقم|العدد)\}/.test(line) ? 70 : 56, y: 0 });
  }
  // spacing tuned so the standard wording sits where HAYAH's poster has it (345, 448, 572, 690, 790, 912, 1030)
  let y = 0, last: Block | null = null, pending = 0;
  for (const b of out) {
    if (b.kind === "gap") { pending += 50; continue; }
    const n = b.lines?.length || 1, lh = b.px * 1.18;
    if (!last) y = 301 + (b.kind === "name" ? 44 : b.px);
    else if (b.kind === "hadith") y += 103;
    else if (last.kind === "hadith" && b.kind === "text") y += 124;
    else if (b.kind === "name") y += n > 1 ? Math.max(122 - (lh * (n - 1)) / 2, b.px * 0.9) : 28 + b.px * (122 - 28) / 112;
    else if (last.kind === "name") y += last.px * 1.05 + (b.px - 48) * 0.8;
    else y += 28 + b.px * 1.286 + (last.kind === "dua" ? Math.max(0, last.px - 48) * 0.5 : 0);
    y += pending; pending = 0;
    b.y = y;
    if (b.kind === "name") y += lh * (n - 1);
    last = b;
  }
  // too long for the space above the footer: squeeze the line spacing
  const vis = out.filter((b) => b.kind !== "gap");
  if (vis.length) {
    const top = vis[0].y, bottom = vis[vis.length - 1].y, limit = 1300;
    if (bottom > limit) {
      const k = (limit - top) / (bottom - top);
      vis.forEach((b) => { b.y = top + (b.y - top) * k; b.px *= Math.max(k, 0.7); });
    }
  }
  return vis;
}

/** A plain line: words navy, the number and quantity red, «|» gold. Empty fields drop out with their «|». */
function lineRuns(line: string, d: SuqyaDesign, px: number): Run[] {
  const parts = line.split(/(\{[^}]+\}|\|)/).map((s) => s.trim()).filter(Boolean);
  let rs: Run[] = parts.map((p) => {
    if (p === "|") return { t: "|", color: GOLD, px: px * 0.87, weight: 700 };
    if (p === PH.no || p === PH.qty) return { t: p === PH.no ? d.number : d.quantity, color: RED, px: px + 10, stroke: true };
    return { t: fill(p, d), color: NAVY, px };
  }).filter((r) => r.t.trim());
  rs = rs.filter((r, i) => r.t !== "|" || (i > 0 && i < rs.length - 1 && rs[i - 1].t !== "|"));
  return rs;
}

function drawBlock(ctx: CanvasRenderingContext2D, b: Block, d: SuqyaDesign, cx: number) {
  if (b.kind === "intro") {
    // «قال رسول الله ﷺ»: the ﷺ sign comes from Amiri, which draws it as calligraphy
    const m = b.text.match(/^(.*?)\s*(ﷺ|صلى الله عليه وسلم)\s*(.*)$/);
    runs(ctx, m ? [{ t: m[1], color: NAVY, px: b.px, weight: 800 }, { t: "ﷺ", color: NAVY, px: b.px + 6, weight: 700, family: "Amiri" },
      { t: m[3], color: NAVY, px: b.px, weight: 800 }] : [{ t: b.text, color: NAVY, px: b.px, weight: 800 }], cx, b.y, 640, 10);
  } else if (b.kind === "hadith") runs(ctx, [{ t: fill(b.text, d), color: RED, px: b.px, stroke: true }], cx, b.y, 860);
  else if (b.kind === "text") {
    const red = /\{(رقم|العدد)\}/.test(b.text);
    runs(ctx, lineRuns(b.text, d, red ? b.px - 10 : b.px), cx, b.y, 900, red ? 20 : 18);
  } else if (b.kind === "name") {
    const fam = d.name_font || FONT, lh = b.px * 1.18;
    (b.lines || []).forEach((s, i) => runs(ctx, [{ t: s, color: RED, px: b.px, weight: weightFor(fam, true), family: fam, stroke: true }], cx, b.y + i * lh, 840));
  } else if (b.kind === "dua") {
    // prayer with two gold lines either side
    const wmax = 600 * Math.max(1, b.px / 48);
    ctx.font = f(900, b.px); const w = Math.min(ctx.measureText(b.text).width, wmax);
    runs(ctx, [{ t: b.text, color: NAVY, px: b.px }], cx, b.y, wmax);
    const len = Math.min(150, (SW - 40 - w) / 2 - 30);
    if (len > 20) {
      ctx.save(); ctx.lineWidth = 4; ctx.lineCap = "round";
      const gy = b.y - b.px / 3;
      for (const dir of [-1, 1]) {
        const x0 = cx + dir * (w / 2 + 26);
        const grd = ctx.createLinearGradient(x0, gy, x0 + dir * len, gy);
        grd.addColorStop(0, GOLD); grd.addColorStop(1, "rgba(214,165,42,0)");
        ctx.strokeStyle = grd; ctx.beginPath(); ctx.moveTo(x0, gy); ctx.lineTo(x0 + dir * len, gy); ctx.stroke();
      }
      ctx.restore();
    }
  } else runs(ctx, [{ t: b.text, color: NAVY, px: b.px, weight: 800 }], cx, b.y, 900);
}

const f = (w: number, px: number, fam = FONT) => `${w} ${px}px ${cssFamily(fam)}`;

export interface SuqyaAssets { bg: HTMLImageElement | null; logo: HTMLImageElement | null }
export async function loadSuqyaAssets(d: SuqyaDesign): Promise<SuqyaAssets> {
  await Promise.all([700, 800, 900].map((w) => ensureFont(FONT, w)));
  await ensureFont("Amiri", 700);
  if (d.name_font && d.name_font !== FONT) await ensureFont(d.name_font, weightFor(d.name_font, true));
  const [bg, logo] = await Promise.all([loadImage(d.bg_src || "/suqya/haram-bg.jpg"), d.show_logo ? loadImage("/hayah-logo.png") : null]);
  return { bg, logo };
}

type Run = { t: string; color: string; px: number; weight?: number; family?: string; stroke?: boolean };

/** Lays out coloured runs right-to-left on one line, centred on cx, shrinking all of them to fit `width`. */
function runs(ctx: CanvasRenderingContext2D, rs: Run[], cx: number, y: number, width: number, gap = 18) {
  rs = rs.filter((r) => r.t.trim());
  if (!rs.length) return;
  let scale = 1;
  const measure = () => rs.map((r) => { ctx.font = f(r.weight ?? 900, r.px * scale, r.family); return ctx.measureText(r.t).width; });
  let ws = measure();
  const total = () => ws.reduce((a, b) => a + b, 0) + gap * scale * (rs.length - 1);
  while (total() > width && scale > 0.4) { scale -= 0.03; ws = measure(); }
  let x = cx + total() / 2; // start at the right edge
  ctx.textAlign = "right"; ctx.direction = "rtl"; ctx.textBaseline = "alphabetic";
  rs.forEach((r, i) => {
    ctx.font = f(r.weight ?? 900, r.px * scale, r.family);
    halo(ctx, r.t, x, y, r.color, r.px * scale, r.stroke);
    x -= ws[i] + gap * scale;
  });
}

/** Text with a soft white halo so it reads on the sky (and a white edge on the red lines, like the poster). */
function halo(ctx: CanvasRenderingContext2D, s: string, x: number, y: number, color: string, px: number, edge = false) {
  ctx.save();
  ctx.shadowColor = "rgba(255,255,255,0.95)"; ctx.shadowBlur = px * 0.35;
  if (edge) { ctx.lineJoin = "round"; ctx.strokeStyle = "#fff"; ctx.lineWidth = px * 0.12; ctx.strokeText(s, x, y); }
  ctx.fillStyle = color; ctx.fillText(s, x, y);
  ctx.shadowColor = "rgba(90,0,0,0.25)"; ctx.shadowBlur = 0; ctx.shadowOffsetY = edge ? px * 0.04 : 0;
  ctx.fillText(s, x, y);
  ctx.restore();
}

/** A stylised Haram sky and gold arch, used only if the background picture fails to load. */
function fallbackBg(ctx: CanvasRenderingContext2D) {
  const g = ctx.createLinearGradient(0, 0, 0, SH);
  g.addColorStop(0, "#4a9be6"); g.addColorStop(0.35, "#eaf4fd"); g.addColorStop(1, "#fff8e6");
  ctx.fillStyle = g; ctx.fillRect(0, 0, SW, SH);
  ctx.strokeStyle = GOLD; ctx.lineWidth = 10;
  ctx.beginPath(); ctx.moveTo(60, SH - 160); ctx.lineTo(60, 420); ctx.quadraticCurveTo(SW / 2, -40, SW - 60, 420); ctx.lineTo(SW - 60, SH - 160); ctx.stroke();
  ctx.fillStyle = "#16306b"; ctx.fillRect(0, SH - 100, SW, 100);
}

export function drawSuqya(ctx: CanvasRenderingContext2D, d: SuqyaDesign, a: SuqyaAssets, scale = 1) {
  ctx.save();
  ctx.scale(scale, scale);
  if (a.bg) {
    // cover the whole poster, keeping the picture's proportions
    const r = Math.max(SW / a.bg.width, SH / a.bg.height), w = a.bg.width * r, h = a.bg.height * r;
    ctx.drawImage(a.bg, (SW - w) / 2, (SH - h) / 2, w, h);
  } else fallbackBg(ctx);

  if (a.logo) {
    const h = 268, w = (a.logo.width / a.logo.height) * h;
    ctx.save(); ctx.shadowColor = "rgba(255,255,255,0.9)"; ctx.shadowBlur = 18;
    ctx.drawImage(a.logo, (SW - w) / 2, 14, w, h); ctx.restore();
  }
  const cx = SW / 2;
  layout(d).forEach((b) => drawBlock(ctx, b, d, cx));

  // footer: website on the left, «تنفيذ مؤسسة حياة» on the right, gold bar between
  const fy = 1460;
  ctx.save(); ctx.fillStyle = "#fff"; ctx.textBaseline = "alphabetic";
  if (d.site.trim()) { ctx.direction = "ltr"; ctx.textAlign = "left"; ctx.font = f(800, fitPx(ctx, d.site, 800, 46, 500)); ctx.fillText(d.site, 22, fy); }
  if (d.footer.trim()) { ctx.direction = "rtl"; ctx.textAlign = "right"; ctx.font = f(800, fitPx(ctx, d.footer, 800, 44, 400)); ctx.fillText(d.footer, SW - 24, fy); }
  if (d.site.trim() && d.footer.trim()) { ctx.fillStyle = GOLD; ctx.fillRect(588, fy - 36, 5, 40); }
  ctx.restore();
  ctx.restore();
}

function fitPx(ctx: CanvasRenderingContext2D, s: string, w: number, max: number, width: number) {
  let px = max;
  for (; px > 16; px -= 2) { ctx.font = f(w, px); if (ctx.measureText(s).width <= width) break; }
  return px;
}

export async function suqyaPng(d: SuqyaDesign, scale = 2): Promise<Blob> {
  const a = await loadSuqyaAssets(d);
  const c = document.createElement("canvas");
  c.width = SW * scale; c.height = SH * scale;
  drawSuqya(c.getContext("2d")!, d, a, scale);
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("PNG failed"))), "image/png"));
}
