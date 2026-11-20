import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, toast, useApi } from "../ui";

interface Group { name: string; values: string[]; count: number; raw: { value: string; count: number }[]; fixed: boolean }

/** Settings > Sales sources: the unified sources and the spellings under each one.
 *  Saving re-applies them to every well and sacrifice; the original text of each record is kept. */
export default function SalesSources() {
  const { t, num } = useI18n();
  const data = useApi<{ groups: Group[] }>("/api/admin/sales-sources");
  const [rows, setRows] = useState<{ name: string; values: string }[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (data.data) setRows(data.data.groups.filter((g) => !g.fixed).map((g) => ({ name: g.name, values: g.values.join(", ") })));
  }, [data.data]);
  if (!data.data) return <ErrorBox error={data.error} />;
  const save = async () => {
    setBusy(true);
    try {
      const body = rows.filter((r) => r.name.trim()).map((r) => ({ name: r.name.trim(), values: r.values.split(",").map((v) => v.trim()).filter(Boolean) }));
      const r = await api<any>("/api/admin/sales-sources", { method: "PUT", body });
      toast(`${t("saved")} · ${t("src_changed")}: ${num(r.records_changed)}`); data.reload();
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  };
  const addTo = (i: number, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, values: r.values ? `${r.values}, ${v}` : v } : r)));
  const byName = Object.fromEntries(data.data.groups.map((g) => [g.name, g]));
  const loose = ["Other", "Unknown"].map((n) => byName[n]).filter(Boolean);
  return (
    <div className="card">
      <h2>{t("src_title")}</h2>
      <p className="muted">{t("src_help")}</p>
      <div className="table-wrap"><table>
        <thead><tr><th>{t("src_group")}</th><th>{t("src_values")}</th><th className="num">{t("src_count")}</th><th /></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}>
            <td><input value={r.name} maxLength={40} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} /></td>
            <td><input dir="ltr" value={r.values} style={{ width: "100%" }} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, values: e.target.value } : x)))} /></td>
            <td className="num">{num(byName[r.name]?.count || 0)}</td>
            <td><button className="ghost" aria-label={t("delete")} onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</button></td>
          </tr>))}
        </tbody></table></div>
      <div className="actions">
        <button onClick={() => setRows([...rows, { name: "", values: "" }])}>＋ {t("src_add")}</button>
        <button className="primary" disabled={busy} onClick={save}>{t("save")}</button>
      </div>
      {loose.map((g) => (
        <div key={g.name} style={{ marginTop: 16 }}>
          <h3>{g.name} <span className="muted">({num(g.count)})</span></h3>
          <p className="muted" style={{ fontSize: 13 }}>{t(g.name === "Other" ? "src_other_help" : "src_unknown_help")}</p>
          <div className="chips">{g.raw.map((r) => (
            <span key={r.value} className="chip" dir="auto">{r.value} · {num(r.count)}
              {g.name === "Other" && r.value !== "—" && <select aria-label={t("src_move")} value="" onChange={(e) => e.target.value !== "" && addTo(Number(e.target.value), r.value)}>
                <option value="">{t("src_move")}</option>{rows.map((x, i) => <option key={i} value={i}>{x.name}</option>)}</select>}
            </span>))}</div>
        </div>))}
    </div>
  );
}
