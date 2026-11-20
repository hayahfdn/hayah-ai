// Interface zoom for the whole system (Hayah, 20 Nov 2026): 80, 90, 100, 110, 125, 150 %.
// Each person's level is saved on their account (so it follows them to any device) and kept in this
// browser for an instant start. It scales every page, menu, table, form and button together (CSS zoom
// on the page root), so nothing is cut off and everything keeps working. Shortcuts that do not clash
// with the browser's own zoom: Ctrl+Alt+= (in), Ctrl+Alt+- (out), Ctrl+Alt+0 (reset).
import { useCallback, useEffect, useRef, useState } from "react";
import { api, User } from "./api";
import { useI18n } from "./i18n";

export const ZOOM_LEVELS = [80, 90, 100, 110, 125, 150];
const key = (id: number) => `hayah.zoom.${id}`;

export function applyZoom(level: number) {
  const z = ZOOM_LEVELS.includes(level) ? level : 100;
  const root = document.documentElement;
  root.style.setProperty("zoom", z === 100 ? "" : String(z / 100));
  root.style.setProperty("--ui-zoom", String(z / 100));
  root.dataset.zoom = String(z);
  window.dispatchEvent(new Event("resize"));  // grids and the plaque preview re-measure
}

/** Reads this person's zoom (browser copy first, then their account) and applies it. */
export function useZoom(user: User | null) {
  const [level, setLevel] = useState(100);
  useEffect(() => {
    if (!user) { applyZoom(100); return; }
    let local: number | null = null;
    try { local = Number(localStorage.getItem(key(user.id))) || null; } catch { /* storage blocked */ }
    const z = user.ui_zoom ?? local ?? 100;
    setLevel(z); applyZoom(z);
  }, [user?.id, user?.ui_zoom]);  // eslint-disable-line react-hooks/exhaustive-deps
  const set = useCallback((z: number) => {
    if (!user || !ZOOM_LEVELS.includes(z)) return;
    setLevel(z); applyZoom(z);
    try { localStorage.setItem(key(user.id), String(z)); } catch { /* storage blocked */ }
    api("/api/auth/me/preferences", { method: "PATCH", body: { ui_zoom: z } }).catch(() => {});
  }, [user]);
  const cur = useRef(level);
  cur.current = level;
  const step = useCallback((dir: 1 | -1) => {
    const i = ZOOM_LEVELS.indexOf(cur.current);
    const next = ZOOM_LEVELS[Math.max(0, Math.min(ZOOM_LEVELS.length - 1, (i < 0 ? 2 : i) + dir))];
    if (next !== cur.current) { cur.current = next; set(next); }
  }, [set]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || !e.altKey) return;
      if (e.code === "Equal" || e.code === "NumpadAdd") { e.preventDefault(); step(1); }
      else if (e.code === "Minus" || e.code === "NumpadSubtract") { e.preventDefault(); step(-1); }
      else if (e.code === "Digit0" || e.code === "Numpad0") { e.preventDefault(); set(100); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [step, set]);
  return { level, set, step };
}

export function ZoomControl({ zoom, compact }: { zoom: ReturnType<typeof useZoom>; compact?: boolean }) {
  const { t, num } = useI18n();
  const { level, set, step } = zoom;
  const i = ZOOM_LEVELS.indexOf(level);
  return (
    <div className={`zoom-ctl${compact ? " compact" : ""}`} role="group" aria-label={t("zoom")} title={t("zoom_keys")}>
      <button type="button" className="sm" onClick={() => step(-1)} disabled={i === 0} aria-label={t("zoom_out")} title={`${t("zoom_out")} (Ctrl+Alt+-)`}>−</button>
      <select className="sm" value={level} onChange={(e) => set(Number(e.target.value))} aria-label={t("zoom")}>
        {ZOOM_LEVELS.map((z) => <option key={z} value={z}>{num(z)}%</option>)}
      </select>
      <button type="button" className="sm" onClick={() => step(1)} disabled={i === ZOOM_LEVELS.length - 1} aria-label={t("zoom_in")} title={`${t("zoom_in")} (Ctrl+Alt+=)`}>+</button>
      <button type="button" className="sm" onClick={() => set(100)} disabled={level === 100} aria-label={t("zoom_reset")} title={`${t("zoom_reset")} (Ctrl+Alt+0)`}>↺{compact ? "" : ` ${t("zoom_reset")}`}</button>
    </div>
  );
}
