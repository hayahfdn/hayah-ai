// The workbook: one page per sheet of HAYAH's Excel file, with Excel-like tabs at the bottom.
//   /book                 Financial Summary
//   /book/acc/WISE        Wise bank, /book/acc/MOHAMMED, GHAZI, CLIQ (partners)
//   /book/con/PAK1        a contractor: its wells, sacrifices and payments
//   /book/wells/2026-11   that month's wells
//   /book/sac/2026-11     that month's sacrifices
import { useEffect, useMemo, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Account, Contractor, Tx } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, useApi } from "../ui";
import { useDataReload, useMoney } from "./grid";
import { contractorColor, countryName, deeper, PARTNERS } from "../look";
import Summary from "./Summary";
import WellsGrid from "./WellsGrid";
import SacrificesGrid from "./SacrificesGrid";
import TxGrid from "./TxGrid";

interface WB { accounts: Account[]; contractors: Contractor[]; months: { wells: string[]; sacrifices: string[]; current: string } }
type Tab = { key: string; label: string; group: "summary" | "acc" | "con" | "partner" | "month" | "smonth" };

const ORDER = ["PAK", "NEP", "BANG", "IND"];
const rank = (code: string) => { const i = ORDER.findIndex((p) => code.startsWith(p)); return i < 0 ? ORDER.length : i; };

export function monthLabel(m: string, lang: string) {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleDateString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { month: "short", year: "2-digit" });
}

export default function Workbook() {
  const { t, lang } = useI18n();
  const nav = useNavigate();
  const { kind, id } = useParams();
  const wb = useApi<WB>("/api/finance/workbook");
  useDataReload(wb.reload);
  const active = kind ? `${kind}/${id}` : "summary";
  const stripRef = useRef<HTMLDivElement>(null);

  const tabs = useMemo<Tab[]>(() => {
    if (!wb.data) return [];
    const { accounts, contractors, months } = wb.data;
    const banks = accounts.filter((a) => a.kind === "bank"), partners = accounts.filter((a) => a.kind === "partner");
    const cons = [...contractors].sort((a, b) => rank(a.code) - rank(b.code) || a.code.localeCompare(b.code, undefined, { numeric: true }));
    const sacCons = cons.filter((c) => c.country === "Tanzania"), wellCons = cons.filter((c) => c.country !== "Tanzania");
    return [
      { key: "summary", label: t("tab_summary"), group: "summary" },
      ...banks.map((a) => ({ key: `acc/${a.code}`, label: a.code === "WISE" ? "Wise" : a.name, group: "acc" as const })),
      ...wellCons.map((c) => ({ key: `con/${c.code}`, label: c.name, group: "con" as const })),
      ...partners.map((a) => { const pp = PARTNERS.find((x) => x.code === a.code);
        return { key: `acc/${a.code}`, label: pp ? (lang === "ar" ? pp.ar : pp.en) : a.name.replace(/\s*\(.*\)/, ""), group: "partner" as const }; }),
      ...months.wells.map((m) => ({ key: `wells/${m}`, label: monthLabel(m, lang), group: "month" as const })),
      ...sacCons.map((c) => ({ key: `con/${c.code}`, label: c.name, group: "con" as const })),
      ...months.sacrifices.map((m) => ({ key: `sac/${m}`, label: `${t("tab_smonth")} ${monthLabel(m, lang)}`, group: "smonth" as const })),
    ];
  }, [wb.data, t, lang]);

  useEffect(() => { stripRef.current?.querySelector(".on")?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [active, tabs.length]);
  const open = (key: string) => nav(key === "summary" ? "/book" : `/book/${key}`);
  const current = tabs.find((x) => x.key === active);

  return (
    <div className="book">
      <div className="topbar"><h1>{current?.label || t("nav_book")}</h1>
        {tabs.length > 0 && <select className="sheet-pick" value={current ? active : ""} onChange={(e) => open(e.target.value)} aria-label={t("open_sheet")}>
          {!current && <option value="">{t("open_sheet")}</option>}
          {tabs.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
        </select>}
      </div>
      <p className="muted book-help" style={{ marginTop: -8 }}>{t("book_help")}</p>
      <ErrorBox error={wb.error} />
      <div className="book-body">
        {active === "summary" && <Summary onOpen={open} />}
        {kind === "wells" && id && <WellsGrid key={id} month={id} height="calc(100vh - 300px)" />}
        {kind === "sac" && id && <SacrificesGrid key={id} month={id} height="calc(100vh - 300px)" />}
        {kind === "acc" && id && wb.data && <AccountSheet key={id} code={id} accounts={wb.data.accounts} />}
        {kind === "con" && id && <ContractorSheet key={id} code={id} />}
      </div>
      <nav className="sheet-tabs" ref={stripRef} aria-label={t("nav_book")}>
        {tabs.map((x) => (
          <button key={x.key} className={`g-${x.group} ${x.key === active ? "on" : ""}`} onClick={() => open(x.key)}
            aria-current={x.key === active ? "page" : undefined}>{x.label}</button>))}
      </nav>
    </div>
  );
}

function Cards({ items }: { items: [string, any, string?][] }) {
  const { t } = useI18n();
  return <div className="grid kpis" style={{ marginBottom: 12 }}>
    {items.map(([k, v, tone]) => <div key={k} className={`card kpi ${tone || ""}`}><div className="label">{t(k)}</div><div className="value">{v}</div></div>)}
  </div>;
}

function AccountSheet({ code, accounts }: { code: string; accounts: Account[] }) {
  const money = useMoney();
  const led = useApi<{ account: Account; transactions: Tx[]; totals: Record<string, any> }>(`/api/finance/accounts/${code}/ledger`);
  useDataReload(led.reload);
  if (!led.data) return <ErrorBox error={led.error} />;
  const { account: a, totals: tt } = led.data;
  const partner = a.kind === "partner";
  const cards: [string, any, string?][] = partner
    ? [["took_from_company", money(tt.took_from_company)], ["spent_on_company", money(tt.spent_on_company)], ["withdrawn", money(tt.withdrawn)],
       ["loans", money(tt.loans)], ["still_with_partner", money(tt.still_with_partner), tt.still_with_partner > 0 ? "attn" : ""]]
    : [["balance", money(tt.balance)], ["money_in", money(tt.in)], ["money_out", money(tt.out)]];
  return <>
    <Cards items={cards} />
    <TxGrid rows={led.data.transactions} accountId={a.id} showBalance={!partner} onChanged={led.reload} height="calc(100vh - 420px)"
      defaultKind={partner ? "partner_took" : "income"}
      kinds={partner ? ["partner_took", "partner_spent", "partner_withdrawal", "loan", "other"] : undefined} />
  </>;
  void accounts;
}

function ContractorSheet({ code }: { code: string }) {
  const { t, lang } = useI18n();
  const money = useMoney();
  const led = useApi<{ contractor: Contractor; payments: Tx[]; totals: Record<string, any> }>(`/api/finance/contractors/${code}/ledger`);
  const accounts = useApi<Account[]>("/api/finance/accounts");
  useDataReload(led.reload);
  if (!led.data) return <ErrorBox error={led.error} />;
  const c = led.data.contractor, tt = led.data.totals;
  return <>
    <p className="con-head"><i className="dot lg" style={{ background: deeper(contractorColor(c), 0.3), borderColor: "#fff" }} />
      <span>{c.name} · <span className="muted">{c.code}{c.country ? ` · ${countryName(c.country, lang)}` : ""}</span></span></p>
    <Cards items={[["wells", tt.wells], ["sacrifices", tt.sacrifices], ["invoiced", money(tt.invoiced)], ["paid", money(tt.paid)],
      ["owed", money(tt.owed), tt.owed > 0 ? "attn" : ""], ["pct_paid", tt.pct_paid == null ? "—" : `${tt.pct_paid}%`]]} />
    {(tt.wells > 0 || c.country !== "Tanzania") && <WellsGrid contractorId={c.id} title={t("wells")} height="50vh" />}
    {(tt.sacrifices > 0 || c.country === "Tanzania") && <div style={{ marginTop: 16 }}><SacrificesGrid contractorId={c.id} title={t("sacrifices")} height="45vh" /></div>}
    <h2 style={{ margin: "18px 0 6px" }}>{t("payments")}</h2>
    <TxGrid rows={led.data.payments} contractorId={c.id} defaultKind="contractor_payment" kinds={["contractor_payment"]}
      accounts={accounts.data || []} onChanged={led.reload} height="35vh"
      accountIdDefault={accounts.data?.find((a) => a.code === "WISE")?.id} />
  </>;
}
