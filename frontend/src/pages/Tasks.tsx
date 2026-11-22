// «مهامي» and the manager board (Hayah, 21 Nov 2026, second version).
// Eight stages, one responsible person each. A task is finished only when it is closed and documented.
//   1 غازي  استلام الطلب ← الدولة ← المقاول          5 غيداء  تدقيق الهاتف والطلب ← رفع الفيديو ← جاهز للتسليم
//   2 شذى   الرسالة الأولى ← تصميم اللوحة ← إرسالها    6 النظام  تجهيز الشهادة الوقفية وحفظها
//   3 شذى   تسجيل موافقة العميل (أو اعتماد المديرة)     7 شذى   إرسال الفيديو والشهادة ← تأكيد التسليم
//   4 غازي  إرسال اللوحة ← قائمة المتطلبات ← وصول الفيديو 8 المديرة تسجيل تاريخ التسليم وإغلاق المشروع
import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, dataChanged, forWells } from "../api";
import { MANAGERS, useAuth } from "../App";
import { useI18n } from "../i18n";
import { countryLabel, useNav } from "../nav";
import { Empty, ErrorBox, toast } from "../ui";
import { PlaqueRow, PlaqueWhatsApp, waLink } from "../plaque/flow";
import * as I from "../icons";
import { PhoneWithWa } from "../WaPhone";

type Step = { done: boolean; label: string; by: string | null; at: string | null; note: string | null };
type Person = { id: number; name: string };
export type TaskCard = {
  well_id: number; order_date: string | null; customer_name: string | null; dedication: string | null;
  customer_phone: string | null; customer_phone_e164: string | null; customer_phone_status: string | null; phone_ok: boolean;
  shopify_order: string | null; country: string | null; contractor_id: number | null; contractor_code: string | null;
  contractor_name: string | null; contractor_phone: string | null; well_type: string | null; construction_status: string;
  plaque_id: number | null; plaque_status: string | null; plaque_missing: string[]; video_status: string;
  stage: string | null; stage_label: string | null; next_step: string | null; waiting_customer: boolean;
  owner: Person | null; helpers?: Person[]; owner_kind: "person" | "system" | "manager"; reassigned: boolean; since: string | null; days: number | null; late: boolean;
  steps: Record<string, Step>;
};
type StageInfo = { key: string; label: string; steps: string[]; owner: Person | null; helpers?: Person[]; kind: string };
type TasksOut = { view: string; items: TaskCard[]; my_stages: string[]; counts: Record<string, number>; stages: StageInfo[];
  people: (Person & { role: string })[]; late_days: number; settings: { start_date: string } };

export default function Tasks() {
  const { t } = useI18n();
  const { can, refreshCounts } = useAuth();
  const manager = can(...MANAGERS);
  const [view, setView] = useState<string>(manager ? "all" : "mine");
  const [data, setData] = useState<TasksOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const load = () => api<TasksOut>("/api/team/tasks", { query: { view } })
    .then((r) => { setData(r); setError(null); }).catch((e) => setError(e.message));
  useEffect(() => { setData((d) => (d ? { ...d, items: [] } : d)); load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [view]);
  const onChange = (c: TaskCard) => {
    const stays = view === "all" || (view === "mine" ? false : c.stage === view);
    setData((d) => d && { ...d, items: stays && c.stage ? d.items.map((x) => (x.well_id === c.well_id ? c : x)) : d.items });
    toast(c.stage ? `${t("tk_moved_to")} «${c.stage_label}»${c.owner ? ` · ${c.owner.name}` : ""}` : t("tk_all_done"));
    load(); refreshCounts(); dataChanged();
  };
  const items = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (data?.items || []).filter((c) => !s || [c.well_id, c.customer_name, c.dedication, c.customer_phone, c.shopify_order, c.owner?.name]
      .some((v) => String(v ?? "").toLowerCase().includes(s)));
  }, [data, q]);
  const stageNo = (k: string | null) => (data?.stages.findIndex((s) => s.key === k) ?? -1) + 1;
  return (
    <>
      <div className="topbar">
        <div><h1>{view === "all" ? t("tk_board") : t("tk_title")}</h1>
          <p className="muted" style={{ margin: 0 }}>{view === "all" ? t("tk_board_help") : t("tk_help")}</p></div>
      </div>
      <div className="tk-views" role="tablist">
        <button type="button" role="tab" aria-selected={view === "mine"} className={view === "mine" ? "on" : ""} onClick={() => setView("mine")}>
          <I.ListTodo size={16} /> {t("nav_tasks")} <span className={`count${data?.counts.mine ? " red" : ""}`}>{data?.counts.mine ?? "…"}</span></button>
        {manager && <button type="button" role="tab" aria-selected={view === "all"} className={view === "all" ? "on" : ""} onClick={() => setView("all")}>
          <I.LayoutDashboard size={16} /> {t("tk_board")} {data?.counts.late ? <span className="count red">{data.counts.late} {t("tk_late")}</span> : null}</button>}
      </div>
      <div className="tk-stages8">
        {(data?.stages || []).map((s, i) => (
          <button key={s.key} type="button" className={`tk-st${view === s.key ? " on" : ""}${data?.my_stages.includes(s.key) ? " mine" : ""}`} onClick={() => setView(view === s.key ? (manager ? "all" : "mine") : s.key)}>
            <span className="tk-stage-no">{i + 1}</span>
            <span className="tk-st-txt"><b>{s.label}</b><small>{s.kind === "system" ? t("tk_system") : s.owner?.name || (s.kind === "manager" ? t("tk_manager") : t("tk_unassigned"))}</small></span>
            <span className={`count${data?.counts[s.key] ? " on" : ""}`}>{data?.counts[s.key] ?? 0}</span>
          </button>))}
      </div>
      <div className="toolbar"><input type="search" placeholder={t("tk_search")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <ErrorBox error={error} />
      {!data ? <p className="muted">…</p> : !items.length ? <Empty />
        : view === "all" ? <Board items={items} people={data.people} stageNo={stageNo} onChange={onChange} />
          : <div className="tk-list">{items.map((c) => <TaskCardView key={c.well_id} c={c} no={stageNo(c.stage)} stage={data.stages.find((s) => s.key === c.stage)} onChange={onChange} />)}</div>}
    </>
  );
}

// ---------------------------------------------------------------- manager board
function Board({ items, people, stageNo, onChange }: { items: TaskCard[]; people: Person[]; stageNo: (k: string | null) => number; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<number | null>(null);
  const assign = (c: TaskCard, v: string) => api<TaskCard>(`/api/team/order/${c.well_id}/assign`, { body: { stage: c.stage, user_id: v ? Number(v) : null } })
    .then(onChange).catch((e) => toast(e.message));
  return <div className="table-wrap tk-board"><table>
    <thead><tr><th>{t("name")}</th><th>{t("tk_order_no")}</th><th>{t("tk_stage")}</th><th>{t("tk_owner")}</th><th>{t("tk_next")}</th><th>{t("tk_waiting")}</th><th></th></tr></thead>
    <tbody>{items.map((c) => <Fragment key={c.well_id}>
      <tr className={c.late ? "late" : ""} data-well={c.well_id}>
        <td className="strong">{c.customer_name || c.dedication || "—"}</td>
        <td><Link to={`/projects/${c.well_id}`} className="well-no mono">{c.well_id}</Link></td>
        <td><span className="tk-stage-no sm">{stageNo(c.stage)}</span> {c.stage_label}</td>
        <td>{c.owner_kind === "system" ? <span className="muted">{t("tk_system")}</span>
          : <select value={c.owner?.id ?? ""} onChange={(e) => assign(c, e.target.value)} aria-label={t("tk_owner")} className={c.reassigned ? "tk-moved" : ""}>
            <option value="">{c.owner_kind === "manager" ? t("tk_manager") : t("tk_unassigned")}</option>
            {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>}</td>
        <td>{c.waiting_customer ? t("tk_waiting_customer") : c.next_step ? t("tk_step_" + c.next_step) : ""}</td>
        <td className={c.late ? "bad" : "muted"}>{c.days === null ? "—" : c.days === 0 ? t("tk_today") : `${c.days} ${t("tk_days")}`}{c.late ? " ⚠" : ""}</td>
        <td><button className="sm" onClick={() => setOpen(open === c.well_id ? null : c.well_id)}>{open === c.well_id ? "▲" : t("tk_open")}</button></td>
      </tr>
      {open === c.well_id && <tr className="tk-board-open"><td colSpan={7}><TaskCardView c={c} no={stageNo(c.stage)} onChange={onChange} /></td></tr>}
    </Fragment>)}</tbody>
  </table></div>;
}

// ---------------------------------------------------------------- one order card
function Steps({ c, stage }: { c: TaskCard; stage?: StageInfo }) {
  const { t } = useI18n();
  const keys = stage?.steps || Object.keys(c.steps).filter((k) => c.steps[k].label && k === c.next_step);
  return <ol className="tk-steps">{keys.map((k) => {
    const s = c.steps[k];
    return <li key={k} className={s.done ? "done" : k === c.next_step ? "next" : ""} title={s.by ? `${s.by}${s.note ? " · " + s.note : ""}` : undefined}>
      <span className="tk-dot" aria-hidden="true">{s.done ? "✓" : ""}</span>{t("tk_step_" + k)}</li>;
  })}</ol>;
}

const ORDER: Record<string, string[]> = {
  intake: ["received", "country", "contractor"], design: ["contacted", "designed", "sent"], approval: ["approved"],
  contractor: ["plaque_sent", "requirements", "video_received"], review: ["checked", "video", "ready"],
  certificate: ["certificate"], delivery: ["sent_customer", "confirmed"], close: ["closed"],
};

function TaskCardView({ c, no, stage, onChange }: { c: TaskCard; no: number; stage?: StageInfo; onChange: (c: TaskCard) => void }) {
  const { t, fmtDate, lang } = useI18n();
  const st = stage || ({ key: c.stage || "", label: c.stage_label || "", steps: ORDER[c.stage || ""] || [], owner: c.owner, kind: c.owner_kind } as StageInfo);
  return (
    <div className={`card tk-card${c.late ? " late" : ""}`} data-well={c.well_id}>
      <div className="tk-head">
        <span className="tk-name">{c.customer_name || c.dedication || "—"}</span>
        <Link to={`/projects/${c.well_id}`} className="well-no mono">{c.well_id}</Link>
        <span className="muted">{[c.well_type, c.country ? countryLabel(c.country, lang) : null, c.contractor_code, fmtDate(c.order_date)].filter(Boolean).join(" · ")}</span>
        <span className="tk-who"><span className="tk-stage-no sm">{no}</span> {c.stage_label} · {c.owner_kind === "system" ? t("tk_system") : [c.owner?.name || t("tk_manager"), ...(c.helpers || []).map((h) => h.name)].join(lang === "ar" ? " و" : " & ")}
          {c.days !== null && <span className={c.late ? "badge bad" : "badge"}>{c.days === 0 ? t("tk_today") : `${c.days} ${t("tk_days")}`}</span>}</span>
      </div>
      <Steps c={c} stage={st} />
      <div className="tk-act">
        {c.stage === "intake" && <IntakeAction c={c} onChange={onChange} />}
        {c.stage === "design" && <DesignAction c={c} onChange={onChange} />}
        {c.stage === "approval" && <ApprovalAction c={c} onChange={onChange} />}
        {c.stage === "contractor" && <ContractorAction c={c} onChange={onChange} />}
        {c.stage === "review" && <ReviewAction c={c} onChange={onChange} />}
        {c.stage === "certificate" && <div className="tk-row"><Link className="btn primary tk-go" to={`/plaque/certificate/${c.well_id}`}><I.Award size={16} /> {t("tk_open_cert")}</Link><span className="muted">{t("tk_cert_help")}</span></div>}
        {c.stage === "delivery" && <DeliveryAction c={c} onChange={onChange} />}
        {c.stage === "close" && <CloseAction c={c} onChange={onChange} />}
      </div>
    </div>
  );
}

function useTick(c: TaskCard, onChange: (c: TaskCard) => void) {
  const [busy, setBusy] = useState(false);
  const run = (p: Promise<TaskCard>) => { setBusy(true); return p.then(onChange).catch((e) => toast(e.message)).finally(() => setBusy(false)); };
  return {
    busy, run,
    tick: (step: string, note?: string | null) => run(api<TaskCard>(`/api/team/order/${c.well_id}/steps/${step}`, { body: { done: true, note: note || null } })),
    reload: () => api<TaskCard>(`/api/team/order/${c.well_id}`).then(onChange).catch((e) => toast(e.message)),
  };
}

/** A step that is closed with a short note: what was done and how (documentation). */
function NoteStep({ c, step, label, placeholder, onChange, icon: Ic = I.Check }: { c: TaskCard; step: string; label: string; placeholder: string; onChange: (c: TaskCard) => void; icon?: I.IconC }) {
  const { busy, tick } = useTick(c, onChange);
  const [note, setNote] = useState("");
  return <div className="tk-note">
    <input placeholder={placeholder} value={note} onChange={(e) => setNote(e.target.value)} data-k={"note-" + step} />
    <button className="primary tk-go" disabled={busy || !note.trim()} onClick={() => tick(step, note.trim())}><Ic size={16} /> {label}</button>
  </div>;
}

// 1 غازي
function IntakeAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t, lang } = useI18n();
  const nav = useNav();
  const { busy, tick, reload } = useTick(c, onChange);
  const [country, setCountry] = useState(c.country || "");
  const countries = useMemo(() => Array.from(new Set((nav?.contractors || []).filter(forWells).map((x) => x.country).filter(Boolean))), [nav]);
  const cons = (nav?.contractors || []).filter(forWells).filter((x) => !country || x.country === country);
  const patch = (body: any) => api(`/api/projects/${c.well_id}`, { method: "PATCH", body }).then(reload).catch((e) => toast(e.message));
  if (!c.steps.received.done) return <button className="primary tk-go" disabled={busy} onClick={() => tick("received")}><I.Check size={16} /> {t("tk_do_received")}</button>;
  return <div className="tk-row">
    <label className="tk-inline">{t("tk_step_country")}
      <select value={country} onChange={(e) => { setCountry(e.target.value); if (e.target.value) patch({ country: e.target.value }); }} data-k="country">
        <option value="">{t("tk_pick")}</option>{countries.map((x) => <option key={x} value={x}>{countryLabel(x, lang)}</option>)}
      </select></label>
    <label className="tk-inline">{t("tk_step_contractor")}
      <select value={c.contractor_id ?? ""} disabled={!country} onChange={(e) => e.target.value && patch({ contractor_id: Number(e.target.value) })} data-k="contractor">
        <option value="">{t("tk_pick")}</option>{cons.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.code})</option>)}
      </select></label>
  </div>;
}

// 2 شذى
const FIRST_MSG = (no: number) => `السلام عليكم ورحمة الله وبركاته\nمعكم فريق حياة، تم استلام طلبكم رقم ${no} بنجاح، جزاكم الله خيراً.\nسنرسل لكم تصميم اللوحة قريباً لمراجعته والموافقة عليه إن شاء الله.`;

function usePlaque(c: TaskCard, when: boolean) {
  const [plaque, setPlaque] = useState<PlaqueRow | null>(null);
  useEffect(() => { if (c.plaque_id && when) api<PlaqueRow>(`/api/plaques/${c.plaque_id}`).then(setPlaque).catch(() => {}); }, [c.plaque_id, when]);
  return plaque;
}

function DesignAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  const { busy, tick, reload } = useTick(c, onChange);
  const plaque = usePlaque(c, c.next_step === "sent");
  const move = (to: string, n?: string) => api(`/api/plaques/${c.plaque_id}/status`, { body: { to, note: n || null } }).then(reload).catch((e) => toast(e.message));
  const wa = waLink(c.customer_phone_e164, FIRST_MSG(c.well_id));
  if (c.next_step === "contacted") return <div className="tk-row">
    {wa ? <a className="btn wa-btn" href={wa} target="_blank" rel="noreferrer" onClick={() => tick("contacted", "واتساب")}><I.MessageCircle size={16} /> {t("tk_do_first_msg")}</a>
      : <span className="badge warn">{t("plwa_no_phone")}</span>}
    <button disabled={busy} onClick={() => tick("contacted", "اتصال")}>{t("tk_do_contacted")}</button>
  </div>;
  if (c.next_step === "designed") return <div className="tk-row">
    <Link className="btn primary tk-go" to={`/plaque/${c.well_id}`}><I.Image size={16} /> {t("tk_do_design")}</Link>
    {c.plaque_missing.length > 0 && <span className="badge warn">{t("pla_missing")}: {c.plaque_missing.map((m) => t("miss_" + m)).join("، ")}</span>}
  </div>;
  return <div className="tk-row">
    {plaque && <PlaqueWhatsApp p={plaque} label onDone={() => reload()} />}
    <button onClick={() => move("awaiting_customer", "أُرسلت بطريقة أخرى")}>{t("tk_do_sent_other")}</button>
    <Link className="btn" to={`/plaque/${c.well_id}`}>{t("pla_open")}</Link>
  </div>;
}

// 3 شذى (or the manager directly)
function ApprovalAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const { reload } = useTick(c, onChange);
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState<"" | "customer" | "manager">("");
  const move = (to: string, n?: string) => api(`/api/plaques/${c.plaque_id}/status`, { body: { to, note: n || null } }).then(reload).catch((e) => toast(e.message));
  if (confirm) return <div className="tk-confirm">
    <b>{confirm === "customer" ? t("tk_confirm_q") : t("tk_confirm_mgr")}</b>
    <input placeholder={confirm === "customer" ? t("tk_confirm_how") : t("tk_confirm_why")} value={note} onChange={(e) => setNote(e.target.value)} />
    <button className="primary" disabled={!note.trim()} onClick={() => move("customer_approved", (confirm === "manager" ? "اعتماد المديرة: " : "") + note.trim())}>{t("tk_confirm_yes")}</button>
    <button onClick={() => setConfirm("")}>{t("cancel")}</button>
  </div>;
  return <div className="tk-row">
    {c.waiting_customer ? <span className="badge warn"><I.Clock size={14} /> {t("tk_waiting_customer")}</span> : <span className="badge">{t("tk_not_sent")}</span>}
    <button className="primary tk-go" disabled={!c.waiting_customer} onClick={() => setConfirm("customer")}><I.BadgeCheck size={16} /> {t("tk_do_approved")}</button>
    {can(...MANAGERS) && <button onClick={() => setConfirm("manager")}>{t("tk_do_mgr_approve")}</button>}
    <button onClick={() => { const n = window.prompt(t("pla_note")) || ""; if (n.trim()) move("needs_changes", n); }}>{t("pla_changes")}</button>
  </div>;
}

// 4 غازي
function ContractorAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  const { busy, run } = useTick(c, onChange);
  const [note, setNote] = useState("");
  if (c.next_step === "plaque_sent") return <div className="tk-check">
    <div className="tk-facts"><span>{t("tk_step_contractor")}: <b>{c.contractor_name} ({c.contractor_code})</b></span>
      {c.contractor_phone && <a href={waLink(c.contractor_phone.replace(/[^+\d]/g, ""), `لوحة مشروع رقم ${c.well_id}`) || "#"} target="_blank" rel="noreferrer">{t("tk_contractor_chat")}</a>}
      {c.plaque_id && <Link to={`/plaque/${c.well_id}`}>{t("tk_get_plaque")}</Link>}</div>
    <div className="tk-note">
      <input placeholder={t("tk_note_send_plaque")} value={note} onChange={(e) => setNote(e.target.value)} data-k="note-plaque" />
      <button className="primary tk-go" disabled={busy || !note.trim()} onClick={() => run(api<TaskCard>(`/api/team/order/${c.well_id}/send-to-contractor`, { body: { note: note.trim() } }))}>
        <I.Share2 size={16} /> {t("tk_do_plaque_sent")}</button>
    </div>
  </div>;
  if (c.next_step === "requirements") return <NoteStep c={c} step="requirements" label={t("tk_do_requirements")} placeholder={t("tk_note_requirements")} onChange={onChange} icon={I.ScrollText} />;
  return <div className="tk-check">
    <span className="muted">{t("tk_waiting_video_help")}</span>
    <NoteStep c={c} step="video_received" label={t("tk_do_video_received")} placeholder={t("tk_note_video_received")} onChange={onChange} icon={I.Clapperboard} />
  </div>;
}

// 5 غيداء
function ReviewAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  const { busy, tick, reload } = useTick(c, onChange);
  const video = (to: string) => api(`/api/videos/order/well/${c.well_id}/status`, { body: { to } }).then(reload).catch((e) => toast(e.message));
  if (c.next_step === "checked") return <div className="tk-check">
    <div className="tk-facts">
      <span>{t("tk_order_no")}: <b className="mono">{c.well_id}</b>{c.shopify_order ? <> · Shopify <b className="mono">{c.shopify_order}</b></> : null}</span>
      <span>{t("phone")}: <PhoneWithWa phone={c.customer_phone} e164={c.customer_phone_e164} status={c.customer_phone_status} />{" "}
        {c.phone_ok ? <span className="badge ok">✓ {t("ph_valid")}</span> : <span className="badge bad">{t(c.customer_phone_status ? "ph_" + c.customer_phone_status : "tk_no_phone")}</span>}</span>
    </div>
    <div className="tk-row">
      <button className="primary tk-go" disabled={busy || !c.phone_ok} onClick={() => tick("checked")}><I.Check size={16} /> {t("tk_do_checked")}</button>
      {!c.phone_ok && <Link className="btn" to={`/projects/${c.well_id}`}>{t("tk_fix_phone")}</Link>}
    </div>
  </div>;
  if (c.next_step === "video") return <div className="tk-row">
    <Link className="btn primary tk-go" to={`/videos/well/${c.well_id}`}><I.Clapperboard size={16} /> {t("tk_do_video")}</Link>
  </div>;
  return <div className="tk-row">
    <Link className="btn" to={`/videos/well/${c.well_id}`}>{t("tk_watch_video")}</Link>
    <button className="primary tk-go" onClick={() => video("ready_for_delivery")}><I.BadgeCheck size={16} /> {t("tk_do_ready")}</button>
    <span className="muted">{t("tk_ready_help")}</span>
  </div>;
}

// 7 شذى
function DeliveryAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  if (c.next_step === "sent_customer") return <div className="tk-row">
    <Link className="btn primary tk-go" to={`/videos/well/${c.well_id}`}><I.Truck size={16} /> {t("tk_do_deliver")}</Link>
    <span className="muted">{t("tk_deliver_help")}</span>
  </div>;
  return <NoteStep c={c} step="confirmed" label={t("tk_do_confirmed")} placeholder={t("tk_note_confirmed")} onChange={onChange} icon={I.BadgeCheck} />;
}

// 8 المديرة
function CloseAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const { busy, run } = useTick(c, onChange);
  const [on, setOn] = useState(new Date().toISOString().slice(0, 10));
  if (!can(...MANAGERS)) return <span className="muted">{t("tk_close_mgr")}</span>;
  return <div className="tk-note">
    <label className="tk-inline">{t("tk_delivery_date")} <input type="date" value={on} onChange={(e) => setOn(e.target.value)} /></label>
    <button className="primary tk-go" disabled={busy} onClick={() => run(api<TaskCard>(`/api/team/order/${c.well_id}/close`, { body: { on } }))}><I.CircleCheck size={16} /> {t("tk_do_close")}</button>
  </div>;
}
