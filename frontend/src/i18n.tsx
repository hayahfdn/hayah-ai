import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { bookAr, bookEn } from "./i18n-book";
import { shopifyAr, shopifyEn } from "./i18n-shopify";

export type Lang = "ar" | "en";

const en: Record<string, string> = {
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
  last_updated: "Last updated", search: "Search Well ID, customer, village…", all: "All", new_project: "New project",
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
  role_maintenance: "Maintenance Team", role_viewer: "Viewer", role_staff: "Team member (no costs)",
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
  last_updated: "آخر تحديث", search: "ابحث برقم البئر أو العميل أو القرية…", all: "الكل", new_project: "مشروع جديد",
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
  role_maintenance: "فريق الصيانة", role_viewer: "مشاهد", role_staff: "موظف (بدون التكاليف)",
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
const dicts = { ar, en };
type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string; st: (v?: string | null) => string; fmtDate: (d?: string | null) => string; num: (n: any) => string };
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
  return <I18n.Provider value={{ lang, setLang, t, st, fmtDate, num }}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);
