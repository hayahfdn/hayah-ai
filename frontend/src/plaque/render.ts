// Plaque drawing and export. Two templates, both matching HAYAH's own plaques:
//  - "hayah_square": the well plaque, laid out on a 1080 × 1080 grid
//  - "sacrifice_portrait": the sacrifice plaque, laid out on a 1024 × 1536 grid
// Each is drawn on a canvas in grid units, then scaled for screen, PNG and print PDF.
// Rule-based: no AI is involved.
import { cssFamily, ensureFont, weightFor } from "./fonts";
import { api } from "../api";

export type Template = "hayah_square" | "sacrifice_portrait";
export const GRIDS: Record<Template, [number, number]> = { hayah_square: [1080, 1080], sacrifice_portrait: [1024, 1536] };
/** Kept for older imports: the square grid size. */
export const GRID = 1080;

export type DuaKind = "living_m" | "living_f" | "living_group" | "dead_m" | "dead_f" | "dead_group" | "anon_m" | "anon_f"
  | "neutral" | "dead_neutral" | "aqiqa_boy" | "aqiqa_girl";
export type Align = "center" | "right" | "left";
export type IconKey = "pump" | "hand_pump" | "hand_tank" | "one_tank_taps" | "two_tanks_taps" | "one_tank_wall" | "two_tanks_wall" | "solar";
export type Occasion = "sadaqa" | "aqiqa_boy" | "aqiqa_girl" | "itam_sadaqa" | "itam_aqiqa";

interface Common {
  template: Template;
  size: SizeKey;
  month: string;
  name: string;
  dua_kind: DuaKind;
  short_dua: string;
  dua: string;
  flag: string;          // flag code from FLAGS, "custom" or "" for none
  flag_custom?: string;  // data: URL when flag === "custom"
  // More flags beside the first one (Hayah, 22 Nov 2026), codes from FLAGS; up to MAX_EXTRA_FLAGS.
  flags_extra?: string[];
  footer_site: string;
  footer_org: string;
  name_color: string;
  name_font: string;
  // Text controls (older saves have none: the defaults below draw them exactly as before).
  name_bold?: boolean; name_size?: number; name_line?: number; name_align?: Align;
  dua_font?: string; dua_bold?: boolean; dua_size?: number; dua_line?: number; dua_align?: Align;
  dua_sure?: boolean;  // false = gender or living/deceased unclear from the order; staff must confirm
  // Optional picture on the plaque (e.g. the solar well): the library image, its centre and width in grid units.
  // The height always follows the picture's own proportions, so it is never stretched.
  image?: PlaqueImage | null;
}
export interface PlaqueImage { ref: string; x: number; y: number; w: number }

/** Text settings with the template defaults filled in. size is a percentage of the template size. */
export function textStyle(d: Design, which: "name" | "dua") {
  const well = d.template === "hayah_square";
  if (which === "name") {
    const family = d.name_font || "Cairo";
    return { family, weight: weightFor(family, d.name_bold ?? true), k: (d.name_size ?? 100) / 100,
             line: d.name_line ?? (well ? 1.15 : 1.18), align: d.name_align ?? "center" };
  }
  const family = d.dua_font || (well ? "Noto Naskh Arabic" : "Cairo");
  const bold = d.dua_bold ?? !well;
  return { family, weight: bold ? Math.min(weightFor(family, true), 700) : 400, k: (d.dua_size ?? 100) / 100,
           line: d.dua_line ?? (well ? 1.48 : 1.5), align: d.dua_align ?? "center" };
}

export interface WellDesign extends Common {
  template: "hayah_square";
  well_id: string;
  well_type: string;
  icon: IconKey | "custom" | "none" | "well";  // "well" = older saves, same as hand_pump; "pump" = simple drawn pump
  icon_custom?: string;
  icon_side?: "left" | "right";
  bismillah: string;
  verse: string;
  project_label: string;
  sadaqa_label: string;
}

export interface SacrificeDesign extends Common {
  template: "sacrifice_portrait";
  sacrifice_no: string;
  number_label: string;
  occasion: Occasion;
  animal: string;
  header1: string;
  quote: string;
  reference: string;
  title: string;
  subtitle: string;
  country_label: string;
}

export type Design = WellDesign | SacrificeDesign;

export const SIZES = {
  digital: { en: "Digital", ar: "رقمي", widthPx: 0, mm: null as number | null, dpi: 72 },
  digital2x: { en: "Digital HD", ar: "رقمي عالي الدقة", widthPx: 0, mm: null as number | null, dpi: 144 },
  print20: { en: "Print 20 cm wide (300 dpi)", ar: "طباعة بعرض 20 سم (300 dpi)", widthPx: 2362, mm: 200, dpi: 300 },
  print30: { en: "Print 30 cm wide (300 dpi)", ar: "طباعة بعرض 30 سم (300 dpi)", widthPx: 3543, mm: 300, dpi: 300 },
};
export type SizeKey = keyof typeof SIZES;

export function pixelSize(d: Design): [number, number] {
  const [gw, gh] = GRIDS[d.template];
  const s = SIZES[d.size] || SIZES.digital;
  const w = d.size === "digital" ? gw : d.size === "digital2x" ? gw * 2 : s.widthPx;
  return [w, Math.round((w * gh) / gw)];
}

export function sizeLabel(key: SizeKey, t: Template, lang: "ar" | "en"): string {
  const s = SIZES[key];
  const [w, h] = pixelSize({ template: t, size: key } as Design);
  const [gw, gh] = GRIDS[t];
  if (s.mm) {
    const hcm = Math.round((s.mm * gh) / gw) / 10;
    return lang === "ar" ? `طباعة ${s.mm / 10} × ${hcm} سم (300 dpi)` : `Print ${s.mm / 10} × ${hcm} cm (300 dpi)`;
  }
  return `${lang === "ar" ? s.ar : s.en} ${w} × ${h}`;
}

// ---------------------------------------------------------------- flags
export interface Flag { code: string; ar: string; en: string; names: string[] }
const F = (code: string, ar: string, en: string, ...names: string[]): Flag => ({ code, ar, en, names: [en.toLowerCase(), ar, ...names] });
/** HAYAH's main countries first, then all Arab countries, then others. */
export const FLAGS: Flag[] = [
  F("pk", "باكستان", "Pakistan", "pak"), F("bd", "بنغلاديش", "Bangladesh", "بنجلاديش", "bang"), F("np", "نيبال", "Nepal", "nep"),
  F("in", "الهند", "India", "ind"), F("tz", "تنزانيا", "Tanzania", "tz"),
  // Arab League
  F("jo", "الأردن", "Jordan", "الاردن"), F("ae", "الإمارات", "United Arab Emirates", "uae", "الامارات"), F("bh", "البحرين", "Bahrain"),
  F("tn", "تونس", "Tunisia"), F("dz", "الجزائر", "Algeria"), F("dj", "جيبوتي", "Djibouti"), F("sa", "السعودية", "Saudi Arabia", "ksa", "saudi"),
  F("sd", "السودان", "Sudan"), F("sy", "سوريا", "Syria", "سورية"), F("so", "الصومال", "Somalia"), F("iq", "العراق", "Iraq"),
  F("om", "عُمان", "Oman", "عمان"), F("ps", "فلسطين", "Palestine", "gaza", "غزة"), F("qa", "قطر", "Qatar"), F("km", "جزر القمر", "Comoros", "القمر"),
  F("kw", "الكويت", "Kuwait"), F("lb", "لبنان", "Lebanon"), F("ly", "ليبيا", "Libya"), F("eg", "مصر", "Egypt"),
  F("ma", "المغرب", "Morocco"), F("mr", "موريتانيا", "Mauritania"), F("ye", "اليمن", "Yemen"),
  // Others
  F("af", "أفغانستان", "Afghanistan", "افغانستان"), F("id", "إندونيسيا", "Indonesia", "اندونيسيا"), F("et", "إثيوبيا", "Ethiopia", "اثيوبيا"),
  F("ug", "أوغندا", "Uganda", "اوغندا"), F("bj", "بنين", "Benin"), F("bf", "بوركينا فاسو", "Burkina Faso"), F("td", "تشاد", "Chad"),
  F("tg", "توغو", "Togo"), F("ci", "ساحل العاج", "Côte d'Ivoire", "ivory coast", "cote d'ivoire"), F("lk", "سريلانكا", "Sri Lanka"),
  F("sn", "السنغال", "Senegal"), F("sl", "سيراليون", "Sierra Leone"), F("gm", "غامبيا", "Gambia"), F("gh", "غانا", "Ghana"),
  F("gn", "غينيا", "Guinea"), F("cm", "الكاميرون", "Cameroon"), F("ke", "كينيا", "Kenya"), F("lr", "ليبيريا", "Liberia"),
  F("ml", "مالي", "Mali"), F("mw", "مالاوي", "Malawi"), F("ne", "النيجر", "Niger"), F("ng", "نيجيريا", "Nigeria"),
];
export const MAIN_FLAG_COUNT = 5;
export const MAX_EXTRA_FLAGS = 3;
/** Every flag on the plaque, the first one then the extra ones (no duplicates, no empties). */
export function allFlags(d: { flag: string; flags_extra?: string[] }): string[] {
  const out: string[] = [];
  for (const c of [d.flag, ...(d.flags_extra || [])]) if (c && !out.includes(c)) out.push(c);
  return out;
}
export const ARAB_FLAG_END = 27;

export function flagFor(country: string | null | undefined): string {
  const c = (country || "").trim().toLowerCase();
  if (!c) return "";
  const exact = FLAGS.find((f) => f.names.some((n) => c === n));
  if (exact) return exact.code;
  const hit = FLAGS.find((f) => f.names.some((n) => n.length >= 3 && c.startsWith(n)));
  return hit ? hit.code : "";
}
export const flagArabic = (code: string) => FLAGS.find((f) => f.code === code)?.ar || "";

// ---------------------------------------------------------------- well icons
export const WELL_ICONS: { key: IconKey; ar: string; en: string }[] = [
  { key: "hand_pump", ar: "مضخة يدوية", en: "Hand pump" },
  { key: "hand_tank", ar: "مضخة يدوية مع خزان", en: "Hand pump with tank" },
  { key: "one_tank_taps", ar: "خزان واحد و4 صنابير", en: "One tank, 4 taps" },
  { key: "two_tanks_taps", ar: "خزانان و4 صنابير", en: "Two tanks, 4 taps" },
  { key: "one_tank_wall", ar: "خزان واحد مع جدار صنابير", en: "One tank with tap wall" },
  { key: "two_tanks_wall", ar: "خزانان مع جدار صنابير", en: "Two tanks with tap wall" },
  // Hayah (21 Nov 2026): the solar well picture is the 7th choice next to the six, drawn in the same place.
  { key: "solar", ar: "بئر بالطاقة الشمسية", en: "Solar well" },
];
export const WELL_TYPES = ["بئر سطحي يدوي", "بئر سطحي مع خزان", "بئر ارتوازي متوسط", "بئر ارتوازي كبير", "بئر ارتوازي متوضأ", "بئر ارتوازي عميق", "بئر ارتوازي بالطاقة الشمسية"];

/** The order stores one of four short types; the plaque prints the full wording (still editable). */
export function plaqueTypeLabel(t: string | null | undefined): string {
  const v = (t || "").trim();
  return ({ "يدوي": "بئر سطحي يدوي", "متوسط": "بئر ارتوازي متوسط", "عميق": "بئر ارتوازي عميق",
    "شمسي": "بئر ارتوازي بالطاقة الشمسية", "كهربائي": "بئر سطحي كهربائي" } as Record<string, string>)[v] ?? v;
}

/** First guess only; staff pick the icon that matches the actual build. */
export function iconFor(wellType: string | null | undefined): IconKey {
  const t = wellType || "";
  if (/شمسي|شمسية/.test(t)) return "solar";
  if (/متوض|وضوء/.test(t)) return /كبير|خزانين|خزانان/.test(t) ? "two_tanks_wall" : "one_tank_wall";
  if (/ارتواز|عميق|شمسي|متوسط|كبير/.test(t)) return /كبير|خزانين|خزانان/.test(t) ? "two_tanks_taps" : "one_tank_taps";
  if (/خزان/.test(t)) return "hand_tank";
  return "hand_pump";
}

// ---------------------------------------------------------------- prayers
export const DUAS: Record<DuaKind, { en: string; ar: string; short: string; long: string; sacrifice?: string }> = {
  living_m: {
    en: "Living, male", ar: "حي، ذكر", short: "حفظه الله",
    long: "اللهم احفظه وأطل في عمره على طاعتك، وأكرم شأنه ويسّر أمره، ووسع له في رزقه وبارك له في ماله وأهله، وألبسه ثوب الصحة والعافية، واجعل حياته سعيدة ومستقرة، واكتب له الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم تقبل منه واجعلها صدقة مباركة، وبارك له في عمره ورزقه، واجعل أجرها في ميزان حسناته.",
  },
  living_f: {
    en: "Living, female", ar: "حية، أنثى", short: "حفظها الله",
    long: "اللهم احفظها وأطل في عمرها على طاعتك، وأكرم شأنها ويسّر أمرها، ووسع لها في رزقها وبارك لها في مالها وأهلها، وألبسها ثوب الصحة والعافية، واجعل حياتها سعيدة ومستقرة، واكتب لها الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم تقبل منها واجعلها صدقة مباركة، وبارك لها في عمرها ورزقها، واجعل أجرها في ميزان حسناتها.",
  },
  living_group: {
    en: "Living, family or group", ar: "أحياء، عائلة أو مجموعة", short: "حفظهم الله",
    long: "اللهم احفظهم وأطل في أعمارهم على طاعتك، وأكرم شأنهم ويسّر أمورهم، ووسع لهم في أرزاقهم وبارك لهم في أموالهم وأهليهم، وألبسهم ثوب الصحة والعافية، واجعل حياتهم سعيدة ومستقرة، واكتب لهم الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم تقبل منهم واجعلها صدقة مباركة، وبارك لهم في أعمارهم وأرزاقهم، واجعل أجرها في ميزان حسناتهم.",
  },
  dead_m: {
    en: "Deceased, male", ar: "متوفى، ذكر", short: "رحمه الله",
    long: "اللهم اغفر له وارحمه، وعافه واعف عنه، وأكرم نزله ووسّع مدخله، واغسله بالماء والثلج والبرد، ونقّه من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبره روضة من رياض الجنة، واجعل هذه الصدقة نورًا له في قبره، وأسكنه الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم ارحمه واغفر له، واجعلها صدقة جارية في ميزان حسناته، ونوّر قبره واجعل مثواه الجنة.",
  },
  dead_f: {
    en: "Deceased, female", ar: "متوفاة، أنثى", short: "رحمها الله",
    long: "اللهم اغفر لها وارحمها، وعافها واعف عنها، وأكرم نزلها ووسّع مدخلها، واغسلها بالماء والثلج والبرد، ونقّها من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبرها روضة من رياض الجنة، واجعل هذه الصدقة نورًا لها في قبرها، وأسكنها الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم ارحمها واغفر لها، واجعلها صدقة جارية في ميزان حسناتها، ونوّر قبرها واجعل مثواها الجنة.",
  },
  dead_group: {
    en: "Deceased, more than one", ar: "متوفون، أكثر من شخص", short: "رحمهم الله",
    long: "اللهم اغفر لهم وارحمهم، وعافهم واعف عنهم، وأكرم نزلهم ووسّع مدخلهم، واغسلهم بالماء والثلج والبرد، ونقّهم من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبورهم روضة من رياض الجنة، واجعل هذه الصدقة نورًا لهم في قبورهم، وأسكنهم الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم اغفر لهم وارحمهم، واجعل هذه الصدقة في ميزان حسناتهم، واجمعهم في جنات النعيم.",
  },
  anon_m: {
    en: "Anonymous donor (فاعل خير)", ar: "فاعل خير", short: "تقبّل الله منه",
    long: "اللهم تقبّل منه هذه الصدقة الجارية واجعل عمله خالصاً لوجهك الكريم، ووسع له في رزقه وبارك له في أهله وماله، واجعلها نوراً له في الدنيا والآخرة، واكتب له الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم تقبل منه واجعل عمله خالصاً لوجهك الكريم، وبارك له في رزقه وأهله.",
  },
  anon_f: {
    en: "Anonymous donor, female (فاعلة خير)", ar: "فاعلة خير", short: "تقبّل الله منها",
    long: "اللهم تقبّل منها هذه الصدقة الجارية واجعل عملها خالصاً لوجهك الكريم، ووسع لها في رزقها وبارك لها في أهلها ومالها، واجعلها نوراً لها في الدنيا والآخرة، واكتب لها الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم تقبل منها واجعل عملها خالصاً لوجهك الكريم، وبارك لها في رزقها وأهلها.",
  },
  neutral: {
    en: "Not clear (neutral wording)", ar: "غير واضح (صيغة محايدة)", short: "تقبّل الله",
    long: "اللهم تقبّل هذه الصدقة الجارية واجعلها في ميزان الحسنات، واجعل كل قطرة ماء منها نوراً وأجراً، واكتب لصاحبها الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم تقبل هذه الصدقة واجعلها صدقة مباركة، واجعل أجرها في ميزان الحسنات.",
  },
  dead_neutral: {
    en: "Deceased, not clear if male or female", ar: "متوفى، الجنس غير واضح", short: "رحمة الله",
    long: "اللهم اجعل هذه الصدقة الجارية رحمةً ونوراً في القبر، واغفر وارحم من قُدّمت عنه، وأسكنه الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم اجعل هذه الصدقة صدقة جارية ورحمة ونوراً، واغفر وارحم من قُدّمت عنه، واجعل مثواه الجنة.",
  },
  aqiqa_boy: {
    en: "Aqiqah, boy", ar: "عقيقة مولود", short: "",
    long: "اللهم بارك فيه، واجعله من الصالحين المصلحين، وارزقه الصحة والعافية، ووفقه لطاعتك، واجعله بارًّا بوالديه وأهله، وارزقه الخير والطمأنينة والبركة.",
  },
  aqiqa_girl: {
    en: "Aqiqah, girl", ar: "عقيقة مولودة", short: "",
    long: "اللهم بارك فيها، واجعلها من الصالحات، وقرّ بها أعين والديها، وارزقها الصحة والعافية، ونشأة طيبةً في طاعتك، واجعلها سببًا للخير والبركة.",
  },
};
export const WELL_DUA_KINDS: DuaKind[] = ["living_m", "living_f", "living_group", "dead_m", "dead_f", "dead_group", "anon_m", "anon_f", "neutral", "dead_neutral"];
export const SACRIFICE_DUA_KINDS: DuaKind[] = ["aqiqa_boy", "aqiqa_girl", ...WELL_DUA_KINDS];

/** First name for "اللهم بارك في …" (keeps compound names like عبد الله together). */
export function firstName(name: string): string {
  const w = name.replace(/^(المولود|المولودة|الطفل|الطفلة)\s+/, "").trim().split(/\s+/);
  if (w[0] === "عبد" && w[1]) return `${w[0]} ${w[1]}`;
  return w[0] || name;
}

export function duaText(kind: DuaKind, template: Template, name: string): { short: string; long: string } {
  const d = DUAS[kind];
  const long = (template === "sacrifice_portrait" && d.sacrifice) ? d.sacrifice : d.long;
  return { short: d.short, long: long.replace("{first}", firstName(name)) };
}

/** Picks the prayer from the dedication text using clear words only (المرحوم، أم، فاعل خير ...).
 * sure=false means gender or living/deceased is not clear: a neutral prayer is used and staff confirm.
 * The same rules run on the server for automatic drafts (backend/app/services/prayers.py). */
export function classifyDua(text: string): { kind: DuaKind; sure: boolean } {
  const n = (text || "").replace(/[\u064B-\u0652]/g, "").replace(/\s+/g, " ").trim();
  const F = "(?:والدتي|امي|أمي|جدتي|زوجتي|ابنتي|بنتي|اختي|أختي|خالتي|عمتي)";
  const M = "(?:ابي|أبي|جدي|زوجي|ابني|اخي|أخي|خالي|عمي)";
  if (!n) return { kind: "neutral", sure: false };
  if (/^فاعلة (ال)?خير/.test(n)) return { kind: "anon_f", sure: true };
  if (/^فاعل (ال)?خير/.test(n)) return { kind: "anon_m", sure: true };
  if (/أرواح|ارواح|موتانا|موتى|المرحومين|المرحومون|الأموات|الاموات|المتوفين|رحمهم الله|روح والدي(ه|ها|نا|ّ)/.test(n)) return { kind: "dead_group", sure: true };
  if (new RegExp(`المرحومة|المرحومه|المغفور لها|الفقيدة|المتوفاة|رحمها الله|روح ${F}`).test(n)) return { kind: "dead_f", sure: true };
  if (new RegExp(`المرحوم|المغفور له|الفقيد|المتوفى|رحمه الله|روح ${M}`).test(n)) return { kind: "dead_m", sure: true };
  if (/روح|وفاة|متوفى|متوفي/.test(n)) return { kind: "dead_neutral", sure: false };
  if (/عائلة|عائله|أسرة|اسرة|^آل |والديه|والديها|والدينا|وأولاده|واولاده|وأهله|واهله|وأهلها|واهلها/.test(n)) return { kind: "living_group", sure: true };
  if (new RegExp(`^(أم|ام|السيدة|الحاجة|الأخت|الاخت|الآنسة|الانسة|الدكتورة|المهندسة|الطفلة|المولودة) |${F}`).test(n)) return { kind: "living_f", sure: true };
  if (new RegExp(`^(أبو|ابو|السيد|الحاج|الأخ|الاخ|الدكتور|المهندس|الطفل|المولود|الشيخ) |${M}`).test(n)) return { kind: "living_m", sure: true };
  return { kind: "neutral", sure: false };
}

/** Older callers: the kind only. */
export function guessDua(name: string): DuaKind {
  return classifyDua(name).kind;
}

export const MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
export function monthLabel(iso: string | null | undefined): string {
  const d = iso ? new Date(iso + (iso.length === 10 ? "T00:00:00" : "")) : new Date();
  const dd = isNaN(d.getTime()) ? new Date() : d;
  return `${MONTHS_AR[dd.getMonth()]} ${dd.getFullYear()}`;
}

const FOOTER = { footer_site: "HayahFoundation.com", footer_org: "تنفيذ مؤسسة حياة" };

/** The name for the plaque from the order's dedication (Hayah, 21 Nov 2026): the name only, with any
 * kinship or job word kept ("والدي شعيب بن عبدالله وحصه بنت زيد"), but without "صدقة جارية عن", "لروح"
 * or prayers like "رحمهم الله"; the plaque already prints those. The prayer is still picked from the
 * full text. The same rules run on the server for automatic drafts (plaque_flow.plaque_name). */
const NAME_LEAD = /^[\s:،,.\-]*(?:(?:صدق[ةه](?:\s+جاري[ةه])?|وقف|إهداء|اهداء|هدية|ثواب)(?:\s*[:،,]\s*|\s+|$))?(?:(?:عن|على|إلى|الى|لـ)(?:\s*[:،,]\s*|\s+))?(?:(?:لروح|روح|لأرواح|لارواح|أرواح|ارواح)(?:\s*[:،,]\s*|\s+))?/;
const NAME_PRAYER = /\s*\(?\s*(?:(?:رحم|يرحم|غفر|تقبل|حفظ|يحفظ)(?:ه|ها|هم|هما|هن)?\s+الله(?:\s+(?:له|لها|لهم|لهما|منه|منها|منهم|منهما))?|رحم[ةه]\s+الله\s+(?:عليه|عليها|عليهم|عليهما))(?:\s+(?:تعالى|جميعا|جميعاً))?(?:\s+و(?:غفر|رحم)\s*(?:له|لها|لهم|لهما))?\s*\)?/g;
export function plaqueName(text: string | null | undefined): string {
  const lines = (text || "").split("\n").map((l) => l.replace(NAME_PRAYER, " ").replace(NAME_LEAD, "").replace(/\s+/g, " ").replace(/^[\s:،,.\-–]+|[\s:،,.\-–]+$/g, ""));
  return lines.filter(Boolean).join("\n");
}

export function defaultDesign(p?: { well_id?: number | string; well_type?: string | null; customer_name?: string | null; dedication?: string | null;
  country?: string | null; contractor?: { country?: string | null } | null; completion_date?: string | null; delivery_date?: string | null; order_date?: string | null }): WellDesign {
  const raw = (p?.dedication || p?.customer_name || "فاعل خير").trim();
  const { kind, sure } = classifyDua(raw);
  const name = plaqueName(raw) || plaqueName(p?.customer_name) || "فاعل خير";
  const wt = plaqueTypeLabel(p?.well_type);
  return {
    template: "hayah_square", size: "digital",
    well_id: p?.well_id ? String(p.well_id) : "",
    well_type: wt,
    month: monthLabel(p?.completion_date || p?.delivery_date || p?.order_date),
    name, dua_kind: kind, dua_sure: sure, short_dua: DUAS[kind].short, dua: DUAS[kind].long,
    flag: flagFor(p?.country || p?.contractor?.country), icon: iconFor(wt), icon_side: "left",
    bismillah: "بسم الله الرحمن الرحيم",
    verse: "﴿وَجَعَلْنَا مِنَ الْمَاءِ كُلَّ شَيْءٍ حَيٍّ﴾",
    project_label: "مشروع رقم", sadaqa_label: "صدقة جارية عن:",
    ...FOOTER, name_color: "#ef3434", name_font: "Cairo",
  };
}

// ---------------------------------------------------------------- sacrifice presets
const BISMILLAH = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ";
const HADITH_HEAD = "قال رسول الله ﷺ:";
const HADITH_AQIQA = "«كلُّ غلامٍ مُرتهنٌ بعقيقته»";
export const OCCASIONS: Record<Occasion, { ar: string; en: string; header1: string; quote: string; reference: string; title: string; subtitle: string; dua?: DuaKind }> = {
  sadaqa: { ar: "صدقة", en: "Sadaqah", header1: BISMILLAH, quote: "«لَنْ تَنَالُوا الْبِرَّ حَتَّى تُنْفِقُوا مِمَّا تُحِبُّونَ»", reference: "[آل عمران: 92]", title: "{animal} صدقة عن:", subtitle: "" },
  aqiqa_boy: { ar: "عقيقة مولود", en: "Aqiqah, boy", header1: HADITH_HEAD, quote: HADITH_AQIQA, reference: "", title: "{animal} عقيقة عن:", subtitle: "", dua: "aqiqa_boy" },
  aqiqa_girl: { ar: "عقيقة مولودة", en: "Aqiqah, girl", header1: HADITH_HEAD, quote: HADITH_AQIQA, reference: "", title: "{animal} عقيقة المولودة:", subtitle: "", dua: "aqiqa_girl" },
  itam_sadaqa: { ar: "صدقة مع الإطعام", en: "Sadaqah with feeding", header1: BISMILLAH, quote: "﴿وَيُطْعِمُونَ الطَّعَامَ عَلَىٰ حُبِّهِ مِسْكِينًا وَيَتِيمًا وَأَسِيرًا﴾", reference: "[الإنسان: 8]", title: "{animal} مع الإطعام", subtitle: "صدقة عن:" },
  itam_aqiqa: { ar: "عقيقة مع الإطعام", en: "Aqiqah with feeding", header1: HADITH_HEAD, quote: HADITH_AQIQA, reference: "", title: "{animal} مع الإطعام", subtitle: "عقيقة عن:", dua: "aqiqa_boy" },
};
export const ANIMALS = ["خروف", "ماعز", "عجل", "بقرة", "جمل"];

export function animalFor(raw: string | null | undefined): string {
  const t = (raw || "").toLowerCase();
  if (/خروف|خراف|غنم|ضأن|نعج|sheep|lamb/.test(t)) return "خروف";
  if (/ماعز|معز|تيس|goat/.test(t)) return "ماعز";
  if (/عجل|calf/.test(t)) return "عجل";
  if (/بقر|cow/.test(t)) return "بقرة";
  if (/جمل|ناق|camel/.test(t)) return "جمل";
  return (raw || "").trim() || "خروف";
}

export function occasionFor(text: string): Occasion {
  const t = text || "";
  const feeding = /إطعام|اطعام|طعام/.test(t);
  if (/عقيق/.test(t)) {
    if (feeding) return "itam_aqiqa";
    return /مولودة|بنت|انثى|أنثى/.test(t) ? "aqiqa_girl" : "aqiqa_boy";
  }
  return feeding ? "itam_sadaqa" : "sadaqa";
}

/** Fills every occasion-dependent field; keeps name, number, month and flag. */
export function applyOccasion(d: SacrificeDesign, occ: Occasion, animal = d.animal): SacrificeDesign {
  const o = OCCASIONS[occ];
  const kind: DuaKind = o.dua || (d.dua_kind.startsWith("aqiqa") ? guessDua(d.name) : d.dua_kind);
  const dua = duaText(kind, "sacrifice_portrait", d.name);
  // Hayah's rule (19 Nov 2026): the name stands on its own line and the prayer follows; no extra line.
  const sadaqaShort = "";
  return { ...d, occasion: occ, animal, header1: o.header1, quote: o.quote, reference: o.reference,
           title: o.title.replace("{animal}", animal), subtitle: o.subtitle, dua_kind: kind, dua: dua.long, short_dua: sadaqaShort };
}

export function defaultSacrificeDesign(s?: { sacrifice_no?: number | string; donor_name?: string | null; dedication?: string | null;
  animal_type?: string | null; intention?: string | null; extras?: string | null; order_date?: string | null; delivery_date?: string | null;
  contractor_country?: string | null }): SacrificeDesign {
  const raw = (s?.dedication || s?.donor_name || "فاعل خير").trim();
  const cls = classifyDua(raw);
  const name = plaqueName(raw) || plaqueName(s?.donor_name) || "فاعل خير";
  const flag = flagFor(s?.contractor_country);
  const base: SacrificeDesign = {
    template: "sacrifice_portrait", size: "digital", sacrifice_no: s?.sacrifice_no ? String(s.sacrifice_no) : "",
    number_label: "ذبيحة رقم", month: monthLabel(s?.delivery_date || s?.order_date), name,
    dua_kind: cls.kind, dua_sure: cls.sure, short_dua: "", dua: "", flag, country_label: flagArabic(flag),
    occasion: "sadaqa", animal: animalFor(s?.animal_type), header1: "", quote: "", reference: "", title: "", subtitle: "",
    footer_site: "Hayah Foundation", footer_org: FOOTER.footer_org, name_color: "#c4161c", name_font: "Cairo",
  };
  return applyOccasion(base, occasionFor(`${s?.intention || ""} ${s?.animal_type || ""} ${s?.extras || ""}`));
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

/** Loads the template's fixed fonts plus the fonts chosen for the name and prayer. */
export function loadFonts(d?: Design): Promise<void> {
  const need: [string, number][] = [["Cairo", 600], ["Cairo", 700], ["Cairo", 800], ["Cairo", 900], ["Amiri", 700],
    ["Noto Naskh Arabic", 400], ["Noto Naskh Arabic", 700]];
  if (d) for (const w of ["name", "dua"] as const) { const st = textStyle(d, w); need.push([st.family, st.weight]); }
  return Promise.all(need.map(([f, w]) => ensureFont(f, w))).then(() => undefined);
}

export interface Assets { logo: HTMLImageElement | null; flag: HTMLImageElement | null; icon: HTMLImageElement | null; image?: HTMLImageElement | null;
  more?: HTMLImageElement[] }  // the extra flags
export interface LibraryImage { id: string; name: string; src: string; builtin: boolean }
let libCache: Promise<LibraryImage[]> | null = null;
/** The approved image library (built-in solar well + images people uploaded). Read once per page. */
export function imageLibrary(reload = false): Promise<LibraryImage[]> {
  if (!libCache || reload) libCache = api<LibraryImage[]>("/api/plaque-images").catch(() => { libCache = null; return []; });
  return libCache;
}
/** "lib:<id>" -> the image's address; a plain address or data: URL is used as it is. */
export async function imageSrc(ref: string): Promise<string | null> {
  if (!ref.startsWith("lib:")) return ref;
  const id = ref.slice(4);
  if (id === "solar-well") return "/plaque-images/solar-well.png";
  return (await imageLibrary()).find((i) => i.id === id)?.src || null;
}
export async function loadAssets(d: Design): Promise<Assets> {
  await loadFonts(d);
  const flagSrc = d.flag === "custom" ? d.flag_custom : d.flag ? `/flags/${d.flag}.svg` : undefined;
  const extra = (d.flags_extra || []).filter((c) => c && c !== d.flag && c !== "custom").slice(0, MAX_EXTRA_FLAGS);
  let iconSrc: string | undefined;
  if (d.template === "hayah_square") {
    const ic = d.icon === "well" ? "hand_pump" : d.icon;
    iconSrc = ic === "custom" ? d.icon_custom : ic === "none" || ic === "pump" ? undefined : `/wells/${ic}.png`;
  }
  const imgSrc = d.image?.ref ? await imageSrc(d.image.ref) : null;
  const [logo, flag, icon, image, ...more] = await Promise.all([
    loadImage("/hayah-logo.png"), flagSrc ? loadImage(flagSrc) : null, iconSrc ? loadImage(iconSrc) : null,
    imgSrc ? loadImage(imgSrc) : null, ...extra.map((c) => loadImage(`/flags/${c}.svg`)),
  ]);
  return { logo, flag, icon, image, more: more.filter(Boolean) as HTMLImageElement[] };
}

// ---------------------------------------------------------------- drawing helpers
type Ctx = CanvasRenderingContext2D;
const INK = "#111";

function font(ctx: Ctx, weight: number, size: number, family: string) {
  ctx.font = `${weight} ${size}px ${cssFamily(family)}`;
}

/** x position and canvas alignment for a line inside [left, right]. */
function place(ctx: Ctx, align: Align, left: number, right: number): number {
  ctx.textAlign = align;
  return align === "center" ? (left + right) / 2 : align === "right" ? right : left;
}

/** Largest size from min to max at which one line fits the box, and the baseline that puts its
 * ink exactly in the middle of the box (measured, so it holds for every font). */
function fitBox(ctx: Ctx, text: string, weight: number, family: string, w: number, h: number, max: number, min: number) {
  let lo = min, hi = max;
  const fits = (s: number) => {
    font(ctx, weight, s, family);
    const m = ctx.measureText(text);
    return m.width <= w && (m.actualBoundingBoxAscent + m.actualBoundingBoxDescent) <= h;
  };
  if (!fits(lo)) hi = lo;
  while (hi - lo > 0.5) { const mid = (lo + hi) / 2; if (fits(mid)) lo = mid; else hi = mid; }
  const size = Math.floor(lo * 2) / 2;
  font(ctx, weight, size, family);
  const m = ctx.measureText(text);
  return { size, dy: (m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2 };
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

/** Largest size (≤ size) at which text wraps into at most maxLines lines within maxW. */
function fitLines(ctx: Ctx, text: string, weight: number, size: number, family: string, maxW: number, maxLines: number, min = 24) {
  let s = size, lines: string[] = [];
  for (; s >= min; s -= 2) {
    font(ctx, weight, s, family);
    lines = wrap(ctx, text, maxW);
    if (lines.length <= maxLines && lines.every((l) => ctx.measureText(l).width <= maxW)) break;
  }
  return { size: Math.max(s, min), lines };
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

function drawFlag(ctx: Ctx, im: HTMLImageElement, x: number, y: number, w: number, h: number, align: "center" | "end") {
  const f = drawContain(ctx, im, x, y, w, h, align);
  ctx.strokeStyle = "#ddd"; ctx.lineWidth = 1; ctx.strokeRect(f.x, f.y, f.w, f.h);
  return f;
}

/** Several flags in one box: the grid (columns × rows) that gives each flag the largest size, centred. */
function drawFlagGroup(ctx: Ctx, ims: HTMLImageElement[], x: number, y: number, w: number, h: number, gap = 10) {
  const n = ims.length, ar = 1.5;
  let best = { cols: 1, rows: n, fw: 0 };
  for (let cols = 1; cols <= n; cols++) {
    const rows = Math.ceil(n / cols);
    const fw = Math.min((w - gap * (cols - 1)) / cols, ((h - gap * (rows - 1)) / rows) * ar);
    if (fw > best.fw) best = { cols, rows, fw };
  }
  const fh = best.fw / ar, totalH = best.rows * fh + (best.rows - 1) * gap;
  ims.forEach((im, i) => {
    const r = Math.floor(i / best.cols), inRow = Math.min(best.cols, n - r * best.cols), c = i % best.cols;
    const rowW = inRow * best.fw + (inRow - 1) * gap;
    drawFlag(ctx, im, x + (w - rowW) / 2 + c * (best.fw + gap), y + (h - totalH) / 2 + r * (fh + gap), best.fw, fh, "center");
  });
}

/** A simple hand pump drawn with lines (the one on HAYAH's certificate), centred on cx, cy; s = scale. */
export function drawSimplePump(ctx: Ctx, cx: number, cy: number, s = 1, color = "#3a7cc0") {
  ctx.save(); ctx.translate(cx, cy); ctx.scale(s, s); ctx.fillStyle = color; ctx.strokeStyle = color; ctx.lineCap = "round";
  const r = (x: number, y: number, w: number, h: number, rr: number) => {
    ctx.beginPath(); ctx.moveTo(x + rr, y); ctx.arcTo(x + w, y, x + w, y + h, rr); ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr); ctx.arcTo(x, y, x + w, y, rr); ctx.closePath(); ctx.fill();
  };
  r(-14, -38, 28, 92, 6);                                                  // body
  ctx.fillRect(-24, 50, 48, 10);                                           // base
  ctx.beginPath(); ctx.arc(0, -42, 13, 0, Math.PI * 2); ctx.fill();        // cap
  ctx.lineWidth = 10; ctx.beginPath(); ctx.moveTo(-12, -20); ctx.lineTo(-34, -16); ctx.lineTo(-38, -4); ctx.stroke(); // spout
  ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(10, -42); ctx.quadraticCurveTo(34, -40, 36, -10); ctx.quadraticCurveTo(38, 14, 26, 24); ctx.stroke(); // handle
  ctx.beginPath(); ctx.arc(26, 28, 6, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

export function drawPlaque(ctx: Ctx, d: Design, a: Assets, scale: number) {
  ctx.save();
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.textBaseline = "alphabetic";
  const [gw, gh] = GRIDS[d.template];
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, gw, gh);
  if (d.template === "sacrifice_portrait") drawSacrifice(ctx, d, a); else drawWell(ctx, d, a);
  const box = imageBox(d, a.image);
  if (box && a.image) ctx.drawImage(a.image, box.x, box.y, box.w, box.h);
  ctx.restore();
}

/** Where the plaque's picture sits, in grid units (null when there is none). */
export function imageBox(d: Design, im: HTMLImageElement | null | undefined) {
  if (!d.image || !im) return null;
  const nw = im.naturalWidth || im.width, nh = im.naturalHeight || im.height;
  if (!nw || !nh) return null;
  const w = d.image.w, h = (w * nh) / nw;
  return { x: d.image.x - w / 2, y: d.image.y - h / 2, w, h };
}

/** Lines the person typed (Enter = new line), each kept as its own line. */
const typedLines = (text: string) => text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

// ---------------------------------------------------------------- well plaque (1080 × 1080)
function drawWell(ctx: Ctx, d: WellDesign, a: Assets) {
  const G = 1080;
  ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.strokeRect(6, 6, G - 12, G - 12);

  // Header: logo (left), flag (right), Bismillah and verse (centre)
  if (a.logo) drawContain(ctx, a.logo, 30, 16, 200, 225, "center");
  const wf = [a.flag, ...(a.more || [])].filter(Boolean) as HTMLImageElement[];
  if (wf.length === 1) drawFlag(ctx, wf[0], 860, 70, 190, 136, "end");
  else if (wf.length > 1) drawFlagGroup(ctx, wf, 850, 26, 206, 214, 8);
  const cx = 545, headW = 590;
  rtl(ctx); ctx.textAlign = "center";
  ctx.fillStyle = INK; fit(ctx, d.bismillah, 800, 46, "Cairo", headW); ctx.fillText(d.bismillah, cx, 112);
  ctx.fillStyle = d.name_color; fit(ctx, d.verse, 700, 44, "Amiri", headW); ctx.fillText(d.verse, cx, 172);

  // Row: [month pill] ... [well type + "sadaqa jariya on:"] [project pill with number]
  const rowY = 248, rowH = 58, mid = rowY + rowH / 2 + 12;
  const numTxt = d.well_id || "—";
  font(ctx, 700, 32, "Cairo"); const numW = Math.max(70, ctx.measureText(numTxt).width + 26);
  font(ctx, 800, 32, "Cairo"); const labW = ctx.measureText(d.project_label).width;
  const projW = labW + numW + 40, projX = G - 22 - projW;
  pill(ctx, projX, rowY, projW, rowH, INK);
  ctx.fillStyle = "#fff"; ctx.textAlign = "right"; ctx.fillText(d.project_label, G - 22 - 16, mid);
  pill(ctx, projX + 8, rowY + 7, numW, rowH - 14, "#fff");
  ctx.fillStyle = INK; rtl(ctx, false); ctx.textAlign = "center"; font(ctx, 700, 32, "Cairo");
  ctx.fillText(numTxt, projX + 8 + numW / 2, mid); rtl(ctx);
  font(ctx, 800, 32, "Cairo");
  const monW = Math.max(200, ctx.measureText(d.month).width + 60), monX = 18;
  pill(ctx, monX, rowY, monW, rowH, INK);
  ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.fillText(d.month, monX + monW / 2, mid);
  // The text between the month and the project number grows when short and shrinks when long,
  // and is always centred in that space, across and down (Hayah's rule, 19 Nov 2026).
  const midTxt = [d.well_type, d.sadaqa_label].filter(Boolean).join("  ");
  const boxL = monX + monW + 12, boxR = projX - 12;
  if (midTxt) {
    const fb = fitBox(ctx, midTxt, 800, "Cairo", boxR - boxL - 8, rowH - 8, 52, 14);
    ctx.fillStyle = INK; ctx.textAlign = "center";
    ctx.fillText(midTxt, (boxL + boxR) / 2, rowY + rowH / 2 + fb.dy);
  }

  // Donor / dedication name: one big line when it fits, two lines for long names
  ctx.fillStyle = d.name_color;
  const ns = textStyle(d, "name");
  const nameWeight = ns.weight;
  const boxTop = 330, boxH = 175, maxNameW = 960;
  const nMax = Math.round((ns.family === "Cairo" ? 170 : 190) * ns.k);
  const typed = typedLines(d.name);
  let nSize = fit(ctx, d.name, nameWeight, nMax, ns.family, maxNameW, 40);
  let nLines = [d.name];
  if (typed.length > 1) {
    // The person split the name into lines: keep exactly those lines and shrink until they all fit.
    const roomH = boxH + 40;
    for (nSize = nMax; nSize > 30; nSize -= 2) {
      font(ctx, nameWeight, nSize, ns.family);
      if (typed.every((l) => ctx.measureText(l).width <= maxNameW) && typed.length * nSize * ns.line <= roomH) break;
    }
    nLines = typed;
  } else if (nSize < 110 && d.name.trim().includes(" ")) {
    for (nSize = Math.min(110, nMax); nSize >= 36; nSize -= 4) {
      font(ctx, nameWeight, nSize, ns.family);
      nLines = wrap(ctx, d.name, maxNameW);
      if (nLines.length <= 2 && nLines.every((l) => ctx.measureText(l).width <= maxNameW) && nLines.length * nSize * ns.line <= boxH) break;
    }
  }
  font(ctx, nameWeight, nSize, ns.family);
  const nLh = nSize * ns.line, nTop = boxTop + (boxH - nLines.length * nLh) / 2;
  const nx = place(ctx, ns.align, (G - maxNameW) / 2, (G + maxNameW) / 2);
  nLines.forEach((l, i) => ctx.fillText(l, nx, nTop + i * nLh + nSize * 0.85));
  ctx.textAlign = "center";

  // Well icon (left or right) and the short prayer beside it
  const right = d.icon_side === "right";
  const simple = d.icon === "pump";
  if (a.icon) drawContain(ctx, a.icon, right ? G - 22 - 300 : 22, 478, 300, 190, right ? "end" : "start");
  else if (simple) drawSimplePump(ctx, right ? G - 22 - 95 : 22 + 95, 568, 1.55, INK);
  ctx.fillStyle = INK;
  const sdLines = typedLines(d.short_dua);
  const sdX = G / 2 + (a.icon || simple ? (right ? -40 : 30) : 0);
  if (sdLines.length > 1) {  // typed on several lines: smaller, stacked around the same centre
    let sz = 66;
    for (; sz > 24; sz -= 2) { font(ctx, 900, sz, "Cairo"); if (sdLines.every((l) => ctx.measureText(l).width <= 520) && sdLines.length * sz * 1.2 <= 150) break; }
    const lh = sz * 1.2, y0 = 615 - ((sdLines.length - 1) * lh) / 2;
    sdLines.forEach((l, i) => ctx.fillText(l, sdX, y0 + i * lh));
  } else {
    fit(ctx, d.short_dua, 900, 66, "Cairo", 520);
    ctx.fillText(d.short_dua.trim(), sdX, 615);
  }

  // Prayer paragraph, shrunk until it fits between y 668 and 935
  const top = 668, bottom = 935, maxW = 990;
  const ds = textStyle(d, "dua");
  let size = Math.round(44 * ds.k), lines: string[] = [], lh = 0;
  for (; size >= 18; size -= 2) {
    font(ctx, ds.weight, size, ds.family);
    lines = wrap(ctx, d.dua, maxW); lh = size * ds.line;
    if (lines.length * lh <= bottom - top && lines.every((l) => ctx.measureText(l).width <= maxW)) break;
  }
  const startY = top + (bottom - top - lines.length * lh) / 2 + size * 1.05;
  const dx = place(ctx, ds.align, (G - maxW) / 2, (G + maxW) / 2);
  lines.forEach((l, i) => ctx.fillText(l, dx, startY + i * lh));
  ctx.textAlign = "center";

  // Separator and footer
  ctx.strokeStyle = "#999"; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(60, 950); ctx.lineTo(1030, 950); ctx.stroke();
  ctx.fillStyle = INK; ctx.fillRect(6, 974, G - 12, 5);
  ctx.textAlign = "right"; fit(ctx, d.footer_org, 900, 54, "Cairo", 480); ctx.fillText(d.footer_org, G - 26, 1046);
  rtl(ctx, false); ctx.textAlign = "left"; fit(ctx, d.footer_site, 800, 50, "Cairo", 520); ctx.fillText(d.footer_site, 24, 1044);
}

// ---------------------------------------------------------------- sacrifice plaque (1024 × 1536)
function drawSacrifice(ctx: Ctx, d: SacrificeDesign, a: Assets) {
  const W = 1024, H = 1536, cx = W / 2;
  ctx.strokeStyle = INK; ctx.lineWidth = 3; ctx.strokeRect(10, 10, W - 20, H - 20);

  // Logo (left), flag and country name (right)
  if (a.logo) drawContain(ctx, a.logo, 45, 30, 200, 270, "center");
  const sf = [a.flag, ...(a.more || [])].filter(Boolean) as HTMLImageElement[];
  if (sf.length === 1) drawFlag(ctx, sf[0], 785, 70, 210, 136, "center");
  else if (sf.length > 1) drawFlagGroup(ctx, sf, 775, 30, 230, 210, 8);
  rtl(ctx); ctx.textAlign = "center";
  if (d.country_label) {
    ctx.fillStyle = "#1a6fe0"; fit(ctx, d.country_label, 900, 68, "Cairo", 230, 30);
    ctx.fillText(d.country_label, 890, 292);
  }

  // Header block between logo and flag: line 1, red quote (up to 2 lines), reference
  const hx = 515, hw = 530;
  const blocks: { text: string; weight: number; size: number; color: string; family: string; lines?: string[]; lh?: number }[] = [];
  if (d.header1) blocks.push({ text: d.header1, weight: 700, size: d.header1.startsWith("بِسْمِ") || d.header1.startsWith("بسم") ? 40 : 50, color: INK, family: d.header1.includes("ﷺ") ? "Cairo" : "Amiri" });
  if (d.quote) blocks.push({ text: d.quote, weight: 700, size: 54, color: d.name_color, family: "Cairo" });
  if (d.reference) blocks.push({ text: d.reference, weight: 700, size: 34, color: INK, family: "Cairo" });
  for (const b of blocks) {
    // The quote stays on one line when it can (at 44px or more), otherwise it takes two.
    let f = fitLines(ctx, b.text, b.weight, b.size, b.family, hw, 1, b.text === d.quote ? 40 : 20);
    if (b.text === d.quote && f.lines.length > 1) f = fitLines(ctx, b.text, b.weight, b.size, b.family, hw, 2, 20);
    b.size = f.size; b.lines = f.lines; b.lh = f.size * 1.35;
  }
  const gap = 18;
  const total = blocks.reduce((s, b) => s + b.lines!.length * b.lh!, 0) + gap * Math.max(0, blocks.length - 1);
  let y = 30 + (290 - total) / 2;
  for (const b of blocks) {
    ctx.fillStyle = b.color; font(ctx, b.weight, b.size, b.family);
    b.lines!.forEach((l) => { ctx.fillText(l, hx, y + b.size * 1.0); y += b.lh!; });
    y += gap;
  }

  // Row: "ذبيحة رقم" + big number (right), month (left)
  const rowBase = 425;
  ctx.fillStyle = INK; ctx.textAlign = "right"; font(ctx, 800, 46, "Cairo");
  ctx.fillText(d.number_label, W - 35, rowBase);
  const lw = ctx.measureText(d.number_label).width;
  rtl(ctx, false); font(ctx, 900, 92, "Cairo"); ctx.textAlign = "right";
  ctx.fillText(d.sacrifice_no || "—", W - 35 - lw - 14, rowBase);
  ctx.textAlign = "left"; font(ctx, 800, 46, "Cairo"); rtl(ctx);
  ctx.textAlign = "left"; ctx.fillText(d.month, 38, rowBase - 4);

  // Body: title, red subtitle, red name, short prayer, prayer paragraph. Shrinks to fit.
  ctx.textAlign = "center";
  const top = 450, bottom = 1375, maxW = 930;
  const ns = textStyle(d, "name"), ds = textStyle(d, "dua");
  for (let k = 1; k >= 0.6; k -= 0.05) {
    const parts: { lines: string[]; size: number; weight: number; family: string; color: string; lh: number; gapAfter: number; align: Align }[] = [];
    const add = (text: string, weight: number, size: number, family: string, color: string, maxLines: number, lhK: number, gapAfter: number, min = 26, align: Align = "center") => {
      if (!text.trim()) return;
      const f = fitLines(ctx, text, weight, Math.round(size * k), family, maxW, maxLines, Math.round(min * k));
      parts.push({ lines: f.lines, size: f.size, weight, family, color, lh: f.size * lhK, gapAfter, align });
    };
    add(d.title, 900, 80, "Cairo", INK, 2, 1.3, 6);
    add(d.subtitle, 900, 80, "Cairo", d.name_color, 1, 1.3, 4);
    add(d.name, ns.weight, Math.round((d.name.trim().length <= 8 ? 190 : 140) * ns.k), ns.family, d.name_color, Math.max(2, typedLines(d.name).length), ns.line, 18, 40, ns.align);
    add(d.short_dua, 800, 66, "Cairo", INK, Math.max(1, typedLines(d.short_dua).length), 1.35, 16);
    add(d.dua, ds.weight, Math.round(60 * ds.k), ds.family, INK, 9, ds.line, 0, 20, ds.align);
    const h = parts.reduce((s, p) => s + p.lines.length * p.lh + p.gapAfter, 0);
    if (h <= bottom - top || k <= 0.61) {
      let yy = top + Math.max(0, (bottom - top - h) / 2) * 0.6;
      for (const p of parts) {
        ctx.fillStyle = p.color; font(ctx, p.weight, p.size, p.family);
        const px = place(ctx, p.align, cx - maxW / 2, cx + maxW / 2);
        p.lines.forEach((l) => { ctx.fillText(l, px, yy + p.lh * 0.78); yy += p.lh; });
        yy += p.gapAfter;
      }
      ctx.textAlign = "center";
      break;
    }
  }

  // Footer
  ctx.strokeStyle = INK; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(30, 1395); ctx.lineTo(W - 30, 1395); ctx.stroke();
  ctx.fillStyle = INK; ctx.textAlign = "right"; fit(ctx, d.footer_org, 600, 54, "Cairo", 460); ctx.fillText(d.footer_org, W - 32, 1470);
  rtl(ctx, false); ctx.textAlign = "left"; fit(ctx, d.footer_site, 600, 50, "Cairo", 460); ctx.fillText(d.footer_site, 32, 1468);
}

export async function renderCanvas(d: Design, w?: number, h?: number): Promise<HTMLCanvasElement> {
  const a = await loadAssets(d);
  const [pw, ph] = w && h ? [w, h] : pixelSize(d);
  const c = document.createElement("canvas");
  c.width = pw; c.height = ph;
  drawPlaque(c.getContext("2d")!, d, a, pw / GRIDS[d.template][0]);
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
  const c = await renderCanvas(d);
  const bytes = new Uint8Array(await (await toBlob(c, "image/png")).arrayBuffer());
  return new Blob([setPngDpi(bytes, (SIZES[d.size] || SIZES.digital).dpi)], { type: "image/png" });
}

/** One-page PDF with the plaque as a high-quality JPEG at its physical size. */
export async function exportPdf(d: Design): Promise<Blob> {
  const s = SIZES[d.size] || SIZES.digital;
  const [gw, gh] = GRIDS[d.template];
  const mmW = s.mm ?? 200, mmH = (mmW * gh) / gw;
  const pxW = s.mm ? s.widthPx : 2362, pxH = Math.round((pxW * gh) / gw);
  return canvasPdf(await renderCanvas(d, pxW, pxH), mmW, mmH);
}

/** Any canvas as a one-page PDF of mmW × mmH (used by the plaques and the contract). */
export async function canvasPdf(c: HTMLCanvasElement, mmW: number, mmH: number): Promise<Blob> {
  const pxW = c.width, pxH = c.height;
  const jpg = new Uint8Array(await (await toBlob(c, "image/jpeg", 0.95)).arrayBuffer());
  const ptW = ((mmW / 25.4) * 72).toFixed(2), ptH = ((mmH / 25.4) * 72).toFixed(2);
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  const offsets: number[] = [];
  let len = 0;
  const push = (x: string | Uint8Array) => { const b = typeof x === "string" ? enc.encode(x) : x; parts.push(b); len += b.length; };
  const obj = (n: number, body: string | (string | Uint8Array)[]) => {
    offsets[n] = len; push(`${n} 0 obj\n`); (Array.isArray(body) ? body : [body]).forEach(push); push("\nendobj\n");
  };
  const content = `q ${ptW} 0 0 ${ptH} 0 0 cm /Im0 Do Q`;
  push("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  obj(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${ptW} ${ptH}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);
  obj(4, [`<< /Type /XObject /Subtype /Image /Width ${pxW} /Height ${pxH} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpg.length} >>\nstream\n`, jpg, "\nendstream"]);
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
