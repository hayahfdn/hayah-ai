import { Link } from "react-router-dom";
import { api } from "../api";
import { EDITORS, MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Status, toast, useApi } from "../ui";
import * as I from "../icons";
import { Sparkline } from "../icons";
import { countryLabel, thisMonth, useLinks } from "../nav";

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

type Trend = { months: string[]; orders: number[]; completed: number[]; delivered: number[]; sacrifices: number[] };
const last = (a: number[] = []) => a[a.length - 1] || 0;
const prev = (a: number[] = []) => a[a.length - 2] || 0;

/** A KPI card in the dashboard style: coloured round icon, number, label, change from last month and a small chart. */
export function KpiCard({ icon: C, tone, value, label, to, trend, delta, sub }: {
  icon: I.IconC; tone: string; value: string; label: string; to?: string; trend?: number[]; delta?: number | null; sub?: string;
}) {
  const { t } = useI18n();
  const body = <>
    <div className="kpi-top">
      <span className={`kpi-ico tone-${tone}`} aria-hidden="true"><C size={20} strokeWidth={2} /></span>
      <div className="kpi-txt">
        <div className="kpi-val">{value}{delta != null && <span className={`delta ${delta > 0 ? "up" : delta < 0 ? "down" : ""}`}
          title={t("dash_vs_last")}>{delta > 0 ? "+" : ""}{delta}</span>}</div>
        <div className="kpi-lbl">{label}</div>
        {sub && <div className="kpi-sub">{sub}</div>}
      </div>
    </div>
    {trend && <div className={`kpi-spark tone-${tone}`}><Sparkline values={trend} color="currentColor" /></div>}
  </>;
  return to ? <Link to={to} className="card kpi2">{body}</Link> : <div className="card kpi2">{body}</div>;
}

/** Status split as a ring with a legend (no chart library). */
function Donut({ rows }: { rows: { label: string; value: number; color: string }[] }) {
  const { num } = useI18n();
  const total = rows.reduce((a, r) => a + r.value, 0) || 1;
  let acc = 0;
  const R = 42, L = 2 * Math.PI * R;
  return <div className="donut-wrap">
    <svg viewBox="0 0 110 110" className="donut" role="img" aria-label={rows.map((r) => `${r.label} ${r.value}`).join(", ")}>
      <circle cx="55" cy="55" r={R} fill="none" stroke="var(--surface-2)" strokeWidth="14" />
      {rows.map((r) => { const len = (r.value / total) * L; const el = <circle key={r.label} cx="55" cy="55" r={R} fill="none" stroke={r.color}
        strokeWidth="14" strokeDasharray={`${len} ${L - len}`} strokeDashoffset={-acc} transform="rotate(-90 55 55)" />; acc += len; return el; })}
      <text x="55" y="60" textAnchor="middle" className="donut-n">{num(total)}</text>
    </svg>
    <ul className="donut-legend">{rows.map((r) => <li key={r.label}><i style={{ background: r.color }} />{r.label}<b>{num(r.value)}</b></li>)}</ul>
  </div>;
}

const STATUS_COLORS: Record<string, string> = { new_order: "#6f4ef2", scheduled: "#2f7cf6", in_progress: "#f2a516", completed: "#19b3a6",
  on_hold: "#8a8ea8", cancelled: "#e5487f" };

export default function Dashboard() {
  const { t, num, fmtDate, st, lang } = useI18n();
  const { user, can } = useAuth();
  const links = useLinks();
  const { data, error, reload } = useApi<any>("/api/dashboard");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <p className="muted">{t("loading")}</p>;
  const k = data.kpis;
  const tr: Trend | undefined = data.trend;
  const d = (a?: number[]) => (a ? last(a) - prev(a) : null);
  const first = (user.full_name || "").split(/\s+/)[0];
  const small: [string, number, I.IconC, string, string?, boolean?][] = [
    ["new_orders", k.new_orders, I.Inbox, "violet", "/projects?construction_status=new_order"],
    ["completed", k.completed, I.CircleCheck, "teal", "/projects?construction_status=completed"],
    ["pending_delivery", k.pending_delivery, I.Truck, "amber", "/delivery"],
    ["videos_processing", k.videos_processing, I.Film, "blue"],
    ["videos_completed", k.videos_completed, I.Clapperboard, "green"],
    ["maintenance_cases", k.maintenance_cases, I.Wrench, "pink", "/maintenance", k.maintenance_cases > 0],
    ...(can(...MANAGERS) ? [["pending_review", k.pending_review, I.ClipboardCheck, "pink", "/review", k.pending_review > 0] as any] : []),
  ];
  const maxC = Math.max(1, ...data.by_country.map((r: any) => r.count));
  return (
    <>
      <div className="page-head">
        <div><h1>{t("dash_hello")}{first ? ` ${first}` : ""} 👋</h1><p className="muted">{t("dash_sub")}</p></div>
        <SyncPill s={data.sheets} onSynced={reload} />
      </div>
      <div className="hero-kpis">
        <KpiCard icon={I.Droplets} tone="violet" value={num(tr ? last(tr.orders) : k.total_projects)} label={t("dash_orders_month")}
          sub={`${t("total_projects")}: ${num(k.total_projects)}`} to="/projects" trend={tr?.orders} delta={d(tr?.orders)} />
        <KpiCard icon={I.HardHat} tone="blue" value={num(k.in_progress)} label={t("in_progress")}
          sub={`${t("dash_finished_month")}: ${num(tr ? last(tr.completed) : 0)}`} to="/construction" trend={tr?.completed} />
        <KpiCard icon={I.Truck} tone="pink" value={num(tr ? last(tr.delivered) : k.delivered)} label={t("dash_delivered_month")}
          sub={`${t("delivered")}: ${num(k.delivered)}`} to="/delivery" trend={tr?.delivered} delta={d(tr?.delivered)} />
        <KpiCard icon={I.Sheep} tone="teal" value={num(tr ? last(tr.sacrifices) : 0)} label={t("dash_sac_month")}
          to={can(...EDITORS) ? links.sac(thisMonth()) : undefined} trend={tr?.sacrifices} delta={d(tr?.sacrifices)} />
      </div>
      <FlowCards />
      <div className="mini-kpis">
        {small.map(([key, v, C, tone, to, attn]) => {
          const body = <><span className={`kpi-ico sm tone-${tone}`} aria-hidden="true"><C size={17} /></span>
            <span className="mini-lbl">{t(key)}</span><b className="mini-val">{num(v)}</b></>;
          return to ? <Link key={key} to={to} className={`mini ${attn ? "attn" : ""}`}>{body}</Link>
            : <div key={key} className={`mini ${attn ? "attn" : ""}`}>{body}</div>;
        })}
      </div>
      <div className="dash-grid">
        <div className="card">
          <div className="card-h"><h2>{t("by_country")}</h2><span className="muted">{t("dash_country_sub")}</span></div>
          <ul className="country-bars">{data.by_country.slice(0, 8).map((r: any, i: number) => (
            <li key={r.country}><div className="cb-top"><span>{countryLabel(r.country, lang)}</span><b>{num(r.count)}</b></div>
              <div className="cb-bar"><i className={`tone-bg-${["violet", "blue", "teal", "pink", "amber", "green"][i % 6]}`} style={{ width: `${(100 * r.count) / maxC}%` }} /></div></li>))}</ul>
        </div>
        <div className="card">
          <div className="card-h"><h2>{t("by_status")}</h2></div>
          <Donut rows={data.by_construction_status.map((r: any) => ({ label: st(r.status), value: r.count, color: STATUS_COLORS[r.status] || "#8a8ea8" }))} />
        </div>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-h"><h2>{t("recent_activity")}</h2></div>
        <ul className="activity">
          {data.recent_activity.map((e: any, i: number) => (
            <li key={i}><span className="act-dot" aria-hidden="true" />
              <div><Link to={`/projects/${e.well_id}`} className="well-no">#{e.well_id}</Link> · {e.summary || e.event_type}
                <div className="muted act-meta">{fmtDate(e.created_at)} · {e.actor_label} · {e.source}</div></div></li>
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
  const p = ops.plaques, v = ops.videos || {}, o = ops.orders || ({} as Record<string, number>);
  const cards: [string, number, "red" | "orange" | "green", string][] = [
    ["dash_new", o.new || 0, "red", "/projects?construction_status=new_order"],
    ["dash_confirm", (p.draft || 0) + (p.ready_for_review || 0) + (p.needs_changes || 0), "red", "/plaques/confirm"],
    ["dash_customer", p.awaiting_customer || 0, "orange", "/plaques/confirm"],
    // approved and waiting for the contractor is the manager's step: employees do not see these two cards
    ...(can(...MANAGERS) ? [["dash_contractor", p.ready_for_contractor || 0, "red", "/plaques/approved"] as [string, number, "red", string],
      ["dash_sent_con", p.sent_to_contractor || 0, "green", "/plaques/approved"] as [string, number, "green", string]] : []),
    ["dash_wait_video", v.waiting_upload || 0, "orange", "/videos"],
    ["dash_video_ready", (v.ready_for_delivery || 0) + (v.uploaded || 0), "red", "/videos"],
    ...(ops.whatsapp?.enabled ? [["wa_unread_msgs", ops.whatsapp.unread_messages || 0, "red", "/inbox"] as [string, number, "red", string],
      ["wa_waiting_chats", ops.whatsapp.waiting_reply || 0, "orange", "/inbox"] as [string, number, "orange", string]] : []),
  ];
  return <section className="card flow-sec">
    <div className="flow-head"><h2 style={{ margin: 0 }}>{t("dash_flow")}</h2><span className="muted">{t("dash_legend")}</span></div>
    <div className="grid kpis flow-cards">
      {cards.map(([key, n, tone, to]) => (
        <Link key={key} to={to} className={`card kpi flow ${n === 0 && tone !== "green" ? "green" : tone}`} style={{ color: "inherit", textDecoration: "none" }}>
          <div className="label">{t(key)}</div><div className="value">{num(n)}</div></Link>))}
    </div>
  </section>;
}

export { Status };
