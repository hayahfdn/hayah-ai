import { Link } from "react-router-dom";
import { api, Project } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, toast, useApi } from "../ui";
import { contractorColor } from "../look";

const COLS = ["new_order", "scheduled", "in_progress", "on_hold", "completed"];

export default function Construction() {
  const { t, st, fmtDate } = useI18n();
  const { can, refreshCounts } = useAuth();
  const { data, error, reload } = useApi<{ items: Project[] }>("/api/projects", { page_size: 500, sort: "-updated_at" });
  const move = async (p: Project, s: string) => {
    try { await api(`/api/projects/${p.well_id}`, { method: "PATCH", body: { construction_status: s, expected_version: p.version } }); toast(t("saved")); reload(); refreshCounts(); }
    catch (e: any) { toast(e.message); }
  };
  const canEdit = can("super_admin", "operations_manager", "contractor");
  return (
    <>
      <div className="topbar"><h1>{t("nav_construction")}</h1></div>
      <ErrorBox error={error} />
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", alignItems: "start" }}>
        {COLS.map((c) => {
          const items = (data?.items || []).filter((p) => p.construction_status === c);
          return (
            <div className="card" key={c} style={{ background: "var(--surface-2)" }}>
              <h3>{st(c)} <span className="muted">({items.length})</span></h3>
              <div className="grid" style={{ gap: 8 }}>
                {items.map((p) => (
                  <div className="card" key={p.id} style={{ padding: 10, background: contractorColor(p.contractor) || undefined }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
                      <Link to={`/projects/${p.well_id}`} className="wid">#{p.well_id}</Link>
                      <span className="muted">{p.contractor?.code || "—"}</span>
                    </div>
                    <div style={{ fontSize: 13.5, fontWeight: 600 }}>{p.customer_name || "—"}</div>
                    <div className="muted" style={{ fontSize: 12.5 }}>{[p.well_type, p.contractor?.name, fmtDate(p.order_date)].filter((x) => x && x !== "—").join(" · ")}</div>
                    {canEdit && <select style={{ marginTop: 6, width: "100%" }} value={c} onChange={(e) => move(p, e.target.value)} aria-label={t("construction_status")}>
                      {[...COLS, "cancelled"].map((s) => <option key={s} value={s}>{st(s)}</option>)}</select>}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
