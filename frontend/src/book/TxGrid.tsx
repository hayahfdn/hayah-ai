// Money rows (bank, partner and contractor-payment sheets). Rows are never deleted; a wrong row is voided.
import { useCallback, useMemo, useState } from "react";
import type { CellValueChangedEvent, ColDef } from "ag-grid-community";
import { api, Contractor, dataChanged, Tx, TX_KINDS } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, toast, useApi } from "../ui";
import { dateCol, HayahGrid, moneyCol, sum, useMoney } from "./grid";

export default function TxGrid({ rows, accountId, accountIdDefault, contractorId, defaultKind, kinds, showBalance, onChanged, height, accounts }: {
  rows: Tx[]; accountId?: number; accountIdDefault?: number; contractorId?: number; defaultKind: string; kinds?: string[]; showBalance?: boolean;
  onChanged: () => void; height?: string; accounts?: { id: number; code: string }[];
}) {
  const { t } = useI18n();
  const money = useMoney();
  const contractors = useApi<Contractor[]>("/api/contractors");
  const [saving, setSaving] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const codeById = useMemo(() => Object.fromEntries((contractors.data || []).map((c) => [c.id, c.code])), [contractors.data]);
  const accById = useMemo(() => Object.fromEntries((accounts || []).map((a) => [a.id, a.code])), [accounts]);
  const kindList = kinds || TX_KINDS;

  const cols = useMemo<ColDef<Tx>[]>(() => {
    const ed = (p: any) => !p.node.isRowPinned() && !p.data?.voided;
    const col = (field: keyof Tx, extra: Partial<ColDef<Tx>> = {}): ColDef<Tx> => ({ field, headerName: t("tx_" + String(field)) !== "tx_" + String(field) ? t("tx_" + String(field)) : t(field as string), editable: ed, ...extra });
    const c: (ColDef<Tx> | false)[] = [
      col("date", { ...dateCol, sort: "asc", valueFormatter: (p) => (p.node?.isRowPinned() ? t("total_row") : p.value || "") }),
      col("kind", { width: 170, cellEditor: "agSelectCellEditor", cellEditorParams: { values: kindList },
        valueFormatter: (p) => (p.node?.isRowPinned() || !p.value ? "" : t("tk_" + p.value)) }),
      !contractorId && col("contractor_id", { headerName: t("contractor"), width: 105, cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: [null, ...(contractors.data || []).map((c) => c.id)] },
        valueFormatter: (p) => (p.value ? codeById[p.value] || "" : "") }),
      !!accounts && col("account_id", { headerName: t("account"), width: 110, cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: [null, ...accounts.map((a) => a.id)] }, valueFormatter: (p) => (p.value ? accById[p.value] || "" : "") }),
      col("channel", { width: 120 }), col("category", { width: 120 }),
      { colId: "in", headerName: t("money_in"), width: 110, cellClass: "num", editable: false,
        valueGetter: (p) => (p.node?.isRowPinned() ? (p.data as any)?._in : p.data?.direction === "in" ? Number(p.data.amount) : null), valueFormatter: (p) => money(p.value) },
      { colId: "out", headerName: t("money_out"), width: 110, cellClass: "num", editable: false,
        valueGetter: (p) => (p.node?.isRowPinned() ? (p.data as any)?._out : p.data?.direction === "out" ? Number(p.data.amount) : null), valueFormatter: (p) => money(p.value) },
      { ...moneyCol<Tx>("amount", t("amount"), true, money), editable: ed },
      !!showBalance && { field: "balance", headerName: t("balance"), width: 115, cellClass: "num locked", editable: false, valueFormatter: (p) => money(p.value) },
      col("description", { width: 240, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }), col("reference", { width: 120 }),
      { colId: "void", headerName: "", width: 90, editable: false, sortable: false, filter: false,
        cellRenderer: (p: any) => p.node.isRowPinned() ? null : p.data.voided
          ? <span className="badge bad" title={p.data.void_reason}>{t("voided")}</span>
          : <button className="sm" onClick={() => voidRow(p.data)}>{t("void")}</button> },
    ];
    return c.filter(Boolean) as ColDef<Tx>[];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, money, contractors.data, codeById, accById, contractorId, showBalance, kindList]);

  const live = rows.filter((r) => !r.voided);
  const totals = useMemo(() => [{ id: -1, _in: sum(live.filter((r) => r.direction === "in"), (r) => r.amount),
    _out: sum(live.filter((r) => r.direction === "out"), (r) => r.amount),
    balance: rows.length ? rows[rows.length - 1].balance : undefined } as any], [rows]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function voidRow(r: Tx) {
    const reason = window.prompt(t("void_reason"));
    if (!reason || reason.trim().length < 3) return;
    try { await api(`/api/finance/transactions/${r.id}/void`, { body: { reason } }); onChanged(); dataChanged(); }
    catch (e: any) { toast(e.message); }
  }

  const onEdit = useCallback(async (e: CellValueChangedEvent<Tx>) => {
    const field = e.colDef.field as string;
    if (!e.data) return;
    let value: any = e.newValue === "" ? null : e.newValue;
    if (field === "amount" && value != null) value = Number(value).toFixed(2);
    setSaving((x) => x + 1);
    try {
      await api(`/api/finance/transactions/${e.data.id}`, { method: "PATCH", body: { [field]: value, expected_version: e.data.version } });
      onChanged(); dataChanged();
    } catch (err: any) {
      e.node.setData({ ...e.data, [field]: e.oldValue == null ? null : field === "amount" ? String(e.oldValue) : e.oldValue });
      toast(err.message);
      if (err.status === 409) onChanged();
    } finally { setSaving((x) => x - 1); }
  }, [onChanged]);

  const add = async () => {
    setErr(null);
    try {
      await api("/api/finance/transactions", { body: { date: new Date().toISOString().slice(0, 10), kind: defaultKind, amount: "0",
        account_id: accountId ?? accountIdDefault ?? null, contractor_id: contractorId ?? null } });
      onChanged();
    } catch (e: any) { setErr(e.message); }
  };

  return (
    <>
      <div className="toolbar">
        <span className="muted" aria-live="polite">{saving ? t("saving") : t("all_saved")}</span>
        <button className="primary" onClick={add}>{t("add_row")}</button>
      </div>
      <ErrorBox error={err} />
      <HayahGrid<Tx> rows={rows} cols={cols} totals={totals} onEdit={onEdit} height={height} rowId={(r) => String(r.id)}
        rowClass={(p) => (p.data?.voided ? "row-void" : undefined)} />
    </>
  );
}
