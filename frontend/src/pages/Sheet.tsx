// Excel-style view of Master Projects. Every cell edit is sent as a normal
// project update (validated, versioned, written to the timeline + audit log).
// Fields the rules protect (Well ID, delivery, maintenance) are read-only here.
import { useCallback, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { CellValueChangedEvent, ColDef, GridApi, ValueFormatterParams } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { useNavigate } from "react-router-dom";
import { api, Contractor, download, Project } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Modal, toast, useApi } from "../ui";
import ProjectForm from "./ProjectForm";

const CONSTRUCTION = ["new_order", "scheduled", "in_progress", "completed", "on_hold", "cancelled"];
const PAYMENT = ["unpaid", "partial", "paid", "refunded"];
const VIDEO = ["none", "raw_received", "processing", "in_review", "completed"];
const CONTRACTOR_EDITABLE = new Set(["construction_status", "construction_start_date", "completion_date", "notes"]);

export default function Sheet() {
  const { t, st, lang } = useI18n();
  const { can, user, refreshCounts } = useAuth();
  const nav = useNavigate();
  const projects = useApi<{ items: Project[] }>("/api/projects", { page_size: 5000, sort: "well_id" });
  const contractors = useApi<Contractor[]>("/api/contractors");
  const gridRef = useRef<GridApi<Project> | null>(null);
  const [quick, setQuick] = useState("");
  const [saving, setSaving] = useState(0);
  const [creating, setCreating] = useState(false);
  const manager = can(...MANAGERS);
  const isContractor = user.role === "contractor";

  const editable = useCallback((field: string) => manager || (isContractor && CONTRACTOR_EDITABLE.has(field)), [manager, isContractor]);
  const codeById = useMemo(() => Object.fromEntries((contractors.data || []).map((c) => [c.id, c.code])), [contractors.data]);

  const columnDefs = useMemo<ColDef<Project>[]>(() => {
    const status = (opts: string[]) => ({
      cellEditor: "agSelectCellEditor", cellEditorParams: { values: opts },
      valueFormatter: (p: ValueFormatterParams) => st(p.value), filterValueGetter: undefined,
    });
    const date = { cellDataType: "dateString" as const, filter: "agDateColumnFilter", width: 140 };
    const col = (field: keyof Project, extra: Partial<ColDef<Project>> = {}): ColDef<Project> => ({
      field, headerName: t(field as string), editable: editable(field as string), ...extra,
    });
    return [
      col("well_id", { editable: false, pinned: lang === "ar" ? "right" : "left", width: 105, filter: "agNumberColumnFilter",
        cellClass: "mono cell-link", sort: "asc" }),
      col("order_date", date), col("customer_name", { width: 170 }), col("customer_phone", { width: 150, cellStyle: { direction: "ltr", textAlign: "end" } }),
      col("country", { width: 120 }), col("city"), col("village"), col("well_type", { width: 160 }), col("sales_source"),
      col("contractor_id", {
        headerName: t("contractor"), width: 120,
        cellEditor: "agSelectCellEditor", cellEditorParams: { values: [null, ...(contractors.data || []).map((c) => c.id)] },
        valueFormatter: (p) => (p.value ? codeById[p.value] || String(p.value) : "—"),
        filterValueGetter: (p) => (p.data?.contractor_id ? codeById[p.data.contractor_id] : ""),
      }),
      col("sale_amount", { cellDataType: "number", filter: "agNumberColumnFilter", width: 120,
        valueGetter: (p) => (p.data?.sale_amount == null ? null : Number(p.data.sale_amount)),
        valueSetter: (p) => { p.data.sale_amount = p.newValue == null ? null : String(p.newValue); return true; } }),
      col("payment_status", { ...status(PAYMENT), width: 120 }),
      col("construction_status", { ...status(CONSTRUCTION), width: 140 }),
      col("construction_start_date", date), col("completion_date", date),
      col("delivery_status", { editable: false, valueFormatter: (p) => st(p.value), width: 120,
        headerTooltip: t("delivery_rule"), cellClass: "locked" }),
      col("delivery_date", { ...date, editable: false, cellClass: "locked" }),
      col("final_video_link", { width: 200 }), col("video_status", { ...status(VIDEO), width: 150 }),
      col("maintenance_status", { editable: false, valueFormatter: (p) => st(p.value), cellClass: "locked", width: 120 }),
      col("last_maintenance_date", { ...date, editable: false, cellClass: "locked" }),
      col("next_maintenance_date", date),
      col("notes", { width: 260, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
      col("updated_at", { headerName: t("last_updated"), editable: false, cellClass: "locked", width: 150,
        valueFormatter: (p) => (p.value ? new Date(p.value).toLocaleString() : "") }),
    ];
  }, [t, st, lang, editable, contractors.data, codeById]);

  const onCellValueChanged = useCallback(async (e: CellValueChangedEvent<Project>) => {
    const field = e.colDef.field as string;
    if (!e.data || e.oldValue === e.newValue) return;
    let value: any = e.newValue === "" ? null : e.newValue;
    if (field === "sale_amount" && value != null) value = Number(value).toFixed(2);
    setSaving((n) => n + 1);
    try {
      const updated = await api<Project>(`/api/projects/${e.data.well_id}`, {
        method: "PATCH", body: { [field]: value, expected_version: e.data.version },
      });
      e.node.setData(updated);  // pick up new version + any server-side changes (e.g. auto dates)
      e.api.flashCells({ rowNodes: [e.node], columns: [field] });
      refreshCounts();
    } catch (err: any) {
      // put the old value back so the grid never shows something that wasn't saved
      const reverted = { ...e.data, [field]: field === "sale_amount" ? (e.oldValue == null ? null : String(e.oldValue)) : e.oldValue };
      e.node.setData(reverted);
      toast(`${t("well_id")} ${e.data.well_id}: ${err.message}`);
      if (err.status === 409) projects.reload();
    } finally { setSaving((n) => n - 1); }
  }, [t, refreshCounts, projects]);

  return (
    <>
      <div className="topbar">
        <h1>{t("nav_sheet")}</h1>
        <div className="toolbar" style={{ margin: 0 }}>
          <input type="search" className="search" placeholder={t("search")} value={quick} onChange={(e) => setQuick(e.target.value)} />
          <span className="muted" aria-live="polite">{saving ? t("saving") : t("all_saved")}</span>
          <button onClick={() => gridRef.current?.setFilterModel(null)}>{t("clear_filters")}</button>
          {manager && <button onClick={() => download("/api/projects/export.csv", "hayah-projects.csv")}>{t("export_csv")}</button>}
          {manager && <button className="primary" onClick={() => setCreating(true)}>+ {t("new_project")}</button>}
        </div>
      </div>
      <p className="muted" style={{ marginTop: -8 }}>{t("sheet_help")}</p>
      <ErrorBox error={projects.error} />
      <div className={`ag-theme-quartz hayah-grid`} style={{ height: "calc(100vh - 190px)", minHeight: 420 }}>
        <AgGridReact<Project>
          rowData={projects.data?.items || []}
          columnDefs={columnDefs}
          defaultColDef={{ sortable: true, filter: true, resizable: true, floatingFilter: true, minWidth: 90, width: 130 }}
          getRowId={(p) => String(p.data.id)}
          enableRtl={lang === "ar"}
          quickFilterText={quick}
          singleClickEdit={false}
          stopEditingWhenCellsLoseFocus
          enterNavigatesVerticallyAfterEdit
          undoRedoCellEditing
          enableCellTextSelection
          suppressColumnVirtualisation
          onGridReady={(p) => { gridRef.current = p.api; }}
          onCellValueChanged={onCellValueChanged}
          onCellDoubleClicked={(e) => { if (e.colDef.field === "well_id" && e.data) nav(`/projects/${e.data.well_id}`); }}
          localeText={lang === "ar" ? AR_GRID : undefined}
        />
      </div>
      {creating && <Modal title={t("new_project")} onClose={() => setCreating(false)}>
        <ProjectForm onCancel={() => setCreating(false)} onSaved={() => { setCreating(false); projects.reload(); refreshCounts(); }} />
      </Modal>}
    </>
  );
}

// Arabic labels for the grid's own menus and filters.
const AR_GRID: Record<string, string> = {
  filterOoo: "تصفية…", equals: "يساوي", notEqual: "لا يساوي", contains: "يحتوي", notContains: "لا يحتوي",
  startsWith: "يبدأ بـ", endsWith: "ينتهي بـ", blank: "فارغ", notBlank: "غير فارغ", lessThan: "أقل من",
  greaterThan: "أكبر من", lessThanOrEqual: "أقل من أو يساوي", greaterThanOrEqual: "أكبر من أو يساوي",
  inRange: "بين", inRangeStart: "من", inRangeEnd: "إلى", andCondition: "و", orCondition: "أو",
  applyFilter: "تطبيق", resetFilter: "إعادة تعيين", clearFilter: "مسح", cancelFilter: "إلغاء",
  noRowsToShow: "لا توجد صفوف", loadingOoo: "جارٍ التحميل…", before: "قبل", after: "بعد",
  sortAscending: "ترتيب تصاعدي", sortDescending: "ترتيب تنازلي", sortUnSort: "إلغاء الترتيب",
  pinColumn: "تثبيت العمود", autosizeThisColumn: "ضبط عرض العمود", autosizeAllColumns: "ضبط كل الأعمدة",
  resetColumns: "إعادة الأعمدة", columns: "الأعمدة", filters: "عوامل التصفية",
};
