// The workbook: one page per sheet of HAYAH's Excel file. The side menu opens each page
// (months, contractors by country and partners sit in drop-downs there).
//   /book                 Financial Summary
//   /book/acc/WISE        Wise bank, /book/acc/MOHAMMED, GHAZI, CLIQ (partners)
//   /book/con/PAK1        a contractor: its wells, sacrifices and payments
//   /book/wells/2026-11   that month's wells
//   /book/sac/2026-11     that month's sacrifices
import { useNavigate, useParams } from "react-router-dom";
import { Account, Contractor, Tx } from "../api";
import { useI18n } from "../i18n";
import { PARTNERS } from "../i18n-ui";
import { countryLabel, monthLabel, MonthSwitcher, useNav } from "../nav";
import { ErrorBox, useApi } from "../ui";
import { useDataReload, useMoney } from "./grid";
import Summary from "./Summary";
import WellsGrid from "./WellsGrid";
import SacrificesGrid from "./SacrificesGrid";
import TxGrid from "./TxGrid";

export { monthLabel };

export default function Workbook() {
  const { t, lang } = useI18n();
  const go = useNavigate();
  const { kind, id } = useParams();
  const nav = useNav();
  const accounts = useApi<Account[]>("/api/finance/accounts");
  useDataReload(accounts.reload);
  const open = (key: string) => go(key === "summary" ? "/book" : `/book/${key}`);
  const con = kind === "con" ? nav?.contractors.find((c) => c.code === id) : undefined;
  const partner = kind === "acc" ? PARTNERS.find((p) => p.code === id) : undefined;
  const acc = kind === "acc" ? accounts.data?.find((a) => a.code === id) : undefined;

  let over = t("nav_book"), title = t("tab_summary");
  if (kind === "wells" && id) { over = t("nav_wells"); title = monthLabel(id, lang); }
  else if (kind === "sac" && id) { over = t("nav_sacrifices"); title = monthLabel(id, lang); }
  else if (kind === "con" && id) { over = `${t("contractor_page")}${con?.country ? " · " + countryLabel(con.country, lang) : ""}`; title = con?.name || id; }
  else if (kind === "acc" && id) { over = partner ? t("nav_people") : t("account"); title = partner ? (lang === "ar" ? partner.ar : partner.en) : id === "WISE" ? "Wise" : acc?.name || id; }

  return (
    <div className="book">
      <div className="topbar">
        <div><span className="muted">{over}</span>
          <h1>{con?.color && <span className="swatch lg" style={{ background: con.color }} aria-hidden="true" />} {title}
            {con && <span className="muted mono" style={{ fontSize: 15 }}> {con.code}</span>}</h1></div>
        {(kind === "wells" || kind === "sac") && id && <MonthSwitcher month={id} kind={kind} />}
      </div>
      <ErrorBox error={accounts.error} />
      <div className="book-body">
        {!kind && <Summary onOpen={open} />}
        {kind === "wells" && id && <WellsGrid key={id} month={id} height="calc(100vh - 250px)" />}
        {kind === "sac" && id && <SacrificesGrid key={id} month={id} height="calc(100vh - 250px)" />}
        {kind === "acc" && id && <AccountSheet key={id} code={id} />}
        {kind === "con" && id && <ContractorSheet key={id} code={id} />}
      </div>
    </div>
  );
}

function Cards({ items }: { items: [string, any, string?][] }) {
  const { t } = useI18n();
  return <div className="grid kpis" style={{ marginBottom: 12 }}>
    {items.map(([k, v, tone]) => <div key={k} className={`card kpi ${tone || ""}`}><div className="label">{t(k)}</div><div className="value">{v}</div></div>)}
  </div>;
}

function AccountSheet({ code }: { code: string }) {
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
}

function ContractorSheet({ code }: { code: string }) {
  const { t } = useI18n();
  const money = useMoney();
  const led = useApi<{ contractor: Contractor; payments: Tx[]; totals: Record<string, any> }>(`/api/finance/contractors/${code}/ledger`);
  const accounts = useApi<Account[]>("/api/finance/accounts");
  useDataReload(led.reload);
  if (!led.data) return <ErrorBox error={led.error} />;
  const c = led.data.contractor, tt = led.data.totals;
  return <>
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
