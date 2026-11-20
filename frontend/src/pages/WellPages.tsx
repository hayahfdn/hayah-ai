// Month and contractor pages for people who do not see the finance workbook (Team members).
// Managers open the same pages inside the workbook, with money totals and payments.
import { useParams } from "react-router-dom";
import { Contractor } from "../api";
import { useI18n } from "../i18n";
import { countryLabel, monthLabel, MonthSwitcher } from "../nav";
import { ErrorBox, useApi } from "../ui";
import WellsGrid from "../book/WellsGrid";
import SacrificesGrid from "../book/SacrificesGrid";
import { EDITORS, useAuth } from "../App";

/** A month of sacrifices for Employees: every detail and the selling price, no cost or profit. */
export function MonthSacrifices() {
  const { month = "" } = useParams();
  const { t, lang } = useI18n();
  return (
    <>
      <div className="topbar">
        <div><span className="muted">{t("nav_sacrifices")}</span><h1>{monthLabel(month, lang)}</h1></div>
        <MonthSwitcher month={month} kind="sac" />
      </div>
      <SacrificesGrid key={month} month={month} height="calc(100vh - 250px)" />
    </>
  );
}

export function MonthWells() {
  const { month = "" } = useParams();
  const { t, lang } = useI18n();
  return (
    <>
      <div className="topbar">
        <div><span className="muted">{t("nav_wells")}</span><h1>{monthLabel(month, lang)}</h1></div>
        <MonthSwitcher month={month} kind="wells" />
      </div>
      <WellsGrid key={month} month={month} height="calc(100vh - 250px)" />
    </>
  );
}

export function ContractorWells() {
  const { code = "" } = useParams();
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const list = useApi<Contractor[]>("/api/contractors");
  const c = list.data?.find((x) => x.code === code);
  if (list.data && !c) return <ErrorBox error={`${t("contractor")} ${code}?`} />;
  if (!c) return <ErrorBox error={list.error} />;
  return (
    <>
      <div className="topbar">
        <div><span className="muted">{t("contractor_page")} · {countryLabel(c.country || "", lang)}</span>
          <h1><span className="swatch lg" style={{ background: c.color || undefined }} aria-hidden="true" /> {c.name} <span className="muted mono">{c.code}</span></h1></div>
      </div>
      <p className="muted" style={{ marginTop: -8 }}>{t("contractor_wells_help")}</p>
      <WellsGrid key={c.id} contractorId={c.id} height={can(...EDITORS) ? "55vh" : "calc(100vh - 250px)"} />
      {can(...EDITORS) && <div style={{ marginTop: 16 }}><SacrificesGrid key={`s${c.id}`} contractorId={c.id} title={t("sacrifices")} height="45vh" /></div>}
    </>
  );
}
