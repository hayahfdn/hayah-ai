// Floating buttons the user can move (Hayah, 2026-11-19): "Edit with a prompt" and the assistant.
// - Press and hold (about 0.4 s) to pick the button up, then drag; a normal tap or click just opens it,
//   so it never moves by mistake. Works with a mouse and with touch.
// - Kept fully on screen (also after the window or phone is rotated or resized).
// - On release it moves to the nearest side of the screen, and away from buttons, links and fields
//   under it, so it never covers the open-project icon, Save/Edit buttons, menus or navigation.
// - The place is saved on this device for this user (localStorage). reset() puts it back.
import { useCallback, useEffect, useRef, useState } from "react";

type Pos = { x: number; y: number } | null;
const HOLD_MS = 400, MARGIN = 12;

const read = (key: string): Pos => {
  try { const v = JSON.parse(localStorage.getItem(key) || "null"); return v && typeof v.x === "number" && typeof v.y === "number" ? v : null; }
  catch { return null; }
};
const write = (key: string, v: Pos) => { try { v ? localStorage.setItem(key, JSON.stringify(v)) : localStorage.removeItem(key); } catch { /* private mode */ } };

function clamp(p: { x: number; y: number }, w: number, h: number) {
  return { x: Math.min(Math.max(MARGIN, p.x), Math.max(MARGIN, window.innerWidth - w - MARGIN)),
           y: Math.min(Math.max(MARGIN, p.y), Math.max(MARGIN, window.innerHeight - h - MARGIN)) };
}

/** True when something the user works with (other than our floating buttons) sits under this box. */
function coversControl(r: { x: number; y: number }, w: number, h: number, self: HTMLElement) {
  const pts = [[r.x + w / 2, r.y + h / 2], [r.x + 4, r.y + 4], [r.x + w - 4, r.y + 4], [r.x + 4, r.y + h - 4], [r.x + w - 4, r.y + h - 4]];
  for (const [px, py] of pts) {
    for (const el of document.elementsFromPoint(px, py)) {
      if (el === self || self.contains(el) || (el as HTMLElement).closest?.(".fab-movable")) continue;
      if ((el as HTMLElement).closest?.("button, a, input, select, textarea, [role=button], .open-ico, nav, .side, .bottom-nav, .ag-header")) return true;
      break;  // only the top-most element at this point matters
    }
  }
  return false;
}

function settle(p: { x: number; y: number }, el: HTMLElement) {
  const w = el.offsetWidth, h = el.offsetHeight;
  // snap to the nearest side so it stays out of the content
  let q = clamp({ x: p.x + w / 2 < window.innerWidth / 2 ? MARGIN : window.innerWidth - w - MARGIN, y: p.y }, w, h);
  for (let i = 0, step = h + 8; i < 12 && coversControl(q, w, h, el); i++) {
    const up = clamp({ ...q, y: q.y - step * (Math.floor(i / 2) + 1) * (i % 2 ? -1 : 1) }, w, h);
    if (!coversControl(up, w, h, el)) { q = up; break; }
  }
  return q;
}

export function useDraggable(key: string) {
  const ref = useRef<HTMLButtonElement | null>(null);
  const [pos, setPos] = useState<Pos>(() => read(key));
  const [dragging, setDragging] = useState(false);
  const st = useRef<{ timer: number | null; start: { x: number; y: number }; off: { x: number; y: number }; moved: boolean; picked: boolean }>(
    { timer: null, start: { x: 0, y: 0 }, off: { x: 0, y: 0 }, moved: false, picked: false });

  useEffect(() => { setPos(read(key)); }, [key]);
  useEffect(() => {  // keep it on screen after a resize / rotation
    const fix = () => setPos((p) => (p && ref.current ? clamp(p, ref.current.offsetWidth, ref.current.offsetHeight) : p));
    window.addEventListener("resize", fix);
    return () => window.removeEventListener("resize", fix);
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    const el = e.currentTarget, r = el.getBoundingClientRect(), s = st.current;
    s.start = { x: e.clientX, y: e.clientY }; s.off = { x: e.clientX - r.left, y: e.clientY - r.top }; s.moved = false; s.picked = false;
    s.timer = window.setTimeout(() => {
      s.picked = true; setDragging(true);
      try { el.setPointerCapture(e.pointerId); } catch { /* ignore */ }
      if (navigator.vibrate) navigator.vibrate(15);
    }, HOLD_MS);
  }, []);
  const onPointerMove = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
    const s = st.current;
    if (!s.picked) {  // moving before the hold ends = scrolling or a slip: cancel, do not drag
      if (s.timer && Math.hypot(e.clientX - s.start.x, e.clientY - s.start.y) > 8) { clearTimeout(s.timer); s.timer = null; }
      return;
    }
    e.preventDefault(); s.moved = true;
    const el = e.currentTarget;
    setPos(clamp({ x: e.clientX - s.off.x, y: e.clientY - s.off.y }, el.offsetWidth, el.offsetHeight));
  }, []);
  const end = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
    const s = st.current;
    if (s.timer) { clearTimeout(s.timer); s.timer = null; }
    if (s.picked) {
      const el = e.currentTarget;
      setPos((p) => { const q = p ? settle(p, el) : p; write(key, q); return q; });
      setDragging(false);
    }
  }, [key]);
  /** Swallow the click that ends a drag, so moving the button never opens it. */
  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (st.current.picked) { e.preventDefault(); e.stopPropagation(); st.current.picked = false; }
  }, []);
  const reset = useCallback(() => { write(key, null); setPos(null); }, [key]);

  // touch-action none: a press-and-hold is not taken by the browser as a scroll (the button is small)
  const style: React.CSSProperties = pos ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto", touchAction: "none" } : { touchAction: "none" };
  return { ref, style, dragging, moved: pos !== null, reset,
           handlers: { onPointerDown, onPointerMove, onPointerUp: end, onPointerCancel: end, onClickCapture,
                       onContextMenu: (e: React.MouseEvent) => e.preventDefault() } };
}
