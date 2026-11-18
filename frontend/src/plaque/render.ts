// Plaque drawing and export. Two templates, both matching HAYAH's own plaques:
//  - "hayah_square": the well plaque, laid out on a 1080 × 1080 grid
//  - "sacrifice_portrait": the sacrifice plaque, laid out on a 1024 × 1536 grid
// Each is drawn on a canvas in grid units, then scaled for screen, PNG and print PDF.
// Rule-based: no AI is involved.
import "@fontsource/cairo/600.css";
import "@fontsource/cairo/700.css";
import "@fontsource/cairo/800.css";
import "@fontsource/cairo/900.css";
import "@fontsource/amiri/700.css";
import "@fontsource/noto-naskh-arabic/400.css";
import "@fontsource/noto-naskh-arabic/700.css";

export type Template = "hayah_square" | "sacrifice_portrait";
export const GRIDS: Record<Template, [number, number]> = { hayah_square: [1080, 1080], sacrifice_portrait: [1024, 1536] };
/** Kept for older imports: the square grid size. */
export const GRID = 1080;

export type DuaKind = "living_m" | "living_f" | "living_group" | "dead_m" | "dead_f" | "dead_group" | "aqiqa_boy" | "aqiqa_girl";
export type IconKey = "hand_pump" | "hand_tank" | "one_tank_taps" | "two_tanks_taps" | "one_tank_wall" | "two_tanks_wall";
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
  footer_site: string;
  footer_org: string;
  name_color: string;
  name_font: "Cairo" | "Amiri" | "Noto Naskh Arabic";
}

export interface WellDesign extends Common {
  template: "hayah_square";
  well_id: string;
  well_type: string;
  icon: IconKey | "custom" | "none" | "well";  // "well" = older saves, same as hand_pump
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
];
export const WELL_TYPES = ["بئر سطحي يدوي", "بئر سطحي مع خزان", "بئر ارتوازي متوسط", "بئر ارتوازي كبير", "بئر ارتوازي متوضأ", "بئر ارتوازي عميق", "بئر بالطاقة الشمسية"];
/** The wording printed on the plaque for each of the four well types in the system (editable on the plaque). */
export const PLAQUE_TYPE_TEXT: Record<string, string> = {
  "يدوي": "بئر سطحي يدوي", "متوسط": "بئر ارتوازي متوسط", "عميق": "بئر ارتوازي عميق", "شمسي": "بئر بالطاقة الشمسية",
  "كهربائي": "بئر سطحي كهربائي",
};

/** First guess only; staff pick the icon that matches the actual build. */
export function iconFor(wellType: string | null | undefined): IconKey {
  const t = wellType || "";
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
    sacrifice: "اللهم احفظه وأطل في عمره على طاعتك، وأكرم شأنه ويسّر أمره، ووسع له في رزقه وبارك له في ماله وأهله، وألبسه ثوب الصحة والعافية، واجعله من عبادك الصالحين.",
  },
  living_f: {
    en: "Living, female", ar: "حية، أنثى", short: "حفظها الله",
    long: "اللهم احفظها وأطل في عمرها على طاعتك، وأكرم شأنها ويسّر أمرها، ووسع لها في رزقها وبارك لها في مالها وأهلها، وألبسها ثوب الصحة والعافية، واجعل حياتها سعيدة ومستقرة، واكتب لها الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم احفظها وبارك لها في عمرها وصحتها وأهلها، ووسّع لها في رزقها، وحقق لها الخير في الدنيا والآخرة، وألبسها ثوب العافية والطمأنينة.",
  },
  living_group: {
    en: "Living, family or group", ar: "أحياء، عائلة أو مجموعة", short: "حفظهم الله",
    long: "اللهم احفظهم وأطل في أعمارهم على طاعتك، وأكرم شأنهم ويسّر أمورهم، ووسع لهم في أرزاقهم وبارك لهم في أموالهم وأهليهم، وألبسهم ثوب الصحة والعافية، واجعل حياتهم سعيدة ومستقرة، واكتب لهم الفردوس الأعلى من الجنة بغير حساب.",
    sacrifice: "اللهم احفظهم وبارك لهم في أعمارهم وصحتهم وأهليهم، ووسّع لهم في أرزاقهم، وحقق لهم الخير في الدنيا والآخرة، وألبسهم ثوب العافية والطمأنينة.",
  },
  dead_m: {
    en: "Deceased, male", ar: "متوفى، ذكر", short: "رحمه الله",
    long: "اللهم اغفر له وارحمه، وعافه واعف عنه، وأكرم نزله ووسّع مدخله، واغسله بالماء والثلج والبرد، ونقّه من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبره روضة من رياض الجنة، واجعل هذه الصدقة نورًا له في قبره، وأسكنه الفردوس الأعلى من الجنة بغير حساب.",
  },
  dead_f: {
    en: "Deceased, female", ar: "متوفاة، أنثى", short: "رحمها الله",
    long: "اللهم اغفر لها وارحمها، وعافها واعف عنها، وأكرم نزلها ووسّع مدخلها، واغسلها بالماء والثلج والبرد، ونقّها من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبرها روضة من رياض الجنة، واجعل هذه الصدقة نورًا لها في قبرها، وأسكنها الفردوس الأعلى من الجنة بغير حساب.",
  },
  dead_group: {
    en: "Deceased, more than one", ar: "متوفون، أكثر من شخص", short: "رحمهم الله",
    long: "اللهم اغفر لهم وارحمهم، وعافهم واعف عنهم، وأكرم نزلهم ووسّع مدخلهم، واغسلهم بالماء والثلج والبرد، ونقّهم من الخطايا كما ينقّى الثوب الأبيض من الدنس، واجعل قبورهم روضة من رياض الجنة، واجعل هذه الصدقة نورًا لهم في قبورهم، وأسكنهم الفردوس الأعلى من الجنة بغير حساب.",
  },
  aqiqa_boy: {
    en: "Aqiqah, boy", ar: "عقيقة مولود", short: "",
    long: "اللهم بارك في {first}، واجعله من الصالحين المصلحين، وارزقه الصحة والعافية، ووفقه لطاعتك، واجعله بارًّا بوالديه وأهله، وارزقه الخير والطمأنينة والبركة.",
  },
  aqiqa_girl: {
    en: "Aqiqah, girl", ar: "عقيقة مولودة", short: "",
    long: "اللهم بارك في {first}، واجعلها من الصالحات، وقرّ بها أعين والديها، وارزقها الصحة والعافية، ونشأة طيبةً في طاعتك، واجعلها سببًا للخير والبركة.",
  },
};
export const WELL_DUA_KINDS: DuaKind[] = ["living_m", "living_f", "living_group", "dead_m", "dead_f", "dead_group"];
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

/** Best guess from the name; staff can always change it. */
export function guessDua(name: string): DuaKind {
  const n = name.replace(/\s+/g, " ").trim();
  if (/المرحومين|المرحومون|أرواح|ارواح/.test(n)) return "dead_group";
  if (/المرحومة|المرحومه|المغفور لها|الفقيدة/.test(n)) return "dead_f";
  if (/المرحوم|المغفور له|الفقيد/.test(n)) return "dead_m";
  if (/عائلة|عائله|أسرة|اسرة|^آل |والديه|والديها|والدي/.test(n)) return "living_group";
  if (/^فاعلة|^السيدة|^الأخت|^الاخت|^الحاجة|^أم /.test(n)) return "living_f";
  return "living_m";
}

export const MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
export function monthLabel(iso: string | null | undefined): string {
  const d = iso ? new Date(iso + (iso.length === 10 ? "T00:00:00" : "")) : new Date();
  const dd = isNaN(d.getTime()) ? new Date() : d;
  return `${MONTHS_AR[dd.getMonth()]} ${dd.getFullYear()}`;
}

const FOOTER = { footer_site: "HayahFoundation.com", footer_org: "تنفيذ مؤسسة حياة" };

export function defaultDesign(p?: { well_id?: number | string; well_type?: string | null; customer_name?: string | null; dedication?: string | null;
  country?: string | null; contractor?: { country?: string | null } | null; completion_date?: string | null; delivery_date?: string | null; order_date?: string | null }): WellDesign {
  const name = (p?.dedication || p?.customer_name || "فاعل خير").trim();
  const kind = guessDua(name);
  const raw = (p?.well_type || "").trim();
  const wt = PLAQUE_TYPE_TEXT[raw] || raw;
  return {
    template: "hayah_square", size: "digital",
    well_id: p?.well_id ? String(p.well_id) : "",
    well_type: wt,
    month: monthLabel(p?.completion_date || p?.delivery_date || p?.order_date),
    name, dua_kind: kind, short_dua: DUAS[kind].short, dua: DUAS[kind].long,
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
  const sadaqaShort = occ === "sadaqa" ? dua.short : "";
  return { ...d, occasion: occ, animal, header1: o.header1, quote: o.quote, reference: o.reference,
           title: o.title.replace("{animal}", animal), subtitle: o.subtitle, dua_kind: kind, dua: dua.long, short_dua: sadaqaShort };
}

export function defaultSacrificeDesign(s?: { sacrifice_no?: number | string; donor_name?: string | null; dedication?: string | null;
  animal_type?: string | null; intention?: string | null; extras?: string | null; order_date?: string | null; delivery_date?: string | null;
  contractor_country?: string | null }): SacrificeDesign {
  const name = (s?.dedication || s?.donor_name || "فاعل خير").trim();
  const flag = flagFor(s?.contractor_country);
  const base: SacrificeDesign = {
    template: "sacrifice_portrait", size: "digital", sacrifice_no: s?.sacrifice_no ? String(s.sacrifice_no) : "",
    number_label: "ذبيحة رقم", month: monthLabel(s?.delivery_date || s?.order_date), name,
    dua_kind: guessDua(name), short_dua: "", dua: "", flag, country_label: flagArabic(flag),
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

let fontsReady: Promise<void> | null = null;
export function loadFonts(): Promise<void> {
  if (!fontsReady) {
    const sample = "بسم الله مشروع رقم HayahFoundation 0123 ﷺ";
    fontsReady = Promise.all([
      "600 40px Cairo", "700 40px Cairo", "800 40px Cairo", "900 40px Cairo", "700 40px Amiri",
      "400 40px 'Noto Naskh Arabic'", "700 40px 'Noto Naskh Arabic'",
    ].map((f) => document.fonts.load(f, sample).catch(() => []))).then(() => undefined);
  }
  return fontsReady;
}

export interface Assets { logo: HTMLImageElement | null; flag: HTMLImageElement | null; icon: HTMLImageElement | null; }
export async function loadAssets(d: Design): Promise<Assets> {
  await loadFonts();
  const flagSrc = d.flag === "custom" ? d.flag_custom : d.flag ? `/flags/${d.flag}.svg` : undefined;
  let iconSrc: string | undefined;
  if (d.template === "hayah_square") {
    const ic = d.icon === "well" ? "hand_pump" : d.icon;
    iconSrc = ic === "custom" ? d.icon_custom : ic === "none" ? undefined : `/wells/${ic}.png`;
  }
  const [logo, flag, icon] = await Promise.all([
    loadImage("/hayah-logo.png"), flagSrc ? loadImage(flagSrc) : null, iconSrc ? loadImage(iconSrc) : null,
  ]);
  return { logo, flag, icon };
}

// ---------------------------------------------------------------- drawing helpers
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

export function drawPlaque(ctx: Ctx, d: Design, a: Assets, scale: number) {
  ctx.save();
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.textBaseline = "alphabetic";
  const [gw, gh] = GRIDS[d.template];
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, gw, gh);
  if (d.template === "sacrifice_portrait") drawSacrifice(ctx, d, a); else drawWell(ctx, d, a);
  ctx.restore();
}

// ---------------------------------------------------------------- well plaque (1080 × 1080)
function drawWell(ctx: Ctx, d: WellDesign, a: Assets) {
  const G = 1080;
  ctx.strokeStyle = INK; ctx.lineWidth = 4; ctx.strokeRect(6, 6, G - 12, G - 12);

  // Header: logo (left), flag (right), Bismillah and verse (centre)
  if (a.logo) drawContain(ctx, a.logo, 30, 16, 200, 225, "center");
  if (a.flag) drawFlag(ctx, a.flag, 860, 70, 190, 136, "end");
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
  const midTxt = [d.well_type, d.sadaqa_label].filter(Boolean).join("  ");
  const room = projX - (monX + monW) - 24;
  ctx.fillStyle = INK; ctx.textAlign = "right"; fit(ctx, midTxt, 800, 34, "Cairo", room, 18);
  ctx.fillText(midTxt, projX - 10, mid);

  // Donor / dedication name: one big line when it fits, two lines for long names
  ctx.textAlign = "center"; ctx.fillStyle = d.name_color;
  const nameWeight = d.name_font === "Cairo" ? 900 : 700;
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
  nLines.forEach((l, i) => ctx.fillText(l, G / 2, nTop + i * nLh + nSize * 0.85));

  // Well icon (left or right) and the short prayer beside it
  const right = d.icon_side === "right";
  if (a.icon) drawContain(ctx, a.icon, right ? G - 22 - 300 : 22, 478, 300, 190, right ? "end" : "start");
  ctx.fillStyle = INK; fit(ctx, d.short_dua, 900, 66, "Cairo", 520);
  ctx.fillText(d.short_dua, G / 2 + (a.icon ? (right ? -40 : 30) : 0), 615);

  // Prayer paragraph, shrunk until it fits between y 668 and 935
  const top = 668, bottom = 935, maxW = 990;
  let size = 44, lines: string[] = [], lh = 0;
  for (; size >= 22; size -= 2) {
    font(ctx, 400, size, "Noto Naskh Arabic");
    lines = wrap(ctx, d.dua, maxW); lh = size * 1.48;
    if (lines.length * lh <= bottom - top) break;
  }
  const startY = top + (bottom - top - lines.length * lh) / 2 + size * 1.05;
  lines.forEach((l, i) => ctx.fillText(l, G / 2, startY + i * lh));

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
  if (a.flag) drawFlag(ctx, a.flag, 785, 70, 210, 136, "center");
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
  const nameWeight = d.name_font === "Cairo" ? 900 : 700;
  for (let k = 1; k >= 0.6; k -= 0.05) {
    const parts: { lines: string[]; size: number; weight: number; family: string; color: string; lh: number; gapAfter: number }[] = [];
    const add = (text: string, weight: number, size: number, family: string, color: string, maxLines: number, lhK: number, gapAfter: number, min = 26) => {
      if (!text.trim()) return;
      const f = fitLines(ctx, text, weight, Math.round(size * k), family, maxW, maxLines, Math.round(min * k));
      parts.push({ lines: f.lines, size: f.size, weight, family, color, lh: f.size * lhK, gapAfter });
    };
    add(d.title, 900, 80, "Cairo", INK, 2, 1.3, 6);
    add(d.subtitle, 900, 80, "Cairo", d.name_color, 1, 1.3, 4);
    add(d.name, nameWeight, d.name.trim().length <= 8 ? 190 : 140, d.name_font, d.name_color, 2, 1.18, 18, 40);
    add(d.short_dua, 800, 66, "Cairo", INK, 1, 1.35, 16);
    add(d.dua, 700, 60, "Cairo", INK, 9, 1.5, 0, 24);
    const h = parts.reduce((s, p) => s + p.lines.length * p.lh + p.gapAfter, 0);
    if (h <= bottom - top || k <= 0.61) {
      let yy = top + Math.max(0, (bottom - top - h) / 2) * 0.6;
      for (const p of parts) {
        ctx.fillStyle = p.color; font(ctx, p.weight, p.size, p.family);
        p.lines.forEach((l) => { ctx.fillText(l, cx, yy + p.lh * 0.78); yy += p.lh; });
        yy += p.gapAfter;
      }
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
  const c = await renderCanvas(d, pxW, pxH);
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
