import { useEffect, useState } from "react";
import { api } from "./api";
import { useI18n } from "./i18n";
import { Field } from "./ui";

interface Check { status: "valid" | "needs_country" | "invalid" | "empty"; e164: string | null; country: string | null; }
interface Country { code: string; dial: string; ar: string | null; en: string | null; }
let countriesCache: Promise<Country[]> | null = null;

/** Customer phone: kept as typed, with a live check of the E.164 number and a country picker
 * that appears when the number is local. The server repeats the same check on save. */
export function PhoneField({ phone, country, onPhone, onCountry }: {
  phone: string; country: string; onPhone: (v: string) => void; onCountry: (v: string) => void;
}) {
  const { t, lang } = useI18n();
  const [check, setCheck] = useState<Check | null>(null);
  const [countries, setCountries] = useState<Country[]>([]);
  useEffect(() => {
    if (!phone.trim()) { setCheck(null); return; }
    const h = setTimeout(() => api<Check>("/api/phones/check", { body: { phone, country: country || null } })
      .then(setCheck).catch(() => setCheck(null)), 300);
    return () => clearTimeout(h);
  }, [phone, country]);
  const needCountry = check?.status === "needs_country" || !!country;
  useEffect(() => {
    if (!needCountry || countries.length) return;
    countriesCache = countriesCache || api<Country[]>("/api/phones/countries");
    countriesCache.then(setCountries).catch(() => { countriesCache = null; });
  }, [needCountry, countries.length]);
  const hint = !check ? undefined : check.status === "valid" ? `${t("ph_valid")}: ${check.e164}`
    : check.status === "needs_country" ? t("ph_needs_country") : check.status === "invalid" ? t("ph_invalid") : undefined;
  const name = (c: Country) => `${(lang === "ar" ? c.ar : c.en) || c.code} ${c.dial}`;
  return <>
    <Field label={t("customer_phone")} hint={hint} tone={check?.status === "valid" ? "ok" : check ? "bad" : undefined}>
      <input dir="ltr" inputMode="tel" value={phone} onChange={(e) => onPhone(e.target.value)} />
    </Field>
    {needCountry && <Field label={t("ph_country")}>
      <select value={country} onChange={(e) => onCountry(e.target.value)}>
        <option value="">{t("ph_pick")}</option>
        {countries.map((c) => <option key={c.code} value={c.code}>{name(c)}</option>)}
      </select>
    </Field>}
  </>;
}
