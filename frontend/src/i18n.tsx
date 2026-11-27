import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { bookAr, bookEn } from "./i18n-book";
import { shopifyAr, shopifyEn } from "./i18n-shopify";
import { uiAr, uiEn } from "./i18n-ui";
import { opsAr, opsEn } from "./i18n-ops";
import { toolsAr, toolsEn } from "./i18n-tools";
import { renAr, renEn } from "./i18n-renumber";
import { featAr, featEn } from "./i18n-feat";
import { certAr, certEn } from "./i18n-cert";
import { designAr, designEn } from "./i18n-design";
import { teamAr, teamEn } from "./i18n-team";
import { suqyaAr, suqyaEn } from "./i18n-suqya";

export type Lang = "ar" | "en";

const en: Record<string, string> = {
  pl_title_sac: "Sacrifice plaque designer", pl_tab_well: "Well plaque", pl_tab_sac: "Sacrifice plaque", pl_open_sac: "Sacrifice No.",
  pl_no_sac: "Type a sacrifice number above to fill the plaque from the workbook. You can also design one by hand here and download it.",
  pl_save_sac: "Save to sacrifice record", pl_flags_main: "Main countries", pl_flags_arab: "Arab countries", pl_flags_other: "Other countries",
  pl_icon_side: "Icon side", pl_left: "Left", pl_right: "Right", pl_occasion: "Type", pl_animal: "Animal", pl_sac_no: "Sacrifice number",
  pl_title_line: "Title line", pl_subtitle_line: "Red line above the name", pl_country_label: "Country name under the flag",
  pl_header1: "Header line", pl_quote: "Verse or hadith (red)", pl_reference: "Reference", pl_number_label: "Number label",
  pl_short_dua_hint: "Leave empty to hide it.", pl_occasion_hint: "Changing the type fills in the header, title and prayer. Everything stays editable.",
  pl_reset_blank: "Reset",
  nav_plaque: "Plaque designer", pl_title: "Plaque designer", pl_design: "Design plaque", pl_open_well: "Well ID", pl_open: "Open",
  pl_no_well: "Type a Well ID above to fill the plaque from that well. You can also design a plaque by hand here and download it.",
  pl_preview: "Plaque preview", pl_size: "Size", pl_download_png: "Download PNG", pl_download_pdf: "Download PDF (print)",
  pl_save: "Save to well history", pl_saved: "Plaque saved to the well", pl_name: "Name (donor or dedication)", pl_project_no: "Project number",
  pl_well_type: "Well type", pl_month: "Month and year", pl_flag: "Flag", pl_flag_upload: "Or upload a flag", pl_icon: "Well icon",
  pl_icon_upload: "Or upload an icon", pl_icon_well: "Hand-pump well", pl_none: "None", pl_uploaded: "Uploaded image",
  pl_dua_kind: "Prayer for", pl_short_dua: "Short prayer under the name", pl_dua: "Prayer", pl_dua_hint: "Picking who the prayer is for fills this in. You can edit it freely.",
  pl_more: "More text and style", pl_bismillah: "Bismillah", pl_verse: "Verse", pl_project_label: "Project label", pl_sadaqa_label: "Sadaqah label",
  pl_footer_org: "Footer (Arabic)", pl_footer_site: "Footer website", pl_name_font: "Name font", pl_color: "Red colour",
  pl_reset: "Refill from the record", pl_saved_sac: "Plaque saved to the sacrifice record", pl_history: "Saved plaques", pl_load: "Open", pl_none_saved: "No plaques saved for this well yet.",
  cat_PLAQUE: "Plaque",
  app_name: "HAYAH AI", app_sub: "Operations", login: "Sign in", email: "Email", password: "Password", logout: "Sign out",
  login_title: "Sign in to HAYAH operations", login_failed: "Sign in failed",
  nav_sheet: "Master Sheet", saving: "Saving…", all_saved: "All changes saved", clear_filters: "Clear filters",
  sheet_help: "Works like Excel: double-click a cell (or press Enter) to edit, Enter to save, Esc to cancel, Ctrl+Z to undo. Sort and filter from the column headers. Grey columns are locked: delivery changes only through an approved confirmation. Every change is saved and logged.",
  nav_dashboard: "Dashboard", nav_projects: "Projects", nav_construction: "Construction", nav_delivery: "Delivery",
  nav_maintenance: "Maintenance", nav_media: "Media Library", nav_review: "AI Review", nav_contractors: "Contractors",
  nav_reports: "Reports", nav_settings: "Settings",
  total_projects: "Total projects", new_orders: "New orders", in_progress: "In progress", completed: "Completed",
  delivered: "Delivered", pending_delivery: "Pending delivery", videos_processing: "Videos processing",
  videos_completed: "Videos completed", maintenance_cases: "Open maintenance", pending_review: "Pending review",
  pending_delivery_approvals: "Deliveries awaiting approval",
  sheets_status: "Google Sheets", sync_now: "Sync now", synced: "Synchronized", pending: "Pending", error: "Error",
  conflicts: "Needs attention", last_sync: "Last sync", never: "Never", recent_activity: "Recent activity",
  by_country: "Projects by country", by_status: "Construction status",
  well_id: "Well ID", order_date: "Order date", customer_name: "Customer", customer_phone: "Customer phone",
  country: "Country", city: "City", village: "Village", well_type: "Well type", sales_source: "Sales source",
  contractor: "Contractor", sale_amount: "Sale amount", currency: "Currency", payment_status: "Payment",
  construction_status: "Construction", construction_start_date: "Construction start", completion_date: "Completion date",
  delivery_status: "Delivery", delivery_date: "Delivery date", raw_media_folder: "Raw media folder",
  final_video_link: "Final video link", video_status: "Video", maintenance_status: "Maintenance",
  last_maintenance_date: "Last maintenance", next_maintenance_date: "Next maintenance", notes: "Notes",
  last_updated: "Last updated", search: "Search by Well ID or customer…", all: "All", new_project: "New project",
  create: "Create", save: "Save", cancel: "Cancel", edit: "Edit", close: "Close", loading: "Loading…", none: "—",
  saved: "Saved", approve: "Approve", reject: "Reject", details: "Details", history: "History", media: "Media",
  deliveries: "Deliveries", maintenance: "Maintenance", timeline: "Timeline", back: "Back", page: "Page", of: "of",
  well_exists: "This Well ID already exists", well_free: "Well ID is free", highest_well: "Highest existing Well ID",
  sample: "Sample", sample_banner: "Sample data: Well IDs 9001–9012 are test projects, not real wells.",
  delivery_rule: "Only an approved confirmation marks a well as delivered. Construction or video completion never does.",
  new_confirmation: "Record delivery confirmation", awaiting_approval: "Awaiting approval", approved: "Approved", rejected: "Rejected",
  sender: "Sender", source: "Source", evidence: "Evidence", decision_note: "Decision note",
  maintenance_id: "Maintenance ID", date: "Date", problem_type: "Problem type", description: "Description",
  technician: "Technician", repair_action: "Repair action", repair_cost: "Repair cost", status: "Status",
  location: "Location", new_maintenance: "New maintenance record",
  upload: "Upload", file: "File", category: "Category", unassigned: "Unassigned", size: "Size", open_link: "Open",
  duplicate_file: "Duplicate file",
  review_intro: "Messages and files the system could not match confidently. Nothing changes until you approve.",
  message: "Message", group: "Group", reason: "Reason", extracted: "Extracted", choose_well: "Well ID to assign",
  event_type: "Event type", no_items: "Nothing here", paste_message: "Paste a WhatsApp message",
  paste_help: "Fallback when the intake number is not connected: paste a group message and the system processes it.",
  process: "Process", code: "Code", name: "Name", phone: "Phone", active: "Active", projects: "Projects",
  avg_build_days: "Avg. build days", new_contractor: "New contractor",
  orders_by_month: "Orders by month", deliveries_by_month: "Deliveries by month", by_well_type: "By well type",
  by_payment: "By payment status", maint_by_problem: "Maintenance by problem", export_csv: "Export CSV", orders: "Orders",
  amount: "Amount", count: "Count", cost: "Cost",
  integrations: "Integrations", ai_settings: "AI and cost control", ai_enabled: "Use Claude AI (paid API)",
  monthly_budget: "Monthly AI budget (USD)", min_confidence: "Minimum confidence to auto-apply",
  manual_over: "Ask before any single AI call above (USD)", ai_cost_month: "AI cost this month",
  users: "Users", new_user: "New user", role: "Role", sync_conflicts: "Sync conflicts", keep_db: "Keep dashboard value",
  keep_sheet: "Accept sheet value", field: "Field", db_value: "Dashboard", sheet_value: "Sheet", jobs: "Background jobs",
  retry: "Retry", attempts: "Attempts", audit_log: "Audit log", action: "Action", by: "By", time: "Time",
  backend: "Mode", mock: "Offline test mode", configured: "Configured", not_configured: "Not configured",
  language: "العربية",
  role_super_admin: "Super Admin", role_operations_manager: "Operations Manager", role_contractor: "Contractor",
  role_maintenance: "Maintenance Team", role_viewer: "Viewer", role_staff: "Employee",
  st_new_order: "New order", st_scheduled: "Scheduled", st_in_progress: "In progress", st_completed: "Completed",
  st_on_hold: "On hold", st_cancelled: "Cancelled", st_not_ready: "Not ready", st_pending: "Pending", st_delivered: "Delivered",
  st_none: "None", st_raw_received: "Raw footage received", st_processing: "Processing", st_in_review: "In review",
  st_open: "Open", st_resolved: "Resolved", st_unpaid: "Unpaid", st_partial: "Partial", st_paid: "Paid", st_refunded: "Refunded",
  st_approved: "Approved", st_rejected: "Rejected", st_queued: "Queued", st_running: "Running", st_succeeded: "Succeeded",
  st_failed: "Failed", st_retrying: "Retrying",
  k_unassigned_message: "Unmatched message", k_ai_extraction: "Check extraction", k_merge_request: "Merge request",
  k_sheet_conflict: "Sheet conflict", k_unassigned_media: "Unassigned media",
  ev_construction_update: "Construction update", ev_delivery_confirmation: "Delivery confirmation", ev_final_video: "Final video",
  ev_maintenance_report: "Maintenance report", ev_general_note: "General note", ev_new_order: "New order", ev_unknown: "Unknown",
  cat_CONSTRUCTION: "Construction", cat_DELIVERY: "Delivery", cat_FINAL: "Final video", cat_MAINT_BEFORE: "Maintenance (before)",
  cat_MAINT_AFTER: "Maintenance (after)", cat_MAINTENANCE: "Maintenance", cat_OTHER: "Other",
  merge_into: "Merge into Well ID", request_merge: "Request merge", merge_reason: "Reason",
};

const ar: Record<string, string> = {
  pl_title_sac: "مصمم لوحة الذبيحة", pl_tab_well: "لوحة بئر", pl_tab_sac: "لوحة ذبيحة", pl_open_sac: "رقم الذبيحة",
  pl_no_sac: "اكتب رقم الذبيحة في الأعلى لتعبئة اللوحة من الدفتر. ويمكنك أيضًا تصميم لوحة يدويًا هنا وتنزيلها.",
  pl_save_sac: "حفظ في سجل الذبيحة", pl_flags_main: "الدول الرئيسية", pl_flags_arab: "الدول العربية", pl_flags_other: "دول أخرى",
  pl_icon_side: "جهة الأيقونة", pl_left: "يسار", pl_right: "يمين", pl_occasion: "النوع", pl_animal: "الذبيحة", pl_sac_no: "رقم الذبيحة",
  pl_title_line: "سطر العنوان", pl_subtitle_line: "السطر الأحمر فوق الاسم", pl_country_label: "اسم الدولة تحت العلم",
  pl_header1: "سطر الافتتاح", pl_quote: "الآية أو الحديث (أحمر)", pl_reference: "المرجع", pl_number_label: "عبارة الرقم",
  pl_short_dua_hint: "اتركه فارغًا لإخفائه.", pl_occasion_hint: "تغيير النوع يعبّئ الافتتاح والعنوان والدعاء تلقائيًا، وكل شيء يبقى قابلًا للتعديل.",
  pl_reset_blank: "إعادة ضبط",
  nav_plaque: "مصمم اللوحات", pl_title: "مصمم اللوحة", pl_design: "تصميم لوحة", pl_open_well: "رقم البئر", pl_open: "فتح",
  pl_no_well: "اكتب رقم البئر في الأعلى لتعبئة اللوحة من بيانات البئر. ويمكنك أيضًا تصميم لوحة يدويًا هنا وتنزيلها.",
  pl_preview: "معاينة اللوحة", pl_size: "المقاس", pl_download_png: "تنزيل PNG", pl_download_pdf: "تنزيل PDF (طباعة)",
  pl_save: "حفظ في سجل البئر", pl_saved: "تم حفظ اللوحة في سجل البئر", pl_name: "الاسم (المتبرع أو الإهداء)", pl_project_no: "رقم المشروع",
  pl_well_type: "نوع البئر", pl_month: "الشهر والسنة", pl_flag: "العلم", pl_flag_upload: "أو ارفع علمًا", pl_icon: "أيقونة البئر",
  pl_icon_upload: "أو ارفع أيقونة", pl_icon_well: "بئر بمضخة يدوية", pl_none: "بدون", pl_uploaded: "صورة مرفوعة",
  pl_dua_kind: "الدعاء لـ", pl_short_dua: "الدعاء القصير تحت الاسم", pl_dua: "الدعاء", pl_dua_hint: "اختيار صاحب الدعاء يعبّئ النص تلقائيًا، ويمكنك تعديله بحرية.",
  pl_more: "نصوص وتنسيق إضافي", pl_bismillah: "البسملة", pl_verse: "الآية", pl_project_label: "عبارة المشروع", pl_sadaqa_label: "عبارة الصدقة",
  pl_footer_org: "التذييل (عربي)", pl_footer_site: "الموقع في التذييل", pl_name_font: "خط الاسم", pl_color: "اللون الأحمر",
  pl_reset: "إعادة التعبئة من السجل", pl_saved_sac: "تم حفظ اللوحة في سجل الذبيحة", pl_history: "اللوحات المحفوظة", pl_load: "فتح", pl_none_saved: "لا توجد لوحات محفوظة لهذا البئر بعد.",
  cat_PLAQUE: "لوحة",
  app_name: "حياة AI", app_sub: "العمليات", login: "تسجيل الدخول", email: "البريد الإلكتروني", password: "كلمة المرور",
  logout: "تسجيل الخروج", login_title: "الدخول إلى نظام عمليات حياة", login_failed: "تعذر تسجيل الدخول",
  nav_sheet: "الجدول الرئيسي", saving: "جارٍ الحفظ…", all_saved: "تم حفظ كل التغييرات", clear_filters: "مسح التصفية",
  sheet_help: "يعمل مثل Excel: انقر مرتين على الخلية (أو اضغط Enter) للتعديل، Enter للحفظ، Esc للإلغاء، Ctrl+Z للتراجع. رتّب وصفِّ من عناوين الأعمدة. الأعمدة الرمادية مقفلة: التسليم يتغير فقط بعد الموافقة على تأكيد التسليم. كل تغيير يُحفظ ويُسجَّل.",
  nav_dashboard: "لوحة التحكم", nav_projects: "المشاريع", nav_construction: "الإنشاء", nav_delivery: "التسليم",
  nav_maintenance: "الصيانة", nav_media: "مكتبة الوسائط", nav_review: "مراجعة الذكاء الاصطناعي", nav_contractors: "المقاولون",
  nav_reports: "التقارير", nav_settings: "الإعدادات",
  total_projects: "إجمالي المشاريع", new_orders: "طلبات جديدة", in_progress: "قيد التنفيذ", completed: "مكتملة",
  delivered: "تم التسليم", pending_delivery: "بانتظار التسليم", videos_processing: "فيديوهات قيد المعالجة",
  videos_completed: "فيديوهات مكتملة", maintenance_cases: "صيانة مفتوحة", pending_review: "بانتظار المراجعة",
  pending_delivery_approvals: "تسليمات بانتظار الموافقة",
  sheets_status: "جداول Google", sync_now: "مزامنة الآن", synced: "متزامن", pending: "قيد الانتظار", error: "خطأ",
  conflicts: "يحتاج انتباه", last_sync: "آخر مزامنة", never: "لم تتم", recent_activity: "آخر النشاطات",
  by_country: "المشاريع حسب الدولة", by_status: "حالة الإنشاء",
  well_id: "رقم البئر", order_date: "تاريخ الطلب", customer_name: "العميل", customer_phone: "هاتف العميل",
  country: "الدولة", city: "المدينة", village: "القرية", well_type: "نوع البئر", sales_source: "مصدر البيع",
  contractor: "المقاول", sale_amount: "مبلغ البيع", currency: "العملة", payment_status: "الدفع",
  construction_status: "الإنشاء", construction_start_date: "بداية الإنشاء", completion_date: "تاريخ الاكتمال",
  delivery_status: "التسليم", delivery_date: "تاريخ التسليم", raw_media_folder: "مجلد الوسائط الخام",
  final_video_link: "رابط الفيديو النهائي", video_status: "الفيديو", maintenance_status: "الصيانة",
  last_maintenance_date: "آخر صيانة", next_maintenance_date: "الصيانة القادمة", notes: "ملاحظات",
  last_updated: "آخر تحديث", search: "ابحث برقم البئر أو اسم العميل…", all: "الكل", new_project: "مشروع جديد",
  create: "إنشاء", save: "حفظ", cancel: "إلغاء", edit: "تعديل", close: "إغلاق", loading: "جارٍ التحميل…", none: "—",
  saved: "تم الحفظ", approve: "موافقة", reject: "رفض", details: "التفاصيل", history: "السجل", media: "الوسائط",
  deliveries: "التسليمات", maintenance: "الصيانة", timeline: "التسلسل الزمني", back: "رجوع", page: "صفحة", of: "من",
  well_exists: "رقم البئر هذا موجود مسبقاً", well_free: "رقم البئر متاح", highest_well: "أعلى رقم بئر موجود",
  sample: "تجريبي", sample_banner: "بيانات تجريبية: الآبار 9001–9012 مشاريع اختبار وليست آباراً حقيقية.",
  delivery_rule: "لا يُعتبر البئر مُسلَّماً إلا بعد الموافقة على تأكيد التسليم. اكتمال الإنشاء أو الفيديو لا يكفي.",
  new_confirmation: "تسجيل تأكيد تسليم", awaiting_approval: "بانتظار الموافقة", approved: "تمت الموافقة", rejected: "مرفوض",
  sender: "المرسل", source: "المصدر", evidence: "الإثبات", decision_note: "ملاحظة القرار",
  maintenance_id: "رقم الصيانة", date: "التاريخ", problem_type: "نوع المشكلة", description: "الوصف",
  technician: "الفني", repair_action: "الإصلاح", repair_cost: "تكلفة الإصلاح", status: "الحالة",
  location: "الموقع", new_maintenance: "سجل صيانة جديد",
  upload: "رفع", file: "الملف", category: "التصنيف", unassigned: "غير مُسند", size: "الحجم", open_link: "فتح",
  duplicate_file: "ملف مكرر",
  review_intro: "رسائل وملفات لم يتمكن النظام من ربطها بثقة. لا يتغير شيء حتى توافق عليها.",
  message: "الرسالة", group: "المجموعة", reason: "السبب", extracted: "المُستخرج", choose_well: "رقم البئر للإسناد",
  event_type: "نوع الحدث", no_items: "لا يوجد شيء هنا", paste_message: "الصق رسالة واتساب",
  paste_help: "بديل عند عدم ربط رقم الاستقبال: الصق رسالة من المجموعة وسيعالجها النظام.",
  process: "معالجة", code: "الرمز", name: "الاسم", phone: "الهاتف", active: "نشط", projects: "المشاريع",
  avg_build_days: "متوسط أيام البناء", new_contractor: "مقاول جديد",
  orders_by_month: "الطلبات حسب الشهر", deliveries_by_month: "التسليمات حسب الشهر", by_well_type: "حسب نوع البئر",
  by_payment: "حسب حالة الدفع", maint_by_problem: "الصيانة حسب المشكلة", export_csv: "تصدير CSV", orders: "الطلبات",
  amount: "المبلغ", count: "العدد", cost: "التكلفة",
  integrations: "التكاملات", ai_settings: "الذكاء الاصطناعي والتكلفة", ai_enabled: "استخدام Claude AI (واجهة مدفوعة)",
  monthly_budget: "الميزانية الشهرية للذكاء الاصطناعي (دولار)", min_confidence: "أدنى ثقة للتطبيق التلقائي",
  manual_over: "اطلب الموافقة لأي طلب يتجاوز (دولار)", ai_cost_month: "تكلفة الذكاء الاصطناعي هذا الشهر",
  users: "المستخدمون", new_user: "مستخدم جديد", role: "الدور", sync_conflicts: "تعارضات المزامنة",
  keep_db: "الإبقاء على قيمة اللوحة", keep_sheet: "قبول قيمة الجدول", field: "الحقل", db_value: "اللوحة", sheet_value: "الجدول",
  jobs: "المهام الخلفية", retry: "إعادة المحاولة", attempts: "المحاولات", audit_log: "سجل التدقيق", action: "الإجراء",
  by: "بواسطة", time: "الوقت", backend: "الوضع", mock: "وضع الاختبار دون اتصال", configured: "مُعد", not_configured: "غير مُعد",
  language: "English",
  role_super_admin: "مدير عام", role_operations_manager: "مدير العمليات", role_contractor: "مقاول",
  role_maintenance: "فريق الصيانة", role_viewer: "مشاهد", role_staff: "موظف",
  st_new_order: "طلب جديد", st_scheduled: "مجدول", st_in_progress: "قيد التنفيذ", st_completed: "مكتمل",
  st_on_hold: "متوقف", st_cancelled: "ملغى", st_not_ready: "غير جاهز", st_pending: "بانتظار", st_delivered: "تم التسليم",
  st_none: "لا يوجد", st_raw_received: "تم استلام الخام", st_processing: "قيد المعالجة", st_in_review: "قيد المراجعة",
  st_open: "مفتوحة", st_resolved: "تم الحل", st_unpaid: "غير مدفوع", st_partial: "جزئي", st_paid: "مدفوع", st_refunded: "مسترد",
  st_approved: "موافق عليه", st_rejected: "مرفوض", st_queued: "في الطابور", st_running: "قيد التشغيل", st_succeeded: "نجح",
  st_failed: "فشل", st_retrying: "إعادة محاولة",
  k_unassigned_message: "رسالة غير مطابقة", k_ai_extraction: "تحقق من الاستخراج", k_merge_request: "طلب دمج",
  k_sheet_conflict: "تعارض الجدول", k_unassigned_media: "وسائط غير مُسندة",
  ev_construction_update: "تحديث إنشاء", ev_delivery_confirmation: "تأكيد تسليم", ev_final_video: "فيديو نهائي",
  ev_maintenance_report: "بلاغ صيانة", ev_general_note: "ملاحظة عامة", ev_new_order: "طلب جديد", ev_unknown: "غير معروف",
  cat_CONSTRUCTION: "إنشاء", cat_DELIVERY: "تسليم", cat_FINAL: "فيديو نهائي", cat_MAINT_BEFORE: "صيانة (قبل)",
  cat_MAINT_AFTER: "صيانة (بعد)", cat_MAINTENANCE: "صيانة", cat_OTHER: "أخرى",
  merge_into: "دمج في رقم البئر", request_merge: "طلب دمج", merge_reason: "السبب",
};

Object.assign(en, bookEn);
Object.assign(ar, bookAr);
Object.assign(en, shopifyEn);
Object.assign(ar, shopifyAr);
Object.assign(en, uiEn);
Object.assign(ar, uiAr);
Object.assign(en, opsEn);
Object.assign(ar, opsAr);
Object.assign(en, toolsEn);
Object.assign(ar, toolsAr);
Object.assign(en, renEn);
Object.assign(ar, renAr);
Object.assign(en, featEn);
Object.assign(ar, featAr);
Object.assign(en, certEn);
Object.assign(ar, certAr);
Object.assign(en, suqyaEn);
Object.assign(ar, suqyaAr);
Object.assign(en, designEn);
Object.assign(ar, designAr);
Object.assign(en, teamEn);
Object.assign(ar, teamAr);
const dicts = { ar, en };
type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string; st: (v?: string | null) => string; fmtDate: (d?: string | null) => string; num: (n: any) => string; money: (n: any) => string };
const I18n = createContext<Ctx>(null!);

function stored(): Lang { try { return (localStorage.getItem("hayah.lang") as Lang) || "ar"; } catch { return "ar"; } }

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(stored());
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  const setLang = (l: Lang) => { setLangState(l); try { localStorage.setItem("hayah.lang", l); } catch { /* ignore */ } };
  const t = (k: string) => dicts[lang][k] ?? en[k] ?? k;
  const st = (v?: string | null) => (v ? dicts[lang]["st_" + v] ?? v.replace(/_/g, " ") : "—");
  const locale = lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB";
  const fmtDate = (d?: string | null) => (d ? new Date(d.length === 10 ? d + "T00:00:00" : d).toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" }) : "—");
  const num = (n: any) => (n === null || n === undefined || n === "" ? "—" : Number(n).toLocaleString(locale));
  return <I18n.Provider value={{ lang, setLang, t, st, fmtDate, num, money: fmtMoney }}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);

/** Every price in the system is US dollars, written the same way everywhere: "$1,250" / "$12.50" / "−$40".
 *  Western digits and the "$" sign before the number, in Arabic and English alike (kept left-to-right inside Arabic text). */
const MONEY = new Intl.NumberFormat("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
export function fmtMoney(v: any): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return `${n < 0 ? "-" : ""}$${MONEY.format(Math.abs(n))}`;
}
