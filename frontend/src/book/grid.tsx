// Shared Excel-style grid used by every sheet in the system.
import { useEffect, useMemo, useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import type { CellValueChangedEvent, ColDef, GridApi, RowClassParams, RowStyle } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { useI18n } from "../i18n";

export const n = (v: any) => (v === null || v === undefined || v === "" ? 0 : Number(v));
export const sum = <T,>(rows: T[], f: (r: T) => any) => rows.reduce((a, r) => a + n(f(r)), 0);

/** Reload whenever any part of the app changes data (prompt edits, new rows…). */
export function useDataReload(reload: () => void) {
  const ref = useRef(reload);
  ref.current = reload;
  useEffect(() => {
    const h = () => ref.current();
    window.addEventListener("hayah:data-changed", h);
    return () => window.removeEventListener("hayah:data-changed", h);
  }, []);
}

export function useMoney() {
  const { lang } = useI18n();
  return useMemo(() => {
    const f = new Intl.NumberFormat(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { maximumFractionDigits: 2 });
    return (v: any) => (v === null || v === undefined || v === "" ? "" : "$" + f.format(Number(v)));
  }, [lang]);
}

/** A money column that edits as a number and is sent to the API as a 2-decimal string. */
export function moneyCol<T>(field: string, header: string, editable: boolean, fmt: (v: any) => string, extra: Partial<ColDef<T>> = {}): ColDef<T> {
  return {
    field: field as any, headerName: header, editable: (p) => editable && !p.node.isRowPinned(), width: 115,
    cellDataType: "number", filter: "agNumberColumnFilter", cellClass: "num",
    valueGetter: (p: any) => (p.data?.[field] == null || p.data?.[field] === "" ? null : Number(p.data[field])),
    valueSetter: (p: any) => { p.data[field] = p.newValue == null ? null : String(p.newValue); return true; },
    valueFormatter: (p) => fmt(p.value), ...extra,
  };
}

export const dateCol = { cellDataType: "dateString" as const, filter: "agDateColumnFilter", width: 135 };

export function HayahGrid<T>({ rows, cols, totals, onEdit, rowClass, rowStyle, height, rowId, onCellDoubleClicked, gridRef }: {
  rows: T[]; cols: ColDef<T>[]; totals?: Partial<T>[]; onEdit?: (e: CellValueChangedEvent<T>) => void;
  rowClass?: (p: RowClassParams<T>) => string | undefined; rowStyle?: (p: RowClassParams<T>) => RowStyle | undefined;
  height?: string | number; rowId: (r: T) => string;
  onCellDoubleClicked?: (e: any) => void; gridRef?: React.MutableRefObject<GridApi<T> | null>;
}) {
  const { lang } = useI18n();
  return (
    <div className="ag-theme-quartz hayah-grid" style={{ height: height ?? "calc(100vh - 260px)", minHeight: 320 }}>
      <AgGridReact<T>
        rowData={rows}
        columnDefs={cols}
        defaultColDef={{ sortable: true, filter: true, resizable: true, floatingFilter: true, minWidth: 60, width: 130 }}
        getRowId={(p) => rowId(p.data)}
        enableRtl={lang === "ar"}
        pinnedBottomRowData={totals as any}
        getRowClass={(p) => (p.node.isRowPinned() ? "total-row" : rowClass?.(p))}
        getRowStyle={(p) => (p.node.isRowPinned() ? undefined : rowStyle?.(p))}
        singleClickEdit={false}
        stopEditingWhenCellsLoseFocus
        enterNavigatesVerticallyAfterEdit
        undoRedoCellEditing
        enableCellTextSelection
        suppressColumnVirtualisation
        onGridReady={(p) => { if (gridRef) gridRef.current = p.api; }}
        onCellValueChanged={(e) => { if (!e.node.isRowPinned() && e.oldValue !== e.newValue) onEdit?.(e); }}
        onCellDoubleClicked={onCellDoubleClicked}
        localeText={lang === "ar" ? AR_GRID : undefined}
      />
    </div>
  );
}

// Arabic labels for the grid's own menus and filters.
export const AR_GRID: Record<string, string> = {
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
