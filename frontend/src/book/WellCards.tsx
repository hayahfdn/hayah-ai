// Phone view of a wells sheet: one card per well with the important fields, no sideways scrolling.
// Everything else is one tap away (Edit opens the full form; "Table" shows the Excel-style grid).
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Contractor, Project } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { Modal, Status, toast } from "../ui";
import ProjectForm from "../pages/ProjectForm";
import PlaqueBadge from "../plaque/PlaqueBadge";
import { sum, useMoney } from "./grid";

const PAGE = 60;

export default function WellCards({ rows, quick, colorById, contractors, showSale, canEdit, isContractor, onSaved }: {
  rows: Project[]; quick: string; colorById: Record<number, string>; codeById: Record<number, string>; contractors: Contractor[];
  showSale: boolean; canEdit: boolean; isContractor: boolean; onSaved: (p: Project) => void;
}) {
  const { t, st, fmtDate, num } = useI18n();
  const { refreshCounts } = useAuth();
  const money = useMoney();
  const go = useNavigate();
  const [limit, setLimit] = useState(PAGE);
  const [editing, setEditing] = useState<Project | null>(null);
  const nameById = useMemo(() => Object.fromEntries(contractors.map((c) => [c.id, c.name])), [contractors]);
  const list = useMemo(() => {
    const q = quick.trim().toLowerCase();
    const sorted = [...rows].sort((a, b) => b.well_id - a.well_id);
    if (!q) return sorted;
    return sorted.filter((r) => [r.well_id, r.customer_name, r.dedication, r.well_type, r.customer_phone, r.shopify_order,
      r.contractor_id ? nameById[r.contractor_id] : ""].some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, quick, nameById]);

  const setStatus = async (p: Project, v: string) => {
    try {
      const u = await api<Project>(`/api/projects/${p.well_id}`, { method: "PATCH", body: { construction_status: v, expected_version: p.version } });
      onSaved(u); refreshCounts(); toast(t("saved"));
    } catch (e: any) { toast(e.message); }
  };

  return (
    <>
      <div className="cards-sum muted">
        <b>{num(list.length)}</b> {t("wells")}{showSale && <> · {money(sum(list, (r) => r.sale_amount))}</>}
      </div>
      <div className="well-cards">
        {list.slice(0, limit).map((p) => {
          const color = p.contractor_id ? colorById[p.contractor_id] : "";
          return (
            <article key={p.id} className="well-card" style={color ? { background: color } : undefined}
              onClick={() => go(`/projects/${p.well_id}`)}>
              <header>
                <span className="well-no">{p.well_id}</span>
                {p.well_type && <span className="chip">{p.well_type}</span>}
                <span className="grow" />
                <PlaqueBadge p={p} compact />
              </header>
              <div className="who">{p.customer_name || p.dedication || "—"}</div>
              <div className="meta">
                <span>{p.contractor_id ? nameById[p.contractor_id] || "—" : "—"}</span>
                <span>{fmtDate(p.order_date)}</span>
                {showSale && p.sale_amount != null && <span className="num strong">{money(p.sale_amount)}</span>}
              </div>
              <div className="badges"><Status v={p.construction_status} /> <Status v={p.delivery_status} />
                {p.payment_status !== "paid" && <Status v={p.payment_status} />}</div>
              <footer onClick={(e) => e.stopPropagation()}>
                {isContractor && <select value={p.construction_status} onChange={(e) => setStatus(p, e.target.value)} aria-label={t("construction_status")}>
                  {["new_order", "scheduled", "in_progress", "completed", "on_hold"].map((s) => <option key={s} value={s}>{st(s)}</option>)}</select>}
                {canEdit && <button onClick={() => setEditing(p)}>{t("edit")}</button>}
                <button onClick={() => go(`/projects/${p.well_id}`)}>{t("open")}</button>
              </footer>
            </article>
          );
        })}
      </div>
      {list.length > limit && <div className="actions" style={{ justifyContent: "center" }}>
        <button onClick={() => setLimit((l) => l + PAGE)}>{t("show_more")} ({list.length - limit})</button></div>}
      {editing && <Modal title={`${t("edit")} · ${editing.well_id}`} onClose={() => setEditing(null)}>
        <ProjectForm project={editing} onCancel={() => setEditing(null)} onSaved={(u) => { setEditing(null); onSaved(u); refreshCounts(); toast(t("saved")); }} />
      </Modal>}
    </>
  );
}
