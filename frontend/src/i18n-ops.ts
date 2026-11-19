// Labels for the connected order workflow: phones, plaque fonts and prayers, plaque states,
// approved plaques, final videos, dashboard and the WhatsApp inbox.
export const opsEn: Record<string, string> = {
  ph_country: "Customer's country (for the phone)", ph_pick: "Choose the country…",
  ph_valid: "WhatsApp number", ph_needs_country: "Local number: choose the customer's country to add the country code",
  ph_invalid: "This number does not look valid. Check it with the customer.", ph_original: "As typed",
  // plaque text controls
  pl_text_name: "Name text", pl_text_dua: "Prayer text", pl_font: "Font", pl_size_pct: "Size",
  pl_line: "Line spacing", pl_align: "Alignment", pl_weight: "Weight", pl_bold: "Bold", pl_normal: "Regular",
  pl_center: "Centre", pl_right: "Right", pl_left: "Left", pl_font_standin: "stand-in",
  pl_font_note: "Media Pro and Niloofar are not installed: no free licence could be confirmed. El Messiri and Reem Kufi are free stand-ins.",
  pl_dua_unsure: "Not sure whether this person is male or female, living or deceased. A neutral prayer is used: please confirm.",
  pl_dua_sure: "Prayer chosen from the dedication",
};
export const opsAr: Record<string, string> = {
  ph_country: "دولة العميل (لرقم الهاتف)", ph_pick: "اختر الدولة…",
  ph_valid: "رقم واتساب", ph_needs_country: "رقم محلي: اختر دولة العميل لإضافة رمز الدولة",
  ph_invalid: "الرقم لا يبدو صحيحاً. تأكد منه مع العميل.", ph_original: "كما كُتب",
  pl_text_name: "نص الاسم", pl_text_dua: "نص الدعاء", pl_font: "الخط", pl_size_pct: "الحجم",
  pl_line: "المسافة بين الأسطر", pl_align: "المحاذاة", pl_weight: "السماكة", pl_bold: "عريض", pl_normal: "عادي",
  pl_center: "وسط", pl_right: "يمين", pl_left: "يسار", pl_font_standin: "بديل",
  pl_font_note: "خطا ميديا برو ونيلوفر غير مثبتين لأنه لم يتأكد وجود ترخيص مجاني لهما. خطا المسيري وريم كوفي بديلان مجانيان.",
  pl_dua_unsure: "لم يتضح هل الشخص ذكر أم أنثى، حي أم متوفى. استُخدم دعاء محايد: الرجاء التأكيد واختيار الصيغة الصحيحة.",
  pl_dua_sure: "اختير الدعاء من نص الإهداء",
};
