// Excel-style wells sheet. Used by the Master Sheet, each month's tab and each contractor tab.
// Every cell edit is a normal audited project update (validated, versioned, logged).
import { useCallback, useMemo, useRef, useState } from "react";
import type { CellValueChangedEvent, ColDef, GridApi } from "ag-grid-community";
import { useNavigate } from "react-router-dom";
import { api, Contractor, dataChanged, download, Project } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Modal, toast, useApi } from "../ui";
import ProjectForm from "../pages/ProjectForm";
import RecentChanges, { Change, undoChange } from "../admin/RecentChanges";
import { dateCol, HayahGrid, moneyCol, n, sum, useDataReload, useMoney } from "./grid";

const CONSTRUCTION = ["new_order", "scheduled", "in_progress", "completed", "on_hold", "cancelled"];
const PAYMENT = ["unpaid", "partial", "paid", "refunded"];
const VIDEO = ["none", "raw_received", "processing", "in_review", "completed"];
// Team members add orders and selling prices; costs and delivery approval stay with managers.
const STAFF_LOCKED = new Set(["cost", "delivery_date"]);
const CONTRACTOR_EDITABLE = new Set(["construction_status", "construction_start_date", "completion_date", "notes"]);

export default function WellsGrid({ month, contractorId, height, title }: { month?: string; contractorId?: number; height?: string; title?: string }) {
  const { t, st, lang } = useI18n();
  const { can, user, refreshCounts } = useAuth();
  const nav = useNavigate();
  const money = useMoney();
  const projects = useApi<{ items: Project[] }>("/api/projects", { page_size: 5000, sort: "well_id", month, contractor_id: contractorId });
  const contractors = useApi<Contractor[]>("/api/contractors");
  const lists = useApi<Record<string, string[]>>("/api/settings/lists");
  useDataReload(projects.reload);
  const gridRef = useRef<GridApi<Project> | null>(null);
  const [quick, setQuick] = useState("");
  const [saving, setSaving] = useState(0);
  const [creating, setCreating] = useState(false);
  const [history, setHistory] = useState(false);
  const undoLast = async () => {
    try {
      const [last] = await api<Change[]>("/api/undo/recent", { query: { mine: true, limit: 1 } });
      if (!last || last.undone) { toast(t("undo_nothing")); return; }
      if (await undoChange(last.id, t)) projects.reload();
    } catch (e: any) { toast(e.message); }
  };
  const manager = can(...MANAGERS);
  const isContractor = user.role === "contractor";
  const staff = user.role === "staff";
  const editable = useCallback((f: string) => manager || (staff && !STAFF_LOCKED.has(f)) || (isContractor && CONTRACTOR_EDITABLE.has(f)),
    [manager, staff, isContractor]);
  const codeById = useMemo(() => Object.fromEntries((contractors.data || []).map((c) => [c.id, c.code])), [contractors.data]);
  const rows = projects.data?.items || [];

  const cols = useMemo<ColDef<Project>[]>(() => {
    const status = (opts: string[]) => ({ cellEditor: "agSelectCellEditor", cellEditorParams: { values: opts }, valueFormatter: (p: any) => (p.node?.isRowPinned() ? "" : st(p.value)) });
    const pick = (opts: string[] = []) => ({ cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["", ...opts] } });
    const col = (field: keyof Project, extra: Partial<ColDef<Project>> = {}): ColDef<Project> => ({
      field, headerName: t(field as string), editable: (p) => editable(field as string) && !p.node.isRowPinned(), ...extra,
    });
    const showSale = !isContractor;  // selling price: everyone on the team
    const showMoney = manager;        // cost and profit: managers only
    const c: (ColDef<Project> | false)[] = [
      col("well_id", { editable: false, pinned: lang === "ar" ? "right" : "left", width: 100, filter: "agNumberColumnFilter",
        cellClass: "mono cell-link", sort: "asc", valueFormatter: (p) => (p.node?.isRowPinned() ? t("total_row") : String(p.value ?? "")) }),
      col("order_date", dateCol), col("customer_name", { width: 170 }),
      col("customer_phone", { width: 145, cellStyle: { direction: "ltr", textAlign: "end" } }),
      col("country", { width: 115, ...pick(lists.data?.countries) }), col("city", { width: 115 }), col("village", { width: 115 }),
      col("well_type", { width: 110, ...pick(lists.data?.well_types) }),
      col("contractor_id", { headerName: t("contractor"), width: 105, cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: [null, ...(contractors.data || []).map((c) => c.id)] },
        valueFormatter: (p) => (p.node?.isRowPinned() ? "" : p.value ? codeById[p.value] || String(p.value) : "—"),
        filterValueGetter: (p) => (p.data?.contractor_id ? codeById[p.data.contractor_id] : "") }),
      showSale && moneyCol<Project>("sale_amount", t("sale_amount"), manager || staff, money),
      showMoney && moneyCol<Project>("cost", t("cost"), manager, money),
      showMoney && { colId: "profit", headerName: t("profit"), editable: false, width: 105, cellClass: "num locked",
        valueGetter: (p) => (p.data?.sale_amount == null && p.data?.cost == null ? null : n(p.data?.sale_amount) - n(p.data?.cost)),
        valueFormatter: (p) => money(p.value), cellClassRules: { "neg": (p) => n(p.value) < 0 } },
      col("payment_status", { ...status(PAYMENT), width: 110 }), col("payment_method", { width: 125 }),
      col("extras", { width: 110 }), col("shopify_order", { width: 105 }), col("sales_source", { width: 120 }),
      col("dedication", { width: 200, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
      col("received_date", dateCol),
      col("construction_status", { ...status(CONSTRUCTION), width: 130 }),
      col("construction_start_date", dateCol), col("completion_date", dateCol),
      col("delivery_status", { editable: false, valueFormatter: (p) => (p.node?.isRowPinned() ? "" : st(p.value)), width: 115, cellClass: "locked" }),
      col("delivery_date", { ...dateCol, headerTooltip: t("delivered_note"), cellClass: manager ? undefined : "locked", editable: (p) => manager && !p.node.isRowPinned() }),
      col("final_video_link", { width: 190 }), col("video_status", { ...status(VIDEO), width: 140 }),
      col("maintenance_status", { editable: false, valueFormatter: (p) => (p.node?.isRowPinned() ? "" : st(p.value)), cellClass: "locked", width: 115 }),
      col("next_maintenance_date", dateCol),
      col("notes", { width: 240, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
      col("updated_at", { headerName: t("last_updated"), editable: false, cellClass: "locked", width: 150,
        valueFormatter: (p) => (p.value ? new Date(p.value).toLocaleString() : "") }),
    ];
    return c.filter(Boolean) as ColDef<Project>[];
  }, [t, st, lang, editable, manager, staff, isContractor, contractors.data, codeById, lists.data, money]);

  const totals = useMemo(() => [{ id: -1, well_id: null as any, customer_name: `${rows.length} ${t("wells")}`,
    sale_amount: String(sum(rows, (r) => r.sale_amount)), cost: String(sum(rows, (r) => r.cost)) } as Partial<Project>], [rows, t]);

  const onEdit = useCallback(async (e: CellValueChangedEvent<Project>) => {
    const field = e.colDef.field as string;
    if (!e.data) return;
    let value: any = e.newValue === "" ? null : e.newValue;
    if ((field === "sale_amount" || field === "cost") && value != null) value = Number(value).toFixed(2);
    setSaving((x) => x + 1);
    try {
      let updated: Project;
      if (field === "delivery_date") {
        if (!value) throw new Error(t("delivered_note"));
        updated = await api<Project>(`/api/finance/deliver/${e.data.well_id}`, { body: { delivery_date: value } });
      } else {
        updated = await api<Project>(`/api/projects/${e.data.well_id}`, { method: "PATCH", body: { [field]: value, expected_version: e.data.version } });
      }
      e.node.setData(updated);
      e.api.flashCells({ rowNodes: [e.node] });
      refreshCounts();
      projects.setData((d) => d && { ...d, items: d.items.map((r) => (r.id === updated.id ? updated : r)) });
      if (["sale_amount", "cost", "contractor_id", "order_date"].includes(field)) dataChanged();  // refresh totals on other sheets
    } catch (err: any) {
      e.node.setData({ ...e.data, [field]: e.oldValue == null ? null : (field === "sale_amount" || field === "cost") ? String(e.oldValue) : e.oldValue });
      toast(`${t("well_id")} ${e.data.well_id}: ${err.message}`);
      if (err.status === 409) projects.reload();
    } finally { setSaving((x) => x - 1); }
  }, [t, refreshCounts, projects]);

  return (
    <>
      <div className="toolbar">
        {title && <h2 style={{ margin: 0, marginInlineEnd: 8 }}>{title}</h2>}
        <input type="search" className="search" placeholder={t("search")} value={quick}
          onChange={(e) => { setQuick(e.target.value); gridRef.current?.setGridOption("quickFilterText", e.target.value); }} />
        <span className="muted" aria-live="polite">{saving ? t("saving") : t("all_saved")}</span>
        <button onClick={() => gridRef.current?.setFilterModel(null)}>{t("clear_filters")}</button>
        {(manager || staff) && <button title={t("undo_last_help")} onClick={undoLast}>↶ {t("undo_last")}</button>}
        {(manager || staff) && <button onClick={() => setHistory(true)}>{t("undo_title")}</button>}
        {manager && !month && !contractorId && <button onClick={() => download("/api/projects/export.csv", "hayah-projects.csv")}>{t("export_csv")}</button>}
        {(manager || staff) && <button className="primary" onClick={() => setCreating(true)}>+ {t("new_project")}</button>}
      </div>
      <ErrorBox error={projects.error} />
      <HayahGrid<Project> rows={rows} cols={cols} totals={totals} onEdit={onEdit} height={height} gridRef={gridRef}
        rowId={(r) => String(r.id)}
        rowClass={(p) => (p.data?.delivery_status === "delivered" ? "row-done" : p.data?.construction_status === "completed" ? "row-wait" : undefined)}
        onCellDoubleClicked={(e) => { if (e.colDef.field === "well_id" && e.data && !e.node.isRowPinned()) nav(`/projects/${e.data.well_id}`); }} />
      {history && <Modal title={t("undo_title")} onClose={() => { setHistory(false); projects.reload(); }}>
        <RecentChanges mine={!manager} />
      </Modal>}
      {creating && <Modal title={t("new_project")} onClose={() => setCreating(false)}>
        <ProjectForm onCancel={() => setCreating(false)} onSaved={() => { setCreating(false); projects.reload(); refreshCounts(); dataChanged(); }} />
      </Modal>}
    </>
  );
}
