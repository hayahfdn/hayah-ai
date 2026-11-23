// Past workbook imports, each with a "Remove" button that takes out everything that import added.
import { useState } from "react";
import { api, dataChanged } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, Modal, toast, useApi } from "../ui";

interface Imp { id: number; at: string; file: string; by: string; wells: number; sacrifices: number; transactions: number; removed: boolean }
interface Plan { wells: number; sacrifices: number; transactions: number; wells_kept: number[]; sacrifices_kept?: number[]; well_ids: number[]; applied: boolean }

export default function PastImports() {
  const { t } = useI18n();
  const list = useApi<Imp[]>("/api/admin/imports");
  const [sel, setSel] = useState<Imp | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const preview = async (i: Imp) => {
    setSel(i); setPlan(null); setErr(null);
    try { setPlan(await api<Plan>(`/api/admin/imports/${i.id}/remove`, { method: "POST" })); } catch (e: any) { setErr(e.message); }
  };
  const remove = async () => {
    if (!sel) return;
    setBusy(true);
    try {
      await api(`/api/admin/imports/${sel.id}/remove`, { method: "POST", query: { apply: true } });
      toast(t("rm_done")); setSel(null); list.reload(); dataChanged();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  if (!list.data?.length) return null;
  return (
    <div className="card">
      <h2>{t("rm_title")}</h2>
      <p className="muted">{t("rm_help")}</p>
      <div className="table-wrap"><table>
        <thead><tr><th>{t("date")}</th><th>{t("rm_file")}</th><th>{t("wells")}</th><th>{t("sacrifices")}</th><th>{t("imp_money_rows")}</th><th></th></tr></thead>
        <tbody>{list.data.map((i) => <tr key={i.id}>
          <td>{new Date(i.at).toLocaleString()}</td><td>{i.file}</td><td className="num">{i.wells}</td>
          <td className="num">{i.sacrifices}</td><td className="num">{i.transactions}</td>
          <td>{i.removed ? <span className="muted">{t("rm_removed")}</span> : <button className="danger" onClick={() => preview(i)}>{t("rm_button")}</button>}</td>
        </tr>)}</tbody>
      </table></div>
      {sel && <Modal title={t("rm_title")} onClose={() => setSel(null)}>
        <ErrorBox error={err} />
        {plan ? <>
          <p>{t("rm_confirm")}</p>
          <ul>
            <li>{plan.wells} {t("wells")}</li><li>{plan.sacrifices} {t("sacrifices")}</li><li>{plan.transactions} {t("imp_money_rows")}</li>
          </ul>
          {(plan.wells_kept.length > 0 || (plan.sacrifices_kept || []).length > 0) &&
            <p className="muted">{t("rm_kept")}: {[...plan.wells_kept, ...(plan.sacrifices_kept || [])].join(", ")}</p>}
          <p className="muted">{t("rm_safe")}</p>
          <div className="actions">
            <button onClick={() => setSel(null)}>{t("cancel")}</button>
            <button className="danger" disabled={busy} onClick={remove}>{t("rm_button")}</button>
          </div>
        </> : !err && <p>{t("imp_reading")}</p>}
      </Modal>}
    </div>
  );
}
