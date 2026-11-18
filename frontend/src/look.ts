// Shared look-up helpers: contractor colours, well types, country names, small hooks.
import { useEffect, useState } from "react";
import type { Contractor } from "./api";

/** Same palette as backend/app/services/contractor_colors.py (used only if a contractor has no colour yet). */
export const PALETTE = ["#DCEBFA", "#E2F3E4", "#FCE8D5", "#EDE3F7", "#FFF3C9", "#DDF2F1", "#FBE3E8", "#E4F0D3", "#E0E7F5", "#F3E6DA", "#F6DFF0", "#E8E6DF"];

export function contractorColor(c: Pick<Contractor, "id" | "color"> | null | undefined): string | undefined {
  if (!c) return undefined;
  return c.color || PALETTE[(c.id - 1 + PALETTE.length) % PALETTE.length];
}

/** A darker shade of a row colour, for dots and card edges. */
export function deeper(hex: string | undefined, amount = 0.38): string | undefined {
  if (!hex || !/^#[0-9a-f]{6}$/i.test(hex)) return undefined;
  const n = parseInt(hex.slice(1), 16);
  const f = (v: number) => Math.round(v * (1 - amount));
  const r = f(n >> 16), g = f((n >> 8) & 255), b = f(n & 255);
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

/** The four HAYAH well types. "كهربائي" is discontinued: shown on its old project, never offered. */
export const WELL_TYPES = ["يدوي", "متوسط", "عميق", "شمسي"];
export const LEGACY_WELL_TYPES = ["كهربائي"];
export const wellTypeOptions = (current?: string | null) =>
  current && !WELL_TYPES.includes(current) ? [...WELL_TYPES, current] : WELL_TYPES;

const COUNTRY_AR: Record<string, string> = {
  Pakistan: "باكستان", Nepal: "نيبال", Bangladesh: "بنغلاديش", India: "الهند", Tanzania: "تنزانيا",
  Kenya: "كينيا", Uganda: "أوغندا", Somalia: "الصومال", Sudan: "السودان", Yemen: "اليمن", Niger: "النيجر",
  Mali: "مالي", Chad: "تشاد", Indonesia: "إندونيسيا", Afghanistan: "أفغانستان", Ethiopia: "إثيوبيا",
};
export const countryName = (c: string | null | undefined, lang: string) =>
  !c ? (lang === "ar" ? "أخرى" : "Other") : lang === "ar" ? COUNTRY_AR[c] || c : c;

/** Contractor order used everywhere: Pakistan, Nepal, Bangladesh, India, then the rest. */
const ORDER = ["PAK", "NEP", "BANG", "IND"];
const rank = (code: string) => { const i = ORDER.findIndex((p) => code.startsWith(p)); return i < 0 ? ORDER.length : i; };
export const sortContractors = <T extends { code: string }>(list: T[]) =>
  [...list].sort((a, b) => rank(a.code) - rank(b.code) || a.code.localeCompare(b.code, undefined, { numeric: true }));

/** Partner accounts shown under "المسؤولون", in HAYAH's order. */
export const PARTNERS: { code: string; ar: string; en: string }[] = [
  { code: "MOHAMMED", ar: "محمد", en: "Mohammed" },
  { code: "CLIQ", ar: "هيا", en: "Haya" },
  { code: "GHAZI", ar: "غازي", en: "Ghazi" },
];

export function monthName(m: string, lang: string, style: "long" | "short" = "long") {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleDateString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { month: style, year: "numeric" });
}

export function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** True on phone-sized screens. */
export function useNarrow(max = 760) {
  const q = `(max-width: ${max}px)`;
  const [m, setM] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const h = () => setM(mq.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [q]);
  return m;
}
