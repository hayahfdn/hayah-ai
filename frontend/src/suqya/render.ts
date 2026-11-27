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
}
export interface SuqyaOrder {
  suqya_no: number; order_date: string | null; quantity: number; donor_name: string | null; dua: string | null;
  customer_name: string | null; customer_phone: string | null; customer_phone_country: string | null;
  customer_phone_e164: string | null; customer_phone_status: string | null; sale_price: number | null; currency: string;
  notes: string | null; design: Partial<SuqyaDesign> | null; plaque_saved_at: string | null; plaque_saved_by: string | null;
  sent_at: string | null; sent_by: string | null; created_by: string | null; created_at: string; month_text: string;
}

/** The plaque filled from the order, with the saved design (text the person changed) on top. */
export function designFor(o: SuqyaOrder): SuqyaDesign {
  const saved = o.design || {};
  return {
    intro: "قال رسول الله ﷺ", hadith: "أفضل الصدقة سقي الماء", number_label: "سقيا رقم", month_text: o.month_text,
    qty_before: "توزيع", qty_after: "عبوة مياه لضيوف الرحمن", sadaqa_label: "صدقة عن",
    name_size: 100, name_font: FONT, site: "HayahFoundation.com", footer: "تنفيذ مؤسسة حياة", bg: "haram", show_logo: true,
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
  // «قال رسول الله ﷺ»: the ﷺ sign comes from Amiri, which draws it as calligraphy
  const intro = d.intro.trim();
  if (intro) {
    const m = intro.match(/^(.*?)\s*(ﷺ|صلى الله عليه وسلم)\s*$/);
    runs(ctx, m ? [{ t: m[1], color: NAVY, px: 44, weight: 800 }, { t: "ﷺ", color: NAVY, px: 50, weight: 700, family: "Amiri" }]
      : [{ t: intro, color: NAVY, px: 44, weight: 800 }], cx, 345, 640, 10);
  }
  runs(ctx, [{ t: d.hadith, color: RED, px: 74, stroke: true }], cx, 448, 860);
  // «سقيا رقم 104 | نوفمبر 2026»
  const sep = "|";
  runs(ctx, [{ t: d.number_label, color: NAVY, px: 62 }, { t: d.number, color: RED, px: 70, stroke: true },
    ...(d.month_text.trim() ? [{ t: sep, color: GOLD, px: 54, weight: 700 }, { t: d.month_text, color: NAVY, px: 62 }] : [])], cx, 572, 860, 22);
  // «توزيع 100 عبوة مياه لضيوف الرحمن»
  runs(ctx, [{ t: d.qty_before, color: NAVY, px: 58 }, { t: d.quantity, color: RED, px: 70, stroke: true }, { t: d.qty_after, color: NAVY, px: 58 }],
    cx, 690, 900, 14);
  runs(ctx, [{ t: d.sadaqa_label, color: NAVY, px: 56 }], cx, 790, 700);

  // the donor name: large, red, one or two lines
  const lines = d.name.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 3);
  const fam = d.name_font || FONT;
  const base = (lines.length > 1 ? 82 : 112) * (d.name_size / 100);
  const lh = base * 1.18;
  const top = lines.length > 1 ? 900 - (lh * (lines.length - 1)) / 2 : 912;
  lines.forEach((s, i) => runs(ctx, [{ t: s, color: RED, px: base, weight: weightFor(fam, true), family: fam, stroke: true }], cx, top + i * lh, 840));

  // prayer with two gold lines either side
  const dua = d.dua.trim();
  if (dua) {
    const y = 1030;
    ctx.font = f(900, 48); const w = Math.min(ctx.measureText(dua).width, 600);
    runs(ctx, [{ t: dua, color: NAVY, px: 48 }], cx, y, 600);
    ctx.save(); ctx.strokeStyle = GOLD; ctx.lineWidth = 4; ctx.lineCap = "round";
    const gy = y - 16, len = 150;
    for (const dir of [-1, 1]) {
      const x0 = cx + dir * (w / 2 + 26);
      const grd = ctx.createLinearGradient(x0, gy, x0 + dir * len, gy);
      grd.addColorStop(0, GOLD); grd.addColorStop(1, "rgba(214,165,42,0)");
      ctx.strokeStyle = grd; ctx.beginPath(); ctx.moveTo(x0, gy); ctx.lineTo(x0 + dir * len, gy); ctx.stroke();
    }
    ctx.restore();
  }

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
