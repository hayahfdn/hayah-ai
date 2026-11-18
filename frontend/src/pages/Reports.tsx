import { useState } from "react";
import { download } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { Bars, ErrorBox, useApi } from "../ui";

export default function Reports() {
  const { t, st, num } = useI18n();
  const { can } = useAuth();
  const today = new Date().toISOString().slice(0, 10);
  const yearAgo = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
  const [range, setRange] = useState({ start: yearAgo, end: today });
  const { data, error } = useApi<any>("/api/reports/summary", range);
  return (
    <>
      <div className="topbar"><h1>{t("nav_reports")}</h1>
        <div className="toolbar" style={{ margin: 0 }}>
          <input type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} />
          <input type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} />
          {can(...MANAGERS) && <button onClick={() => download("/api/projects/export.csv", "hayah-projects.csv")}>{t("export_csv")}</button>}
        </div></div>
      <ErrorBox error={error} />
      {data && <div className="grid two">
        <div className="card"><h2>{t("orders_by_month")}</h2><Bars rows={data.orders_by_month.map((r: any) => ({ label: r.month, value: r.orders }))} /></div>
        <div className="card"><h2>{t("deliveries_by_month")}</h2><Bars rows={data.deliveries_by_month.map((r: any) => ({ label: r.month, value: r.delivered }))} /></div>
        <div className="card"><h2>{t("by_well_type")}</h2><Bars rows={data.by_well_type.map((r: any) => ({ label: r.well_type, value: r.count }))} /></div>
        <div className="card"><h2>{t("by_payment")}</h2>
          <table><thead><tr><th>{t("status")}</th><th>{t("count")}</th><th>{t("amount")}</th></tr></thead>
            <tbody>{data.by_payment_status.map((r: any) => <tr key={r.status}><td>{st(r.status)}</td><td className="num">{num(r.count)}</td><td className="num">{num(r.amount)}</td></tr>)}</tbody></table></div>
        <div className="card"><h2>{t("maint_by_problem")}</h2>
          <table><thead><tr><th>{t("problem_type")}</th><th>{t("count")}</th><th>{t("cost")}</th></tr></thead>
            <tbody>{data.maintenance_by_problem.map((r: any) => <tr key={r.problem_type}><td>{r.problem_type}</td><td className="num">{num(r.count)}</td><td className="num">{num(r.cost)}</td></tr>)}</tbody></table></div>
      </div>}
    </>
  );
}
