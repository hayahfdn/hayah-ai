// Upload the Excel workbook: Preview shows what would be loaded (nothing saved), Apply loads it.
import { useState } from "react";
import { api, dataChanged } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, toast } from "../ui";
import PastImports from "./PastImports";

interface Problem { where: string; problem: string; kind: "action" | "check" | "info" }
interface Report { applied: boolean; file: string; wells: number; delivered: number; sacrifices: number; transactions: number;
  skipped_existing_wells: number[]; skipped_existing_sacrifices: number[]; contractors_created: string[]; problems: Problem[] }

export default function ImportWorkbook() {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [rep, setRep] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [show, setShow] = useState<string>("action");

  const run = async (apply: boolean) => {
    if (!file && !link.trim()) return;
    setBusy(true); setErr(null);
    const form = new FormData();
    if (link.trim()) form.append("url", link.trim());
    else if (file) form.append("file", file);
    form.append("apply", String(apply));
    try {
      const r = await api<Report>("/api/admin/import-workbook", { form });
      setRep(r);
      if (apply) { toast(t("imp_done")); dataChanged(); }
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const groups = { action: t("imp_action"), check: t("imp_check"), info: t("imp_info") } as Record<string, string>;
  const list = (rep?.problems || []).filter((p) => p.kind === show);

  return (
    <div className="grid">
      <div className="card">
        <h2>{t("imp_title")}</h2>
        <p className="muted">{t("imp_help")}</p>
        <input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] || null); setLink(""); setRep(null); }} />
        <p className="muted" style={{ margin: "10px 0 4px" }}>{t("imp_or_link")}</p>
        <input type="url" dir="ltr" style={{ width: "100%" }} placeholder="https://1drv.ms/… · https://docs.google.com/spreadsheets/…"
          value={link} onChange={(e) => { setLink(e.target.value); setRep(null); }} />
        <p className="muted" style={{ fontSize: 13 }}>{t("imp_link_help")}</p>
        <div className="actions">
          <button disabled={(!file && !link.trim()) || busy} onClick={() => run(false)}>{busy ? t("imp_reading") : t("imp_preview")}</button>
          {rep && !rep.applied && <button className="primary" disabled={busy} onClick={() => run(true)}>{t("imp_apply")}</button>}
        </div>
        <ErrorBox error={err} />
      </div>
      {rep && <div className="card">
        <h2>{rep.applied ? t("imp_loaded") : t("imp_would_load")}</h2>
        <div className="kpis">
          {[["wells", rep.wells], ["sacrifices", rep.sacrifices], ["imp_money_rows", rep.transactions], ["imp_delivered", rep.delivered]].map(([k, v]) =>
            <div key={k as string} className="kpi"><div className="muted">{t(k as string)}</div><b>{v as number}</b></div>)}
        </div>
        {(rep.skipped_existing_wells.length > 0 || rep.skipped_existing_sacrifices.length > 0) &&
          <p className="muted">{t("imp_skipped")}: {[...rep.skipped_existing_wells, ...rep.skipped_existing_sacrifices].slice(0, 30).join(", ")}
            {rep.skipped_existing_wells.length + rep.skipped_existing_sacrifices.length > 30 ? " …" : ""}</p>}
        {rep.contractors_created.length > 0 && <p className="muted">{t("imp_new_contractors")}: {rep.contractors_created.join(", ")}</p>}
        <div className="tabs">{Object.entries(groups).map(([k, label]) =>
          <button key={k} className={show === k ? "on" : ""} onClick={() => setShow(k)}>{label} ({rep.problems.filter((p) => p.kind === k).length})</button>)}</div>
        <div className="table-wrap"><table><tbody>
          {list.map((p, i) => <tr key={i}><td className="mono" style={{ whiteSpace: "nowrap" }}>{p.where}</td><td>{p.problem}</td></tr>)}
        </tbody></table></div>
      </div>}
      <PastImports key={rep?.applied ? "after" : "before"} />
    </div>
  );
}
