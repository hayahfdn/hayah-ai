// Excel-style sacrifices sheet (one per month, and inside each contractor tab).
import OpenIcon from "../OpenIcon";
import { useCallback, useMemo, useState } from "react";
import type { CellValueChangedEvent, ColDef } from "ag-grid-community";
import { api, Contractor, dataChanged, Sacrifice } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, Field, Modal, toast, useApi } from "../ui";
import { dateCol, HayahGrid, moneyCol, n, newestFirst, sum, useDataReload, useMoney } from "./grid";
import { Link, useNavigate } from "react-router-dom";
import { useIsMobile } from "../nav";
import { AddonPicker, splitAddons } from "../AddonPicker";
import { ChangeNumber, OrderChip } from "../Renumber";

export default function SacrificesGrid({ month, contractorId, height, title }: { month?: string; contractorId?: number; height?: string; title?: string }) {
  const { t, lang } = useI18n();
  const money = useMoney();
  const data = useApi<Sacrifice[]>("/api/sacrifices", { month, contractor_id: contractorId });
  const contractors = useApi<Contractor[]>("/api/contractors");
  const lists = useApi<Record<string, string[]>>("/api/settings/lists");
  useDataReload(data.reload);
  const [saving, setSaving] = useState(0);
  const [adding, setAdding] = useState(false);
  const rows = data.data || [];
  const codeById = useMemo(() => Object.fromEntries((contractors.data || []).map((c) => [c.id, c.code])), [contractors.data]);
  const colorById = useMemo(() => Object.fromEntries((contractors.data || []).map((c) => [c.id, c.color || ""])), [contractors.data]);
  const mobile = useIsMobile();
  const [view, setView] = useState<"cards" | "table">("cards");
  const [editing, setEditing] = useState<Sacrifice | null>(null);
  const cards = mobile && view === "cards";

  const cols = useMemo<ColDef<Sacrifice>[]>(() => {
    const col = (field: keyof Sacrifice, extra: Partial<ColDef<Sacrifice>> = {}): ColDef<Sacrifice> => ({
      field, headerName: t(field as string), editable: (p) => !p.node.isRowPinned(), ...extra });
    return [
      col("sacrifice_no", { editable: false, pinned: lang === "ar" ? "right" : "left", width: 95, sort: "desc", sortIndex: 1, cellClass: "well-no",
        cellRenderer: (p: any) => (p.node.isRowPinned() || !p.data ? p.valueFormatted : <span className="no-cell">{p.value}<OpenIcon kind="sacrifice" no={p.value} /></span>),
        filter: "agNumberColumnFilter", valueFormatter: (p) => (p.node?.isRowPinned() ? t("total_row") : String(p.value ?? "")) }),
      { colId: "plaque", headerName: t("plaque"), pinned: lang === "ar" ? "right" : "left", width: 96, editable: false, sortable: false, filter: false,
        cellRenderer: (p: any) => (p.node.isRowPinned() || !p.data ? null
          : <Link className="plaque-chip new" to={`/plaque/sacrifice/${p.data.sacrifice_no}`} onDoubleClick={(e) => e.stopPropagation()}>＋ {t("plaque")}</Link>) },
      col("order_date", { ...dateCol, sort: "desc", sortIndex: 0 }), col("donor_name", { width: 170, cellClass: "strong" }), col("delivery_date", dateCol),
      col("contractor_id", { headerName: t("contractor"), width: 105, cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: [null, ...(contractors.data || []).map((c) => c.id)] },
        valueFormatter: (p) => (p.node?.isRowPinned() ? "" : p.value ? codeById[p.value] || String(p.value) : "—"),
        filterValueGetter: (p) => (p.data?.contractor_id ? codeById[p.data.contractor_id] : "") }),
      col("animal_type", { width: 110, cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["", ...(lists.data?.animal_types || [])] } }),
      moneyCol<Sacrifice>("cost", t("cost"), true, money), moneyCol<Sacrifice>("sale_price", t("sale_price"), true, money),
      { colId: "profit", headerName: t("profit"), editable: false, width: 100, cellClass: "num locked",
        valueGetter: (p) => (p.data?.sale_price == null && p.data?.cost == null ? null : n(p.data?.sale_price) - n(p.data?.cost)),
        valueFormatter: (p) => money(p.value) },
      col("payment_method", { width: 120 }), col("extras", { headerName: t("addons"), width: 130, tooltipValueGetter: (p) => p.value || null }),
      { colId: "parent_well_id", headerName: t("parent_well"), editable: false, width: 110, valueGetter: (p) => p.data?.parent_well_id ?? null,
        cellRenderer: (p: any) => (p.value ? <Link to={`/projects/${p.value}`} className="mono">{p.value}</Link> : null) }, col("sales_source", { width: 120, valueGetter: (p) => p.data?.source_group ?? p.data?.sales_source,
        tooltipValueGetter: (p) => (p.data?.sales_source && p.data.sales_source !== p.data.source_group ? `${t("src_original")}: ${p.data.sales_source}` : null),
        cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["", ...(lists.data?.sales_sources || [])] } }),
      col("shopify_order", { headerName: t("order_no"), width: 110, cellRenderer: (p: any) => (p.node.isRowPinned() || !p.data ? null : <OrderChip order={p.value} />) }), col("intention", { width: 130 }),
      col("dedication", { width: 200, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
      col("notes", { width: 220, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
    ];
  }, [t, lang, contractors.data, codeById, lists.data, money]);

  const totals = useMemo(() => [{ id: -1, donor_name: `${rows.length} ${t("sacrifices")}`,
    cost: String(sum(rows, (r) => r.cost)), sale_price: String(sum(rows, (r) => r.sale_price)) } as Partial<Sacrifice>], [rows, t]);

  const onEdit = useCallback(async (e: CellValueChangedEvent<Sacrifice>) => {
    const field = e.colDef.field as string;
    if (!e.data) return;
    let value: any = e.newValue === "" ? null : e.newValue;
    if ((field === "cost" || field === "sale_price") && value != null) value = Number(value).toFixed(2);
    setSaving((x) => x + 1);
    try {
      const updated = await api<Sacrifice>(`/api/sacrifices/${e.data.sacrifice_no}`, { method: "PATCH", body: { [field]: value, expected_version: e.data.version } });
      data.setData((d) => d && d.map((r) => (r.id === updated.id ? updated : r)));
      if (["sale_price", "cost", "contractor_id", "order_date"].includes(field)) dataChanged();
      e.api.flashCells({ rowNodes: [e.node] });
    } catch (err: any) {
      e.node.setData({ ...e.data, [field]: e.oldValue == null ? null : (field === "cost" || field === "sale_price") ? String(e.oldValue) : e.oldValue });
      toast(`${e.data.sacrifice_no}: ${err.message}`);
      if (err.status === 409) data.reload();
    } finally { setSaving((x) => x - 1); }
  }, [data]);

  return (
    <>
      <div className="toolbar">
        {title && <h2 style={{ margin: 0, marginInlineEnd: 8 }}>{title}</h2>}
        {mobile && <div className="seg" role="group">
          <button className={view === "cards" ? "on" : ""} onClick={() => setView("cards")}>{t("view_cards")}</button>
          <button className={view === "table" ? "on" : ""} onClick={() => setView("table")}>{t("view_table")}</button>
        </div>}
        <span className="muted save-state" aria-live="polite">{saving ? t("saving") : t("all_saved")}</span>
        <button className="primary" onClick={() => setAdding(true)}>{t("add_row")}</button>
      </div>
      <ErrorBox error={data.error} />
      {cards ? <SacCards rows={rows} colorById={colorById} codeById={codeById} onEdit={setEditing} />
        : <HayahGrid<Sacrifice> rows={rows} cols={cols} totals={totals} onEdit={onEdit} height={height} rowId={(r) => String(r.id)}
        rowStyle={(p) => (p.data?.contractor_id && colorById[p.data.contractor_id] ? { background: colorById[p.data.contractor_id] } : undefined)}
        rowClass={(p) => (p.data?.delivery_date ? "row-done" : "row-wait")} />}
      {editing && <SacrificeForm s={editing} contractors={contractors.data || []} animals={lists.data?.animal_types || []}
        addons={lists.data?.sacrifice_addons || ["إطعام"]}
        onClose={() => setEditing(null)} onSaved={(u) => { setEditing(null); data.setData((d) => d && d.map((r) => (r.id === u.id ? u : r))); dataChanged(); }} />}
      {adding && <NewSacrifice month={month} contractorId={contractorId} animals={lists.data?.animal_types || []}
        addons={lists.data?.sacrifice_addons || ["إطعام"]} onClose={() => setAdding(false)}
        onSaved={() => { setAdding(false); data.reload(); dataChanged(); }} />}
    </>
  );
}

function NewSacrifice({ month, contractorId, animals, addons, onClose, onSaved }: { month?: string; contractorId?: number; animals: string[];
  addons: string[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const next = useApi<{ suggested_next: number }>("/api/sacrifices/next-number");
  const [no, setNo] = useState("");
  const [qty, setQty] = useState("1");
  const [f, setF] = useState<{ donor_name: string; animal_type: string; sale_price: string; extras: string | null; dedication: string; shopify_order: string }>(
    { donor_name: "", animal_type: "", sale_price: "", extras: null, dedication: "", shopify_order: "" });
  const [err, setErr] = useState<string | null>(null);
  const today = new Date().toISOString().slice(0, 10);
  const orderDate = month && !today.startsWith(month) ? `${month}-01` : today;
  const count = Math.max(1, Math.min(50, Number(qty) || 1));
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const fields = { order_date: orderDate, contractor_id: contractorId ?? null,
      donor_name: f.donor_name.trim() || null, animal_type: f.animal_type || null, extras: f.extras,
      shopify_order: f.shopify_order.trim() || null,
      sale_price: f.sale_price ? Number(f.sale_price).toFixed(2) : null, dedication: f.dedication.trim() || null };
    try {
      if (no && count === 1) await api("/api/sacrifices", { body: { ...fields, sacrifice_no: Number(no) } });
      else {
        const made = await api<Sacrifice[]>("/api/sacrifices/bulk", { body: { ...fields, quantity: count } });
        toast(made.map((s) => s.sacrifice_no).join(", "));
      }
      onSaved();
    } catch (x: any) { setErr(x.message); }
  };
  return (
    <Modal title={t("add_row")} onClose={onClose}><form onSubmit={save}>
      <div className="form-grid">
        <Field label={t("new_sacrifice_no")} hint={t("num_auto_hint")}><input inputMode="numeric" value={count > 1 ? "" : no} disabled={count > 1}
          placeholder={`${t("num_auto")}${next.data ? ` · ${next.data.suggested_next}` : ""}`} onChange={(e) => setNo(e.target.value.replace(/\D/g, ""))} /></Field>
        <Field label={t("order_no")}><input className="mono" value={f.shopify_order} onChange={(e) => setF({ ...f, shopify_order: e.target.value })} placeholder="#1231" autoFocus /></Field>
        <Field label={t("quantity")}><input type="number" min={1} max={50} value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
        <Field label={t("donor_name")}><input value={f.donor_name} onChange={(e) => setF({ ...f, donor_name: e.target.value })} /></Field>
        <Field label={t("animal_type")}><select value={f.animal_type} onChange={(e) => setF({ ...f, animal_type: e.target.value })}><option value="">—</option>
          {animals.map((a) => <option key={a} value={a}>{a}</option>)}</select></Field>
        <Field label={t("sale_price")}><input type="number" min={0} step="0.01" value={f.sale_price} onChange={(e) => setF({ ...f, sale_price: e.target.value })} /></Field>
        <div className="field span-all"><label>{t("addons")}</label>
          <AddonPicker value={f.extras} options={addons} onChange={(v) => setF({ ...f, extras: v })} /></div>
      </div>
      <div style={{ marginTop: 12 }}><Field label={t("dedication")}><textarea value={f.dedication} onChange={(e) => setF({ ...f, dedication: e.target.value })} /></Field></div>
      <ErrorBox error={err} />
      <div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("create")}{count > 1 ? ` (${count})` : ""}</button></div>
    </form></Modal>
  );
}

function SacCards({ rows, colorById, codeById, onEdit }: { rows: Sacrifice[]; colorById: Record<number, string>; codeById: Record<number, string>; onEdit: (s: Sacrifice) => void }) {
  const { t, fmtDate, num } = useI18n();
  const money = useMoney();
  const go = useNavigate();
  const list = [...rows].sort(newestFirst((s) => s.sacrifice_no));
  return <>
    <div className="cards-sum muted"><b>{num(list.length)}</b> {t("sacrifices")} · {money(sum(list, (r) => r.sale_price))}</div>
    <div className="well-cards">{list.map((s) => {
      const color = s.contractor_id ? colorById[s.contractor_id] : "";
      return <article key={s.id} className="well-card" style={color ? { background: color } : undefined} onClick={() => onEdit(s)}>
        <header><span className="well-no">{s.sacrifice_no}</span><OpenIcon kind="sacrifice" no={s.sacrifice_no} />{s.animal_type && <span className="chip">{s.animal_type}</span>}
          {splitAddons(s.extras).map((a) => <span key={a} className="chip addon">＋ {a}</span>)}<span className="grow" />
          {s.delivery_date ? <span className="badge ok">{t("delivered")}</span> : <span className="badge warn">{t("st_pending")}</span>}</header>
        <div className="who">{s.donor_name || s.dedication || "—"}</div>
        {s.shopify_order && <div className="muted" style={{ fontSize: 12.5 }} onClick={(e) => e.stopPropagation()}>{t("order_no")} <OrderChip order={s.shopify_order} /></div>}
        {s.parent_well_id && <div className="muted" style={{ fontSize: 12.5 }}>{t("parent_well")} <Link to={`/projects/${s.parent_well_id}`} onClick={(e) => e.stopPropagation()} className="mono">{s.parent_well_id}</Link></div>}
        <div className="meta"><span>{s.contractor_id ? codeById[s.contractor_id] : "—"}</span><span>{fmtDate(s.order_date)}</span>
          {s.sale_price != null && <span className="num strong">{money(s.sale_price)}</span>}</div>
        <footer onClick={(e) => e.stopPropagation()}>
          <button onClick={() => onEdit(s)}>{t("edit")}</button>
          <button onClick={() => go(`/plaque/sacrifice/${s.sacrifice_no}`)}>＋ {t("plaque")}</button>
        </footer>
      </article>; })}</div>
  </>;
}

function SacrificeForm({ s, contractors, animals, addons, onClose, onSaved }: { s: Sacrifice; contractors: Contractor[]; animals: string[]; addons: string[]; onClose: () => void; onSaved: (s: Sacrifice) => void }) {
  const { t } = useI18n();
  const [f, setF] = useState<any>({ ...s });
  const [err, setErr] = useState<string | null>(null);
  const [renumbering, setRenumbering] = useState(false);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const keys = ["order_date", "donor_name", "delivery_date", "contractor_id", "animal_type", "cost", "sale_price", "payment_method",
    "extras", "sales_source", "shopify_order", "intention", "dedication", "notes"];
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: any = {};
    for (const k of keys) {
      let v = f[k] === "" || f[k] === undefined ? null : f[k];
      if (k === "contractor_id" && v != null) v = Number(v);
      if ((k === "cost" || k === "sale_price") && v != null) v = Number(v).toFixed(2);
      const old = (s as any)[k];
      if (String(v ?? "") !== String(old ?? "")) body[k] = v;
    }
    if (!Object.keys(body).length) { onClose(); return; }
    try { onSaved(await api<Sacrifice>(`/api/sacrifices/${s.sacrifice_no}`, { method: "PATCH", body: { ...body, expected_version: s.version } })); toast(t("saved")); }
    catch (x: any) { setErr(x.message); }
  };
  const inp = (k: string, extra: any = {}) => <Field label={t(k)}><input value={f[k] ?? ""} onChange={set(k)} {...extra} /></Field>;
  if (renumbering) return <ChangeNumber kind="sacrifice" current={s.sacrifice_no} onClose={() => setRenumbering(false)}
    onDone={(_, r) => onSaved(r.sacrifice)} />;
  return <Modal title={`${t("edit")} · ${s.sacrifice_no}`} onClose={onClose}><form onSubmit={save}>
    <div className="actions" style={{ justifyContent: "flex-start", marginTop: 0 }}>
      <button type="button" onClick={() => setRenumbering(true)}>🔢 {t("num_change")}</button>
      {s.shopify_order && <span className="muted">{t("order_no")} <OrderChip order={s.shopify_order} /></span>}</div>
    <div className="form-grid">
      {inp("order_date", { type: "date" })}{inp("donor_name")}{inp("delivery_date", { type: "date" })}
      <Field label={t("contractor")}><select value={f.contractor_id ?? ""} onChange={set("contractor_id")}><option value="">—</option>
        {contractors.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}</select></Field>
      <Field label={t("animal_type")}><select value={f.animal_type ?? ""} onChange={set("animal_type")}><option value="">—</option>
        {[...new Set([...animals, ...(f.animal_type ? [f.animal_type] : [])])].map((a) => <option key={a} value={a}>{a}</option>)}</select></Field>
      {inp("cost", { type: "number", step: "0.01", min: 0 })}{inp("sale_price", { type: "number", step: "0.01", min: 0 })}
      {inp("payment_method")}{inp("sales_source")}{inp("shopify_order")}{inp("intention")}
      <div className="field span-all"><label>{t("addons")}</label>
        <AddonPicker value={f.extras} options={addons} onChange={(v) => setF({ ...f, extras: v })} />
        {s.parent_well_id && <span className="hint muted">{t("parent_well")} {s.parent_well_id}</span>}</div>
    </div>
    <div style={{ marginTop: 12 }}><Field label={t("dedication")}><textarea value={f.dedication ?? ""} onChange={set("dedication")} /></Field></div>
    <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes ?? ""} onChange={set("notes")} /></Field></div>
    <ErrorBox error={err} />
    <div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("save")}</button></div>
  </form></Modal>;
}
