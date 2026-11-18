// Excel-style sacrifices sheet (one per month, and inside each contractor tab).
import { useCallback, useMemo, useState } from "react";
import type { CellValueChangedEvent, ColDef } from "ag-grid-community";
import { useNavigate } from "react-router-dom";
import { api, Contractor, dataChanged, Sacrifice } from "../api";
import { useI18n } from "../i18n";
import { useNarrow } from "../look";
import { PlaqueIcon } from "../plaque/PlaqueView";
import { ErrorBox, Field, Modal, toast, useApi } from "../ui";
import { dateCol, HayahGrid, moneyCol, n, sum, useDataReload, useMoney } from "./grid";

export default function SacrificesGrid({ month, contractorId, height, title }: { month?: string; contractorId?: number; height?: string; title?: string }) {
  const { t, lang } = useI18n();
  const money = useMoney();
  const nav = useNavigate();
  const narrow = useNarrow();
  const [view, setView] = useState<"auto" | "table" | "cards">("auto");
  const cards = view === "cards" || (view === "auto" && narrow);
  const [editing, setEditing] = useState<Sacrifice | null>(null);
  const data = useApi<Sacrifice[]>("/api/sacrifices", { month, contractor_id: contractorId });
  const contractors = useApi<Contractor[]>("/api/contractors");
  const lists = useApi<Record<string, string[]>>("/api/settings/lists");
  useDataReload(data.reload);
  const [saving, setSaving] = useState(0);
  const [adding, setAdding] = useState(false);
  const rows = data.data || [];
  const codeById = useMemo(() => Object.fromEntries((contractors.data || []).map((c) => [c.id, c.code])), [contractors.data]);

  const cols = useMemo<ColDef<Sacrifice>[]>(() => {
    const col = (field: keyof Sacrifice, extra: Partial<ColDef<Sacrifice>> = {}): ColDef<Sacrifice> => ({
      field, headerName: t(field as string), editable: (p) => !p.node.isRowPinned(), ...extra });
    return [
      col("sacrifice_no", { editable: false, pinned: lang === "ar" ? "right" : "left", width: 95, sort: "asc",
        filter: "agNumberColumnFilter", cellClass: "wid", valueFormatter: (p) => (p.node?.isRowPinned() ? t("total_row") : String(p.value ?? "")) }),
      { colId: "plaque", headerName: t("plaque_short"), pinned: lang === "ar" ? "right" : "left", width: 66, minWidth: 60, editable: false,
        sortable: false, filter: false, floatingFilter: false, cellClass: "plaque-cell",
        cellRenderer: (p: any) => (p.node.isRowPinned() || !p.data ? null
          : <button type="button" className="plaque-btn compact" title={t("pl_create")} aria-label={`${t("pl_create")} ${p.data.sacrifice_no}`}
              onClick={() => nav(`/plaque/sacrifice/${p.data.sacrifice_no}`)}><PlaqueIcon /></button>) },
      col("order_date", dateCol), col("donor_name", { width: 170, cellClass: "strong" }), col("delivery_date", dateCol),
      col("contractor_id", { headerName: t("contractor"), width: 105, cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: [null, ...(contractors.data || []).map((c) => c.id)] },
        valueFormatter: (p) => (p.node?.isRowPinned() ? "" : p.value ? codeById[p.value] || String(p.value) : "—"),
        filterValueGetter: (p) => (p.data?.contractor_id ? codeById[p.data.contractor_id] : "") }),
      col("animal_type", { width: 110, cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["", ...(lists.data?.animal_types || [])] } }),
      moneyCol<Sacrifice>("cost", t("cost"), true, money), moneyCol<Sacrifice>("sale_price", t("sale_price"), true, money),
      { colId: "profit", headerName: t("profit"), editable: false, width: 100, cellClass: "num locked",
        valueGetter: (p) => (p.data?.sale_price == null && p.data?.cost == null ? null : n(p.data?.sale_price) - n(p.data?.cost)),
        valueFormatter: (p) => money(p.value) },
      col("payment_method", { width: 120 }), col("extras", { width: 110 }), col("sales_source", { width: 120 }),
      col("shopify_order", { width: 105 }), col("intention", { width: 130 }),
      col("dedication", { width: 200, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
      col("notes", { width: 220, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
    ];
  }, [t, lang, contractors.data, codeById, lists.data, money, nav]);

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
        <span className="muted save-state" aria-live="polite">{saving ? t("saving") : t("all_saved")}</span>
        <div className="seg" role="group" aria-label={t("view_table")}>
          <button className={!cards ? "on" : ""} onClick={() => setView("table")}>{t("view_table")}</button>
          <button className={cards ? "on" : ""} onClick={() => setView("cards")}>{t("view_cards")}</button>
        </div>
        <button className="primary" onClick={() => setAdding(true)}>{t("add_row")}</button>
      </div>
      <ErrorBox error={data.error} />
      {cards ? <SacrificeCards rows={rows} codeById={codeById} conName={(id) => contractors.data?.find((c) => c.id === id)?.name}
          money={money} onEdit={setEditing} onPlaque={(no) => nav(`/plaque/sacrifice/${no}`)} />
        : <HayahGrid<Sacrifice> rows={rows} cols={cols} totals={totals} onEdit={onEdit} height={height} rowId={(r) => String(r.id)}
            rowClass={(p) => (p.data?.delivery_date ? "row-done" : "row-wait")} />}
      {editing && <SacrificeForm s={editing} contractors={contractors.data || []} animals={lists.data?.animal_types || []}
        onClose={() => setEditing(null)} onSaved={(u) => { setEditing(null); data.setData((d) => d && d.map((r) => (r.id === u.id ? u : r))); dataChanged(); toast(t("saved")); }} />}
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

function SacrificeCards({ rows, codeById, conName, money, onEdit, onPlaque }: {
  rows: Sacrifice[]; codeById: Record<number, string>; conName: (id: number) => string | undefined; money: (v: any) => string;
  onEdit: (s: Sacrifice) => void; onPlaque: (no: number) => void;
}) {
  const { t, fmtDate } = useI18n();
  if (!rows.length) return <div className="empty card">{t("no_items")}</div>;
  return <>
    <div className="cards-meta muted">{rows.length} {t("sacrifices")} · {money(sum(rows, (r) => r.sale_price))}</div>
    <ul className="well-cards">{rows.map((s) => (
      <li key={s.id} className={`well-card ${s.delivery_date ? "is-done" : "is-wait"}`}>
        <div className="wc-top"><span className="wid">{s.sacrifice_no}</span>
          <button type="button" className="plaque-btn" onClick={() => onPlaque(s.sacrifice_no)}><PlaqueIcon /><span>{t("pl_create")}</span></button></div>
        <div className="wc-name">{s.donor_name || "—"}</div>
        <div className="wc-meta">
          {s.animal_type && <span className="chip-s">{s.animal_type}</span>}{s.intention && <span className="chip-s">{s.intention}</span>}
          {s.contractor_id && <span className="chip-s">{conName(s.contractor_id) || codeById[s.contractor_id]}</span>}
          {s.order_date && <span className="muted">{fmtDate(s.order_date)}</span>}
        </div>
        <div className="wc-status">
          <span className={`badge ${s.delivery_date ? "ok" : "warn"}`}>{s.delivery_date ? `${t("st_delivered_short")} · ${fmtDate(s.delivery_date)}` : t("st_waiting_short")}</span>
          {s.sale_price != null && <b className="num wc-money">{money(s.sale_price)}</b>}
        </div>
        {s.dedication && <div className="wc-ded" dir="auto">{s.dedication}</div>}
        <div className="wc-actions"><button onClick={() => onEdit(s)}>{t("edit_row")}</button></div>
      </li>))}</ul>
  </>;
}

/** Full edit form for one sacrifice (used on phones, where cell editing is awkward). */
function SacrificeForm({ s, contractors, animals, onClose, onSaved }: {
  s: Sacrifice; contractors: Contractor[]; animals: string[]; onClose: () => void; onSaved: (s: Sacrifice) => void;
}) {
  const { t } = useI18n();
  const [f, setF] = useState<any>({ ...s });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const KEYS = ["order_date", "donor_name", "delivery_date", "contractor_id", "animal_type", "cost", "sale_price", "payment_method",
    "extras", "sales_source", "shopify_order", "intention", "dedication", "notes"];
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: any = { expected_version: s.version };
    for (const k of KEYS) {
      let v = f[k] === "" || f[k] === undefined ? null : f[k];
      if (k === "contractor_id" && v !== null) v = Number(v);
      if ((k === "cost" || k === "sale_price") && v !== null) v = Number(v).toFixed(2);
      const old = (s as any)[k];
      if (!(v === old || (v === null && old === null) || ((k === "cost" || k === "sale_price") && v !== null && old !== null && Number(v) === Number(old)))) body[k] = v;
    }
    if (Object.keys(body).length === 1) { onClose(); return; }
    try { onSaved(await api<Sacrifice>(`/api/sacrifices/${s.sacrifice_no}`, { method: "PATCH", body })); }
    catch (x: any) { setErr(x.message); }
  };
  const text = (k: string, extra: any = {}) => <Field label={t(k)} key={k}><input value={f[k] ?? ""} onChange={set(k)} {...extra} /></Field>;
  const date = (k: string) => <Field label={t(k)} key={k}><input type="date" value={f[k] || ""} onChange={set(k)} /></Field>;
  const money = { type: "number", min: 0, step: "0.01", inputMode: "decimal", className: "num" };
  return <Modal title={`${t("sacrifice_edit")} · ${s.sacrifice_no}`} onClose={onClose}><form onSubmit={save}>
    <div className="form-grid">
      {date("order_date")}{text("donor_name")}{date("delivery_date")}
      <Field label={t("contractor")}><select value={f.contractor_id ?? ""} onChange={set("contractor_id")}><option value="">—</option>
        {contractors.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}</select></Field>
      <Field label={t("animal_type")}><select value={f.animal_type ?? ""} onChange={set("animal_type")}><option value="">—</option>
        {Array.from(new Set([...animals, ...(s.animal_type ? [s.animal_type] : [])])).map((a) => <option key={a} value={a}>{a}</option>)}</select></Field>
      {text("cost", money)}{text("sale_price", money)}{text("payment_method")}{text("extras")}{text("sales_source")}
      {text("shopify_order", { dir: "ltr" })}{text("intention")}
    </div>
    <div style={{ marginTop: 12 }}><Field label={t("dedication")}><textarea value={f.dedication ?? ""} onChange={set("dedication")} /></Field></div>
    <div style={{ marginTop: 12 }}><Field label={t("notes")}><textarea value={f.notes ?? ""} onChange={set("notes")} /></Field></div>
    <ErrorBox error={err} />
    <div className="actions"><button type="button" onClick={onClose}>{t("cancel")}</button><button className="primary">{t("save")}</button></div>
  </form></Modal>;
}
