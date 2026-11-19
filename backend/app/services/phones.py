"""Customer phone numbers in one standard form (E.164, e.g. +962791234567).

Uses `phonenumbers`, the Python port of Google's libphonenumber. Rules (Hayah, 19 Nov 2026):
- A full international number (+.. or 00..) is kept after it is validated.
- A local number (0791234567) gets its country code only when the customer's country is
  known for sure: chosen by staff, or the same number in international form elsewhere on
  the order (Shopify's checkout phone). The country where the well is built is never used,
  because it is not the customer's country.
- An extra local 0 after the country code (+44 07...) is dropped; no other digit is removed.
- The original text is always kept as it was typed; only the E.164 copy is added.
Result statuses: valid | needs_country | invalid | empty.
"""
from __future__ import annotations

import re

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType

# Names staff or Shopify may use for a customer's country -> ISO code.
COUNTRY_NAMES = {
    "GB": ["uk", "united kingdom", "great britain", "britain", "england", "بريطانيا", "المملكة المتحدة", "انجلترا", "إنجلترا"],
    "JO": ["jordan", "الأردن", "الاردن"],
    "SA": ["saudi arabia", "saudi", "ksa", "السعودية", "المملكة العربية السعودية"],
    "AE": ["uae", "united arab emirates", "emirates", "الإمارات", "الامارات"],
    "QA": ["qatar", "قطر"],
    "KW": ["kuwait", "الكويت"],
    "BH": ["bahrain", "البحرين"],
    "OM": ["oman", "عمان", "عُمان"],
    "EG": ["egypt", "مصر"],
    "PS": ["palestine", "فلسطين"],
    "LB": ["lebanon", "لبنان"],
    "IQ": ["iraq", "العراق"],
    "SY": ["syria", "سوريا", "سورية"],
    "YE": ["yemen", "اليمن"],
    "LY": ["libya", "ليبيا"],
    "TN": ["tunisia", "تونس"],
    "DZ": ["algeria", "الجزائر"],
    "MA": ["morocco", "المغرب"],
    "SD": ["sudan", "السودان"],
    "TR": ["turkey", "türkiye", "تركيا"],
    "US": ["usa", "united states", "america", "أمريكا", "امريكا", "الولايات المتحدة"],
    "CA": ["canada", "كندا"],
    "AU": ["australia", "أستراليا", "استراليا"],
    "DE": ["germany", "ألمانيا", "المانيا"],
    "FR": ["france", "فرنسا"],
    "NL": ["netherlands", "holland", "هولندا"],
    "BE": ["belgium", "بلجيكا"],
    "SE": ["sweden", "السويد"],
    "NO": ["norway", "النرويج"],
    "DK": ["denmark", "الدنمارك"],
    "IE": ["ireland", "أيرلندا", "ايرلندا"],
    "IT": ["italy", "إيطاليا", "ايطاليا"],
    "ES": ["spain", "إسبانيا", "اسبانيا"],
    "AT": ["austria", "النمسا"],
    "CH": ["switzerland", "سويسرا"],
    "MY": ["malaysia", "ماليزيا"],
    "PK": ["pakistan", "باكستان"],
    "IN": ["india", "الهند"],
    "BD": ["bangladesh", "بنغلاديش", "بنجلاديش"],
}
_BY_NAME = {n: code for code, names in COUNTRY_NAMES.items() for n in names}
# Countries shown first in the staff picker (Hayah's list), then the rest A-Z.
MAIN = ["GB", "JO", "SA", "AE", "QA", "KW"]

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def country_code(value: str | None) -> str | None:
    """'UK', 'gb', 'الأردن' -> 'GB' / 'JO'. None when unknown (never guessed)."""
    v = (value or "").strip()
    if not v:
        return None
    if len(v) == 2 and v.upper() in phonenumbers.SUPPORTED_REGIONS:
        return v.upper()
    return _BY_NAME.get(v.lower())


def _clean(raw: str) -> str:
    s = raw.translate(_ARABIC_DIGITS).strip()
    s = re.sub(r"[^\d+]", "", s)            # spaces, dashes, brackets, dots
    s = s[0] + s[1:].replace("+", "") if s else s
    if s.startswith("00"):
        s = "+" + s[2:]
    return s


def _result(status: str, raw: str | None, e164: str | None = None, region: str | None = None, note: str | None = None) -> dict:
    return {"status": status, "original": raw, "e164": e164, "country": region, "note": note,
            "whatsapp_ok": status == "valid"}


def normalize(raw: str | None, country: str | None = None, hints: list[str | None] | None = None) -> dict:
    """Returns {status, original, e164, country, note, whatsapp_ok}. Never raises."""
    if not raw or not raw.strip():
        return _result("empty", raw)
    s = _clean(raw)
    if len(re.sub(r"\D", "", s)) < 6:
        return _result("invalid", raw, note="Too few digits")
    region = country_code(country)
    if not s.startswith("+") and not region:
        region = _region_from_hints(s, hints or [])
        if not region:
            return _result("needs_country", raw, note="Local number: choose the customer's country")
    try:
        num = phonenumbers.parse(s, None if s.startswith("+") else region)
    except NumberParseException as e:
        return _result("invalid", raw, note=str(e))
    if not phonenumbers.is_valid_number(num):
        return _result("invalid", raw, note="Not a valid number for that country")
    kind = phonenumbers.number_type(num)
    if kind in (PhoneNumberType.PREMIUM_RATE, PhoneNumberType.TOLL_FREE, PhoneNumberType.SHARED_COST):
        return _result("invalid", raw, note="Not a personal number")
    return _result("valid", raw, phonenumbers.format_number(num, PhoneNumberFormat.E164),
                   phonenumbers.region_code_for_number(num))


def _region_from_hints(local: str, hints: list[str | None]) -> str | None:
    """A local number takes the country of the same number written internationally elsewhere
    on the order (e.g. Shopify's checkout phone): same national digits, so not a guess."""
    digits = local.lstrip("0")
    for h in hints:
        if not h:
            continue
        hs = _clean(h)
        if not hs.startswith("+"):
            continue
        try:
            n = phonenumbers.parse(hs, None)
        except NumberParseException:
            continue
        if phonenumbers.is_valid_number(n) and str(n.national_number) == digits:
            return phonenumbers.region_code_for_number(n)
    return None


def apply(obj, *, hints: list[str | None] | None = None) -> None:
    """Fill customer_phone_e164 / _country / _status on a Project or Sacrifice from its
    customer_phone (kept unchanged) and the staff-chosen customer_phone_country."""
    obj.customer_phone_country = country_code(obj.customer_phone_country)
    r = normalize(obj.customer_phone, obj.customer_phone_country, hints)
    obj.customer_phone_status = r["status"]
    obj.customer_phone_e164 = r["e164"]
    if r["country"]:
        obj.customer_phone_country = r["country"]


def countries() -> list[dict]:
    """For the staff picker: ISO code, calling code, names."""
    out = []
    for code in sorted(phonenumbers.SUPPORTED_REGIONS):
        names = COUNTRY_NAMES.get(code, [])
        ar = next((n for n in names if re.search(r"[؀-ۿ]", n)), None)
        out.append({"code": code, "dial": f"+{phonenumbers.country_code_for_region(code)}", "ar": ar,
                    "en": names[1].title() if len(names) > 1 and code != "GB" else ("United Kingdom" if code == "GB" else None)})
    out.sort(key=lambda c: (MAIN.index(c["code"]) if c["code"] in MAIN else 99, c["code"]))
    return out
