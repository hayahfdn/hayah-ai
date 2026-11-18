// Labels for the side menu, mobile layout, contractor colours, well types and plaque approval.
export const uiEn: Record<string, string> = {
  nav_wells: "Wells", nav_sacrifices: "Sacrifices", nav_people: "Partners", nav_sec_book: "Workbook", nav_sec_contractors: "Contractors",
  nav_sec_work: "Daily work", nav_sec_admin: "Admin", nav_menu: "Menu", nav_home: "Home", nav_pick: "Choose…",
  nav_this_month: "This month", nav_prev_month: "Previous month", nav_next_month: "Next month", nav_month: "Month",
  nav_contractors_list: "Contractors list", contractor_page: "Contractor", contractor_wells_help: "Every well this contractor builds, in all months.",
  month_wells_help: "That month's wells. Tap a row to open it.",
  view_cards: "Cards", view_table: "Table", show_more: "Show more", open: "Open", rows_count: "rows",
  color: "Row colour", color_help: "Used for this contractor's wells on every page.",
  plaque: "Plaque", plaque_create: "Create plaque", plaque_approved: "Approved", plaque_draft: "Draft", plaque_none: "No plaque",
  plaque_view: "View plaque", plaque_new_version: "New version", plaque_approve: "Approve plaque", plaque_save_draft: "Save draft",
  plaque_approve_this: "Approve this version", plaque_replace_q: "This order already has an approved plaque. Replace it with this one? The earlier plaque stays in the versions list.",
  plaque_approved_ok: "Plaque approved and linked to the order", plaque_draft_ok: "Draft saved to the order",
  plaque_versions: "Versions", plaque_version: "Version", plaque_approved_by: "Approved by", plaque_order_data: "Order details",
  plaque_order_help: "Filled in from the order. Change anything that should look different on the plaque.",
  plaque_back: "Back to the order", plaque_none_yet: "No plaque yet for this order.", plaque_loading: "Loading plaque…",
  wt_title: "Well types", wt_help: "Every well uses one of the four types. Older names were changed to these, and the change can be undone here.",
  wt_now: "Wells by type now", wt_pending: "Still to unify", wt_unknown: "Not one of the four (fix by hand)", wt_runs: "Past unifications",
  wt_apply: "Unify now", wt_undo: "Undo", wt_undone: "Undone", wt_none_pending: "Nothing left to unify.", wt_legacy: "old, not offered for new wells",
  wt_confirm: "Change these well types to the four names? The old names are kept in the log and can be put back.",
  wt_undo_confirm: "Put back the old well-type names from this run?",
};

export const uiAr: Record<string, string> = {
  nav_wells: "الآبار", nav_sacrifices: "الأضاحي", nav_people: "المسؤولون", nav_sec_book: "دفتر الحسابات", nav_sec_contractors: "المقاولون",
  nav_sec_work: "العمل اليومي", nav_sec_admin: "الإدارة", nav_menu: "القائمة", nav_home: "الرئيسية", nav_pick: "اختر…",
  nav_this_month: "الشهر الحالي", nav_prev_month: "الشهر السابق", nav_next_month: "الشهر التالي", nav_month: "الشهر",
  nav_contractors_list: "قائمة المقاولين", contractor_page: "المقاول", contractor_wells_help: "كل آبار هذا المقاول في جميع الأشهر.",
  month_wells_help: "آبار هذا الشهر. اضغط على الصف لفتحه.",
  view_cards: "بطاقات", view_table: "جدول", show_more: "عرض المزيد", open: "فتح", rows_count: "صف",
  color: "لون الصف", color_help: "يظهر به كل آبار هذا المقاول في جميع الصفحات.",
  plaque: "اللوحة", plaque_create: "إنشاء لوحة", plaque_approved: "معتمدة", plaque_draft: "مسودة", plaque_none: "لا توجد لوحة",
  plaque_view: "عرض اللوحة", plaque_new_version: "نسخة جديدة", plaque_approve: "اعتماد اللوحة", plaque_save_draft: "حفظ كمسودة",
  plaque_approve_this: "اعتماد هذه النسخة", plaque_replace_q: "لهذا الطلب لوحة معتمدة من قبل. هل تريد استبدالها بهذه؟ اللوحة السابقة تبقى محفوظة في قائمة النسخ.",
  plaque_approved_ok: "تم اعتماد اللوحة وربطها بالطلب", plaque_draft_ok: "تم حفظ المسودة في الطلب",
  plaque_versions: "النسخ", plaque_version: "النسخة", plaque_approved_by: "اعتمدها", plaque_order_data: "بيانات الطلب",
  plaque_order_help: "معبأة من الطلب تلقائياً. عدّل ما تريده أن يظهر بشكل مختلف على اللوحة.",
  plaque_back: "العودة إلى الطلب", plaque_none_yet: "لا توجد لوحة لهذا الطلب بعد.", plaque_loading: "جارٍ تحميل اللوحة…",
  wt_title: "أنواع الآبار", wt_help: "كل بئر له نوع واحد من الأنواع الأربعة. الأسماء القديمة حُوّلت إليها، ويمكن التراجع عن التحويل من هنا.",
  wt_now: "عدد الآبار حسب النوع الآن", wt_pending: "أسماء لم تُوحَّد بعد", wt_unknown: "ليست من الأنواع الأربعة (تُصحَّح يدوياً)", wt_runs: "عمليات التوحيد السابقة",
  wt_apply: "وحّد الآن", wt_undo: "تراجع", wt_undone: "تم التراجع", wt_none_pending: "لا يوجد ما يحتاج توحيداً.", wt_legacy: "قديم، لا يظهر للآبار الجديدة",
  wt_confirm: "تحويل أنواع الآبار هذه إلى الأسماء الأربعة؟ الأسماء القديمة تبقى في السجل ويمكن إرجاعها.",
  wt_undo_confirm: "إرجاع أسماء أنواع الآبار القديمة من هذه العملية؟",
};

/** Country names as HAYAH writes them in Arabic. */
export const COUNTRY_AR: Record<string, string> = {
  Pakistan: "باكستان", Nepal: "نيبال", Bangladesh: "بنغلاديش", India: "الهند", Tanzania: "تنزانيا", Kenya: "كينيا",
  Uganda: "أوغندا", Somalia: "الصومال", Sudan: "السودان", Yemen: "اليمن", Chad: "تشاد", Niger: "النيجر", Mali: "مالي",
};
/** Partner pages in the order Hayah asked for: Mohammed, Haya, Ghazi. */
export const PARTNERS: { code: string; ar: string; en: string }[] = [
  { code: "MOHAMMED", ar: "محمد", en: "Mohammed" }, { code: "CLIQ", ar: "هيا", en: "Haya" }, { code: "GHAZI", ar: "غازي", en: "Ghazi" },
];
