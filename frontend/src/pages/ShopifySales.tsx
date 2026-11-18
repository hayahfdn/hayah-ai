import { useI18n } from "../i18n";
import { Bars, useApi } from "../ui";

/** Reports card: Shopify sales (selling price only, no costs). */
export default function ShopifySales({ start, end }: { start: string; end: string }) {
  const { t, num } = useI18n();
  const { data } = useApi<any>("/api/shopify/summary", { start, end });
  if (!data || (!data.orders && !data.by_month.length)) return null;
  return <>
    <div className="card"><h2>{t("shop_sales")}</h2>
      <p><b className="num" style={{ fontSize: 22 }}>${num(data.total_amount)}</b> <span className="muted">· {t("shop_sales_orders")}: {num(data.orders)}</span></p>
      <div className="table-wrap"><table><thead><tr><th>{t("month")}</th><th>{t("shop_sales_wells")}</th><th>{t("amount")}</th><th>{t("shop_sales_sacrifices")}</th><th>{t("amount")}</th></tr></thead>
        <tbody>{data.by_month.map((r: any) => <tr key={r.month}><td className="mono">{r.month}</td><td className="num">{num(r.wells)}</td>
          <td className="num">{num(r.wells_amount)}</td><td className="num">{num(r.sacrifices)}</td><td className="num">{num(r.sacrifices_amount)}</td></tr>)}</tbody></table></div></div>
    <div className="card"><h2>{t("shop_by_source")}</h2><Bars rows={data.by_source.map((r: any) => ({ label: r.source, value: r.amount }))} /></div>
  </>;
}
