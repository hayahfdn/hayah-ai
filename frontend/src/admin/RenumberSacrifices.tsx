// Settings → Sacrifice numbers: change several sacrifice numbers and link them to their orders.
// Preview shows every row before/after and changes nothing; Apply runs it in one go; Undo puts it back.
import { useState } from "react";
import { api, download } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, toast, useApi } from "../ui";

type Rename = { from: string; to: string };
type OrderRow = { order: string; numbers: string };
type Row = { id: number; before_no: number; after_no: number; before_order: string | null; after_order: string | null; donor_name: string | null;
  animal_type: string | null; order_date: string | null; sale_price: string | null; parent_well_id: number | null; changes: boolean };
type Check = { ok: boolean; duplicates: number[]; orders: { order: string; expected: number[]; actual: number[]; ok: boolean; elsewhere: { number: number; order: string | null; missing: boolean }[] }[] };
type Preview = { ok: boolean; errors: string[]; rows: Row[]; untouched_nearby: any[]; token: string };

const NOV20_RENAMES: Rename[] = [{ from: "3098", to: "3091" }, { from: "3099", to: "3092" }, { from: "3100", to: "3096" }];
const NOV20_ORDERS: OrderRow[] = [{ order: "1231", numbers: "3097, 3098" }, { order: "1229", numbers: "3096" },
  { order: "1228", numbers: "3094, 3095" }, { order: "1227", numbers: "3093" }, { order: "1225", numbers: "3091, 3092" }];

export default function RenumberSacrifices() {
  const { t, fmtDate, money, lang } = useI18n();
  const arrow = lang === "ar" ? "←" : "→";
  const [renames, setRenames] = useState<Rename[]>([{ from: "", to: "" }]);
  const [orders, setOrders] = useState<OrderRow[]>([{ order: "", numbers: "" }]);
  const [p, setP] = useState<Preview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [check, setCheck] = useState<Check | null>(null);
  const [kept, setKept] = useState<{ batch: number; rows: number } | null>(null);
  const hist = useApi<{ id: number; at: string; by: string; changed: any[]; undone: boolean }[]>("/api/sacrifices/renumber/history");
  const body = () => ({
    renames: renames.filter((r) => r.from && r.to).map((r) => ({ from: Number(r.from), to: Number(r.to) })),
    orders: orders.filter((o) => o.order && o.numbers).map((o) => ({ order: o.order.replace(/\D/g, ""),
      numbers: o.numbers.split(/[^\d]+/).filter(Boolean).map(Number) })),
  });
  const edit = () => setP(null);
  const preview = async () => {
    setErr(null); setBusy(true);
    try { setP(await api<Preview>("/api/sacrifices/renumber/preview", { body: body() })); }
    catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  const apply = async () => {
    if (!p || !window.confirm(t("ren_confirm"))) return;
    setBusy(true);
    try {
      const r = await api<any>("/api/sacrifices/renumber/apply", { body: { ...body(), token: p.token } });
      toast(`${t("ren_done")}: ${r.changed}`); setP(null); hist.reload();
      setCheck(r.verify || null); setKept({ batch: r.batch_id, rows: r.backup_rows });
      if ((r.plaque_image_old_number || []).length) setErr(`${t("num_plaque_old")} ${r.plaque_image_old_number.join(", ")}`);
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  const undo = async (id: number) => {
    try { await api(`/api/sacrifices/renumber/undo/${id}`, { method: "POST" }); toast(t("ren_undone")); hist.reload(); setP(null); }
    catch (x: any) { setErr(x.message); }
  };
  const verify = async () => {
    setErr(null);
    try { setCheck(await api<Check>("/api/sacrifices/renumber/verify", { body: body() })); } catch (x: any) { setErr(x.message); }
  };
  const diff = (a: any, b: any) => (String(a ?? "") !== String(b ?? "") ? "changed" : "");
  return <div className="card">
    <h2 style={{ marginTop: 0 }}>{t("ren_title")}</h2>
    <p className="muted">{t("ren_help")}</p>
    <div className="actions" style={{ justifyContent: "flex-start" }}>
      <button onClick={() => { setRenames(NOV20_RENAMES); setOrders(NOV20_ORDERS); edit(); setCheck(null); }}>{t("ren_fill_20nov")}</button>
      <button onClick={() => download("/api/sacrifices/backup.csv", `sacrifices-backup-${new Date().toISOString().slice(0, 10)}.csv`)}>⬇ {t("ren_backup_now")}</button>
      <button onClick={verify}>✓ {t("ren_verify")}</button></div>
    <p className="muted" style={{ fontSize: 13 }}>{t("ren_backup_help")}</p>
    <div className="ren-cols">
      <div><h3>{t("ren_renames")}</h3>
        <table><thead><tr><th>{t("ren_from")}</th><th></th><th>{t("ren_to")}</th></tr></thead><tbody>
          {renames.map((r, i) => <tr key={i}>
            <td><input className="mono" inputMode="numeric" value={r.from} onChange={(e) => { const x = [...renames]; x[i] = { ...r, from: e.target.value.replace(/\D/g, "") }; setRenames(x); edit(); }} /></td>
            <td>{arrow}</td>
            <td><input className="mono" inputMode="numeric" value={r.to} onChange={(e) => { const x = [...renames]; x[i] = { ...r, to: e.target.value.replace(/\D/g, "") }; setRenames(x); edit(); }} /></td></tr>)}
        </tbody></table>
        <button className="sm" onClick={() => setRenames([...renames, { from: "", to: "" }])}>＋ {t("ren_add_row")}</button></div>
      <div><h3>{t("ren_orders")}</h3>
        <table><thead><tr><th>{t("order_no")}</th><th>{t("ren_numbers")}</th></tr></thead><tbody>
          {orders.map((o, i) => <tr key={i}>
            <td><input className="mono" value={o.order} onChange={(e) => { const x = [...orders]; x[i] = { ...o, order: e.target.value }; setOrders(x); edit(); }} /></td>
            <td><input className="mono" value={o.numbers} onChange={(e) => { const x = [...orders]; x[i] = { ...o, numbers: e.target.value }; setOrders(x); edit(); }} /></td></tr>)}
        </tbody></table>
        <button className="sm" onClick={() => setOrders([...orders, { order: "", numbers: "" }])}>＋ {t("ren_add_row")}</button></div>
    </div>
    <div className="actions" style={{ justifyContent: "flex-start" }}><button className="primary" disabled={busy} onClick={preview}>{t("ren_preview")}</button></div>
    <ErrorBox error={err} />
    {p && <>
      {!!p.errors.length && <div className="error" role="alert"><b>{t("ren_errors")}</b><ul>{p.errors.map((e) => <li key={e} dir="auto">{e}</li>)}</ul></div>}
      <div className="table-wrap"><table className="ren-table"><thead><tr>
        <th>{t("ren_before")} · {t("sacrifice_no")}</th><th>{t("ren_before")} · {t("order_no")}</th><th></th>
        <th>{t("ren_after")} · {t("sacrifice_no")}</th><th>{t("ren_after")} · {t("order_no")}</th>
        <th>{t("donor_name")}</th><th>{t("animal_type")}</th><th>{t("order_date")}</th><th>{t("sale_price")}</th><th>{t("parent_well")}</th></tr></thead>
        <tbody>{p.rows.map((r) => <tr key={r.id} className={r.changes ? "" : "muted"}>
          <td className="mono">{r.before_no}</td><td className="mono">{r.before_order || "—"}</td><td>{r.changes ? arrow : t("ren_no_change")}</td>
          <td className={`mono strong ${diff(r.before_no, r.after_no)}`}>{r.after_no}</td><td className={`mono ${diff(r.before_order, r.after_order)}`}>{r.after_order || "—"}</td>
          <td>{r.donor_name || "—"}</td><td>{r.animal_type || "—"}</td><td>{fmtDate(r.order_date)}</td>
          <td className="num">{money(r.sale_price)}</td><td className="mono">{r.parent_well_id || "—"}</td></tr>)}</tbody></table></div>
      {!!p.untouched_nearby.length && <details><summary className="muted">{t("ren_nearby")} ({p.untouched_nearby.length})</summary>
        <ul>{p.untouched_nearby.map((s: any) => <li key={s.id} className="mono">{s.sacrifice_no} · {s.order || "—"} · {s.donor_name || "—"}</li>)}</ul></details>}
      <div className="actions" style={{ justifyContent: "flex-start" }}>
        <button className="primary" disabled={!p.ok || busy} onClick={apply}>{t("ren_apply")}</button></div>
    </>}
    {kept && <div className="banner info">✓ {t("ren_backup_kept")} ({kept.rows}) · <button className="link-btn"
      onClick={() => download(`/api/sacrifices/renumber/${kept.batch}/backup.csv`, `sacrifices-before-renumber-${kept.batch}.csv`)}>⬇ {t("ren_backup_dl")}</button></div>}
    {check && <div className={`card ren-check ${check.ok ? "ok" : "bad"}`} style={{ marginTop: 10 }}>
      <h3 style={{ marginTop: 0 }}>{check.ok ? `✓ ${t("ren_check_ok")}` : `⚠ ${t("ren_check_bad")}`}</h3>
      <div className="table-wrap"><table><thead><tr><th>{t("order_no")}</th><th>{t("ren_check_want")}</th><th>{t("ren_check_have")}</th><th>{t("status")}</th></tr></thead>
        <tbody>{check.orders.map((o) => <tr key={o.order}><td className="mono">{o.order}</td><td className="mono">{o.expected.join("، ")}</td>
          <td className="mono">{o.actual.join("، ") || "—"}</td>
          <td>{o.ok ? <span className="badge ok">✓</span> : <span className="badge bad">✗ {o.elsewhere.map((e) => e.missing ? `${e.number}: ${t("ren_check_missing")}` : `${e.number} → ${e.order || "—"}`).join("، ")}</span>}</td></tr>)}</tbody></table></div>
      {check.duplicates.length > 0 && <p className="missing">{t("ren_check_dups")}: {check.duplicates.join("، ")}</p>}
    </div>}
    {!!hist.data?.length && <><h3>{t("ren_history")}</h3>
      <ul>{hist.data.map((h) => <li key={h.id}>{fmtDate(h.at)} · {h.by} · {h.changed.map((c: any) => `${c.from.sacrifice_no}→${c.to.sacrifice_no}`).join(", ")}
        {" "}{h.undone ? <span className="badge">{t("ren_undone")}</span> : <button className="sm" onClick={() => undo(h.id)}>{t("ren_undo")}</button>}
        {" "}<button className="sm" onClick={() => download(`/api/sacrifices/renumber/${h.id}/backup.csv`, `sacrifices-before-renumber-${h.id}.csv`).catch(() => toast(t("ren_backup_none")))}>⬇ {t("ren_backup_dl")}</button></li>)}</ul></>}
  </div>;
}
