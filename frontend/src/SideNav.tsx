// The side menu. Month pages, contractors (one list per country) and partners are grouped into
// drop-down lists so the menu stays short. Each list shows what is open now, or the current month.
import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Account, Contractor } from "./api";
import { EDITORS, MANAGERS, useAuth } from "./App";
import { useI18n } from "./i18n";
import { contractorColor, countryName, deeper, monthName, PARTNERS, sortContractors, thisMonth } from "./look";
import { useApi } from "./ui";

interface WB { accounts: Account[]; contractors: Contractor[]; months: { wells: string[]; sacrifices: string[]; current: string } }
type Item = { to: string; label: string; badge?: string; dot?: string };

function Chevron({ open }: { open: boolean }) {
  return <svg className={`chev ${open ? "up" : ""}`} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
    <path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

/** A drop-down list in the menu: the header shows the open (or default) choice; tapping it lists every choice. */
function Pick({ id, label, shown, items, activeTo, openId, setOpenId }: {
  id: string; label: string; shown: string; items: Item[]; activeTo?: string; openId: string | null; setOpenId: (v: string | null) => void;
}) {
  const open = openId === id;
  const active = !!activeTo && items.some((i) => i.to === activeTo);
  return (
    <div className={`pick ${open ? "open" : ""} ${active ? "has-active" : ""}`}>
      <button type="button" className="pick-head" aria-expanded={open} aria-controls={`pick-${id}`} onClick={() => setOpenId(open ? null : id)}>
        <span className="pick-text"><b>{label}</b><small>{shown}</small></span><Chevron open={open} />
      </button>
      {open && <div className="pick-list" id={`pick-${id}`} role="list">
        {items.map((i) => (
          <NavLink key={i.to} to={i.to} role="listitem" className={({ isActive }) => (isActive ? "active" : "")}>
            {i.dot && <i className="dot" style={{ background: i.dot }} />}<span>{i.label}</span>{i.badge && <span className="tag">{i.badge}</span>}
          </NavLink>))}
      </div>}
    </div>
  );
}

export default function SideNav() {
  const { t, lang } = useI18n();
  const { can, counts } = useAuth();
  const loc = useLocation();
  const manager = can(...MANAGERS);
  const wb = useApi<WB>(manager ? "/api/finance/workbook" : null);
  const [openId, setOpenId] = useState<string | null>(null);
  useEffect(() => setOpenId(null), [loc.pathname]);
  const reload = wb.reload;
  useEffect(() => {  // a new month or contractor appears after edits elsewhere
    window.addEventListener("hayah:data-changed", reload);
    return () => window.removeEventListener("hayah:data-changed", reload);
  }, [reload]);
  const here = decodeURIComponent(loc.pathname);

  const groups = useMemo(() => {
    if (!wb.data) return null;
    const { months, contractors, accounts } = wb.data;
    const cur = months.current || thisMonth();
    const monthItems = (list: string[], base: string): Item[] => {
      const all = Array.from(new Set([...list, cur])).sort().reverse();
      return all.map((m) => ({ to: `${base}/${m}`, label: monthName(m, lang), badge: m === cur ? t("current_month") : undefined }));
    };
    const byCountry = new Map<string, Contractor[]>();
    for (const c of sortContractors(contractors)) {
      const k = c.country || "";
      if (!byCountry.has(k)) byCountry.set(k, []);
      byCountry.get(k)!.push(c);
    }
    const partners = accounts.filter((a) => a.kind === "partner");
    const partnerItems: Item[] = [
      ...PARTNERS.filter((p) => partners.some((a) => a.code === p.code))
        .map((p) => ({ to: `/book/acc/${p.code}`, label: lang === "ar" ? p.ar : p.en })),
      ...partners.filter((a) => !PARTNERS.some((p) => p.code === a.code))
        .map((a) => ({ to: `/book/acc/${a.code}`, label: a.name.replace(/\s*\(.*\)/, "") })),
    ];
    return { cur, wells: monthItems(months.wells, "/book/wells"), sac: monthItems(months.sacrifices, "/book/sac"), byCountry, partnerItems };
  }, [wb.data, lang, t]);

  const shownMonth = (base: string, cur: string) => {
    const m = here.startsWith(base + "/") ? here.slice(base.length + 1) : cur;
    return monthName(m, lang) + (m === cur ? ` · ${t("current_month")}` : "");
  };
  const link = (to: string, key: string, n?: number) => (
    <NavLink key={to} to={to} end={to === "/" || to === "/book"}>{t(key)}{n ? <span className="count">{n}</span> : null}</NavLink>);

  return (
    <nav className="nav" aria-label={t("app_name")}>
      {link("/", "nav_dashboard")}
      {manager && groups && <>
        <Pick id="wells" label={t("nav_wells")} shown={shownMonth("/book/wells", groups.cur)} items={groups.wells}
          activeTo={here} openId={openId} setOpenId={setOpenId} />
        <Pick id="sac" label={t("nav_sacrifices")} shown={shownMonth("/book/sac", groups.cur)} items={groups.sac}
          activeTo={here} openId={openId} setOpenId={setOpenId} />
        <div className="nav-sec">{t("nav_contractors_by_country")}</div>
        {[...groups.byCountry.entries()].map(([country, list]) => {
          const items: Item[] = list.map((c) => ({ to: `/book/con/${c.code}`, label: c.name, dot: deeper(contractorColor(c), 0.3) }));
          const on = list.find((c) => here === `/book/con/${c.code}`);
          return <Pick key={country || "-"} id={`c-${country}`} label={countryName(country, lang)}
            shown={on ? on.name : `${list.length} ${t("n_contractors")}`} items={items} activeTo={here} openId={openId} setOpenId={setOpenId} />;
        })}
        {groups.partnerItems.length > 0 && <Pick id="partners" label={t("nav_partners")}
          shown={groups.partnerItems.find((i) => i.to === here)?.label || groups.partnerItems.map((i) => i.label).join("، ")}
          items={groups.partnerItems} activeTo={here} openId={openId} setOpenId={setOpenId} />}
        {link("/book", "nav_book")}
      </>}
      <div className="nav-sec">{t("nav_operations")}</div>
      {link("/sheet", "nav_sheet")}{link("/projects", "nav_projects")}{link("/construction", "nav_construction")}
      {link("/delivery", "nav_delivery", counts.pending_delivery_approvals)}{link("/maintenance", "nav_maintenance")}
      {link("/media", "nav_media")}{can(...EDITORS) && link("/plaque", "nav_plaque")}
      {manager && link("/review", "nav_review", counts.pending_review)}
      <div className="nav-sec">{t("nav_admin")}</div>
      {link("/contractors", manager ? "nav_contractors_manage" : "nav_contractors")}{link("/reports", "nav_reports")}
      {manager && link("/settings", "nav_settings")}
    </nav>
  );
}
