// Excel-style sacrifices sheet (one per month, and inside each contractor tab).
import { useCallback, useMemo, useState } from "react";
import type { CellValueChangedEvent, ColDef } from "ag-grid-community";
import { api, Contractor, dataChanged, Sacrifice } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, Field, Modal, toast, useApi } from "../ui";
import { dateCol, HayahGrid, moneyCol, n, sum, useDataReload, useMoney } from "./grid";

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

  const cols = useMemo<ColDef<Sacrifice>[]>(() => {
    const col = (field: keyof Sacrifice, extra: Partial<ColDef<Sacrifice>> = {}): ColDef<Sacrifice> => ({
      field, headerName: t(field as string), editable: (p) => !p.node.isRowPinned(), ...extra });
    return [
      col("sacrifice_no", { editable: false, pinned: lang === "ar" ? "right" : "left", width: 95, sort: "asc", cellClass: "mono",
        filter: "agNumberColumnFilter", valueFormatter: (p) => (p.node?.isRowPinned() ? t("total_row") : String(p.value ?? "")) }),
      col("order_date", dateCol), col("donor_name", { width: 170 }), col("received_date", dateCol), col("delivery_date", dateCol),
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
        <span className="muted" aria-live="polite">{saving ? t("saving") : t("all_saved")}</span>
        <button className="primary" onClick={() => setAdding(true)}>{t("add_row")}</button>
      </div>
      <ErrorBox error={data.error} />
      <HayahGrid<Sacrifice> rows={rows} cols={cols} totals={totals} onEdit={onEdit} height={height} rowId={(r) => String(r.id)}
        rowClass={(p) => (p.data?.delivery_date ? "row-done" : "row-wait")} />
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
