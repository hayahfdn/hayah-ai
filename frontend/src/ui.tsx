import { ReactNode, useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { useI18n } from "./i18n";

export function useApi<T>(path: string | null, query?: Record<string, any>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const key = path + JSON.stringify(query || {});
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try { setData(await api<T>(path, { query })); setError(null); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

const TONE: Record<string, string> = {
  completed: "ok", delivered: "ok", paid: "ok", approved: "ok", resolved: "ok", succeeded: "ok", synced: "ok",
  in_progress: "info", scheduled: "info", processing: "info", raw_received: "info", in_review: "info", running: "info", partial: "warn",
  pending: "warn", new_order: "brand", open: "warn", retrying: "warn", queued: "warn", conflicts: "warn", on_hold: "warn",
  unpaid: "bad", rejected: "bad", failed: "bad", cancelled: "bad", error: "bad",
};

export function Status({ v }: { v?: string | null }) {
  const { st } = useI18n();
  if (!v) return <span className="muted">—</span>;
  return <span className={`badge ${TONE[v] || ""}`}>{st(v)}</span>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useI18n();
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <header><h2 style={{ margin: 0 }}>{title}</h2><button className="sm" onClick={onClose}>{t("close")}</button></header>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children, hint, tone }: { label: string; children: ReactNode; hint?: string; tone?: "ok" | "bad" }) {
  return <div className="field"><label>{label}</label>{children}{hint && <span className={`hint ${tone || "muted"}`}>{hint}</span>}</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="error" role="alert">{error}</div> : null;
}

let toastTimer: any;
export function toast(msg: string) {
  let el = document.getElementById("toast");
  if (!el) { el = document.createElement("div"); el.id = "toast"; el.className = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
  el.textContent = msg; el.style.display = "block";
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el!.style.display = "none"; }, 2600);
}

export function Bars({ rows }: { rows: { label: string; value: number }[] }) {
  const { num } = useI18n();
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return <div className="empty">—</div>;
  return <div>{rows.map((r) => (
    <div className="bar-row" key={r.label}>
      <span title={r.label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.label}</span>
      <div className="bar"><i style={{ width: `${(100 * r.value) / max}%` }} /></div>
      <span className="num" style={{ textAlign: "end" }}>{num(r.value)}</span>
    </div>))}</div>;
}

export function Empty() { const { t } = useI18n(); return <div className="empty">{t("no_items")}</div>; }
