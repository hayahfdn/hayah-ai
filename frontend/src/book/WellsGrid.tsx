// Excel-style wells sheet. Used by the Master Sheet, each month's tab and each contractor tab.
// Every cell edit is a normal audited project update (validated, versioned, logged).
// Each row has its contractor's colour; on phones the same wells are shown as cards.
import { useCallback, useMemo, useRef, useState } from "react";
import type { CellValueChangedEvent, ColDef, GridApi } from "ag-grid-community";
import { useNavigate } from "react-router-dom";
import { api, Contractor, dataChanged, download, Project } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { contractorColor, deeper, useNarrow, wellTypeOptions } from "../look";
import { PlaqueButton } from "../plaque/PlaqueView";
import { ErrorBox, Field, Modal, Status, toast, useApi } from "../ui";
import ProjectForm from "../pages/ProjectForm";
import RecentChanges, { Change, undoChange } from "../admin/RecentChanges";
import { dateCol, HayahGrid, moneyCol, n, sum, useDataReload, useMoney } from "./grid";

const CONSTRUCTION = ["new_order", "scheduled", "in_progress", "completed", "on_hold", "cancelled"];
const PAYMENT = ["unpaid", "partial", "paid", "refunded"];
const VIDEO = ["none", "raw_received", "processing", "in_review", "completed"];
// Team members add orders and selling prices; costs and delivery approval stay with managers.
const STAFF_LOCKED = new Set(["cost", "delivery_date"]);
const CONTRACTOR_EDITABLE = new Set(["construction_status", "notes"]);

export default function WellsGrid({ month, contractorId, height, title }: { month?: string; contractorId?: number; height?: string; title?: string }) {
  const { t, st, lang } = useI18n();
  const { can, user, refreshCounts } = useAuth();
  const nav = useNavigate();
  const money = useMoney();
  const narrow = useNarrow();
  const [view, setView] = useState<"auto" | "table" | "cards">("auto");
  const cards = view === "cards" || (view === "auto" && narrow);
  const projects = useApi<{ items: Project[] }>("/api/projects", { page_size: 5000, sort: "well_id", month, contractor_id: contractorId });
  const contractors = useApi<Contractor[]>("/api/contractors");
  useDataReload(projects.reload);
  useDataReload(contractors.reload);
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
  const conById = useMemo(() => Object.fromEntries((contractors.data || []).map((c) => [c.id, c])), [contractors.data]);
  const colorOf = useCallback((p?: Project | null) => (p?.contractor_id ? contractorColor(conById[p.contractor_id] || p.contractor) : undefined), [conById]);
  const rows = projects.data?.items || [];

  const cols = useMemo<ColDef<Project>[]>(() => {
    const status = (opts: string[]) => ({ cellEditor: "agSelectCellEditor", cellEditorParams: { values: opts }, valueFormatter: (p: any) => (p.node?.isRowPinned() ? "" : st(p.value)) });
    const col = (field: keyof Project, extra: Partial<ColDef<Project>> = {}): ColDef<Project> => ({
      field, headerName: t(field as string), editable: (p) => editable(field as string) && !p.node.isRowPinned(), ...extra,
    });
    const showSale = !isContractor;  // selling price: everyone on the team
    const showMoney = manager;        // cost and profit: managers only
    const pin = lang === "ar" ? "right" : "left";
    const c: (ColDef<Project> | false)[] = [
      col("well_id", { editable: false, pinned: pin, width: 96, filter: "agNumberColumnFilter",
        cellClass: "wid cell-link", sort: "asc", valueFormatter: (p) => (p.node?.isRowPinned() ? t("total_row") : String(p.value ?? "")),
        cellClassRules: { "st-done": (p) => p.data?.delivery_status === "delivered", "st-wait": (p) => p.data?.construction_status === "completed" && p.data?.delivery_status !== "delivered" } }),
      { colId: "plaque", headerName: t("plaque_short"), pinned: pin, width: 66, minWidth: 60, editable: false, sortable: false, filter: false,
        floatingFilter: false, cellClass: "plaque-cell", headerTooltip: t("pl_create"),
        cellRenderer: (p: any) => (p.node.isRowPinned() || !p.data ? null
          : <PlaqueButton compact wellId={p.data.well_id} mediaId={p.data.plaque_media_id} approvedAt={p.data.plaque_approved_at} />) },
      col("order_date", dateCol), col("customer_name", { width: 180, cellClass: "strong" }),
      col("customer_phone", { width: 145, cellStyle: { direction: "ltr", textAlign: "end" } }),
      col("well_type", { width: 100, cellEditor: "agSelectCellEditor",
        cellEditorParams: (p: any) => ({ values: ["", ...wellTypeOptions(p.data?.well_type)] }) }),
      col("contractor_id", { headerName: t("contractor"), width: 120, cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: [null, ...(contractors.data || []).map((c) => c.id)] },
        valueFormatter: (p) => (p.node?.isRowPinned() ? "" : p.value ? conById[p.value]?.name || conById[p.value]?.code || String(p.value) : "—"),
        filterValueGetter: (p) => (p.data?.contractor_id ? conById[p.data.contractor_id]?.name : "") }),
      showSale && moneyCol<Project>("sale_amount", t("sale_amount"), manager || staff, money),
      showMoney && moneyCol<Project>("cost", t("cost"), manager, money),
      showMoney && { colId: "profit", headerName: t("profit"), editable: false, width: 105, cellClass: "num locked",
        valueGetter: (p) => (p.data?.sale_amount == null && p.data?.cost == null ? null : n(p.data?.sale_amount) - n(p.data?.cost)),
        valueFormatter: (p) => money(p.value), cellClassRules: { "neg": (p) => n(p.value) < 0 } },
      col("payment_status", { ...status(PAYMENT), width: 110 }), col("payment_method", { width: 125 }),
      col("extras", { width: 110 }), col("shopify_order", { width: 105 }), col("sales_source", { width: 120 }),
      col("dedication", { width: 200, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
      col("construction_status", { ...status(CONSTRUCTION), width: 130 }),
      col("delivery_status", { editable: false, width: 120, cellClass: "locked",
        cellRenderer: (p: any) => (p.node.isRowPinned() ? null : <Status v={p.value} />) }),
      col("delivery_date", { ...dateCol, headerTooltip: t("delivered_note"), cellClass: manager ? undefined : "locked", editable: (p) => manager && !p.node.isRowPinned() }),
      col("final_video_link", { width: 190 }), col("video_status", { ...status(VIDEO), width: 140 }),
      col("maintenance_status", { editable: false, valueFormatter: (p) => (p.node?.isRowPinned() ? "" : st(p.value)), cellClass: "locked", width: 115 }),
      col("next_maintenance_date", dateCol),
      col("notes", { width: 240, cellEditor: "agLargeTextCellEditor", cellEditorPopup: true }),
    ];
    return c.filter(Boolean) as ColDef<Project>[];
  }, [t, st, lang, editable, manager, staff, isContractor, contractors.data, conById, money]);

  const totals = useMemo(() => [{ id: -1, well_id: null as any, customer_name: `${rows.length} ${t("wells")}`,
    sale_amount: String(sum(rows, (r) => r.sale_amount)), cost: String(sum(rows, (r) => r.cost)) } as Partial<Project>], [rows, t]);

  const replace = useCallback((updated: Project) =>
    projects.setData((d) => d && { ...d, items: d.items.map((r) => (r.id === updated.id ? updated : r)) }), [projects]);

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
      if (field === "contractor_id") e.api.redrawRows({ rowNodes: [e.node] });  // new contractor, new row colour
      refreshCounts();
      replace(updated);
      if (["sale_amount", "cost", "contractor_id", "order_date"].includes(field)) dataChanged();  // refresh totals on other sheets
    } catch (err: any) {
      e.node.setData({ ...e.data, [field]: e.oldValue == null ? null : (field === "sale_amount" || field === "cost") ? String(e.oldValue) : e.oldValue });
      toast(`${t("well_id")} ${e.data.well_id}: ${err.message}`);
      if (err.status === 409) projects.reload();
    } finally { setSaving((x) => x - 1); }
  }, [t, refreshCounts, projects, replace]);

  const shown = useMemo(() => {
    const q = quick.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => [r.well_id, r.customer_name, r.well_type, r.dedication, r.notes, r.contractor_id && conById[r.contractor_id]?.name]
      .some((v) => v != null && String(v).toLowerCase().includes(q)));
  }, [rows, quick, conById]);

  return (
    <>
      <div className="toolbar">
        {title && <h2 style={{ margin: 0, marginInlineEnd: 8 }}>{title}</h2>}
        <input type="search" className="search" placeholder={t("search")} value={quick}
          onChange={(e) => { setQuick(e.target.value); gridRef.current?.setGridOption("quickFilterText", e.target.value); }} />
        <span className="muted save-state" aria-live="polite">{saving ? t("saving") : t("all_saved")}</span>
        <div className="seg" role="group" aria-label={t("view_table")}>
          <button className={!cards ? "on" : ""} onClick={() => setView("table")}>{t("view_table")}</button>
          <button className={cards ? "on" : ""} onClick={() => setView("cards")}>{t("view_cards")}</button>
        </div>
        {!cards && <button onClick={() => gridRef.current?.setFilterModel(null)}>{t("clear_filters")}</button>}
        {(manager || staff) && <button title={t("undo_last_help")} onClick={undoLast}>↶ {t("undo_last")}</button>}
        {(manager || staff) && <button className="hide-narrow" onClick={() => setHistory(true)}>{t("undo_title")}</button>}
        {manager && !month && !contractorId && <button className="hide-narrow" onClick={() => download("/api/projects/export.csv", "hayah-projects.csv")}>{t("export_csv")}</button>}
        {(manager || staff) && <button className="primary" onClick={() => setCreating(true)}>+ {t("new_project")}</button>}
      </div>
      <ErrorBox error={projects.error} />
      {cards
        ? <WellCards rows={shown} conById={conById} colorOf={colorOf} money={money} showSale={!isContractor} manager={manager}
            canEdit={manager || staff || isContractor} onChanged={(p) => { replace(p); refreshCounts(); dataChanged(); }} />
        : <HayahGrid<Project> rows={rows} cols={cols} totals={totals} onEdit={onEdit} height={height} gridRef={gridRef}
            rowId={(r) => String(r.id)}
            rowStyle={(p) => { const c = colorOf(p.data); return c ? { background: c } : undefined; }}
            onCellDoubleClicked={(e) => { if (e.colDef.field === "well_id" && e.data && !e.node.isRowPinned()) nav(`/projects/${e.data.well_id}`); }} />}
      {history && <Modal title={t("undo_title")} onClose={() => { setHistory(false); projects.reload(); }}>
        <RecentChanges mine={!manager} />
      </Modal>}
      {creating && <Modal title={t("new_project")} onClose={() => setCreating(false)}>
        <ProjectForm defaults={{ contractor_id: contractorId, order_date: month && !new Date().toISOString().startsWith(month) ? `${month}-01` : undefined }}
          onCancel={() => setCreating(false)} onSaved={() => { setCreating(false); projects.reload(); refreshCounts(); dataChanged(); }} />
      </Modal>}
    </>
  );
}

/** Phone view: one card per well with the most important details and every action. */
function WellCards({ rows, conById, colorOf, money, showSale, manager, canEdit, onChanged }: {
  rows: Project[]; conById: Record<number, Contractor>; colorOf: (p: Project) => string | undefined; money: (v: any) => string;
  showSale: boolean; manager: boolean; canEdit: boolean; onChanged: (p: Project) => void;
}) {
  const { t, fmtDate } = useI18n();
  const nav = useNavigate();
  const [editing, setEditing] = useState<Project | null>(null);
  const [delivering, setDelivering] = useState<Project | null>(null);
  const [limit, setLimit] = useState(60);
  if (!rows.length) return <div className="empty card">{t("no_items")}</div>;
  return <>
    <div className="cards-meta muted">{rows.length} {t("wells")}{showSale && <> · {money(sum(rows, (r) => r.sale_amount))}</>}</div>
    <ul className="well-cards">
      {rows.slice(0, limit).map((p) => {
        const bg = colorOf(p), con = p.contractor_id ? conById[p.contractor_id] || p.contractor : null;
        return (
          <li key={p.id} className="well-card" style={{ background: bg, borderInlineStartColor: deeper(bg) }}>
            <div className="wc-top">
              <button className="wc-id" onClick={() => nav(`/projects/${p.well_id}`)} aria-label={`${t("well_id")} ${p.well_id}`}>
                <span className="wid">{p.well_id}</span>{p.is_sample && <span className="badge">{t("sample")}</span>}</button>
              <PlaqueButton wellId={p.well_id} mediaId={p.plaque_media_id} approvedAt={p.plaque_approved_at} />
            </div>
            <div className="wc-name">{p.customer_name || "—"}</div>
            <div className="wc-meta">
              {p.well_type && <span className="chip-s">{p.well_type}</span>}
              {con && <span className="chip-s">{con.name}</span>}
              {p.order_date && <span className="muted">{fmtDate(p.order_date)}</span>}
            </div>
            <div className="wc-status">
              <Status v={p.construction_status} /><Status v={p.delivery_status} />{showSale && <Status v={p.payment_status} />}
              {showSale && p.sale_amount != null && <b className="num wc-money">{money(p.sale_amount)}</b>}
            </div>
            {p.dedication && <div className="wc-ded" dir="auto">{p.dedication}</div>}
            <div className="wc-actions">
              {canEdit && <button onClick={() => setEditing(p)}>{t("edit_row")}</button>}
              <button onClick={() => nav(`/projects/${p.well_id}`)}>{t("details")}</button>
              {manager && p.delivery_status !== "delivered" && <button onClick={() => setDelivering(p)}>{t("record_delivery")}</button>}
            </div>
          </li>);
      })}
    </ul>
    {rows.length > limit && <div className="actions" style={{ justifyContent: "center" }}><button onClick={() => setLimit(limit + 60)}>+ {rows.length - limit}</button></div>}
    {editing && <Modal title={`${t("edit")} · ${editing.well_id}`} onClose={() => setEditing(null)}>
      <ProjectForm project={editing} onCancel={() => setEditing(null)} onSaved={(np) => { setEditing(null); onChanged(np); toast(t("saved")); }} />
    </Modal>}
    {delivering && <DeliverModal p={delivering} onClose={() => setDelivering(null)} onDone={(np) => { setDelivering(null); onChanged(np); }} />}
  </>;
}

function DeliverModal({ p, onClose, onDone }: { p: Project; onClose: () => void; onDone: (p: Project) => void }) {
  const { t } = useI18n();
  const [d, setD] = useState(new Date().toISOString().slice(0, 10));
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    try { onDone(await api<Project>(`/api/finance/deliver/${p.well_id}`, { body: { delivery_date: d } })); toast(t("saved")); }
    catch (e: any) { setErr(e.message); }
  };
  return <Modal title={`${t("record_delivery")} · ${p.well_id}`} onClose={onClose}>
    <Field label={t("delivery_date_prompt")} hint={t("delivered_note")}><input type="date" value={d} onChange={(e) => setD(e.target.value)} /></Field>
    <ErrorBox error={err} />
    <div className="actions"><button onClick={onClose}>{t("cancel")}</button><button className="primary" disabled={!d} onClick={save}>{t("save")}</button></div>
  </Modal>;
}
