// Floating assistant (Hayah, 2026-11-19): explains how to use the system, in Arabic or English.
// Read only: the server has no tool that changes data, hides money from non-managers and uses the
// same AI key and monthly budget as «عدّل بكتابة طلب». The button can be moved like the prompt button.
import { Fragment, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "./api";
import { useAuth } from "./App";
import { useI18n } from "./i18n";
import { useDraggable } from "./useDraggable";

type Msg = { role: "user" | "assistant"; content: string };
const KEY = "hayah.help.chat";

const load = (): Msg[] => { try { return JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch { return []; } };
const save = (m: Msg[]) => { try { sessionStorage.setItem(KEY, JSON.stringify(m.slice(-30))); } catch { /* ignore */ } };

/** Page paths in an answer (e.g. /projects/1305) become links. */
function Rich({ text, onNav }: { text: string; onNav: () => void }) {
  const parts = text.split(/(\/(?:projects|plaque|plaques|videos|wells|book|inbox|settings|delivery|construction|maintenance|media|reports|contractors)(?:\/[\w-]+)*)/g);
  return <>{parts.map((p, i) => (i % 2 ? <Link key={i} to={p} onClick={onNav} dir="ltr" className="help-link">{p}</Link> : <Fragment key={i}>{p}</Fragment>))}</>;
}

export default function HelpChat() {
  const { t } = useI18n();
  const { user } = useAuth();
  const fab = useDraggable(`hayah.fab.help.${user.id}`);
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>(load);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ ready: boolean; reason: string | null } | null>(null);
  const end = useRef<HTMLDivElement | null>(null);

  useEffect(() => { if (open) api("/api/help/status").then(setStatus).catch(() => setStatus(null)); }, [open]);
  useEffect(() => { save(msgs); end.current?.scrollIntoView({ block: "end" }); }, [msgs, open]);

  const ask = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    const next: Msg[] = [...msgs, { role: "user", content: question }];
    setMsgs(next); setQ(""); setBusy(true);
    try {
      const r = await api<{ answer: string }>("/api/help/ask", { body: { messages: next, page: loc.pathname } });
      setMsgs([...next, { role: "assistant", content: r.answer }]);
    } catch (e: any) {
      setMsgs([...next, { role: "assistant", content: `⚠ ${e.message}` }]);
    } finally { setBusy(false); }
  };

  return (
    <>
      <button ref={fab.ref} className={`help-fab fab-movable${fab.dragging ? " dragging" : ""}`} style={fab.style} {...fab.handlers}
        onClick={() => setOpen((o) => !o)} title={`${t("help_btn")} · ${t("fab_hold_to_move")}`} aria-label={t("help_btn")} aria-expanded={open}>
        <span aria-hidden>?</span> <span className="fab-label">{t("help_btn")}</span>
      </button>
      {open && <section className="help-panel" role="dialog" aria-label={t("help_title")}>
        <header>
          <b>{t("help_title")}</b>
          <span style={{ marginInlineStart: "auto", display: "flex", gap: 6 }}>
            {msgs.length > 0 && <button className="sm ghost" onClick={() => setMsgs([])}>{t("help_clear")}</button>}
            <button className="sm" onClick={() => setOpen(false)} aria-label={t("close")}>✕</button>
          </span>
        </header>
        <div className="help-body">
          {status && !status.ready && <div className="banner">{status.reason}</div>}
          <div className="bubble in"><div className="bubble-text">{t("help_hello")}</div></div>
          {msgs.length === 0 && <div className="chips">
            {["help_ex1", "help_ex2", "help_ex3"].map((k) => <button key={k} className="chip" disabled={status !== null && !status.ready} onClick={() => ask(t(k))}>{t(k)}</button>)}
          </div>}
          {msgs.map((m, i) => (
            <div key={i} className={`bubble ${m.role === "user" ? "out" : "in"}`}>
              <div className="bubble-text">{m.role === "assistant" ? <Rich text={m.content} onNav={() => setOpen(false)} /> : m.content}</div>
            </div>))}
          {busy && <p className="muted">{t("help_thinking")}</p>}
          <div ref={end} />
        </div>
        <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <textarea value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("help_ph")} rows={1} maxLength={2000}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(q); } }} />
          <button className="primary" disabled={busy || !q.trim() || (status !== null && !status.ready)}>{t("help_send")}</button>
        </form>
        {fab.moved && <button className="ghost sm help-reset" onClick={fab.reset}>↺ {t("fab_reset")}</button>}
      </section>}
    </>
  );
}
