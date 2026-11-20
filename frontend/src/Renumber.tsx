// Changing a project / sacrifice number, and the order window that lists every sacrifice of one order.
import { useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { api } from "./api";
import { useI18n } from "./i18n";
import { ErrorBox, Field, Modal, toast, useApi } from "./ui";

export function ChangeNumber({ kind, current, onClose, onDone }: { kind: "project" | "sacrifice"; current: number;
  onClose: () => void; onDone: (newNo: number, result: any) => void }) {
  const { t } = useI18n();
  const [v, setV] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const path = kind === "project" ? `/api/projects/${current}/number` : `/api/sacrifices/${current}/number`;
      const r = await api<any>(path, { method: "PATCH", body: { new_number: Number(v) } });
      const image = kind === "project" ? r.plaque_image_old_number : (r.plaque_image_old_number || []).length > 0;
      toast(image ? `${t("num_changed")} · ${t("num_plaque_old")}` : t("num_changed"));
      onDone(Number(v), r);
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return <Modal title={`${t("num_change")} · ${current}`} onClose={onClose}><form onSubmit={save}>
    <p className="muted">{t(kind === "project" ? "num_help_project" : "num_help_sacrifice")}</p>
    <div className="form-grid">
      <Field label={t("num_current")}><input value={current} disabled className="mono" /></Field>
      <Field label={t("num_new")}><input inputMode="numeric" className="mono" autoFocus value={v} onChange={(e) => setV(e.target.value.replace(/\D/g, ""))} /></Field>
    </div>
    <ErrorBox error={err} />
    <div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button>
      <button className="primary" disabled={!v || Number(v) === current || busy}>{t("save")}</button></div>
  </form></Modal>;
}

type OrderView = { order: string; shopify: null | { name: string; created_at: string | null; customer_name: string | null; total: string | null; currency: string; cancelled: boolean };
  sacrifices: { id: number; sacrifice_no: number; donor_name: string | null; animal_type: string | null; order_date: string | null; sale_price: string | null; parent_well_id: number | null }[];
  wells: { well_id: number; customer_name: string | null; well_type: string | null; country: string | null }[] };

export function OrderChip({ order }: { order: string | null }) {
  const [open, setOpen] = useState(false);
  if (!order) return null;
  return <>
    <button className="sm link-btn mono" onClick={(e) => { e.stopPropagation(); setOpen(true); }} onDoubleClick={(e) => e.stopPropagation()}>{order}</button>
    {open && createPortal(<div onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}><OrderModal order={order} onClose={() => setOpen(false)} /></div>, document.body)}
  </>;
}

export function OrderModal({ order, onClose }: { order: string; onClose: () => void }) {
  const { t, fmtDate, num, money } = useI18n();
  const v = useApi<OrderView>(`/api/sacrifices/orders/${encodeURIComponent(order.replace(/\D/g, ""))}`);
  const d = v.data;
  return <Modal title={`${t("order_no")} ${order}`} onClose={onClose}>
    <ErrorBox error={v.error} />
    {!d ? <p className="muted">{t("loading")}</p> : <>
      {d.shopify && <p className="muted">{t("order_shopify")} <b className="mono">{d.shopify.name}</b>
        {d.shopify.customer_name && <> · {d.shopify.customer_name}</>}{d.shopify.created_at && <> · {fmtDate(d.shopify.created_at)}</>}
        {d.shopify.total && <> · {t("order_total")} {d.shopify.currency === "USD" || !d.shopify.currency ? money(d.shopify.total) : `${num(d.shopify.total)} ${d.shopify.currency}`}</>}
        {d.shopify.cancelled && <span className="badge bad"> {t("order_cancelled")}</span>}</p>}
      <h3>{t("order_sacrifices")} ({d.sacrifices.length})</h3>
      {d.sacrifices.length ? <div className="table-wrap"><table><thead><tr><th>{t("sacrifice_no")}</th><th>{t("donor_name")}</th><th>{t("animal_type")}</th>
        <th>{t("order_date")}</th><th>{t("sale_price")}</th><th>{t("parent_well")}</th></tr></thead>
        <tbody>{d.sacrifices.map((s) => <tr key={s.id}><td className="mono"><Link to={`/plaque/sacrifice/${s.sacrifice_no}`}>{s.sacrifice_no}</Link></td>
          <td>{s.donor_name || "—"}</td><td>{s.animal_type || "—"}</td><td>{fmtDate(s.order_date)}</td><td className="num">{money(s.sale_price)}</td>
          <td>{s.parent_well_id ? <Link className="mono" to={`/projects/${s.parent_well_id}`}>{s.parent_well_id}</Link> : "—"}</td></tr>)}</tbody></table></div>
        : <p className="muted">{t("order_none")}</p>}
      {!!d.wells.length && <><h3>{t("order_wells")} ({d.wells.length})</h3>
        <ul>{d.wells.map((w) => <li key={w.well_id}><Link className="mono" to={`/projects/${w.well_id}`}>{w.well_id}</Link> · {w.customer_name || "—"} · {w.well_type || "—"}</li>)}</ul></>}
    </>}
  </Modal>;
}
