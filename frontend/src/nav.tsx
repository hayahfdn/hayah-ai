// Side menu: month pages for wells and sacrifices, contractors by country and the three
// partners each sit in one drop-down, so the menu stays short. Also the phone bottom bar.
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { NavData } from "./api";
import { EDITORS, MANAGERS, useAuth } from "./App";
import { useI18n } from "./i18n";
import { COUNTRY_AR, PARTNERS } from "./i18n-ui";
import { useApi } from "./ui";
import * as I from "./icons";

type IconT = I.IconC;
const Ico = ({ i: C }: { i: IconT }) => <i className="nav-ico" aria-hidden="true"><C size={18} strokeWidth={1.9} /></i>;

const NavCtx = createContext<NavData | null>(null);
export const useNav = () => useContext(NavCtx);

export function NavProvider({ children }: { children: React.ReactNode }) {
  const nav = useApi<NavData>("/api/nav");
  useEffect(() => {
    const h = () => nav.reload();
    window.addEventListener("hayah:data-changed", h);
    return () => window.removeEventListener("hayah:data-changed", h);
  }, [nav.reload]); // eslint-disable-line react-hooks/exhaustive-deps
  return <NavCtx.Provider value={nav.data}>{children}</NavCtx.Provider>;
}

export function thisMonth() { return new Date().toISOString().slice(0, 7); }

export function monthLabel(m: string, lang: string, style: "long" | "short" = "long") {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleDateString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB",
    { month: style, year: style === "long" ? "numeric" : "2-digit" });
}

export function countryLabel(c: string, lang: string) { return lang === "ar" ? COUNTRY_AR[c] || c : c; }

export function useIsMobile(width = 760) {
  const q = `(max-width: ${width}px)`;
  const [m, setM] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const h = () => setM(mq.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [q]);
  return m;
}

/** Where a month / contractor / partner page lives for this person (managers see the finance workbook). */
export function useLinks() {
  const { can } = useAuth();
  const manager = can(...MANAGERS);
  return useMemo(() => ({
    wells: (m: string) => (manager ? `/book/wells/${m}` : `/wells/${m}`),
    sac: (m: string) => (manager ? `/book/sac/${m}` : `/sacrifices/${m}`),
    con: (code: string) => (manager ? `/book/con/${code}` : `/contractor/${code}`),
    acc: (code: string) => `/book/acc/${code}`,
  }), [manager]);
}

type Item = { key: string; label: string; to: string; color?: string | null; hint?: string };

/** A drop-down group: the header shows the chosen (or default) item, the list opens on tap. */
function NavPicker({ title, items, defaultKey, icon }: { title: string; items: Item[]; defaultKey?: string; icon?: IconT }) {
  const loc = useLocation();
  const { t } = useI18n();
  const active = items.find((i) => loc.pathname === i.to);
  const shown = active || items.find((i) => i.key === defaultKey);
  const [open, setOpen] = useState(!!active);
  useEffect(() => { if (active) setOpen(true); }, [active?.key]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!items.length) return null;
  return (
    <div className={`nav-pick ${active ? "has-active" : ""} ${open ? "open" : ""}`}>
      <button type="button" className="nav-pick-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="nav-pick-title">{icon ? <Ico i={icon} /> : <i className="nav-ico dot" aria-hidden="true" />}{title}</span>
        <span className="nav-pick-sel">{shown ? shown.label : `${items.length}`}</span>
        <span className="chev" aria-hidden="true">▾</span>
      </button>
      {open && <div className="nav-pick-list" role="list">
        {items.map((i) => (
          <NavLink key={i.key} to={i.to} role="listitem" className={i.key === defaultKey && !active ? "is-default" : undefined}>
            {i.color && <span className="swatch" style={{ background: i.color }} aria-hidden="true" />}
            <span className="nav-item-label">{i.label}</span>
            {i.hint && <span className="nav-item-hint">{i.hint}</span>}
            {i.key === defaultKey && <span className="nav-now">{t("nav_this_month")}</span>}
          </NavLink>))}
      </div>}
    </div>
  );
}

export function SideNav({ counts }: { counts: Record<string, number> }) {
  const { t, lang } = useI18n();
  const { can, user } = useAuth();
  const nav = useNav();
  const L = useLinks();
  const manager = can(...MANAGERS);
  const months = (list: string[], to: (m: string) => string): Item[] =>
    [...list].reverse().map((m) => ({ key: m, label: monthLabel(m, lang), to: to(m) }));
  const byCountry = useMemo(() => {
    const g: Record<string, Item[]> = {};
    for (const c of nav?.contractors || []) {
      (g[c.country || "—"] ||= []).push({ key: c.code, label: c.name, hint: c.code, to: L.con(c.code), color: c.color });
    }
    const order = ["Pakistan", "Nepal", "Bangladesh", "India", "Tanzania"];
    return Object.entries(g).sort(([a], [b]) => ((order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99)) || a.localeCompare(b));
  }, [nav?.contractors, L]);
  const partners: Item[] = PARTNERS.filter((p) => nav?.partners.some((x) => x.code === p.code))
    .map((p) => ({ key: p.code, label: lang === "ar" ? p.ar : p.en, to: L.acc(p.code) }));
  const link = (to: string, key: string, icon: IconT, n?: number, red?: boolean) => (
    <NavLink to={to} end={to === "/" || to === "/book"}><span className="nav-l"><Ico i={icon} />{t(key)}</span>{n ? <span className={`count${red ? " red" : ""}`}>{n}</span> : null}</NavLink>);
  const cur = nav?.current || thisMonth();
  return (
    <nav className="nav">
      <div className="nav-sec">{t("nav_sec_main")}</div>
      {link("/", "nav_dashboard", I.LayoutDashboard)}
      {nav && <NavPicker title={t("nav_wells")} icon={I.Droplets} items={months(nav.wells, L.wells)} defaultKey={cur} />}
      {nav && can(...EDITORS) && <NavPicker title={t("nav_sacrifices")} icon={I.Sheep} items={months(nav.sacrifices, L.sac)} defaultKey={cur} />}
      {manager && <>
        <div className="nav-sec">{t("nav_sec_book")}</div>
        {link("/book", "tab_summary", I.ChartColumn)}
        {(nav?.banks || []).map((b) => <NavLink key={b.code} to={L.acc(b.code)}><span className="nav-l"><Ico i={b.code === "WISE" ? I.Landmark : I.Wallet} />{b.code === "WISE" ? "Wise" : b.name}</span></NavLink>)}
      </>}
      {byCountry.length > 0 && user.role !== "contractor" && <>
        <div className="nav-sec">{t("nav_sec_contractors")}</div>
        {byCountry.map(([country, items]) => <NavPicker key={country} title={countryLabel(country, lang)} icon={I.MapPin} items={items} />)}
      </>}
      {manager && partners.length > 0 && <NavPicker title={t("nav_people")} icon={I.Users} items={partners} />}
      {can(...EDITORS) && <>
        <div className="nav-sec">{t("nav_sec_flow")}</div>
        {link("/tasks", "nav_tasks", I.ListTodo, counts.tasks_mine, true)}
        {link("/inbox", "nav_inbox", I.MessageCircle, counts.wa_unread, true)}
        {link("/plaques/confirm", "nav_pl_confirm", I.ClipboardCheck, counts.pl_confirm, true)}
        {manager && link("/plaques/approved", "nav_pl_approved", I.BadgeCheck, counts.pl_ready, true)}
        {link("/videos", "nav_videos", I.Clapperboard, counts.vid_ready, true)}
      </>}
      <div className="nav-sec">{t("nav_sec_work")}</div>
      {link("/sheet", "nav_sheet", I.Table2)}{link("/projects", "nav_projects", I.FolderKanban)}{link("/construction", "nav_construction", I.HardHat)}
      {link("/delivery", "nav_delivery", I.Truck, counts.pending_delivery_approvals)}{link("/maintenance", "nav_maintenance", I.Wrench)}
      {link("/media", "nav_media", I.Images)}
      {can(...EDITORS) && link("/plaque", "nav_plaque", I.Image)}
      {manager && link("/review", "nav_review", I.ClipboardCheck, counts.pending_review)}
      <div className="nav-sec">{t("nav_sec_admin")}</div>
      {link("/contractors", "nav_contractors_list", I.HardHat)}{link("/reports", "nav_reports", I.ChartColumn)}
      {manager && link("/settings", "nav_settings", I.Settings)}
    </nav>
  );
}

/** Phone only: the pages people open most, one tap away. */
export function BottomBar({ onMenu }: { onMenu: () => void }) {
  const { t } = useI18n();
  const { can, counts, user } = useAuth();
  const nav = useNav();
  const L = useLinks();
  const cur = nav?.current || thisMonth();
  const manager = can(...MANAGERS);
  const loc = useLocation();
  const plaques = (counts.pl_confirm || 0) + (counts.pl_ready || 0) + (counts.vid_ready || 0) + (counts.wa_unread || 0);
  const on = (prefix: string) => (loc.pathname.startsWith(prefix) ? "active" : "");
  return (
    <nav className="bottom-bar" aria-label={t("nav_menu")}>
      <NavLink to="/" end><i aria-hidden="true"><I.House size={21} /></i><span>{t("nav_home")}</span></NavLink>
      <NavLink to={L.wells(cur)} className={on(manager ? "/book/wells" : "/wells")}><i aria-hidden="true"><I.Droplets size={21} /></i><span>{t("nav_wells")}</span></NavLink>
      {can(...EDITORS)
        ? <NavLink to={L.sac(cur)} className={on(manager ? "/book/sac" : "/sacrifices")}><i aria-hidden="true"><I.Sheep size={21} /></i><span>{t("nav_sacrifices")}</span></NavLink>
        : <NavLink to="/projects"><i aria-hidden="true"><I.FolderKanban size={21} /></i><span>{t("nav_projects")}</span></NavLink>}
      {can(...EDITORS) && user.team_stage
        ? <NavLink to="/tasks"><i aria-hidden="true"><I.ListTodo size={21} /></i><span>{t("nav_tasks")}</span>{counts.tasks_mine ? <b className="dot-count">{counts.tasks_mine}</b> : null}</NavLink>
        : can(...EDITORS)
        ? <NavLink to="/plaque"><i aria-hidden="true"><I.Image size={21} /></i><span>{t("plaque")}</span></NavLink>
        : <NavLink to="/reports"><i aria-hidden="true"><I.ChartColumn size={21} /></i><span>{t("nav_reports")}</span></NavLink>}
      <button type="button" onClick={onMenu}><i aria-hidden="true"><I.Menu size={21} /></i><span>{t("nav_menu")}</span>{plaques > 0 && <b className="dot-count">{plaques}</b>}</button>
    </nav>
  );
}

/** Previous / next month and a month list, at the top of every month page. */
export function MonthSwitcher({ month, kind }: { month: string; kind: "wells" | "sac" }) {
  const { t, lang } = useI18n();
  const nav = useNav();
  const go = useNavigate();
  const L = useLinks();
  const list = (kind === "wells" ? nav?.wells : nav?.sacrifices) || [month];
  const all = list.includes(month) ? list : [...list, month].sort();
  const i = all.indexOf(month);
  const to = (m: string) => (kind === "wells" ? L.wells(m) : L.sac(m));
  return (
    <div className="month-switch" role="group" aria-label={t("nav_month")}>
      <button type="button" disabled={i <= 0} onClick={() => go(to(all[i - 1]))} aria-label={t("nav_prev_month")}>{lang === "ar" ? "›" : "‹"}</button>
      <select value={month} onChange={(e) => go(to(e.target.value))} aria-label={t("nav_month")}>
        {[...all].reverse().map((m) => <option key={m} value={m}>{monthLabel(m, lang)}{m === nav?.current ? ` · ${t("nav_this_month")}` : ""}</option>)}
      </select>
      <button type="button" disabled={i >= all.length - 1} onClick={() => go(to(all[i + 1]))} aria-label={t("nav_next_month")}>{lang === "ar" ? "‹" : "›"}</button>
    </div>
  );
}
