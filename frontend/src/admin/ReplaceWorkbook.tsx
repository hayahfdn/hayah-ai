// Replace everything earlier workbook imports loaded with a new workbook (super admin only).
// Preview first (saves nothing), then type the word to confirm; a database backup is written before anything changes.
import { useState } from "react";
import { api, dataChanged, download } from "../api";
import { useI18n } from "../i18n";
import { ErrorBox, toast } from "../ui";

interface Kept { number: number; why: string[] }
interface Rep {
  applied: boolean; file: string; backup: { files: string[]; notes: string[] } | null;
  previous_imports: { id: number; file: string; at: string }[];
  before: { wells: number; sacrifices: number; transactions: number };
  after: { wells: number; sacrifices: number; transactions: number };
  wells_updated: number; sacrifices_updated: number; wells_added: number; sacrifices_added: number; transactions_added: number;
  wells_deleted: number[]; sacrifices_deleted: number[]; transactions_deleted: number;
  wells_kept: Kept[]; sacrifices_kept: Kept[]; transactions_kept: { id: number; date: string; amount: string; why: string }[];
  wise_relinked: number; hand_edits_overwritten: { number: number; fields: string[]; sacrifice?: boolean }[];
  deliveries_changed: { number: number; from: string | null; to: string }[];
  renumbered_check: { old: number; now: number; kind: string }[];
  import: { skipped_existing_wells: number[]; skipped_existing_sacrifices: number[] };
  problems: { where: string; problem: string; kind: string }[];
}

const short = (xs: (number | string)[], n = 40) => xs.slice(0, n).join(", ") + (xs.length > n ? ` … (+${xs.length - n})` : "");

export default function ReplaceWorkbook() {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [link, setLink] = useState("");
  const [word, setWord] = useState("");
  const [busy, setBusy] = useState(false);
  const [rep, setRep] = useState<Rep | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async (apply: boolean) => {
    if (!file && !link.trim()) return;
    setBusy(true); setErr(null);
    const form = new FormData();
    if (link.trim()) form.append("url", link.trim());
    else if (file) form.append("file", file);
    form.append("apply", String(apply));
    if (apply) form.append("confirm", word);
    try {
      const r = await api<Rep>("/api/admin/import-workbook/replace", { form });
      setRep(r); setWord("");
      if (apply) { toast(t("rp_done")); dataChanged(); }
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const okWord = ["REPLACE", "استبدال"].includes(word.trim().toUpperCase()) || word.trim() === "استبدال";
  const reset = () => { setRep(null); setWord(""); };
  const why = (w: string) => { const k = "rp_why_" + w.toLowerCase().replace(/[^a-z]+/g, "_").replace(/^_+|_+$/g, ""); const v = t(k); return v === k ? w : v; };

  return (
    <div className="card" style={{ borderInlineStart: "4px solid var(--bad)" }}>
      <h2>{t("rp_title")}</h2>
      <p className="muted">{t("rp_help")}</p>
      <ul className="muted" style={{ fontSize: 14 }}>
        <li>{t("rp_rule_update")}</li><li>{t("rp_rule_delete")}</li><li>{t("rp_rule_keep")}</li>
        <li>{t("rp_rule_money")}</li><li>{t("rp_rule_hand")}</li><li>{t("rp_rule_backup")}</li>
      </ul>
      <input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] || null); setLink(""); reset(); }} />
      <p className="muted" style={{ margin: "10px 0 4px" }}>{t("imp_or_link")}</p>
      <input type="url" dir="ltr" style={{ width: "100%" }} placeholder="https://1drv.ms/… · https://docs.google.com/spreadsheets/…"
        value={link} onChange={(e) => { setLink(e.target.value); reset(); }} />
      <div className="actions">
        <button disabled={(!file && !link.trim()) || busy} onClick={() => run(false)}>{busy && !rep ? t("imp_reading") : t("rp_preview")}</button>
      </div>
      <ErrorBox error={err} />

      {rep && <>
        <h3>{rep.applied ? t("rp_applied") : t("rp_would")}</h3>
        {rep.previous_imports.length > 0
          ? <p className="muted">{t("rp_prev")}: {rep.previous_imports.map((p) => `${p.file} (${new Date(p.at).toLocaleDateString()})`).join(" · ")}</p>
          : <p className="muted">{t("rp_no_prev")}</p>}
        <div className="table-wrap"><table>
          <thead><tr><th></th><th>{t("wells")}</th><th>{t("sacrifices")}</th><th>{t("imp_money_rows")}</th></tr></thead>
          <tbody>
            <tr><td>{t("rp_now")}</td><td className="num">{rep.before.wells}</td><td className="num">{rep.before.sacrifices}</td><td className="num">{rep.before.transactions}</td></tr>
            <tr><td>{t("rp_updated")}</td><td className="num">{rep.wells_updated}</td><td className="num">{rep.sacrifices_updated}</td><td className="num">–</td></tr>
            <tr><td>{t("rp_deleted")}</td><td className="num">{rep.wells_deleted.length}</td><td className="num">{rep.sacrifices_deleted.length}</td><td className="num">{rep.transactions_deleted}</td></tr>
            <tr><td>{t("rp_kept")}</td><td className="num">{rep.wells_kept.length}</td><td className="num">{rep.sacrifices_kept.length}</td><td className="num">{rep.transactions_kept.length}</td></tr>
            <tr><td>{t("rp_added")}</td><td className="num">{rep.wells_added}</td><td className="num">{rep.sacrifices_added}</td><td className="num">{rep.transactions_added}</td></tr>
            <tr><td><b>{t("rp_after")}</b></td><td className="num"><b>{rep.after.wells}</b></td><td className="num"><b>{rep.after.sacrifices}</b></td><td className="num"><b>{rep.after.transactions}</b></td></tr>
          </tbody>
        </table></div>

        {(rep.wells_kept.length > 0 || rep.sacrifices_kept.length > 0) && <div>
          <h4>{t("rp_kept_title")}</h4>
          <p className="muted">{t("rp_kept_help")}</p>
          <ul>{[...rep.wells_kept.map((k) => ({ ...k, s: false })), ...rep.sacrifices_kept.map((k) => ({ ...k, s: true }))].slice(0, 60).map((k) =>
            <li key={`${k.s}-${k.number}`}><span className="mono">{k.s ? t("rp_sac") : t("rp_well")} {k.number}</span>: {k.why.map(why).join("، ")}</li>)}</ul>
        </div>}
        {rep.hand_edits_overwritten.length > 0 && <div>
          <h4>{t("rp_hand_title")}</h4>
          <p className="muted">{t("rp_hand_help")}</p>
          <ul>{rep.hand_edits_overwritten.slice(0, 60).map((h) =>
            <li key={`${h.sacrifice}-${h.number}`}><span className="mono">{h.sacrifice ? t("rp_sac") : t("rp_well")} {h.number}</span>: {h.fields.map((f) => t(f === "sale_price" ? "sale_amount" : f)).join("، ")}</li>)}</ul>
        </div>}
        {rep.renumbered_check.length > 0 && <div>
          <h4>{t("rp_renum_title")}</h4>
          <ul>{rep.renumbered_check.map((r) => <li key={`${r.kind}-${r.old}`}>{r.kind === "well" ? t("rp_well") : t("rp_sac")} {r.old} → {r.now}</li>)}</ul>
        </div>}
        {rep.wells_deleted.length > 0 && <p className="muted">{t("rp_deleted_list")}: <span className="mono">{short(rep.wells_deleted)}</span></p>}
        {rep.sacrifices_deleted.length > 0 && <p className="muted">{t("rp_deleted_sac_list")}: <span className="mono">{short(rep.sacrifices_deleted)}</span></p>}
        {rep.deliveries_changed.length > 0 && <p className="muted">{t("rp_deliveries")}: {rep.deliveries_changed.length}</p>}
        {rep.transactions_kept.length > 0 && <p className="muted">{t("rp_tx_kept")}: {rep.transactions_kept.map((x) => `${x.date} ${x.amount}`).join(" · ")}</p>}
        {(rep.import.skipped_existing_wells.length > 0 || rep.import.skipped_existing_sacrifices.length > 0) &&
          <p className="muted">{t("imp_skipped")}: <span className="mono">{short([...rep.import.skipped_existing_wells, ...rep.import.skipped_existing_sacrifices])}</span></p>}
        {rep.problems.filter((p) => p.kind === "action").length > 0 &&
          <p className="muted">{t("imp_action")}: {rep.problems.filter((p) => p.kind === "action").length} · {t("rp_problems_hint")}</p>}

        {!rep.applied && <div style={{ marginTop: 12 }}>
          <p><b>{t("rp_type")}</b></p>
          <input dir="auto" value={word} onChange={(e) => setWord(e.target.value)} placeholder="REPLACE / استبدال" style={{ maxWidth: 260 }} />
          <div className="actions">
            <button onClick={reset}>{t("cancel")}</button>
            <button className="danger" disabled={!okWord || busy} onClick={() => run(true)}>{busy ? t("rp_working") : t("rp_apply")}</button>
          </div>
        </div>}
        {rep.applied && rep.backup && <div>
          <p className="muted">{t("rp_backup")}:</p>
          <ul>{rep.backup.files.map((f) => <li key={f}><a href="#" className="mono" onClick={(e) => { e.preventDefault(); download(`/api/admin/backups/${encodeURIComponent(f)}`, f); }}>{f}</a></li>)}</ul>
        </div>}
      </>}
    </div>
  );
}
