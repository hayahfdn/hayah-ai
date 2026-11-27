// «طلبات شوبيفاي» (Hayah, 27 Nov 2026): every store order as HAYAH received it, laid out like Shopify's own
// orders list: order number, date, customer, phone, country, total, payment, source, and the details on a tap
// (items with their options, and the well / sacrifice / سقيا made for each). Selling prices only; no costs.
import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { EDITORS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox } from "../ui";
import { LiveBadge, useShopifyLive } from "../shopifyLive";
import { WaPhoneIcon } from "../WaPhone";
import * as I from "../icons";

type Ref = { no: number; line: number; unit: number };
type Item = { id: number; title: string; variant: string | null; quantity: number; price: number; discount: number; kind: string; props: Record<string, string> };
type Order = {
  id: number; name: string; created_at: string | null; financial_status: string | null; cancelled: boolean; total: number; currency: string;
  customer_name: string | null; phone: string | null; country_code: string | null; source: string | null; status: string; message: string | null;
  note: string | null; items: Item[]; links: { wells: Ref[]; sacrifices: Ref[]; suqya: Ref[] };
};
type Page = { orders: Order[]; total: number; page: number; per_page: number };
const FILTERS = ["all", "open", "review", "cancelled"] as const;
const digits = (s: string | null) => (s || "").replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d))).replace(/[^\d+]/g, "");
const flag = (cc: string | null) => (cc && /^[A-Z]{2}$/i.test(cc) ? String.fromCodePoint(...[...cc.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65)) : "");

export default function ShopifyOrders() {
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const load = (mark = false) => api<Page>("/api/shopify/orders/list", { query: { q, status: filter === "all" ? "" : filter, page } })
    .then((r) => {
      setData((old) => {
        if (mark && old) { const seen = new Set(old.orders.map((o) => o.id)); setFresh(new Set(r.orders.filter((o) => !seen.has(o.id)).map((o) => o.id))); }
        return r;
      });
      setError(null);
    }).catch((e) => setError(e.message));
  useEffect(() => {
    const h = setTimeout(() => load(), q ? 300 : 0);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, filter, page]);
  const live = useShopifyLive("orders_version", () => load(true));
  if (!can(...EDITORS)) return <ErrorBox error="403" />;
  const region = (() => { try { return new Intl.DisplayNames([lang], { type: "region" }); } catch { return null; } })();
  const country = (cc: string | null) => (cc ? `${flag(cc)} ${region?.of(cc.toUpperCase()) || cc}` : "—");
  const when = (d: string | null) => (d ? new Date(d).toLocaleString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
  const money = (n: number, cur: string) => `${cur === "USD" ? "$" : cur + " "}${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const pay = (o: Order) => o.cancelled ? <span className="so-badge bad">{t("so_cancelled_b")}</span>
    : o.financial_status === "paid" || o.financial_status === "partially_refunded" ? <span className="so-badge ok">{t("so_paid")}</span>
    : o.financial_status === "refunded" || o.financial_status === "voided" ? <span className="so-badge bad">{t("so_refunded")}</span>
    : <span className="so-badge warn">{t("so_pending")}</span>;
  const made = (o: Order, line?: number) => {
    const pick = (r: Ref[]) => (line == null ? r : r.filter((x) => x.line === line));
    return <>
      {pick(o.links.wells).map((r) => <Link key={`w${r.no}`} className="so-chip well" to={`/projects/${r.no}`} onClick={(e) => e.stopPropagation()}>{t("so_well")} {r.no}</Link>)}
      {pick(o.links.sacrifices).map((r) => <Link key={`s${r.no}`} className="so-chip sac" to={`/plaque/sacrifice/${r.no}`} onClick={(e) => e.stopPropagation()}>{t("so_sac")} {r.no}</Link>)}
      {pick(o.links.suqya).map((r) => <Link key={`q${r.no}`} className="so-chip suqya" to={`/plaque/suqya/${r.no}`} onClick={(e) => e.stopPropagation()}>💧 {t("so_suqya")} {r.no}</Link>)}
    </>;
  };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;
  return <>
    <div className="topbar">
      <div><span className="muted">{t("so_sub")}</span><h1><I.ShoppingBag size={24} aria-hidden="true" style={{ verticalAlign: "-4px" }} /> {t("so_title")}</h1></div>
      <LiveBadge live={live} />
    </div>
    <div className="card so-card">
      <div className="so-head">
        <div className="tabs" role="tablist">
          {FILTERS.map((f) => <button key={f} type="button" role="tab" aria-selected={filter === f} className={filter === f ? "on" : ""}
            onClick={() => { setFilter(f); setPage(1); }}>{t("so_" + f)}</button>)}
        </div>
        <input className="so-search" placeholder={t("so_search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      </div>
      <ErrorBox error={error} />
      {!data ? <p className="muted">{t("loading")}</p> : !data.orders.length ? <p className="muted">{t("so_none")}</p> : <>
        <div className="table-wrap so-table"><table className="table">
          <thead><tr><th>{t("so_order")}</th><th>{t("so_date")}</th><th>{t("so_customer")}</th><th>{t("so_phone")}</th><th>{t("so_country")}</th>
            <th>{t("so_total")}</th><th>{t("so_payment")}</th><th>{t("so_items")}</th><th>{t("so_source")}</th><th>{t("so_made")}</th></tr></thead>
          <tbody>{data.orders.map((o) => <Fragment key={o.id}>
            <tr className={`clickable${fresh.has(o.id) ? " so-fresh" : ""}${open === o.id ? " so-open" : ""}${o.cancelled ? " so-cancelled" : ""}`} onClick={() => setOpen(open === o.id ? null : o.id)}>
              <td><b className="mono">{o.name}</b></td><td className="nowrap">{when(o.created_at)}</td><td dir="auto">{o.customer_name || "—"}</td>
              <td className="nowrap" dir="ltr">{o.phone ? <>{o.phone} <WaPhoneIcon e164={digits(o.phone)} /></> : "—"}</td>
              <td className="nowrap">{country(o.country_code)}</td><td className="num nowrap">{money(o.total, o.currency)}</td><td>{pay(o)}</td>
              <td>{o.items.reduce((a, i) => a + (i.quantity || 1), 0)}</td>
              <td className="so-src">{o.source || "—"}</td><td><div className="so-chips">{made(o)}</div></td>
            </tr>
            {open === o.id && <tr className="so-detail"><td colSpan={10}>
              <div className="so-detail-box">
                <h3>{t("so_details")} {o.name}</h3>
                {o.items.map((i) => <div key={i.id} className="so-line">
                  <div className="so-line-main">
                    <b>{i.title}</b>{i.variant && <span className="muted"> · {i.variant}</span>}
                    {Object.entries(i.props).length > 0 && <div className="so-props">{Object.entries(i.props).map(([k, v]) => <span key={k}><span className="muted">{k}:</span> {v}</span>)}</div>}
                    <div className="so-chips">{made(o, i.id)}</div>
                  </div>
                  <div className="so-line-price num">{money(i.price, o.currency)} × {i.quantity}{i.discount ? <div className="muted">−{money(i.discount, o.currency)}</div> : null}</div>
                </div>)}
                <div className="so-line so-total"><b>{t("so_total")}</b><b className="num">{money(o.total, o.currency)}</b></div>
                {o.note && <p><span className="muted">{t("so_note")}:</span> {o.note}</p>}
                {o.message && <p className="muted" style={{ fontSize: 12.5 }}>{o.message}</p>}
              </div>
            </td></tr>}
          </Fragment>)}</tbody>
        </table></div>
        <div className="so-pager">
          <span className="muted">{(data.page - 1) * data.per_page + 1}–{Math.min(data.total, data.page * data.per_page)} {t("so_of")} {data.total}</span>
          <button className="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("so_prev")}</button>
          <button className="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t("so_next")}</button>
        </div>
      </>}
    </div>
  </>;
}
