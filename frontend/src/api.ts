// Thin API client. The token lives in sessionStorage (cleared when the tab closes);
// no API keys or secrets ever reach the browser.
const TOKEN_KEY = "hayah.token";

export function getToken() { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } }
export function setToken(t: string | null) {
  try { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

export async function api<T = any>(path: string, opts: { method?: string; body?: any; form?: FormData; query?: Record<string, any> } = {}): Promise<T> {
  const url = new URL(path, window.location.origin);
  Object.entries(opts.query || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v)); });
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  const res = await fetch(url.toString().replace(window.location.origin, ""), { method: opts.method || (body ? "POST" : "GET"), headers, body });
  if (res.status === 401 && path !== "/api/auth/login") { setToken(null); window.dispatchEvent(new Event("hayah:logout")); }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : (j.detail || []).map((d: any) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; "); } catch { /* ignore */ }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export async function download(path: string, filename: string) {
  const res = await fetch(path, { headers: { Authorization: `Bearer ${getToken()}` } });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename; a.click();
  URL.revokeObjectURL(a.href);
}

export type Role = "super_admin" | "operations_manager" | "staff" | "contractor" | "maintenance" | "viewer";
export interface User { id: number; email: string; full_name: string; role: Role; is_active: boolean; preferred_lang: "ar" | "en"; phone: string | null; contractor_id: number | null; last_login_at: string | null; ui_zoom?: number | null; }
export interface Contractor { id: number; code: string; name: string; country: string | null; phone: string | null; is_active: boolean; notes: string | null; color?: string | null; }
export interface Project {
  id: number; well_id: number; order_date: string | null; customer_name: string | null; customer_phone: string | null;
  customer_phone_e164?: string | null; customer_phone_country?: string | null; customer_phone_status?: string | null;
  country: string | null; city: string | null; village: string | null; well_type: string | null; sales_source: string | null; source_group?: string | null;
  contractor_id: number | null; contractor: Contractor | null; sale_amount: string | null; cost: string | null; currency: string;
  payment_method: string | null; extras: string | null; shopify_order: string | null; dedication?: string | null; received_date: string | null;
  listed_at?: string | null; addon_sacrifices?: { sacrifice_no: number; animal_type: string | null; sale_price: string | null; currency: string }[];
  payment_status: string; construction_status: string; construction_start_date: string | null; completion_date: string | null;
  delivery_status: string; delivery_date: string | null; delivery_estimated?: boolean; raw_media_folder_url: string | null; final_video_link: string | null;
  video_status: string; maintenance_status: string; last_maintenance_date: string | null; next_maintenance_date: string | null;
  notes: string | null; merged_into_id: number | null; is_sample: boolean; version: number; updated_at: string; created_at: string;
  plaque_status?: "draft" | "approved" | null; plaque_media_id?: number | null; plaque_approved_at?: string | null; plaque_approved_by?: string | null;
}
export interface NavContractor { id: number; code: string; name: string; country: string; color: string | null; }
export interface NavData {
  current: string; wells: string[]; sacrifices: string[]; contractors: NavContractor[];
  partners: { code: string; name: string }[]; banks: { code: string; name: string }[];
}

/** An authenticated file (e.g. an approved plaque) as an object URL for <img src>. */
export async function fileUrl(path: string): Promise<string> {
  const res = await fetch(path, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return URL.createObjectURL(await res.blob());
}
export interface Sacrifice {
  id: number; sacrifice_no: number; order_date: string | null; donor_name: string | null; received_date: string | null;
  delivery_date: string | null; delivery_status?: string; delivery_estimated?: boolean; contractor_id: number | null; animal_type: string | null; cost: string | null; sale_price: string | null;
  currency: string; payment_method: string | null; extras: string | null; sales_source: string | null; source_group?: string | null; shopify_order: string | null;
  parent_project_id?: number | null; parent_well_id?: number | null;
  intention: string | null; dedication?: string | null; notes: string | null; is_sample: boolean; version: number; updated_at: string;
}
export interface Account { id: number; code: string; name: string; kind: "bank" | "partner"; currency: string; notes: string | null; is_active: boolean; }
export interface Tx {
  id: number; date: string; kind: string; direction: "in" | "out"; account_id: number | null; contractor_id: number | null;
  channel: string | null; category: string | null; amount: string; currency: string; description: string | null; reference: string | null;
  voided: boolean; void_reason: string | null; is_sample: boolean; version: number; updated_at: string; balance?: number;
}
export const TX_KINDS = ["income", "contractor_payment", "ad_spend", "operating_expense", "partner_took", "partner_spent", "partner_withdrawal", "loan", "transfer", "other"];
/** Tell every open sheet to reload (after a prompt edit, a new row, etc.). */
export const dataChanged = () => window.dispatchEvent(new Event("hayah:data-changed"));
