// «شهادة وقفية»: the endowment certificate, laid out on a 1080 × 1640 portrait grid to match
// HAYAH's own certificate (logo, title, project type, donor names in gold, opening month and year,
// well number and country boxes, closing prayer, stamp, website). Drawn on a canvas, rule-based.
import { ensureFont, cssFamily } from "../plaque/fonts";
import { flagArabic, flagFor, iconFor, IconKey, loadImage } from "../plaque/render";

export const CW = 1080, CH = 1640;

export interface CertDesign {
  title: string; intro: string; project_type: string; sadaqa_line: string;
  names: string; names_size: number;           // percent of the default size
  opened_prefix: string; month: string; year: string;
  number_label: string; number: string; country_label: string; country: string;
  dua: string; site: string; icon: IconKey | "pump" | "none"; show_stamp: boolean;
}
export interface CertDefaults { names: string; project_type: string; month: string; year: string; number: string; country: string; date_guessed: boolean; well_type?: string | null }

export function defaultCert(d: CertDefaults, wellType: string | null | undefined = d.well_type): CertDesign {
  return {
    title: "شهادة وقفية", intro: "تشهد مؤسسة حياة للمشاريع التنموية\nبأنها قد نفذت مشروع", project_type: d.project_type,
    sadaqa_line: "صدقة جارية بإذن الله تعالى عن:", names: d.names, names_size: 100,
    opened_prefix: "والذي تم افتتاحه في شهر", month: d.month, year: d.year,
    number_label: "رقم البئر:", number: d.number, country_label: "الدولة:", country: flagArabic(flagFor(d.country)) || d.country,
    dua: "نسأل الله أن يتقبل منكم ويسقيكم من أنهار الجنة", site: "HayahFoundation.com",
    icon: wellType === "يدوي" || !wellType ? "pump" : iconFor(wellType), show_stamp: true,
  };
}

const BLUE = "#3a7cc0", INK = "#1d2b3a", GOLD = "#b48a46", GOLD_LIGHT = "#d9bd84", FONT = "Cairo";
const f = (w: number, px: number, fam = FONT) => `${w} ${px}px ${cssFamily(fam)}`;

export interface CertAssets { logo: HTMLImageElement | null; stamp: HTMLImageElement | null; icon: HTMLImageElement | null }
export async function loadCertAssets(d: CertDesign): Promise<CertAssets> {
  await Promise.all([[400], [600], [700], [800], [900]].map(([w]) => ensureFont(FONT, w)));
  const [logo, stamp, icon] = await Promise.all([loadImage("/hayah-logo.png"), loadImage("/certificate-stamp.png"),
    d.icon === "none" || d.icon === "pump" ? null : loadImage(`/wells/${d.icon}.png`)]);
  return { logo, stamp, icon };
}

/** Largest font size (≤ max) at which the text fits the width. */
function fit(ctx: CanvasRenderingContext2D, text: string, weight: number, max: number, width: number, min = 18) {
  let px = max;
  for (; px > min; px -= 2) { ctx.font = f(weight, px); if (ctx.measureText(text).width <= width) break; }
  return px;
}
function text(ctx: CanvasRenderingContext2D, s: string, x: number, y: number, weight: number, px: number, color: string, width?: number) {
  const size = width ? fit(ctx, s, weight, px, width) : px;
  ctx.font = f(weight, size); ctx.fillStyle = color; ctx.fillText(s, x, y);
  return size;
}
function rounded(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function star(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  ctx.beginPath();
  for (let i = 0; i < 16; i++) {
    const a = (Math.PI / 8) * i - Math.PI / 2, rr = i % 2 ? r * 0.62 : r;
    ctx.lineTo(cx + rr * Math.cos(a), cy + rr * Math.sin(a));
  }
  ctx.closePath(); ctx.stroke();
  ctx.beginPath(); ctx.arc(cx, cy, r * 0.32, 0, Math.PI * 2); ctx.stroke();
}
/** A simple blue hand pump, like the one on HAYAH's certificate. */
function pump(ctx: CanvasRenderingContext2D, cx: number, cy: number) {
  ctx.save(); ctx.translate(cx, cy); ctx.fillStyle = BLUE; ctx.strokeStyle = BLUE; ctx.lineCap = "round";
  rounded(ctx, -14, -38, 28, 92, 6); ctx.fill();                       // body
  ctx.fillRect(-24, 50, 48, 10);                                        // base
  ctx.beginPath(); ctx.arc(0, -42, 13, 0, Math.PI * 2); ctx.fill();      // cap
  ctx.lineWidth = 10; ctx.beginPath(); ctx.moveTo(-12, -20); ctx.lineTo(-34, -16); ctx.lineTo(-38, -4); ctx.stroke(); // spout
  ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(10, -42); ctx.quadraticCurveTo(34, -40, 36, -10); ctx.quadraticCurveTo(38, 14, 26, 24); ctx.stroke(); // handle
  ctx.beginPath(); ctx.arc(26, 28, 6, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}
function pin(ctx: CanvasRenderingContext2D, cx: number, cy: number, s: number) {
  ctx.save(); ctx.translate(cx, cy); ctx.scale(s / 100, s / 100);
  ctx.fillStyle = BLUE; ctx.strokeStyle = BLUE; ctx.lineWidth = 6;
  ctx.beginPath(); ctx.moveTo(0, 30); ctx.bezierCurveTo(-40, -10, -34, -60, 0, -62); ctx.bezierCurveTo(34, -60, 40, -10, 0, 30); ctx.fill();
  ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(0, -30, 18, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = BLUE; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(-18, -30); ctx.lineTo(18, -30); ctx.moveTo(0, -48); ctx.lineTo(0, -12); ctx.stroke();
  ctx.lineWidth = 6; ctx.beginPath(); ctx.ellipse(0, 36, 44, 14, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.restore();
}

/** Light geometric background and the double gold frame. */
function frame(ctx: CanvasRenderingContext2D) {
  ctx.fillStyle = "#f6f9fc"; ctx.fillRect(0, 0, CW, CH);
  ctx.save(); ctx.strokeStyle = "rgba(90,140,190,0.10)"; ctx.lineWidth = 1.2;
  for (let x = -CH; x < CW + CH; x += 26) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + CH, CH); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x, CH); ctx.lineTo(x + CH, 0); ctx.stroke();
  }
  ctx.restore();
  ctx.fillStyle = "#ffffff"; rounded(ctx, 34, 34, CW - 68, CH - 68, 6); ctx.fill();
  ctx.strokeStyle = GOLD_LIGHT; ctx.lineWidth = 3; rounded(ctx, 24, 24, CW - 48, CH - 48, 8); ctx.stroke();
  ctx.strokeStyle = GOLD; ctx.lineWidth = 1.5; rounded(ctx, 34, 34, CW - 68, CH - 68, 6); ctx.stroke();
}

export function drawCertificate(ctx: CanvasRenderingContext2D, d: CertDesign, a: CertAssets, scale = 1) {
  ctx.save(); ctx.scale(scale, scale);
  ctx.direction = "rtl"; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
  frame(ctx);
  const cx = CW / 2;
  if (a.logo) { const h = 175, w = (a.logo.width / a.logo.height) * h; ctx.drawImage(a.logo, cx - w / 2, 42, w, h); }
  // title
  ctx.fillStyle = BLUE; text(ctx, d.title, cx, 375, 800, 150, BLUE, 860);
  // ornament
  ctx.strokeStyle = GOLD; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(370, 422); ctx.lineTo(505, 422); ctx.moveTo(575, 422); ctx.lineTo(710, 422); ctx.stroke();
  ctx.fillStyle = GOLD; for (const x of [505, 575]) { ctx.beginPath(); ctx.arc(x, 422, 3, 0, Math.PI * 2); ctx.fill(); }
  star(ctx, cx, 422, 20);
  // intro (up to two lines)
  d.intro.split("\n").slice(0, 2).forEach((l, i) => text(ctx, l.trim(), cx, 505 + i * 58, 600, 42, INK, 840));
  // project type in the blue band
  const g = ctx.createLinearGradient(0, 592, 0, 688); g.addColorStop(0, "#4b8fd0"); g.addColorStop(1, "#3170b2");
  ctx.fillStyle = g; rounded(ctx, 104, 592, CW - 208, 96, 30); ctx.fill();
  text(ctx, d.project_type, cx, 662, 700, 62, "#ffffff", 800);
  text(ctx, d.sadaqa_line, cx, 800, 700, 52, INK, 860);
  // donor names (gold), each line shrunk to fit; up to 4 lines, smaller when there are more
  const lines = d.names.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 4);
  const k = (d.names_size || 100) / 100;
  const base = (lines.length <= 2 ? 86 : lines.length === 3 ? 66 : 54) * k;
  const lh = base * 1.22, top = 905 - (lines.length > 2 ? 20 : 0);
  lines.forEach((l, i) => text(ctx, l, cx, top + i * lh, 800, base, GOLD, 880));
  const lastY = top + Math.max(0, lines.length - 1) * lh + 22;
  ctx.fillStyle = GOLD; for (let x = 140; x <= CW - 140; x += 9) { ctx.beginPath(); ctx.arc(x, Math.min(lastY, 1040), 1.8, 0, Math.PI * 2); ctx.fill(); }
  // opening
  text(ctx, `${d.opened_prefix} ${d.month} عام ${d.year}`.replace(/\s+/g, " ").trim(), cx, 1100, 600, 40, INK, 860);
  // two boxes: number (right) and country (left)
  const box = (x: number, label: string, value: string, iconDraw: (ix: number) => void) => {
    ctx.fillStyle = "#ffffff"; ctx.strokeStyle = "#5b8fc2"; ctx.lineWidth = 2.5; rounded(ctx, x, 1135, 372, 150, 16); ctx.fill(); ctx.stroke();
    ctx.strokeStyle = "rgba(91,143,194,0.35)"; ctx.lineWidth = 1; rounded(ctx, x + 7, 1142, 358, 136, 12); ctx.stroke();
    iconDraw(x + 300);
    text(ctx, label, x + 145, 1195, 600, 42, INK, 220);
    text(ctx, value, x + 145, 1257, 700, 46, INK, 230);
  };
  box(CW - 104 - 372, d.number_label, d.number, (ix) => {
    if (d.icon === "pump") { pump(ctx, ix, 1206); return; }
    if (!a.icon) return;
    const h = 120, w = Math.min(110, (a.icon.width / a.icon.height) * h);
    ctx.drawImage(a.icon, ix - w / 2, 1150, w, (a.icon.height / a.icon.width) * w > h ? h : (a.icon.height / a.icon.width) * w);
  });
  box(104, d.country_label, d.country, (ix) => pin(ctx, ix, 1222, 80));
  text(ctx, d.dua, cx, 1350, 600, 46, INK, 900);
  if (d.show_stamp && a.stamp) { const s = 180, h = (a.stamp.height / a.stamp.width) * s; ctx.globalAlpha = 0.92; ctx.drawImage(a.stamp, cx - s / 2, 1385, s, h); ctx.globalAlpha = 1; }
  ctx.direction = "ltr"; text(ctx, d.site, cx, 1592, 700, 54, BLUE, 760);
  ctx.restore();
}

/** The certificate as a PNG file (1080 × 1640, or 2× for print quality). */
export async function certificatePng(d: CertDesign, scale = 2): Promise<Blob> {
  const a = await loadCertAssets(d);
  const c = document.createElement("canvas");
  c.width = CW * scale; c.height = CH * scale;
  drawCertificate(c.getContext("2d")!, d, a, scale);
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("PNG failed"))), "image/png"));
}
