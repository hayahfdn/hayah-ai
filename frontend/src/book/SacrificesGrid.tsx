// Excel-style sacrifices sheet (one per month, and inside each contractor tab).
import { useCallback, useMemo, useState } from "react";
import type { CellValueChangedEvent, ColDef } from "ag-grid-community";
import { api, Contractor, dataChanged, Sacrifice } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, Field, Modal, toast, useApi } from "../ui";
import { dateCol, HayahGrid, moneyCol, n, newestFirst, sum, useDataReload, useMoney } from "./grid";
import { Link, useNavigate } from "react-router-dom";
import { useIsMobile } from "../nav";

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
      col("payment_method", { width: 120 }), col("extras", { width: 110 }), col("sales_source", { width: 120, valueGetter: (p) => p.data?.source_group ?? p.data?.sales_source,
        tooltipValueGetter: (p) => (p.data?.sales_source && p.data.sales_source !== p.data.source_group ? `${t("src_original")}: ${p.data.sales_source}` : null),
        cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["", ...(lists.data?.sales_sources || [])] } }),
      col("shopify_order", { width: 105 }), col("intention", { width: 130 }),
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
        onClose={() => setEditing(null)} onSaved={(u) => { setEditing(null); data.setData((d) => d && d.map((r) => (r.id === u.id ? u : r))); dataChanged(); }} />}
      {adding && <NewSacrifice month={month} contractorId={contractorId} onClose={() => setAdding(false)}
        onSaved={() => { setAdding(false); data.reload(); dataChanged(); }} />}
    </>
  );
}

function NewSacrifice({ month, contractorId, onClose, onSaved }: { month?: string; contractorId?: number; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const next = useApi<{ suggested_next: number }>("/api/sacrifices/next-number");
  const [no, setNo] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const today = new Date().toISOString().slice(0, 10);
  const orderDate = month && !today.startsWith(month) ? `${month}-01` : today;
  const value = no || (next.data ? String(next.data.suggested_next) : "");
  const save = async () => {
    try {
      await api("/api/sacrifices", { body: { sacrifice_no: Number(value), order_date: orderDate, contractor_id: contractorId ?? null } });
      onSaved();
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <Modal title={t("add_row")} onClose={onClose}>
      <Field label={t("new_sacrifice_no")}><input inputMode="numeric" value={value} onChange={(e) => setNo(e.target.value.replace(/\D/g, ""))} autoFocus /></Field>
      <ErrorBox error={err} />
      <div className="actions"><button onClick={onClose}>{t("cancel")}</button><button className="primary" disabled={!value} onClick={save}>{t("create")}</button></div>
    </Modal>
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
        <header><span className="well-no">{s.sacrifice_no}</span>{s.animal_type && <span className="chip">{s.animal_type}</span>}<span className="grow" />
          {s.delivery_date ? <span className="badge ok">{t("delivered")}</span> : <span className="badge warn">{t("st_pending")}</span>}</header>
        <div className="who">{s.donor_name || s.dedication || "—"}</div>
        <div className="meta"><span>{s.contractor_id ? codeById[s.contractor_id] : "—"}</span><span>{fmtDate(s.order_date)}</span>
          {s.sale_price != null && <span className="num strong">{money(s.sale_price)}</span>}</div>
        <footer onClick={(e) => e.stopPropagation()}>
          <button onClick={() => onEdit(s)}>{t("edit")}</button>
          <button onClick={() => go(`/plaque/sacrifice/${s.sacrifice_no}`)}>＋ {t("plaque")}</button>
        </footer>
      </article>; })}</div>
  </>;
}

function SacrificeForm({ s, contractors, animals, onClose, onSaved }: { s: Sacrifice; contractors: Contractor[]; animals: string[]; onClose: () => void; onSaved: (s: Sacrifice) => void }) {
  const { t } = useI18n();
  const [f, setF] = useState<any>({ ...s });
  const [err, setErr] = useState<string | null>(null);
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
  return <Modal title={`${t("edit")} · ${s.sacrifice_no}`} onClose={onClose}><form onSubmit={save}>
    <div className="form-grid">
      {inp("order_date", { type: "date" })}{inp("donor_name")}{inp("delivery_date", { type: "date" })}
      <Field label={t("contractor")}><select value={f.contractor_id ?? ""} onChange={set("contractor_id")}><option value="">—</option>
        {contractors.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}</select></Field>
      <Field label={t("animal_type")}><select value={f.animal_type ?? ""} onChange={set("animal_type")}><option value="">—</option>
        {[...new Set([...animals, ...(f.animal_type ? [f.animal_type] : [])])].map((a) => <option key={a} value={a}>{a}</option>)}</select></Field>
      {inp("cost", { type: "number", step: "0.01", min: 0 })}{inp("sale_price", { type: "number", step: "0.01", min: 0 })}
      {inp("payment_method")}{inp("extras")}{inp("sales_source")}{inp("shopify_order")}{inp("intention")}
    </div>
    <div style={{ marginTop: 12 }}><Field label={t("dedication")}><textarea value={f.dedication ?? ""} onChange={set("dedication")} /></Field></div>
    <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes ?? ""} onChange={set("notes")} /></Field></div>
    <ErrorBox error={err} />
    <div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("save")}</button></div>
  </form></Modal>;
}
