import { useState } from "react";
import { api, dataChanged } from "../api";
import { useI18n } from "../i18n";
import { monthLabel } from "../nav";
import { ErrorBox, toast, useApi } from "../ui";

type Row = { month: string; wells: number; sacrifices: number; real_date: number; estimated_date: number };
interface Preview {
  before: string; months: Row[]; totals: Omit<Row, "month">; skipped: Record<string, number>;
  history: { id: number; created_at: string; count: number; undone_at: string | null }[];
}

/** Settings > Old projects delivered: counts first; nothing changes until a manager confirms; undo any time. */
export default function OldDelivered() {
  const { t, num, lang } = useI18n();
  const pv = useApi<Preview>("/api/bulk/old-delivered/preview");
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!pv.data) return <ErrorBox error={pv.error} />;
  const d = pv.data, total = d.totals.wells + d.totals.sacrifices;
  const run = async (path: string, body?: any) => {
    setBusy(true);
    try {
      const r = await api<any>(path, { body: body ?? {} });
      toast(r.restored !== undefined ? `${t("od_undone")}: ${num(r.restored)}` : `${t("od_done")}: ${num(r.changed)}`);
      setOk(false); pv.reload(); dataChanged();
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>{t("od_title")}</h2>
      <p className="muted">{t("od_intro").replace("{d}", monthLabel(d.before.slice(0, 7), lang))}</p>
      {total === 0 ? <p><b>{t("od_none")}</b></p> : <>
        <table>
          <thead><tr><th>{t("od_month")}</th><th>{t("od_wells")}</th><th>{t("od_sacs")}</th><th>{t("od_real")}</th><th>{t("od_est")}</th></tr></thead>
          <tbody>
            {d.months.map((r) => <tr key={r.month}><td>{monthLabel(r.month, lang)}</td><td>{num(r.wells)}</td><td>{num(r.sacrifices)}</td>
              <td>{num(r.real_date)}</td><td>{r.estimated_date ? <span className="badge warn">{num(r.estimated_date)}</span> : 0}</td></tr>)}
            <tr><td><b>{t("od_total")}</b></td><td><b>{num(d.totals.wells)}</b></td><td><b>{num(d.totals.sacrifices)}</b></td>
              <td><b>{num(d.totals.real_date)}</b></td><td><b>{num(d.totals.estimated_date)}</b></td></tr>
          </tbody>
        </table>
        {Object.keys(d.skipped).length > 0 && <p className="muted">{t("od_skipped")}: {Object.entries(d.skipped).map(([k, v]) => `${t("od_" + k)} ${num(v)}`).join(" · ")}</p>}
        <label style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
          <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />
          {t("od_confirm").replace("{w}", num(d.totals.wells)).replace("{s}", num(d.totals.sacrifices))}
        </label>
        <button className="primary" disabled={!ok || busy}
          onClick={() => run("/api/bulk/old-delivered/apply", { wells: d.totals.wells, sacrifices: d.totals.sacrifices, confirm: true })}>{t("od_apply")}</button>
      </>}
      {d.history.length > 0 && <>
        <h3>{t("od_history")}</h3>
        <ul>{d.history.map((h) => <li key={h.id}>{new Date(h.created_at).toLocaleString()} · {num(h.count)}
          {h.undone_at ? <span className="muted"> · {t("od_was_undone")}</span>
            : <button className="sm" style={{ marginInlineStart: 8 }} disabled={busy} onClick={() => run(`/api/bulk/old-delivered/${h.id}/undo`)}>↺ {t("od_undo")}</button>}</li>)}</ul>
      </>}
    </div>
  );
}
