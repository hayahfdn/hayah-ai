// Recent changes with an Undo button on each. Managers see everyone's; others see their own well edits.
import { api, dataChanged } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, toast, useApi } from "../ui";

export interface Change { id: number; at: string; action: string; label: string; entity_id: string; by: string;
  fields: string[]; before: Record<string, any>; after: Record<string, any>; undone: boolean }

export async function undoChange(id: number, t: (k: string) => string) {
  try { const r = await api<{ summary: string }>(`/api/undo/${id}`, { method: "POST" }); toast(t("undo_done")); void r; dataChanged(); return true; }
  catch (e: any) { toast(e.message); return false; }
}

export default function RecentChanges({ mine = false }: { mine?: boolean }) {
  const { t } = useI18n();
  const list = useApi<Change[]>("/api/undo/recent", { mine, limit: 100 });
  const show = (v: any) => (v === null || v === undefined || v === "" ? "—" : String(v));
  return (
    <div className="card">
      <h2>{t("undo_title")}</h2>
      <p className="muted">{t("undo_help")}</p>
      <ErrorBox error={list.error} />
      <div className="table-wrap"><table>
        <thead><tr><th></th><th>{t("date")}</th><th>{t("undo_what")}</th><th>{t("undo_change")}</th><th>{t("undo_by")}</th></tr></thead>
        <tbody>{(list.data || []).map((c) => <tr key={c.id}>
          <td>{c.undone ? <span className="muted">{t("undo_undone")}</span>
            : <button onClick={async () => { if (await undoChange(c.id, t)) list.reload(); }}>↶ {t("undo")}</button>}</td>
          <td style={{ whiteSpace: "nowrap" }}>{new Date(c.at).toLocaleString()}</td>
          <td>{t("undo_" + c.action.replace(".", "_"))} <span className="mono">{c.entity_id}</span></td>
          <td className="wrap">{c.fields.length ? c.fields.map((f) => <div key={f}>{t(f)}: {show(c.before[f])} → {show(c.after[f])}</div>) : "—"}</td>
          <td>{c.by}</td>
        </tr>)}</tbody>
      </table></div>
    </div>
  );
}
