// Plaque drawing and export. Everything is laid out on a 1080 × 1080 grid that matches
// HAYAH's current plaque, then scaled for print. Rule-based: no AI is involved.
import "@fontsource/cairo/700.css";
import "@fontsource/cairo/800.css";
import "@fontsource/cairo/900.css";
import "@fontsource/amiri/700.css";
import "@fontsource/noto-naskh-arabic/400.css";
import "@fontsource/noto-naskh-arabic/700.css";

export const GRID = 1080;

export type DuaKind = "living_m" | "living_f" | "living_group" | "dead_m" | "dead_f" | "dead_group";

export interface Design {
  template: "hayah_square";
  size: SizeKey;
  well_id: string;
  well_type: string;
  month: string;
  name: string;
  dua_kind: DuaKind;
  short_dua: string;
  dua: string;
  flag: string;          // flag code from FLAGS, "custom" or "" for none
  flag_custom?: string;  // data: URL when flag === "custom"
  icon: "well" | "custom" | "none";
  icon_custom?: string;  // data: URL when icon === "custom"
  bismillah: string;
  verse: string;
  project_label: string;
  sadaqa_label: string;
  footer_site: string;
  footer_org: string;
  name_color: string;
  name_font: "Cairo" | "Amiri" | "Noto Naskh Arabic";
}

export const SIZES = {
  digital: { label_en: "Digital 1080 × 1080 px", label_ar: "رقمي 1080 × 1080", px: 1080, mm: null as number | null, dpi: 72 },
  digital2x: { label_en: "Digital HD 2160 × 2160 px", label_ar: "رقمي عالي الدقة 2160 × 2160", px: 2160, mm: null as number | null, dpi: 144 },
  print20: { label_en: "Print 20 × 20 cm (300 dpi)", label_ar: "طباعة 20 × 20 سم (300 dpi)", px: 2362, mm: 200, dpi: 300 },
  print30: { label_en: "Print 30 × 30 cm (300 dpi)", label_ar: "طباعة 30 × 30 سم (300 dpi)", px: 3543, mm: 300, dpi: 300 },
};
export type SizeKey = keyof typeof SIZES;

/** Country name (as typed in the well record, English or Arabic) → flag code. */
export const FLAGS: [string, string, string[]][] = [
  ["pk", "Pakistan / باكستان", ["pakistan", "باكستان", "pak"]],
  ["np", "Nepal / نيبال", ["nepal", "نيبال", "nep"]],
  ["bd", "Bangladesh / بنغلاديش", ["bangladesh", "بنغلاديش", "بنجلاديش", "bang"]],
  ["in", "India / الهند", ["india", "الهند", "ind"]],
  ["tz", "Tanzania / تنزانيا", ["tanzania", "تنزانيا", "tz"]],
  ["so", "Somalia / الصومال", ["somalia", "الصومال"]],
  ["sd", "Sudan / السودان", ["sudan", "السودان"]],
  ["ke", "Kenya / كينيا", ["kenya", "كينيا"]],
  ["ug", "Uganda / أوغندا", ["uganda", "أوغندا", "اوغندا"]],
  ["et", "Ethiopia / إثيوبيا", ["ethiopia", "إثيوبيا", "اثيوبيا"]],
  ["ng", "Nigeria / نيجيريا", ["nigeria", "نيجيريا"]],
  ["ne", "Niger / النيجر", ["niger", "النيجر"]],
  ["td", "Chad / تشاد", ["chad", "تشاد"]],
  ["ml", "Mali / مالي", ["mali", "مالي"]],
  ["bf", "Burkina Faso / بوركينا فاسو", ["burkina faso", "بوركينا فاسو"]],
  ["gh", "Ghana / غانا", ["ghana", "غانا"]],
  ["gm", "Gambia / غامبيا", ["gambia", "غامبيا"]],
  ["sn", "Senegal / السنغال", ["senegal", "السنغال"]],
  ["gn", "Guinea / غينيا", ["guinea", "غينيا"]],
  ["sl", "Sierra Leone / سيراليون", ["sierra leone", "سيراليون"]],
  ["lr", "Liberia / ليبيريا", ["liberia", "ليبيريا"]],
  ["ci", "Côte d'Ivoire / ساحل العاج", ["ivory coast", "cote d'ivoire", "ساحل العاج"]],
  ["bj", "Benin / بنين", ["benin", "بنين"]],
  ["tg", "Togo / توغو", ["togo", "توغو"]],
  ["cm", "Cameroon / الكاميرون", ["cameroon", "الكاميرون"]],
  ["mw", "Malawi / مالاوي", ["malawi", "مالاوي"]],
  ["mr", "Mauritania / موريتانيا", ["mauritania", "موريتانيا"]],
  ["eg", "Egypt / مصر", ["egypt", "مصر"]],
  ["ye", "Yemen / اليمن", ["yemen", "اليمن"]],
  ["sy", "Syria / سوريا", ["syria", "سوريا"]],
  ["ps", "Palestine / فلسطين", ["palestine", "فلسطين", "gaza", "غزة"]],
  ["af", "Afghanistan / أفغانستان", ["afghanistan", "أفغانستان", "افغانستان"]],
  ["lk", "Sri Lanka / سريلانكا", ["sri lanka", "سريلانكا"]],
  ["id", "Indonesia / إندونيسيا", ["indonesia", "إندونيسيا", "اندونيسيا"]],
];

export function flagFor(country: string | null | undefined): string {
  const c = (country || "").trim().toLowerCase();
  if (!c) return "";
  const hit = FLAGS.find(([, , names]) => names.some((n) => c === n || c.startsWith(n + " ") || c.startsWith(n)));
  return hit ? hit[0] : "";
}

export const DUAS: Record<DuaKind, { label_en: string; label_ar: string; short: string; long: string }> = {
  living_m: {
    label_en: "Living, male", label_ar: "حي، ذكر", short: "حفظه الله",
    long: "اللهم احفظه وأطل في عمره على طاعتك، وأكرم شأنه ويسّر أمره، ووسع له في رزقه وبارك له في ماله وأهله، وألبسه ثوب الصحة والعافية، واجعل حياته سعيدة ومستقرة، واكتب له الفردوس الأعلى من الجنة بغير حساب.",
  },
  living_f: {
    label_en: "Living, female", label_ar: "حية، أنثى", short: "حفظها الله",
    long: "اللهم احفظها وأطل في عمرها على طاعتك، وأكرم شأنها ويسّر أمرها، ووسع لها في رزقها وبارك لها في مالها وأهلها، وألبسها ثوب الصحة والعافية، واجعل حياتها سعيدة ومستقرة، واكتب لها الفردوس الأعلى من الجنة بغير حساب.",
  },
  living_group: {
    label_en: "Living, family or group", label_ar: "أحياء، عائلة أو مجموعة", short: "حفظهم الله",
    long: "اللهم احفظهم وأطل في أعمارهم على طاعتك، وأكرم شأنهم ويسّر أمورهم، ووسع لهم في أرزاقهم وبارك لهم في أموالهم وأهليهم، وألبسهم ثوب الصحة والعافية، واجعل حياتهم سعيدة ومستقرة، واكتب لهم الفردوس الأعلى من الجنة بغير حساب.",
  },
  dead_m: {
    label_en: "Deceased, male", label_ar: "متوفى، ذكر", short: "رحمه الله",
    long: "اللهم اغفر له وارحمه، وعافه واعف عنه، وأكرم نزله ووسّع مدخله، واغسله بالماء والثلج والبرد، ونقّه من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبره روضة من رياض الجنة، واجعل هذه الصدقة نورًا له في قبره، وأسكنه الفردوس الأعلى من الجنة بغير حساب.",
  },
  dead_f: {
    label_en: "Deceased, female", label_ar: "متوفاة، أنثى", short: "رحمها الله",
    long: "اللهم اغفر لها وارحمها، وعافها واعف عنها، وأكرم نزلها ووسّع مدخلها، واغسلها بالماء والثلج والبرد، ونقّها من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبرها روضة من رياض الجنة، واجعل هذه الصدقة نورًا لها في قبرها، وأسكنها الفردوس الأعلى من الجنة بغير حساب.",
  },
  dead_group: {
    label_en: "Deceased, more than one", label_ar: "متوفون، أكثر من شخص", short: "رحمهم الله",
    long: "اللهم اغفر لهم وارحمهم، وعافهم واعف عنهم، وأكرم نزلهم ووسّع مدخلهم، واغسلهم بالماء والثلج والبرد، ونقّهم من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبورهم روضة من رياض الجنة، واجعل هذه الصدقة نورًا لهم في قبورهم، وأسكنهم الفردوس الأعلى من الجنة بغير حساب.",
  },
};

/** Best guess from the name; staff can always change it. */
export function guessDua(name: string): DuaKind {
  const n = name.replace(/\s+/g, " ").trim();
  if (/المرحومين|المرحومون|أرواح|ارواح|والديه|والديها|والدي/.test(n)) return /المرحوم|أرواح|ارواح/.test(n) ? "dead_group" : "living_group";
  if (/المرحومة|المرحومه|المغفور لها|الفقيدة/.test(n)) return "dead_f";
  if (/المرحوم|المغفور له|الفقيد/.test(n)) return "dead_m";
  if (/عائلة|عائله|أسرة|اسرة|آل /.test(n)) return "living_group";
  if (/^فاعلة|^السيدة|^الأخت|^الاخت|^الحاجة|^أم /.test(n)) return "living_f";
  return "living_m";
}

export const MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
export function monthLabel(iso: string | null | undefined): string {
  const d = iso ? new Date(iso + (iso.length === 10 ? "T00:00:00" : "")) : new Date();
  const dd = isNaN(d.getTime()) ? new Date() : d;
  return `${MONTHS_AR[dd.getMonth()]} ${dd.getFullYear()}`;
}

export function defaultDesign(p?: { well_id?: number | string; well_type?: string | null; customer_name?: string | null; dedication?: string | null;
  country?: string | null; contractor?: { country?: string | null } | null; completion_date?: string | null; delivery_date?: string | null; order_date?: string | null }): Design {
  const name = (p?.dedication || p?.customer_name || "فاعل خير").trim();
  const kind = guessDua(name);
  return {
    template: "hayah_square", size: "digital",
    well_id: p?.well_id ? String(p.well_id) : "",
    well_type: (p?.well_type || "").trim(),
    month: monthLabel(p?.completion_date || p?.delivery_date || p?.order_date),
    name, dua_kind: kind, short_dua: DUAS[kind].short, dua: DUAS[kind].long,
    flag: flagFor(p?.country || p?.contractor?.country), icon: "well",
    bismillah: "بسم الله الرحمن الرحيم",
    verse: "﴿وَجَعَلْنَا مِنَ الْمَاءِ كُلَّ شَيْءٍ حَيٍّ﴾",
    project_label: "مشروع رقم", sadaqa_label: "صدقة جارية عن:",
    footer_site: "HayahFoundation.com", footer_org: "تنفيذ مؤسسة حياة",
    name_color: "#ef3434", name_font: "Cairo",
  };
}

// ---------------------------------------------------------------- assets
const imgCache = new Map<string, Promise<HTMLImageElement | null>>();
export function loadImage(src: string): Promise<HTMLImageElement | null> {
  if (!imgCache.has(src)) {
    imgCache.set(src, new Promise((res) => {
      const im = new Image();
      im.onload = () => res(im);
      im.onerror = () => res(null);
      im.src = src;
    }));
  }
  return imgCache.get(src)!;
}

let fontsReady: Promise<void> | null = null;
export function loadFonts(): Promise<void> {
  if (!fontsReady) {
    const sample = "بسم الله مشروع رقم HayahFoundation 0123";
    fontsReady = Promise.all([
      "700 40px Cairo", "800 40px Cairo", "900 40px Cairo", "700 40px Amiri",
      "400 40px 'Noto Naskh Arabic'", "700 40px 'Noto Naskh Arabic'",
    ].map((f) => document.fonts.load(f, sample).catch(() => []))).then(() => undefined);
  }
  return fontsReady;
}

export interface Assets { logo: HTMLImageElement | null; flag: HTMLImageElement | null; icon: HTMLImageElement | null; }
export async function loadAssets(d: Design): Promise<Assets> {
  await loadFonts();
  const flagSrc = d.flag === "custom" ? d.flag_custom : d.flag ? `/flags/${d.flag}.svg` : undefined;
  const iconSrc = d.icon === "custom" ? d.icon_custom : d.icon === "well" ? "/plaque-well.png" : undefined;
  const [logo, flag, icon] = await Promise.all([
    loadImage("/hayah-logo.png"), flagSrc ? loadImage(flagSrc) : null, iconSrc ? loadImage(iconSrc) : null,
  ]);
  return { logo, flag, icon };
}

// ---------------------------------------------------------------- drawing
type Ctx = CanvasRenderingContext2D;
const INK = "#111";

function font(ctx: Ctx, weight: number, size: number, family: string) {
  ctx.font = `${weight} ${size}px ${family.includes(" ") ? `'${family}'` : family}`;
}

/** Shrinks the font until the text fits maxW; returns the size used. */
function fit(ctx: Ctx, text: string, weight: number, size: number, family: string, maxW: number, min = 14): number {
  let s = size;
  font(ctx, weight, s, family);
  while (s > min && ctx.measureText(text).width > maxW) { s -= 2; font(ctx, weight, s, family); }
  return s;
}

function rtl(ctx: Ctx, on = true) { (ctx as any).direction = on ? "rtl" : "ltr"; }

function wrap(ctx: Ctx, text: string, maxW: number): string[] {
  const lines: string[] = [];
  for (const para of text.split(/\n/)) {
    let line = "";
    for (const w of para.split(/\s+/).filter(Boolean)) {
      const t = line ? `${line} ${w}` : w;
      if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t;
    }
    if (line) lines.push(line);
  }
  return lines;
}

function pill(ctx: Ctx, x: number, y: number, w: number, h: number, fill: string) {
  const r = h / 2;
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.arc(x + w - r, y + r, r, -Math.PI / 2, Math.PI / 2);
  ctx.lineTo(x + r, y + h); ctx.arc(x + r, y + r, r, Math.PI / 2, (3 * Math.PI) / 2); ctx.closePath();
  ctx.fillStyle = fill; ctx.fill();
}

function drawContain(ctx: Ctx, im: HTMLImageElement, x: number, y: number, w: number, h: number, align: "start" | "center" | "end" = "center") {
  const iw = im.naturalWidth || im.width || w, ih = im.naturalHeight || im.height || h;
  const s = Math.min(w / iw, h / ih);
  const dw = iw * s, dh = ih * s;
  const dx = align === "start" ? x : align === "end" ? x + w - dw : x + (w - dw) / 2;
  ctx.drawImage(im, dx, y + (h - dh) / 2, dw, dh);
  return { x: dx, y: y + (h - dh) / 2, w: dw, h: dh };
}

export function drawPlaque(ctx: Ctx, d: Design, a: Assets, scale: number) {
  ctx.save();
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, GRID, GRID);

  // Frame
  ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.strokeRect(6, 6, GRID - 12, GRID - 12);

  // Header: logo (left), flag (right), Bismillah and verse (centre)
  if (a.logo) drawContain(ctx, a.logo, 30, 16, 200, 225, "center");
  if (a.flag) {
    const f = drawContain(ctx, a.flag, 860, 70, 190, 136, "end");
    ctx.strokeStyle = "#ddd"; ctx.lineWidth = 1; ctx.strokeRect(f.x, f.y, f.w, f.h);
  }
  const cx = 545, headW = 590;
  rtl(ctx); ctx.textAlign = "center";
  ctx.fillStyle = INK; fit(ctx, d.bismillah, 800, 46, "Cairo", headW); ctx.fillText(d.bismillah, cx, 112);
  ctx.fillStyle = d.name_color; fit(ctx, d.verse, 700, 44, "Amiri", headW); ctx.fillText(d.verse, cx, 172);

  // Row: [month pill] ... [well type + "sadaqa jariya on:"] [project pill with number]
  const rowY = 248, rowH = 58, mid = rowY + rowH / 2 + 12;
  font(ctx, 800, 32, "Cairo");
  // project pill on the right
  const numTxt = d.well_id || "—";
  font(ctx, 700, 32, "Cairo"); const numW = Math.max(70, ctx.measureText(numTxt).width + 26);
  font(ctx, 800, 32, "Cairo"); const labW = ctx.measureText(d.project_label).width;
  const projW = labW + numW + 40, projX = GRID - 22 - projW;
  pill(ctx, projX, rowY, projW, rowH, INK);
  ctx.fillStyle = "#fff"; ctx.textAlign = "right"; ctx.fillText(d.project_label, GRID - 22 - 16, mid);
  pill(ctx, projX + 8, rowY + 7, numW, rowH - 14, "#fff");
  ctx.fillStyle = INK; rtl(ctx, false); ctx.textAlign = "center"; font(ctx, 700, 32, "Cairo");
  ctx.fillText(numTxt, projX + 8 + numW / 2, mid); rtl(ctx);
  // month pill on the left
  font(ctx, 800, 32, "Cairo");
  const monW = Math.max(200, ctx.measureText(d.month).width + 60), monX = 18;
  pill(ctx, monX, rowY, monW, rowH, INK);
  ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.fillText(d.month, monX + monW / 2, mid);
  // well type + label between them
  const midTxt = [d.well_type, d.sadaqa_label].filter(Boolean).join("  ");
  const room = projX - (monX + monW) - 24;
  ctx.fillStyle = INK; ctx.textAlign = "right"; fit(ctx, midTxt, 800, 34, "Cairo", room, 18);
  ctx.fillText(midTxt, projX - 10, mid);

  // Donor / dedication name
  ctx.textAlign = "center"; ctx.fillStyle = d.name_color;
  const nameWeight = d.name_font === "Cairo" ? 900 : 700;
  // One big line when it fits; long names go onto two lines instead of shrinking to nothing.
  const boxTop = 330, boxH = 175, maxNameW = 960;
  let nSize = fit(ctx, d.name, nameWeight, d.name_font === "Cairo" ? 170 : 190, d.name_font, maxNameW, 40);
  let nLines = [d.name];
  if (nSize < 110 && d.name.trim().includes(" ")) {
    for (nSize = 110; nSize >= 36; nSize -= 4) {
      font(ctx, nameWeight, nSize, d.name_font);
      nLines = wrap(ctx, d.name, maxNameW);
      if (nLines.length <= 2 && nLines.every((l) => ctx.measureText(l).width <= maxNameW) && nLines.length * nSize * 1.15 <= boxH) break;
    }
  }
  const nLh = nSize * 1.15, nTop = boxTop + (boxH - nLines.length * nLh) / 2;
  nLines.forEach((l, i) => ctx.fillText(l, GRID / 2, nTop + i * nLh + nSize * 0.85));

  // Well icon (left) and short dua (centre)
  if (a.icon) drawContain(ctx, a.icon, 22, 505, 296, 147, "start");
  ctx.fillStyle = INK; fit(ctx, d.short_dua, 900, 66, "Cairo", 520);
  ctx.fillText(d.short_dua, GRID / 2 + 30, 615);

  // Dua paragraph, shrunk until it fits between y 660 and 940
  const top = 668, bottom = 935, maxW = 990;
  let size = 44, lines: string[] = [], lh = 0;
  for (; size >= 22; size -= 2) {
    font(ctx, 400, size, "Noto Naskh Arabic");
    lines = wrap(ctx, d.dua, maxW); lh = size * 1.48;
    if (lines.length * lh <= bottom - top) break;
  }
  const startY = top + (bottom - top - lines.length * lh) / 2 + size * 1.05;
  lines.forEach((l, i) => ctx.fillText(l, GRID / 2, startY + i * lh));

  // Separator and footer
  ctx.strokeStyle = "#999"; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(60, 950); ctx.lineTo(1030, 950); ctx.stroke();
  ctx.fillStyle = INK; ctx.fillRect(6, 974, GRID - 12, 5);
  ctx.textAlign = "right"; fit(ctx, d.footer_org, 900, 54, "Cairo", 480); ctx.fillText(d.footer_org, GRID - 26, 1046);
  rtl(ctx, false); ctx.textAlign = "left"; fit(ctx, d.footer_site, 800, 50, "Cairo", 520); ctx.fillText(d.footer_site, 24, 1044);
  ctx.restore();
}

export async function renderCanvas(d: Design, px: number): Promise<HTMLCanvasElement> {
  const a = await loadAssets(d);
  const c = document.createElement("canvas");
  c.width = px; c.height = px;
  drawPlaque(c.getContext("2d")!, d, a, px / GRID);
  return c;
}

// ---------------------------------------------------------------- export
const crcTable = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
function crc32(b: Uint8Array) { let c = 0xffffffff; for (const x of b) c = crcTable[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }

/** Adds a pHYs chunk so printers and design apps read the right physical size. */
export function setPngDpi(png: Uint8Array, dpi: number): Uint8Array {
  const ppm = Math.round(dpi / 0.0254);
  const chunk = new Uint8Array(21);
  const dv = new DataView(chunk.buffer);
  dv.setUint32(0, 9); chunk.set([0x70, 0x48, 0x59, 0x73], 4); // "pHYs"
  dv.setUint32(8, ppm); dv.setUint32(12, ppm); chunk[16] = 1;
  dv.setUint32(17, crc32(chunk.subarray(4, 17)));
  const ihdrEnd = 8 + 25; // signature + IHDR chunk
  const out = new Uint8Array(png.length + 21);
  out.set(png.subarray(0, ihdrEnd)); out.set(chunk, ihdrEnd); out.set(png.subarray(ihdrEnd), ihdrEnd + 21);
  return out;
}

function toBlob(c: HTMLCanvasElement, type: string, q?: number): Promise<Blob> {
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("Could not export the plaque"))), type, q));
}

export async function exportPng(d: Design): Promise<Blob> {
  const s = SIZES[d.size];
  const c = await renderCanvas(d, s.px);
  const bytes = new Uint8Array(await (await toBlob(c, "image/png")).arrayBuffer());
  return new Blob([setPngDpi(bytes, s.dpi)], { type: "image/png" });
}

/** One-page PDF with the plaque as a high-quality JPEG at its physical size. */
export async function exportPdf(d: Design): Promise<Blob> {
  const s = SIZES[d.size];
  const mm = s.mm ?? 200;
  const px = s.mm ? s.px : Math.max(s.px, 2362);
  const c = await renderCanvas(d, px);
  const jpg = new Uint8Array(await (await toBlob(c, "image/jpeg", 0.95)).arrayBuffer());
  const pt = (mm / 25.4) * 72;
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  const offsets: number[] = [];
  let len = 0;
  const push = (x: string | Uint8Array) => { const b = typeof x === "string" ? enc.encode(x) : x; parts.push(b); len += b.length; };
  const obj = (n: number, body: string | (string | Uint8Array)[]) => {
    offsets[n] = len; push(`${n} 0 obj\n`); (Array.isArray(body) ? body : [body]).forEach(push); push("\nendobj\n");
  };
  const W = pt.toFixed(2);
  const content = `q ${W} 0 0 ${W} 0 0 cm /Im0 Do Q`;
  push("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  obj(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${W} ${W}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);
  obj(4, [`<< /Type /XObject /Subtype /Image /Width ${px} /Height ${px} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpg.length} >>\nstream\n`, jpg, "\nendstream"]);
  obj(5, `<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  const xref = len;
  push(`xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}`);
  push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(parts, { type: "application/pdf" });
}

/** Shrinks an uploaded flag or icon so it can be kept inside the saved design. */
export function fileToSmallDataUrl(file: File, maxPx = 360): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onerror = () => rej(new Error("Could not read the file"));
    r.onload = () => {
      const im = new Image();
      im.onerror = () => rej(new Error("That file is not an image"));
      im.onload = () => {
        const s = Math.min(1, maxPx / Math.max(im.width, im.height));
        const c = document.createElement("canvas");
        c.width = Math.round(im.width * s); c.height = Math.round(im.height * s);
        c.getContext("2d")!.drawImage(im, 0, 0, c.width, c.height);
        res(c.toDataURL("image/png"));
      };
      im.src = String(r.result);
    };
    r.readAsDataURL(file);
  });
}
