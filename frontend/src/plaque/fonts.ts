// Arabic fonts for the plaques. The font files are bundled with the system (from @fontsource,
// all SIL Open Font Licence), so the preview and the exported PNG/PDF use exactly the same font.
// Media Pro and Niloofar are NOT included: no free licence for them could be confirmed. El Messiri
// and Reem Kufi stand in for them and are labelled as stand-ins in the list.
import "@fontsource/cairo/400.css";
import "@fontsource/cairo/600.css";
import "@fontsource/cairo/700.css";
import "@fontsource/cairo/800.css";
import "@fontsource/cairo/900.css";
import "@fontsource/amiri/400.css";
import "@fontsource/amiri/700.css";
import "@fontsource/noto-naskh-arabic/400.css";
import "@fontsource/noto-naskh-arabic/700.css";
import "@fontsource/ibm-plex-sans-arabic/400.css";
import "@fontsource/ibm-plex-sans-arabic/700.css";
import "@fontsource/kufam/400.css";
import "@fontsource/kufam/900.css";
import "@fontsource/tajawal/400.css";
import "@fontsource/tajawal/900.css";
import "@fontsource/aref-ruqaa/400.css";
import "@fontsource/aref-ruqaa/700.css";
import "@fontsource/alexandria/400.css";
import "@fontsource/alexandria/900.css";
import "@fontsource/el-messiri/400.css";
import "@fontsource/el-messiri/700.css";
import "@fontsource/reem-kufi/400.css";
import "@fontsource/reem-kufi/700.css";

export interface PlaqueFont { family: string; ar: string; en: string; bold: number; standIn?: string }

/** Order shown in the editor's font list. `bold` is the heaviest weight bundled for that font. */
export const FONTS: PlaqueFont[] = [
  { family: "Cairo", ar: "كايرو", en: "Cairo", bold: 900 },
  { family: "Tajawal", ar: "تجوال", en: "Tajawal", bold: 900 },
  { family: "Kufam", ar: "كوفام", en: "Kufam", bold: 900 },
  { family: "Alexandria", ar: "إسكندرية", en: "Alexandria", bold: 900 },
  { family: "IBM Plex Sans Arabic", ar: "آي بي إم بلكس", en: "IBM Plex Sans Arabic", bold: 700 },
  { family: "Amiri", ar: "أميري", en: "Amiri", bold: 700 },
  { family: "Noto Naskh Arabic", ar: "نوتو نسخ", en: "Noto Naskh Arabic", bold: 700 },
  { family: "Aref Ruqaa", ar: "عارف الرقعة", en: "Aref Ruqaa", bold: 700 },
  { family: "El Messiri", ar: "المسيري", en: "El Messiri", bold: 700, standIn: "Media Pro" },
  { family: "Reem Kufi", ar: "ريم كوفي", en: "Reem Kufi", bold: 700, standIn: "Niloofar" },
];

export function fontInfo(family: string): PlaqueFont {
  return FONTS.find((f) => f.family === family) || FONTS[0];
}

/** Weight to draw with: the font's boldest bundled weight, or 400 for regular. */
export function weightFor(family: string, bold: boolean): number {
  return bold ? fontInfo(family).bold : 400;
}

export function cssFamily(family: string): string {
  return family.includes(" ") ? `'${family}'` : family;
}

const loaded = new Map<string, Promise<unknown>>();
const SAMPLE = "بسم الله مشروع رقم المرحومة فاعل خير HayahFoundation 0123 ﷺ";
/** Makes sure the font file is downloaded before the canvas draws with it. */
export function ensureFont(family: string, weight: number): Promise<unknown> {
  const key = `${weight} ${family}`;
  if (!loaded.has(key)) loaded.set(key, document.fonts.load(`${weight} 40px ${cssFamily(family)}`, SAMPLE).catch(() => []));
  return loaded.get(key)!;
}
