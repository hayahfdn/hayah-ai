// "Edit with a prompt": a button on every page (managers only). Type what to change,
// see exactly what would change, then press Apply. Nothing is saved before Apply.
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, dataChanged } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, Modal, toast } from "../ui";
import { useDraggable } from "../useDraggable";

interface Op { op: string; target: string; label?: string; fields: Record<string, string>; changes: { field: string; from: any; to: any }[]; error: string | null; expected_version?: number }
interface Plan { summary: string; questions: string[]; operations: Op[]; cost_usd: number; can_apply: boolean }

function pageContext(path: string) {
  const m = path.match(/^\/book\/(wells|sac|acc|con)\/([^/]+)/);
  if (!m) return { path };
  if (m[1] === "wells") return { path, kind: "wells", month: m[2] };
  if (m[1] === "sac") return { path, kind: "sacrifices", month: m[2] };
  if (m[1] === "acc") return { path, account: m[2] };
  return { path, contractor: m[2] };
}

export default function PromptBar() {
  const { t, st } = useI18n();
  const { refreshCounts, user } = useAuth();
  const fab = useDraggable(`hayah.fab.prompt.${user.id}`);
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [status, setStatus] = useState<{ ready: boolean; reason: string | null; code: string | null } | null>(null);

  useEffect(() => { if (open) api("/api/assistant/status").then(setStatus).catch(() => setStatus(null)); }, [open]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(true); } };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const preview = async () => {
    setBusy(true); setErr(null); setPlan(null);
    try { setPlan(await api<Plan>("/api/assistant/plan", { body: { prompt, page: pageContext(loc.pathname) } })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const apply = async () => {
    if (!plan) return;
    setBusy(true); setErr(null);
    try {
      await api("/api/assistant/apply", { body: { prompt, operations: plan.operations } });
      toast(t("prompt_applied")); dataChanged(); refreshCounts();
      setPlan(null); setPrompt(""); setOpen(false);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const label = (f: string) => (f === "kind" ? t("tx_kind") : f === "account_id" ? t("account") : f === "contractor_id" ? t("contractor")
    : t(f) !== f ? t(f) : t("tx_" + f) !== "tx_" + f ? t("tx_" + f) : f);
  const show = (v: any) => typeof v === "string" && t("tk_" + v) !== "tk_" + v ? t("tk_" + v) : (v === null || v === undefined || v === "" ? "—" : typeof v === "string" && /^[a-z_]+$/.test(v) ? st(v) : String(v));

  return (
    <>
      <button ref={fab.ref} className={`prompt-fab fab-movable${fab.dragging ? " dragging" : ""}`} style={fab.style} {...fab.handlers}
        onClick={() => setOpen(true)} title={`${t("prompt_btn")} (Ctrl+K) · ${t("fab_hold_to_move")}`} aria-label={t("prompt_btn")}>✦ <span className="fab-label">{t("prompt_btn")}</span></button>
      {open && <Modal title={t("prompt_title")} onClose={() => setOpen(false)}>
        {status && !status.ready && <div className="banner"><b>{t("prompt_not_ready")}.</b> {status.code && t("why_" + status.code) !== "why_" + status.code ? t("why_" + status.code) : status.reason}</div>}
        <textarea value={prompt} onChange={(e) => { setPrompt(e.target.value); setPlan(null); }} placeholder={t("prompt_ph")} rows={4} autoFocus
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && prompt.trim().length > 1) preview(); }} />
        <div className="chips" aria-label={t("prompt_examples")}>
          {["ex1", "ex2", "ex3", "ex4"].map((k) => <button key={k} className="chip" onClick={() => { setPrompt(t(k)); setPlan(null); }}>{t(k)}</button>)}
        </div>
        <p className="muted" style={{ margin: "8px 0" }}>{t("prompt_note")}</p>
        <ErrorBox error={err} />
        {busy && !plan && <p className="muted">{t("prompt_thinking")}</p>}
        {plan && <div className="plan">
          {plan.summary && <p><b>{plan.summary}</b></p>}
          {plan.questions.length > 0 && <div className="banner info"><b>{t("prompt_questions")}:</b><ul>{plan.questions.map((q, i) => <li key={i}>{q}</li>)}</ul></div>}
          {!plan.operations.length && !plan.questions.length && <p>{t("prompt_none")}</p>}
          {plan.operations.map((o, i) => (
            <div key={i} className={`plan-op ${o.error ? "bad" : ""}`}>
              <div className="plan-head"><b>{o.label === "New money row" ? t("new_money_row") : o.label || o.target || o.op}</b>{o.error && <span className="badge bad">{o.error}</span>}</div>
              {o.changes.length > 0 && <table><thead><tr><th>{t("field")}</th><th>{t("from")}</th><th>{t("to")}</th></tr></thead>
                <tbody>{o.changes.map((c) => <tr key={c.field}><td>{label(c.field)}</td><td className="muted">{show(c.from)}</td><td><b>{show(c.to)}</b></td></tr>)}</tbody></table>}
            </div>))}
          <p className="muted" style={{ fontSize: 12 }}>{t("prompt_cost")}: ${plan.cost_usd.toFixed(4)}</p>
        </div>}
        <div className="actions">
          {fab.moved && <button className="ghost" style={{ marginInlineEnd: "auto" }} onClick={fab.reset}>↺ {t("fab_reset")}</button>}
          <button onClick={() => setOpen(false)}>{t("cancel")}</button>
          {!plan && <button className="primary" disabled={busy || prompt.trim().length < 2 || (status !== null && !status.ready)} onClick={preview}>{t("prompt_preview")}</button>}
          {plan && <button className="primary" disabled={busy || !plan.can_apply} onClick={apply}>{t("prompt_apply")}</button>}
        </div>
      </Modal>}
    </>
  );
}
