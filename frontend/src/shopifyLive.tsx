// Live Shopify (Hayah, 27 Nov 2026): orders arrive by Shopify webhook and are imported at once; these pages
// ask a tiny status every few seconds and reload their list only when something actually changed.
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { useI18n } from "./i18n";

export type Live = { orders_version: string; suqya_version: string; last_webhook_at: string | null; last_sync_at: string | null; instant: boolean; enabled: boolean };
const EVERY_MS = 5000;

/** Calls onChange whenever `which` changes on the server (a new or changed order). Pauses while the tab is hidden. */
export function useShopifyLive(which: "orders_version" | "suqya_version", onChange: () => void) {
  const [live, setLive] = useState<Live | null>(null);
  const last = useRef<string | null>(null);
  const cb = useRef(onChange);
  cb.current = onChange;
  useEffect(() => {
    let stop = false, timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (!document.hidden) {
        try {
          const r = await api<Live>("/api/shopify/live");
          if (stop) return;
          setLive(r);
          if (last.current !== null && r[which] !== last.current) cb.current();
          last.current = r[which];
        } catch { /* offline for a moment: try again on the next tick */ }
      }
      if (!stop) timer = setTimeout(tick, EVERY_MS);
    };
    const wake = () => { if (!document.hidden) { clearTimeout(timer); tick(); } };
    tick();
    document.addEventListener("visibilitychange", wake);
    return () => { stop = true; clearTimeout(timer); document.removeEventListener("visibilitychange", wake); };
  }, [which]);
  return live;
}

/** «مباشر» badge: green when Shopify sends orders instantly, amber when only the 2‑minute check is running. */
export function LiveBadge({ live }: { live: Live | null }) {
  const { t, lang } = useI18n();
  if (!live || !live.enabled) return null;
  const at = live.last_webhook_at || live.last_sync_at;
  const when = at ? new Date(at).toLocaleTimeString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { hour: "2-digit", minute: "2-digit" }) : null;
  return <span className={`live-badge${live.instant ? " on" : ""}`} title={live.instant ? t("live_on_help") : t("live_off_help")}>
    <span className="live-dot" aria-hidden="true" />{live.instant ? t("live_on") : t("live_off")}
    {when && <span className="muted"> · {t("live_last")} {when}</span>}
  </span>;
}
