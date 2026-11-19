import { Link } from "react-router-dom";
import { api } from "../api";
import { EDITORS, MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { Bars, ErrorBox, Status, toast, useApi } from "../ui";

export function SyncPill({ s, onSynced }: { s: any; onSynced?: () => void }) {
  const { t, fmtDate } = useI18n();
  const { can } = useAuth();
  const run = async () => {
    try { await api("/api/sync/run", { method: "POST" }); toast(t("synced")); onSynced?.(); }
    catch (e: any) { toast(e.message); onSynced?.(); }
  };
  const label = { synced: t("synced"), pending: t("pending"), error: t("error"), conflicts: t("conflicts") }[s.state as string] || s.state;
  return (
    <div className="card sync-pill">
      <b>{t("sheets_status")}</b>
      <span className={`badge ${s.state === "synced" ? "ok" : s.state === "error" ? "bad" : "warn"}`}>{label}</span>
      <span className="muted">{t("last_sync")}: {s.last_success_at ? fmtDate(s.last_success_at) + " " + new Date(s.last_success_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : t("never")}</span>
      {s.backend === "mock" && <span className="badge">{t("mock")}</span>}
      {can(...MANAGERS) && <button className="sm" onClick={run}>{t("sync_now")}</button>}
    </div>
  );
}

export default function Dashboard() {
  const { t, num, fmtDate } = useI18n();
  const { data, error, reload } = useApi<any>("/api/dashboard");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <p className="muted">{t("loading")}</p>;
  const k = data.kpis;
  const tiles: [string, number, boolean?, string?][] = [
    ["total_projects", k.total_projects, false, "/projects"], ["new_orders", k.new_orders, false, "/projects?construction_status=new_order"],
    ["in_progress", k.in_progress, false, "/construction"], ["completed", k.completed, false, "/projects?construction_status=completed"],
    ["delivered", k.delivered], ["pending_delivery", k.pending_delivery, false, "/delivery"],
    ["videos_processing", k.videos_processing], ["videos_completed", k.videos_completed],
    ["maintenance_cases", k.maintenance_cases, k.maintenance_cases > 0, "/maintenance"],
    ["pending_review", k.pending_review, k.pending_review > 0, "/review"],
  ];
  return (
    <>
      <div className="topbar"><h1>{t("nav_dashboard")}</h1><SyncPill s={data.sheets} onSynced={reload} /></div>
      <FlowCards />
      <div className="grid kpis">
        {tiles.map(([key, v, attn, to]) => {
          const body = <><div className="label">{t(key)}</div><div className="value">{num(v)}</div></>;
          return to ? <Link key={key} to={to} className={`card kpi ${attn ? "attn" : ""}`} style={{ color: "inherit", textDecoration: "none" }}>{body}</Link>
            : <div key={key} className={`card kpi ${attn ? "attn" : ""}`}>{body}</div>;
        })}
      </div>
      <div className="grid two" style={{ marginTop: 14 }}>
        <div className="card"><h2>{t("by_country")}</h2><Bars rows={data.by_country.map((r: any) => ({ label: r.country, value: r.count }))} /></div>
        <div className="card"><h2>{t("by_status")}</h2><BarsStatus rows={data.by_construction_status} /></div>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <h2>{t("recent_activity")}</h2>
        <ul className="timeline">
          {data.recent_activity.map((e: any, i: number) => (
            <li key={i}><span className="muted">{fmtDate(e.created_at)}</span>
              <span><Link to={`/projects/${e.well_id}`} className="mono">#{e.well_id}</Link> · {e.summary || e.event_type} <span className="muted">· {e.actor_label} · {e.source}</span></span></li>
          ))}
        </ul>
      </div>
    </>
  );
}

/** The order workflow at a glance, live (re-read every 10 s with the menu counts). No money.
 * Red: needs action. Orange: in progress. Green: done, or nothing waiting. */
function FlowCards() {
  const { t, num } = useI18n();
  const { can, ops } = useAuth();
  if (!can(...EDITORS) || !ops.plaques) return null;
  const p = ops.plaques, v = ops.videos || {}, o = ops.orders || {};
  const cards: [string, number, "red" | "orange" | "green", string][] = [
    ["dash_new", o.new || 0, "red", "/projects?construction_status=new_order"],
    ["dash_confirm", (p.draft || 0) + (p.ready_for_review || 0) + (p.needs_changes || 0), "red", "/plaques/confirm"],
    ["dash_customer", p.awaiting_customer || 0, "orange", "/plaques/confirm"],
    ["dash_contractor", p.ready_for_contractor || 0, "red", "/plaques/approved"],
    ["dash_sent_con", p.sent_to_contractor || 0, "green", "/plaques/approved"],
    ["dash_wait_video", v.waiting_upload || 0, "orange", "/videos"],
    ["dash_video_ready", (v.ready_for_delivery || 0) + (v.uploaded || 0), "red", "/videos"],
  ];
  return <section style={{ marginBottom: 14 }}>
    <div className="flow-head"><h2 style={{ margin: 0 }}>{t("dash_flow")}</h2><span className="muted">{t("dash_legend")}</span></div>
    <div className="grid kpis flow-cards">
      {cards.map(([key, n, tone, to]) => (
        <Link key={key} to={to} className={`card kpi flow ${n === 0 && tone !== "green" ? "green" : tone}`} style={{ color: "inherit", textDecoration: "none" }}>
          <div className="label">{t(key)}</div><div className="value">{num(n)}</div></Link>))}
    </div>
  </section>;
}

function BarsStatus({ rows }: { rows: any[] }) {
  const { st } = useI18n();
  return <Bars rows={rows.map((r) => ({ label: st(r.status), value: r.count }))} />;
}

export { Status };
