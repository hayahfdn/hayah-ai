import { Fragment, useState } from "react";
import { api } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, toast, useApi } from "../ui";

interface Status {
  token: { set: boolean; last4: string | null }; profile_name: string | null; last_sync: string | null; last_error: string | null;
  counts: { unmatched: number; matched: number; ignored: number }; recipient_contractors: Record<string, string>;
}
interface Row {
  id: number; at: string; direction: string; amount: string; currency: string; usd_amount: string | null; counterparty: string | null;
  description: string | null; category: string; contractor: string | null; match_status: string; transaction_id: number | null;
}
interface Cand { id: number; date: string; amount: string; kind: string; description: string | null }

/** Settings > Wise (read only): connect with a read only token, sync, review what did not match the ledger. */
export default function WiseSettings() {
  const { t, num } = useI18n();
  const { user } = useAuth();
  const st = useApi<Status>("/api/wise/status");
  const [tab, setTab] = useState<"unmatched" | "matched" | "ignored">("unmatched");
  const rows = useApi<Row[]>("/api/wise/transactions", { status: tab });
  const [token, setToken] = useState("");
  const [map, setMap] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [cands, setCands] = useState<Cand[]>([]);
  const [busy, setBusy] = useState(false);
  if (!st.data) return <ErrorBox error={st.error} />;
  const s = st.data;
  const run = async (fn: () => Promise<any>, ok?: string) => {
    setBusy(true);
    try { const r = await fn(); if (ok) toast(typeof ok === "string" ? ok : String(r)); st.reload(); rows.reload(); return r; }
    catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const mapText = map ?? Object.entries(s.recipient_contractors).map(([k, v]) => `${k} = ${v}`).join("\n");
  const money = (r: Row) => `${r.direction === "in" ? "+" : r.direction === "out" ? "−" : ""}${num(Number(r.amount))} ${r.currency}` +
    (r.currency !== "USD" && r.usd_amount ? ` (${num(Number(r.usd_amount))} USD)` : "");
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Wise</h2>
      <p className="muted">{t("wise_intro")}</p>
      {s.token.set
        ? <p>✅ {t("wise_connected")}: <b>{s.profile_name || "—"}</b> · {t("wise_last_sync")}: {s.last_sync ? new Date(s.last_sync).toLocaleString() : "—"}</p>
        : <div className="banner">{t("wise_not_connected")}</div>}
      {s.last_error && <div className="banner">{s.last_error}</div>}
      {user.role === "super_admin" && <details open={!s.token.set} style={{ margin: "10px 0" }}>
        <summary>{t("wise_token")}{s.token.set && s.token.last4 ? ` (…${s.token.last4})` : ""}</summary>
        <ol className="muted" style={{ fontSize: 13 }}>
          <li>{t("wise_step1")}</li><li>{t("wise_step2")}</li><li>{t("wise_step3")}</li>
        </ol>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder={t("wise_token_ph")} style={{ flex: 1, minWidth: 220 }} />
          <button className="primary" disabled={busy || token.trim().length < 10}
            onClick={() => run(() => api("/api/wise/token", { method: "PUT", body: { token } }), t("saved")).then(() => setToken(""))}>{t("save")}</button>
          {s.token.set && <button disabled={busy} onClick={() => run(() => api("/api/wise/token", { method: "PUT", body: { token: null } }), t("wise_disconnected"))}>{t("wise_disconnect")}</button>}
        </div>
      </details>}
      {s.token.set && <button className="primary" disabled={busy}
        onClick={() => run(async () => { const r = await api<any>("/api/wise/sync", { body: {} }); toast(`${t("wise_new")}: ${num(r.new)} · ${t("wise_auto")}: ${num(r.auto_matched)}`); })}>
        ↻ {t("wise_sync_now")}</button>}

      <h3>{t("wise_recipients")}</h3>
      <p className="muted" style={{ fontSize: 13 }}>{t("wise_recipients_note")}</p>
      <textarea rows={4} value={mapText} onChange={(e) => setMap(e.target.value)} placeholder="Ghaidaa Sabbah = UK1" style={{ width: "100%" }} />
      <button disabled={busy || map === null} onClick={() => run(() => api("/api/wise/recipients", {
        method: "PUT", body: { recipient_contractors: Object.fromEntries(mapText.split("\n").map((l) => l.split("=").map((x) => x.trim())).filter((p) => p.length === 2 && p[0] && p[1])) },
      }), t("saved")).then(() => setMap(null))}>{t("save")}</button>

      <h3>{t("wise_list")}</h3>
      <div className="seg" role="tablist">
        {(["unmatched", "matched", "ignored"] as const).map((k) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t("wise_" + k)} ({num(s.counts[k])})</button>)}
      </div>
      <ErrorBox error={rows.error} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("date")}</th><th>{t("wise_who")}</th><th>{t("amount")}</th><th>{t("wise_cat")}</th><th /></tr></thead>
        <tbody>{(rows.data || []).map((r) => <Fragment key={r.id}>
          <tr>
            <td>{new Date(r.at).toLocaleDateString()}</td>
            <td>{r.counterparty}{r.description ? <div className="muted" style={{ fontSize: 12 }}>{r.description}</div> : null}</td>
            <td dir="ltr" style={{ whiteSpace: "nowrap" }}>{money(r)}</td>
            <td>{t("wcat_" + r.category)}{r.contractor ? ` · ${r.contractor}` : ""}</td>
            <td style={{ whiteSpace: "nowrap" }}>
              {r.match_status === "unmatched" && <>
                <button className="sm" disabled={busy} onClick={async () => { setOpen(open === r.id ? null : r.id); setCands(await api<Cand[]>(`/api/wise/transactions/${r.id}/candidates`)); }}>{t("wise_match")}</button>{" "}
                <button className="sm" disabled={busy || !r.usd_amount} onClick={() => run(() => api(`/api/wise/transactions/${r.id}/record`, { body: {} }), t("wise_recorded"))}>{t("wise_record")}</button>{" "}
                <button className="sm ghost" disabled={busy} onClick={() => run(() => api(`/api/wise/transactions/${r.id}/ignore`, { body: {} }))}>{t("wise_ignore")}</button>
              </>}
              {r.match_status === "matched" && <button className="sm ghost" disabled={busy} onClick={() => run(() => api(`/api/wise/transactions/${r.id}/unmatch`, { body: {} }))}>{t("wise_unmatch")} #{r.transaction_id}</button>}
              {r.match_status === "ignored" && <button className="sm ghost" disabled={busy} onClick={() => run(() => api(`/api/wise/transactions/${r.id}/ignore?undo=true`, { body: {} }))}>↺</button>}
            </td>
          </tr>
          {open === r.id && <tr><td colSpan={5}>
            {cands.length === 0 ? <span className="muted">{t("wise_no_cands")}</span> : cands.map((c) => (
              <div key={c.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0" }}>
                <span>#{c.id} · {c.date} · <b>{num(Number(c.amount))}</b> USD · {c.description || c.kind}</span>
                <button className="sm primary" disabled={busy} onClick={() => run(() => api(`/api/wise/transactions/${r.id}/match`, { body: { transaction_id: c.id } }), t("saved")).then(() => setOpen(null))}>{t("wise_this_one")}</button>
              </div>))}
          </td></tr>}
        </Fragment>)}</tbody>
      </table></div>
      {rows.data && rows.data.length === 0 && <p className="muted">{t("wise_empty")}</p>}
    </div>
  );
}
