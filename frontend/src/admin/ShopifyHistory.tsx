import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, toast, useApi } from "../ui";

/** Settings > Shopify > Past orders: match orders from before the start date to the workbook, then review what's left. */
export default function ShopifyHistory({ configured, onDone }: { configured: boolean; onDone: () => void }) {
  const { t, fmtDate, num, money } = useI18n();
  const { can } = useAuth();
  const admin = can("super_admin");
  const h = useApi<any>("/api/shopify/history");
  const [start, setStart] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [links, setLinks] = useState<Record<number, string>>({});
  const run = async (name: string, fn: () => Promise<any>) => {
    setBusy(name);
    try { await fn(); } catch (e: any) { toast(e.message); } finally { setBusy(null); h.reload(); onDone(); }
  };
  const importPast = () => run("import", async () => {
    const r = await api("/api/shopify/history", { body: { start: start || null } });
    toast(t("hist_done").replace("{n}", r.orders).replace("{m}", r.sure + r.likely + r.guess).replace("{x}", r.none));
  });
  const add = (order?: string) => run("add" + (order || ""), async () => {
    if (!order && !window.confirm(t("hist_add_all_confirm"))) return;
    const r = await api("/api/shopify/history/add", { body: { order: order || null } });
    toast(`${t("hist_added")}: ${r.created.join(", ") || "—"}`);
  });
  const link = (itemId: number) => run("link" + itemId, async () => {
    await api("/api/shopify/history/link", { body: { item_id: itemId, number: Number(links[itemId]) } });
    toast(t("saved"));
  });
  const d = h.data;
  const last = d?.last_run;
  const u = d?.units || {};
  const nNone = d?.review?.reduce((a: number, o: any) => a + o.items.filter((i: any) => i.match === "none").length, 0) || 0;
  return <div className="card"><h2>{t("hist_title")}</h2>
    <ErrorBox error={h.error} />
    <p className="muted">{t("hist_help").replace("{d}", d?.before ? fmtDate(d.before) : "—")}</p>
    {last && !last.all_orders_scope && <div className="banner warn">{t("hist_scope")}</div>}
    {last && <p>
      <span className="badge ok">{t("hist_sure")}: {(u.sure || 0) + (u.likely || 0)}</span>{" "}
      <span className="badge">{t("hist_created")}: {u.created || 0}</span>{" "}
      <span className="badge warn">{t("hist_guess")}: {u.guess || 0}</span>{" "}
      <span className="badge warn">{t("hist_none")}: {u.none || 0}</span>
      <span className="muted"> · {t("shop_last_sync")}: {fmtDate(last.at)} · {last.first_order}–{last.last_order}</span>
    </p>}
    {admin && <div className="actions">
      <label className="muted">{t("hist_from")} <input type="date" value={start} onChange={(e) => setStart(e.target.value)} style={{ width: "auto" }} /></label>
      <button className="primary" disabled={!!busy || !configured} onClick={importPast}>{busy === "import" ? t("loading") : t("hist_run")}</button>
    </div>}
    {!!d?.review?.length && <>
      <h3>{t("hist_review")}</h3>
      <div className="actions">
        {nNone > 0 && <button disabled={!!busy} onClick={() => add()}>{t("hist_add_all").replace("{n}", String(nNone))}</button>}
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>{t("shop_order")}</th><th>{t("date")}</th><th>{t("customer_name")}</th><th>{t("hist_line")}</th><th>{t("shop_result")}</th><th></th></tr></thead>
        <tbody>{d.review.flatMap((o: any) => o.items.map((i: any, k: number) => <tr key={i.id}>
          {k === 0 && <><td className="mono" rowSpan={o.items.length}>{o.name}</td>
            <td rowSpan={o.items.length}>{fmtDate(o.created_at)}</td>
            <td rowSpan={o.items.length}>{o.customer_name || "—"}</td></>}
          <td className="wrap">{i.title} · {o.currency === "USD" || !o.currency ? money(i.amount) : `${num(i.amount)} ${o.currency}`}
            {i.dedication && <div className="muted" style={{ fontSize: 12 }}>{t("dedication")}: {i.dedication}</div>}</td>
          <td>{i.match === "none" ? <span className="badge warn">{t("hist_none")}</span>
            : <span className={`badge ${i.match === "guess" ? "warn" : "ok"}`}>
              {t("hist_" + i.match)} → {i.kind === "well" ? `${t("well_id")} ${i.well_id}` : `${t("sacrifice_no")} ${i.sacrifice_no}`}</span>}</td>
          <td style={{ whiteSpace: "nowrap" }}>{i.match !== "created" && <>
            <input type="number" min={1} placeholder={i.kind === "well" ? t("well_id") : t("sacrifice_no")} value={links[i.id] || ""}
              onChange={(e) => setLinks({ ...links, [i.id]: e.target.value })} style={{ width: 110 }} />
            <button disabled={!!busy || !links[i.id]} onClick={() => link(i.id)}>{t("hist_link")}</button></>}
            {k === 0 && o.items.some((x: any) => x.match === "none") &&
              <button disabled={!!busy} onClick={() => add(o.name)}>{t("hist_add")}</button>}</td>
        </tr>))}</tbody>
      </table></div></>}
  </div>;
}
