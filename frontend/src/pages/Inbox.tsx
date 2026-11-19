// WhatsApp inbox (official Cloud API). Chats on the left, the open chat on the right; on a phone,
// one at a time. New messages are read again every few seconds (no websockets on the small server).
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, getToken } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { ErrorBox, toast } from "../ui";
import { PlaqueStatusBadge } from "../plaque/flow";

interface Order { kind: "well" | "sacrifice"; number: number; type: string | null; plaque_status: any; customer_name?: string | null; linked?: boolean; }
interface Conv {
  id: number; phone: string; name: string | null; status: "open" | "pending" | "closed"; assigned_to_id: number | null; assigned_to: string | null;
  order: Order | null; unread: number; last_message_at: string | null; last_preview: string | null; last_direction: string | null;
  waiting_reply: boolean; window_open: boolean; window_ends_at: string | null; plaque_unconfirmed: boolean; orders?: Order[];
}
interface Msg {
  id: number; direction: "in" | "out"; type: string; text: string | null; status: string; error: string | null; source: string;
  sent_by: string | null; at: string; media: any; file: string | null; media_pending: boolean; template: string | null;
}
interface Template { name: string; language: string; body: string; params: number; }
const BOXES = ["all", "mine", "unassigned", "unread", "waiting", "pending", "closed"];
const newRef = () => (crypto as any).randomUUID?.().replace(/-/g, "") || `${Date.now()}${Math.random().toString(16).slice(2)}`;

function useInterval(fn: () => void, ms: number, deps: any[]) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    const id = window.setInterval(() => { if (document.visibilityState === "visible") saved.current(); }, ms);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

function initials(c: Conv) {
  const n = (c.name || "").trim();
  return n ? n.split(/\s+/).slice(0, 2).map((w) => w[0]).join("") : "☎";
}

export default function Inbox() {
  const { t } = useI18n();
  const { id } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const { ops, can } = useAuth();
  const [box, setBox] = useState("all");
  const [q, setQ] = useState("");
  const [list, setList] = useState<Conv[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ enabled: boolean; mock: boolean; display_number: string | null } | null>(null);
  const load = () => api<Conv[]>("/api/inbox/conversations", { query: { box, q: q.trim() } }).then(setList).catch((e) => setError(e.message));
  useEffect(() => { api("/api/inbox/status").then(setStatus).catch(() => {}); }, []);
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [box]);
  useInterval(load, 10000, [box, q]);
  // ?phone=+962… (from an order page): open or start that customer's chat
  useEffect(() => {
    const phone = sp.get("phone");
    if (!phone) return;
    api<Conv>("/api/inbox/conversations", { body: { phone } }).then((c) => nav(`/inbox/${c.id}`, { replace: true })).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp]);
  const w = ops.whatsapp || {};
  return (
    <>
      <div className={`topbar inbox-top${id ? " in-chat" : ""}`}>
        <h1>🟢 {t("wa_title")}{w.unread_messages ? <span className="count-pill">{w.unread_messages}</span> : null}</h1>
        {status?.display_number && <span className="muted" dir="ltr">{status.display_number}</span>}
        {status?.mock && <span className="badge">{t("wa_mock")}</span>}
      </div>
      {status && !status.enabled && <div className="banner warn">{t("wa_not_connected")} {can("super_admin") && <Link to="/settings">{t("wa_not_connected_admin")}</Link>}</div>}
      <ErrorBox error={error} />
      <div className={`inbox${id ? " has-chat" : ""}`}>
        <aside className="inbox-list card">
          <form onSubmit={(e) => { e.preventDefault(); load(); }}>
            <input type="search" placeholder={t("wa_search")} value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <div className="inbox-boxes">{BOXES.map((b) => (
            <button key={b} type="button" className={`sm${box === b ? " on" : ""}`} onClick={() => setBox(b)}>{t("wa_box_" + b)}
              {b === "unread" && w.unread_chats ? ` (${w.unread_chats})` : b === "waiting" && w.waiting_reply ? ` (${w.waiting_reply})` : b === "unassigned" && w.unassigned ? ` (${w.unassigned})` : ""}</button>))}
          </div>
          {list === null ? <p className="muted">…</p> : !list.length ? <p className="muted" style={{ padding: 8 }}>{t("no_items")}</p> :
            <ul>{list.map((c) => <ConvItem key={c.id} c={c} on={String(c.id) === id} />)}</ul>}
        </aside>
        <section className="inbox-chat">
          {id ? <Chat key={id} id={Number(id)} onChanged={load} /> : <div className="card muted inbox-empty">{t("wa_pick")}</div>}
        </section>
      </div>
    </>
  );
}

function ConvItem({ c, on }: { c: Conv; on: boolean }) {
  const { t, fmtDate } = useI18n();
  const when = c.last_message_at ? new Date(c.last_message_at) : null;
  const today = when && when.toDateString() === new Date().toDateString();
  return (
    <li>
      <Link to={`/inbox/${c.id}`} className={`conv${on ? " on" : ""}${c.unread ? " unread" : ""}`}>
        <span className="avatar" title={t("wa_no_avatar")}>{initials(c)}</span>
        <span className="conv-main">
          <span className="conv-top"><b>{c.name || <bdi dir="ltr">{c.phone}</bdi>}</b>
            <span className="muted">{when ? (today ? when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : fmtDate(c.last_message_at)) : ""}</span></span>
          <span className="conv-prev">{c.last_direction === "out" ? "↩ " : ""}{c.last_preview || "—"}</span>
          <span className="conv-tags">
            {c.name && <bdi dir="ltr" className="muted">{c.phone}</bdi>}
            {c.order && <span className="badge brand">{c.order.kind === "well" ? "💧" : "🐑"} {c.order.number}</span>}
            {c.plaque_unconfirmed && <span className="badge bad">{t("wa_plaque_unconfirmed")}</span>}
            {c.status !== "open" && <span className="badge">{t("wa_st_" + c.status)}</span>}
            {c.assigned_to && <span className="badge">👤 {c.assigned_to}</span>}
          </span>
        </span>
        {c.unread > 0 && <span className="unread-dot">{c.unread}</span>}
      </Link>
    </li>
  );
}

function Ticks({ m }: { m: Msg }) {
  const { t } = useI18n();
  if (m.direction !== "out") return null;
  if (m.status === "failed") return <span className="tick bad" title={m.error || ""}>⚠ {t("wa_failed")}</span>;
  if (m.status === "queued") return <span className="tick">🕓</span>;
  return <span className={`tick${m.status === "read" ? " read" : ""}`} title={m.status}>{m.status === "sent" ? "✓" : "✓✓"}</span>;
}

function Media({ m }: { m: Msg }) {
  const { t } = useI18n();
  if (m.media_pending) return <div className="muted">{t("wa_media_pending")}</div>;
  if (!m.file) return m.type === "location" && m.media?.latitude ? <a href={`https://maps.google.com/?q=${m.media.latitude},${m.media.longitude}`} target="_blank" rel="noreferrer">📍 Map</a> : null;
  const mime: string = m.media?.mime_type || "";
  if (m.type === "image" || m.type === "sticker" || mime.startsWith("image/")) return <a href={m.file} target="_blank" rel="noreferrer"><img className="wa-img" src={m.file} alt="" loading="lazy" /></a>;
  if (m.type === "video" || mime.startsWith("video/")) return <video className="wa-img" src={m.file} controls preload="metadata" playsInline />;
  if (m.type === "audio" || mime.startsWith("audio/")) return <audio src={m.file} controls preload="none" />;
  return <a className="wa-doc" href={`${m.file}&download=true`}>📄 {m.media?.filename || t("wa_download")}{m.media?.size ? ` · ${Math.ceil(m.media.size / 1024)} KB` : ""}</a>;
}

function Chat({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { t, fmtDate } = useI18n();
  const { user, can, refreshCounts } = useAuth();
  const [c, setC] = useState<Conv | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [people, setPeople] = useState<{ id: number; name: string }[]>([]);
  const [tpls, setTpls] = useState<Template[] | null>(null);
  const [tpl, setTpl] = useState<Template | null>(null);
  const [params, setParams] = useState<string[]>([]);
  const [attach, setAttach] = useState<any[] | null>(null);
  const [showOrders, setShowOrders] = useState(false);
  const [linkNo, setLinkNo] = useState("");
  const fileIn = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const lastId = msgs.length ? msgs[msgs.length - 1].id : 0;
  const manager = can(...MANAGERS);

  const loadConv = () => api<Conv>(`/api/inbox/conversations/${id}`).then(setC).catch((e) => setError(e.message));
  const markRead = () => api(`/api/inbox/conversations/${id}/read`, { method: "POST" }).then(() => { refreshCounts(); onChanged(); }).catch(() => {});
  useEffect(() => {
    loadConv();
    api<Msg[]>(`/api/inbox/conversations/${id}/messages`).then((m) => { setMsgs(m); markRead(); }).catch((e) => setError(e.message));
    api<{ id: number; name: string }[]>("/api/inbox/assignees").then(setPeople).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [lastId]);
  // new messages and status ticks
  useInterval(async () => {
    try {
      const fresh = await api<Msg[]>(`/api/inbox/conversations/${id}/messages`, { query: { after_id: lastId } });
      if (fresh.some((m) => m.direction === "in")) { loadConv(); markRead(); }
      // re-read the last 30 for ticks / downloaded media
      const recent = await api<Msg[]>(`/api/inbox/conversations/${id}/messages`, { query: { limit: 30 } });
      setMsgs((xs) => {
        const byId = new Map(xs.map((m) => [m.id, m]));
        for (const m of [...recent, ...fresh]) byId.set(m.id, m);
        return [...byId.values()].sort((a, b) => a.id - b.id);
      });
    } catch { /* keep the chat */ }
  }, 4000, [id, lastId]);
  useEffect(() => {
    if (c && !c.window_open && tpls === null) api<Template[]>("/api/inbox/templates").then(setTpls).catch((e) => { setTpls([]); setError(e.message); });
  }, [c, tpls]);

  const add = (m: Msg) => setMsgs((xs) => (xs.some((x) => x.id === m.id) ? xs.map((x) => (x.id === m.id ? m : x)) : [...xs, m]));
  const post = async (body: any) => {
    setBusy(true); setError(null);
    try { add(await api<Msg>(`/api/inbox/conversations/${id}/send`, { body: { client_ref: newRef(), ...body } })); onChanged(); refreshCounts(); return true; }
    catch (e: any) { setError(e.message); return false; } finally { setBusy(false); }
  };
  const sendText = async () => { if (text.trim() && await post({ text })) setText(""); };
  const sendFile = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true); setError(null);
    const form = new FormData();
    form.append("client_ref", newRef()); form.append("file", f);
    if (text.trim()) form.append("caption", text.trim());
    try {
      const res = await fetch(`/api/inbox/conversations/${id}/upload`, { method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body: form });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : res.statusText);
      add(j); setText(""); onChanged();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); if (fileIn.current) fileIn.current.value = ""; }
  };
  const sendTemplate = async () => {
    if (!tpl) return;
    let preview = tpl.body;
    params.forEach((p, i) => { preview = preview.split(`{{${i + 1}}}`).join(p); });
    if (await post({ template: { name: tpl.name, language: tpl.language, params, preview } })) { setTpl(null); setParams([]); }
  };
  const act = async (path: string, body: any) => {
    try { const r = await api<Conv>(`/api/inbox/conversations/${id}/${path}`, { body }); setC((x) => ({ ...(x || {}), ...r } as Conv)); onChanged(); refreshCounts(); }
    catch (e: any) { toast(e.message); }
  };
  const retry = async (m: Msg) => { try { add(await api<Msg>(`/api/inbox/messages/${m.id}/retry`, { method: "POST" })); } catch (e: any) { toast(e.message); } };
  const openAttach = async () => {
    if (attach) { setAttach(null); return; }
    try { setAttach(await api<any[]>(`/api/inbox/conversations/${id}/attachables`)); } catch (e: any) { toast(e.message); }
  };
  const days = useMemo(() => {
    const out: { day: string; items: Msg[] }[] = [];
    for (const m of msgs) {
      const d = new Date(m.at).toDateString();
      if (!out.length || out[out.length - 1].day !== d) out.push({ day: d, items: [] });
      out[out.length - 1].items.push(m);
    }
    return out;
  }, [msgs]);
  if (!c) return <div className="card"><ErrorBox error={error} />{!error && "…"}</div>;
  const mine = c.assigned_to_id === user.id;
  return (
    <div className="card chat">
      <header className="chat-head">
        <Link to="/inbox" className="btn sm chat-back">‹ {t("wa_back")}</Link>
        <span className="avatar">{initials(c)}</span>
        <div className="chat-who"><b>{c.name || c.phone}</b> <bdi dir="ltr" className="muted">{c.phone}</bdi>
          <div className="conv-tags">
            {c.order && <Link className="badge brand" to={c.order.kind === "well" ? `/projects/${c.order.number}` : `/videos/sacrifice/${c.order.number}`}>
              {c.order.kind === "well" ? "💧" : "🐑"} {c.order.number}{c.order.type ? ` · ${c.order.type}` : ""}</Link>}
            {c.order?.plaque_status && <PlaqueStatusBadge s={c.order.plaque_status} />}
            <button type="button" className="sm" onClick={() => setShowOrders((x) => !x)}>{t("wa_orders")} ({c.orders?.length || 0})</button>
          </div></div>
        <div className="chat-tools">
          <select value={c.assigned_to_id ?? ""} disabled={!manager && c.assigned_to_id !== null && !mine}
            onChange={(e) => act("assign", { user_id: e.target.value ? Number(e.target.value) : null })} aria-label={t("wa_assign")}>
            <option value="">{t("wa_assign")}: {t("wa_nobody")}</option>
            {people.filter((p) => manager || p.id === user.id || p.id === c.assigned_to_id).map((p) => <option key={p.id} value={p.id}>{t("wa_assign")}: {p.name}</option>)}
          </select>
          {c.status !== "pending" && <button className="sm" onClick={() => act("status", { status: "pending" })}>{t("wa_follow")}</button>}
          {c.status !== "closed" ? <button className="sm" onClick={() => act("status", { status: "closed" })}>{t("wa_close")}</button>
            : <button className="sm" onClick={() => act("status", { status: "open" })}>{t("wa_reopen")}</button>}
        </div>
      </header>
      {showOrders && <div className="chat-orders">
        {!c.orders?.length ? <span className="muted">{t("wa_no_orders")}</span> : c.orders.map((o) => (
          <span key={o.kind + o.number} className="order-chip">
            <Link to={o.kind === "well" ? `/projects/${o.number}` : `/videos/sacrifice/${o.number}`}>{o.kind === "well" ? "💧" : "🐑"} {o.number}</Link>
            {o.type ? ` · ${o.type}` : ""} {o.plaque_status && <PlaqueStatusBadge s={o.plaque_status} />}
            {o.linked ? <span className="badge ok">{t("wa_linked")}</span> : <button className="sm" onClick={() => act("link", { kind: o.kind, number: o.number })}>{t("wa_link")}</button>}
          </span>))}
        <form className="order-chip" onSubmit={(e) => { e.preventDefault(); if (linkNo.trim()) act("link", { kind: "well", number: Number(linkNo) }); }}>
          <input type="number" placeholder={t("wa_link_other")} value={linkNo} onChange={(e) => setLinkNo(e.target.value)} style={{ width: 140 }} />
          <button className="sm">{t("wa_link")}</button>
          {c.order && <button type="button" className="sm" onClick={() => act("link", { kind: null, number: null })}>{t("wa_unlink")}</button>}
          <Link className="btn sm" to={`/projects?new=1&phone=${encodeURIComponent(c.phone)}&name=${encodeURIComponent(c.name || "")}`}>+ {t("wa_new_order")}</Link>
        </form>
      </div>}
      <div className="chat-body">
        {!msgs.length && <p className="muted">{t("wa_no_messages")}</p>}
        {days.map((d) => <div key={d.day}>
          <div className="day-sep"><span>{fmtDate(d.items[0].at)}</span></div>
          {d.items.map((m) => (
            <div key={m.id} className={`bubble ${m.direction}${m.status === "failed" ? " failed" : ""}`}>
              {m.template && <div className="muted" style={{ fontSize: 11.5 }}>📋 {m.template}</div>}
              <Media m={m} />
              {m.text && <div className="bubble-text" dir="auto">{m.type === "reaction" ? `${m.text} ↩` : m.text}</div>}
              <div className="bubble-meta">
                {m.direction === "out" && <span>{m.source === "phone_app" ? t("wa_from_phone") : m.sent_by}</span>}
                <span>{new Date(m.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span><Ticks m={m} />
              </div>
              {m.status === "failed" && <div className="bubble-err">{m.error} <button className="sm" onClick={() => retry(m)}>{t("wa_retry")}</button></div>}
            </div>))}
        </div>)}
        <div ref={end} />
      </div>
      <ErrorBox error={error} />
      {attach && <div className="chat-attach">
        {!attach.length ? <span className="muted">—</span> : attach.map((a) => (
          <button key={a.asset_id} className="sm" disabled={busy || !c.window_open} onClick={async () => { if (await post({ asset_id: a.asset_id, text: text.trim() || null })) { setText(""); setAttach(null); } }}>
            {a.kind === "plaque" ? `🖼 ${t("wa_plaque")}` : `🎬 ${t("wa_final_video")}`}{a.size ? ` · ${Math.round(a.size / 1024 / 1024)} MB` : ""}</button>))}
      </div>}
      {c.window_open ? (
        <form className="composer" onSubmit={(e) => { e.preventDefault(); sendText(); }}>
          <input ref={fileIn} type="file" hidden onChange={(e) => sendFile(e.target.files?.[0])}
            accept="image/*,video/*,audio/*,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip" />
          <button type="button" className="sm" title={t("wa_attach")} onClick={() => fileIn.current?.click()} disabled={busy}>📎</button>
          {c.order && <button type="button" className="sm" title={t("wa_from_order")} onClick={openAttach} disabled={busy}>🖼</button>}
          <textarea dir="auto" rows={1} placeholder={t("wa_write")} value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !(e.nativeEvent as any).isComposing) { e.preventDefault(); sendText(); } }} />
          <button className="primary" disabled={busy || !text.trim()}>{busy ? "…" : t("wa_send")}</button>
        </form>) : (
        <div className="composer closed">
          <p className="muted" style={{ margin: 0 }}>{t("wa_window_closed")}</p>
          <select value={tpl?.name || ""} onChange={(e) => { const x = (tpls || []).find((y) => y.name === e.target.value) || null; setTpl(x); setParams(Array(x?.params || 0).fill("")); }}>
            <option value="">{t("wa_choose_template")}</option>
            {(tpls || []).map((x) => <option key={x.name + x.language} value={x.name}>{x.name} ({x.language})</option>)}
          </select>
          {tpl && <><p className="tpl-body" dir="auto">{tpl.body}</p>
            {params.map((p, i) => <input key={i} dir="auto" placeholder={`{{${i + 1}}} ${t("wa_param")}`} value={p} onChange={(e) => setParams(params.map((x, j) => (j === i ? e.target.value : x)))} />)}
            <button className="primary" disabled={busy || params.some((p) => !p.trim())} onClick={sendTemplate}>{t("wa_send_template")}</button></>}
        </div>)}
      {c.window_open && c.window_ends_at && <div className="muted window-note">{t("wa_window_left")} {new Date(c.window_ends_at).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}</div>}
    </div>
  );
}
