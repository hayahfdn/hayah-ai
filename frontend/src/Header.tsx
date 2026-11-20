// The white bar at the top of every page on a computer: search, the day's waiting work as icons with
// counts (each opens its page), new order, and the zoom control. On a phone the dark mobile bar is used.
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EDITORS, MANAGERS, useAuth } from "./App";
import { useI18n } from "./i18n";
import * as I from "./icons";
import { useZoom, ZoomControl } from "./Zoom";

export function initials(name: string) {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] || "") + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase() || "؟";
}

export default function Header({ zoom }: { zoom: ReturnType<typeof useZoom> }) {
  const { t, lang } = useI18n();
  const { can, counts, user } = useAuth();
  const go = useNavigate();
  const [q, setQ] = useState("");
  const editor = can(...EDITORS);
  const today = new Date();
  const quick: [string, string, I.IconC, number | undefined][] = editor ? [
    ["/inbox", "nav_inbox", I.MessageCircle, counts.wa_unread],
    ["/plaques/confirm", "nav_pl_confirm", I.ClipboardCheck, counts.pl_confirm],
    ...(can(...MANAGERS) ? [["/plaques/approved", "nav_pl_approved", I.BadgeCheck, counts.pl_ready] as [string, string, any, number]] : []),
    ["/videos", "nav_videos", I.Clapperboard, counts.vid_ready],
  ] : [];
  return (
    <header className="app-top">
      <form className="top-search" role="search" onSubmit={(e) => { e.preventDefault(); const v = q.trim(); if (v) go(`/projects?q=${encodeURIComponent(v)}`); }}>
        <I.Search size={18} aria-hidden="true" />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("top_search")} aria-label={t("top_search")} />
      </form>
      <div className="top-date" aria-label={t("today")}>
        <b>{today.getDate()}</b>
        <span>{today.toLocaleDateString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { month: "long", year: "numeric" })}<small>
          {today.toLocaleDateString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { weekday: "long" })}</small></span>
      </div>
      <nav className="top-quick" aria-label={t("top_quick")}>
        {quick.map(([to, key, C, n]) => (
          <Link key={to} to={to} className="top-ico" title={t(key)} aria-label={`${t(key)}${n ? ` (${n})` : ""}`}>
            <C size={20} strokeWidth={1.9} />{n ? <b className="top-badge">{n > 99 ? "99+" : n}</b> : null}</Link>))}
        {editor && <Link to="/projects?new=1" className="btn primary top-new"><I.Plus size={18} /> <span>{t("new_project")}</span></Link>}
      </nav>
      <ZoomControl zoom={zoom} />
      <span className="top-user" title={`${user.full_name} · ${t("role_" + user.role)}`}><span className="avatar sm">{initials(user.full_name)}</span></span>
    </header>
  );
}
