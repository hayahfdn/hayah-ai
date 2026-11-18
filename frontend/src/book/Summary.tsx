// Financial Summary: the same sections as the "Financial Summary" sheet, computed live.
import { Fragment, useState } from "react";
import { useI18n } from "../i18n";
import { ErrorBox, useApi } from "../ui";
import { useDataReload, useMoney } from "./grid";

type Row = Record<string, any>;
interface S {
  headline: Row; by_month: Row[]; contractors: Row[]; ads_by_channel: Row[]; opex_by_category: Row[]; accounts: Row[];
  loans: Row[]; same_day: { this_month: Row; last_month: Row }; has_samples: boolean; includes_samples: boolean;
}

export default function Summary({ onOpen }: { onOpen: (key: string) => void }) {
  const { t } = useI18n();
  const money = useMoney();
  const [samples, setSamples] = useState(true);
  const s = useApi<S>("/api/finance/summary", { include_samples: samples });
  useDataReload(s.reload);
  if (!s.data) return <ErrorBox error={s.error} />;
  const h = s.data.headline;
  const pct = (v: any) => (v == null ? "—" : `${v}%`);
  const kpis: [string, any, string?][] = [
    ["total_sales", money(h.total_sales)], ["cost", money(h.cost)], ["gross_profit", money(h.gross_profit)],
    ["margin", pct(h.margin_pct)], ["ad_spend", money(h.ad_spend)], ["operating_expenses", money(h.operating_expenses)],
    ["pure_profit", money(h.pure_profit), h.pure_profit < 0 ? "bad" : "ok"], ["cash_on_hand", money(h.cash_on_hand)],
    ["owed_to_contractors", money(h.owed_to_contractors), h.owed_to_contractors > 0 ? "attn" : ""],
  ];
  const byCountry = s.data.contractors.reduce<Record<string, Row[]>>((a, r) => ((a[r.country] ||= []).push(r), a), {});
  const maxMonth = Math.max(1, ...s.data.by_month.map((m) => m.sales));
  const sd = s.data.same_day;

  return (
    <div className="fs">
      <div className="toolbar" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>{t("fs_headline")}</h2>
        {s.data.has_samples && <label className="muted" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={samples} onChange={(e) => setSamples(e.target.checked)} style={{ minHeight: 0 }} />{t("include_samples")}
        </label>}
      </div>
      {s.data.includes_samples && s.data.has_samples && <div className="banner">{t("samples_note")}</div>}
      <div className="grid kpis">
        {kpis.map(([k, v, tone]) => <div key={k} className={`card kpi ${tone === "attn" ? "attn" : ""}`}>
          <div className="label">{t(k)}</div><div className={`value ${tone === "bad" ? "neg" : ""}`}>{v}</div></div>)}
      </div>

      <div className="grid two" style={{ marginTop: 14 }}>
        <section className="card">
          <h3>{t("fs_chart")}</h3>
          <div className="mchart" role="img" aria-label={t("fs_chart")}>
            {s.data.by_month.map((m) => (
              <div key={m.month} className="mcol" title={`${m.month}: ${money(m.sales)}`}>
                <div className="mstack" style={{ height: `${(100 * m.sales) / maxMonth}%` }}>
                  <i className="w" style={{ flex: m.well_sales || 0 }} /><i className="s" style={{ flex: m.sac_sales || 0 }} />
                </div>
                <span>{m.month.slice(2)}</span>
              </div>))}
          </div>
          <div className="legend"><span><i className="w" />{t("well_sales")}</span><span><i className="s" />{t("sac_sales")}</span></div>
        </section>
        <section className="card">
          <h3>{t("fs_same_day")}</h3>
          <table><thead><tr><th></th><th>{t("this_month")}</th><th>{t("last_month")}</th></tr></thead>
            <tbody>{(["wells", "sacrifices", "sales", "profit"] as const).map((k) => (
              <tr key={k}><td>{t(k === "sales" ? "total_sales" : k)}</td>
                <td className="num">{k === "wells" || k === "sacrifices" ? sd.this_month[k] : money(sd.this_month[k])}</td>
                <td className="num">{k === "wells" || k === "sacrifices" ? sd.last_month[k] : money(sd.last_month[k])}</td></tr>))}
            </tbody></table>
          <p className="muted" dir="ltr" style={{ margin: "8px 0 0", textAlign: "end" }}>{sd.this_month.from} → {sd.this_month.to} · {sd.last_month.from} → {sd.last_month.to}</p>
        </section>
      </div>

      <section className="card" style={{ marginTop: 14 }}>
        <h3>{t("fs_by_month")}</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("month")}</th><th>{t("wells")}</th><th>{t("well_sales")}</th><th>{t("profit")}</th><th>{t("sacrifices")}</th>
            <th>{t("sac_sales")}</th><th>{t("profit")}</th><th>{t("gross_profit")}</th><th>{t("ads")}</th><th>{t("opex")}</th><th>{t("pure_profit")}</th></tr></thead>
          <tbody>{s.data.by_month.map((m) => (
            <tr key={m.month}>
              <td><button className="linkish" onClick={() => onOpen(`wells/${m.month}`)}>{m.month}</button></td>
              <td className="num">{m.wells}</td><td className="num">{money(m.well_sales)}</td><td className="num">{money(m.well_profit)}</td>
              <td className="num"><button className="linkish" onClick={() => onOpen(`sac/${m.month}`)}>{m.sacrifices}</button></td>
              <td className="num">{money(m.sac_sales)}</td><td className="num">{money(m.sac_profit)}</td>
              <td className="num">{money(m.gross_profit)}</td><td className="num">{money(m.ads)}</td><td className="num">{money(m.opex)}</td>
              <td className={`num ${m.pure_profit < 0 ? "neg" : ""}`}><b>{money(m.pure_profit)}</b></td></tr>))}
          </tbody>
          <tfoot><tr className="total-row"><td>{t("total_row")}</td><td className="num">{h.wells}</td><td colSpan={2} /><td className="num">{h.sacrifices}</td>
            <td colSpan={2} /><td className="num">{money(h.gross_profit)}</td><td className="num">{money(h.ad_spend)}</td>
            <td className="num">{money(h.operating_expenses)}</td><td className="num"><b>{money(h.pure_profit)}</b></td></tr></tfoot>
        </table></div>
      </section>

      <section className="card" style={{ marginTop: 14 }}>
        <h3>{t("fs_contractors")}</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("contractor")}</th><th>{t("invoiced")}</th><th>{t("paid")}</th><th>{t("owed")}</th><th>{t("pct_paid")}</th></tr></thead>
          <tbody>{Object.entries(byCountry).map(([country, rows]) => (
            <Fragment key={country}>
              {rows.map((r) => (
                <tr key={r.id}><td><button className="linkish" onClick={() => onOpen(`con/${r.code}`)}>{r.name}</button> <span className="muted mono">{r.code}</span></td>
                  <td className="num">{money(r.invoiced)}</td><td className="num">{money(r.paid)}</td>
                  <td className={`num ${r.owed > 0 ? "warn-t" : ""}`}>{money(r.owed)}</td><td className="num">{pct(r.pct_paid)}</td></tr>))}
              <tr className="subtotal"><td>{t("subtotal")} · {country}</td>
                <td className="num">{money(rows.reduce((a, r) => a + r.invoiced, 0))}</td><td className="num">{money(rows.reduce((a, r) => a + r.paid, 0))}</td>
                <td className="num">{money(rows.reduce((a, r) => a + r.owed, 0))}</td><td /></tr>
            </Fragment>))}
          </tbody></table></div>
      </section>

      <div className="grid two" style={{ marginTop: 14 }}>
        <section className="card"><h3>{t("fs_ads")}</h3><SimpleTable rows={s.data.ads_by_channel} k="channel" money={money} total={h.ad_spend} t={t} /></section>
        <section className="card"><h3>{t("fs_opex")}</h3><SimpleTable rows={s.data.opex_by_category} k="category" money={money} total={h.operating_expenses} t={t} /></section>
      </div>

      <section className="card" style={{ marginTop: 14 }}>
        <h3>{t("fs_accounts")}</h3>
        <div className="table-wrap"><table>
          <thead><tr><th></th><th>{t("balance")}</th><th>{t("money_in")}</th><th>{t("money_out")}</th><th>{t("took_from_company")}</th>
            <th>{t("spent_on_company")}</th><th>{t("withdrawn")}</th><th>{t("loans")}</th></tr></thead>
          <tbody>{s.data.accounts.map((a) => (
            <tr key={a.id}><td><button className="linkish" onClick={() => onOpen(`acc/${a.code}`)}>{a.name}</button></td>
              <td className="num"><b>{money(a.balance)}</b></td><td className="num">{money(a.in)}</td><td className="num">{money(a.out)}</td>
              <td className="num">{a.kind === "partner" ? money(a.took_from_company) : ""}</td><td className="num">{a.kind === "partner" ? money(a.spent_on_company) : ""}</td>
              <td className="num">{a.kind === "partner" ? money(a.withdrawn) : ""}</td><td className="num">{a.kind === "partner" ? money(a.loans) : ""}</td></tr>))}
          </tbody></table></div>
      </section>
    </div>
  );
}

function SimpleTable({ rows, k, money, total, t }: { rows: Row[]; k: string; money: (v: any) => string; total: number; t: (s: string) => string }) {
  if (!rows.length) return <div className="empty">{t("no_items")}</div>;
  return <table><tbody>{rows.map((r) => <tr key={r[k]}><td>{r[k]}</td><td className="num">{money(r.amount)}</td>
    <td className="num muted">{total ? Math.round((100 * r.amount) / total) : 0}%</td></tr>)}</tbody>
    <tfoot><tr className="total-row"><td>{t("total_row")}</td><td className="num">{money(total)}</td><td /></tr></tfoot></table>;
}
