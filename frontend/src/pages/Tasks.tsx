// «مهامي»: the order workflow split between three people (Hayah, 21 Nov 2026).
//   غازي  (intake)   استلام الطلب ← تحديد الدولة ← اختيار المقاول
//   شذى   (customer) التواصل مع العميل ← تصميم اللوحة ← إرسالها للموافقة ← تسجيل الموافقة
//   غيداء (delivery) مراجعة رقم الطلب والهاتف ← رفع الفيديو النهائي ← جاهز للتسليم ← استكمال التسليم
// Each card shows the order's steps in order and one button for the next step. The steps are read from
// the order, its plaque and its final video, so working from the usual pages moves the cards too.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, dataChanged } from "../api";
import { useAuth } from "../App";
import { useI18n } from "../i18n";
import { countryLabel, useNav } from "../nav";
import { Empty, ErrorBox, toast } from "../ui";
import { PlaqueRow, PlaqueWhatsApp, waLink } from "../plaque/flow";
import * as I from "../icons";

type Stage = "intake" | "customer" | "delivery";
type Step = { done: boolean; label: string; by: string | null; at: string | null; note: string | null };
export type TaskCard = {
  well_id: number; order_date: string | null; customer_name: string | null; dedication: string | null;
  customer_phone: string | null; customer_phone_e164: string | null; customer_phone_status: string | null; phone_ok: boolean;
  shopify_order: string | null; sales_source: string | null; country: string | null; contractor_id: number | null;
  contractor_code: string | null; contractor_name: string | null; well_type: string | null; construction_status: string;
  plaque_id: number | null; plaque_status: string | null; plaque_missing: string[]; video_status: string;
  stage: Stage | null; next_step: string | null; steps: Record<string, Step>;
};
type TasksOut = {
  my_stage: Stage | null; items: TaskCard[]; counts: Record<Stage, number>; members: Record<Stage, { id: number; name: string }[]>;
  stages: { key: Stage; label: string; steps: string[] }[]; settings: { start_date: string };
};

const STAGES: Stage[] = ["intake", "customer", "delivery"];
const ICON: Record<Stage, I.IconC> = { intake: I.ClipboardCheck, customer: I.MessageCircle, delivery: I.Truck };

export default function Tasks() {
  const { t } = useI18n();
  const { user, refreshCounts } = useAuth();
  const [stage, setStage] = useState<Stage>((user.team_stage as Stage) || "intake");
  const [data, setData] = useState<TasksOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const load = () => api<TasksOut>("/api/team/tasks", { query: { stage } })
    .then((r) => { setData(r); setError(null); }).catch((e) => setError(e.message));
  useEffect(() => { setData((d) => (d ? { ...d, items: [] } : d)); load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [stage]);
  const onChange = (c: TaskCard) => {
    setData((d) => d && { ...d, items: c.stage === stage ? d.items.map((x) => (x.well_id === c.well_id ? c : x)) : d.items.filter((x) => x.well_id !== c.well_id) });
    if (c.stage !== stage) { toast(c.stage ? `${t("tk_moved_to")} ${t("tk_stage_" + c.stage)}` : t("tk_all_done")); load(); }
    refreshCounts(); dataChanged();
  };
  const items = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (data?.items || []).filter((c) => !s || [c.well_id, c.customer_name, c.dedication, c.customer_phone, c.shopify_order]
      .some((v) => String(v ?? "").toLowerCase().includes(s)));
  }, [data, q]);
  const names = (s: Stage) => (data?.members[s] || []).map((m) => m.name).join("، ");
  return (
    <>
      <div className="topbar">
        <div><h1>{t("tk_title")}</h1>
          <p className="muted" style={{ margin: 0 }}>{t("tk_help")}</p></div>
      </div>
      <div className="tk-stages" role="tablist">
        {STAGES.map((s, i) => {
          const Ic = ICON[s];
          return <button key={s} type="button" role="tab" aria-selected={stage === s} className={`tk-stage${stage === s ? " on" : ""}${user.team_stage === s ? " mine" : ""}`} onClick={() => setStage(s)}>
            <span className="tk-stage-no">{i + 1}</span>
            <span className="tk-stage-txt"><b><Ic size={16} /> {t("tk_stage_" + s)}</b>
              <small>{names(s) || t("tk_unassigned")}{user.team_stage === s ? ` · ${t("tk_you")}` : ""}</small></span>
            <span className={`count${data?.counts[s] ? " red" : ""}`}>{data?.counts[s] ?? "…"}</span>
          </button>;
        })}
      </div>
      <div className="tk-flow muted">{(data?.stages.find((x) => x.key === stage)?.steps || []).map((k, i) => <span key={k}>{i ? " ← " : ""}{t("tk_step_" + k)}</span>)}</div>
      <div className="toolbar"><input type="search" placeholder={t("tk_search")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <ErrorBox error={error} />
      {!data ? <p className="muted">…</p> : !items.length ? <Empty /> :
        <div className="tk-list">{items.map((c) => <TaskCardView key={c.well_id} c={c} onChange={onChange} />)}</div>}
    </>
  );
}

function Steps({ c }: { c: TaskCard }) {
  const { t } = useI18n();
  if (!c.stage) return null;
  const order: Record<Stage, string[]> = { intake: ["received", "country", "contractor"], customer: ["contacted", "designed", "sent", "approved"], delivery: ["checked", "video", "ready", "delivered"] };
  return <ol className="tk-steps">{order[c.stage].map((k) => {
    const s = c.steps[k];
    return <li key={k} className={s.done ? "done" : k === c.next_step ? "next" : ""} title={s.by ? `${s.by}${s.note ? " · " + s.note : ""}` : undefined}>
      <span className="tk-dot" aria-hidden="true">{s.done ? "✓" : ""}</span>{t("tk_step_" + k)}</li>;
  })}</ol>;
}

function TaskCardView({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { fmtDate, lang } = useI18n();
  return (
    <div className={`card tk-card tk-${c.stage}`} data-well={c.well_id}>
      <div className="tk-head">
        <Link to={`/projects/${c.well_id}`} className="well-no mono">{c.well_id}</Link>
        <span className="tk-name">{c.customer_name || c.dedication || "—"}</span>
        <span className="muted">{[c.well_type, c.country ? countryLabel(c.country, lang) : null, c.contractor_code, fmtDate(c.order_date)].filter(Boolean).join(" · ")}</span>
      </div>
      <Steps c={c} />
      <div className="tk-act">
        {c.stage === "intake" && <IntakeAction c={c} onChange={onChange} />}
        {c.stage === "customer" && <CustomerAction c={c} onChange={onChange} />}
        {c.stage === "delivery" && <DeliveryAction c={c} onChange={onChange} />}
      </div>
    </div>
  );
}

function useTick(c: TaskCard, onChange: (c: TaskCard) => void) {
  const [busy, setBusy] = useState(false);
  return {
    busy,
    tick: (step: string, note?: string | null, done = true) => {
      setBusy(true);
      return api<TaskCard>(`/api/team/order/${c.well_id}/steps/${step}`, { body: { done, note: note || null } })
        .then(onChange).catch((e) => toast(e.message)).finally(() => setBusy(false));
    },
    reload: () => api<TaskCard>(`/api/team/order/${c.well_id}`).then(onChange).catch((e) => toast(e.message)),
  };
}

// ---------------------------------------------------------------- غازي
function IntakeAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t, lang } = useI18n();
  const nav = useNav();
  const { busy, tick, reload } = useTick(c, onChange);
  const [country, setCountry] = useState(c.country || "");
  const countries = useMemo(() => Array.from(new Set((nav?.contractors || []).map((x) => x.country).filter(Boolean))), [nav]);
  const cons = (nav?.contractors || []).filter((x) => !country || x.country === country);
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

// ---------------------------------------------------------------- شذى
const FIRST_MSG = (no: number) => `السلام عليكم ورحمة الله وبركاته\nمعكم فريق حياة، تم استلام طلبكم رقم ${no} بنجاح، جزاكم الله خيراً.\nسنرسل لكم تصميم اللوحة قريباً لمراجعته والموافقة عليه إن شاء الله.`;

function CustomerAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  const { busy, tick, reload } = useTick(c, onChange);
  const [plaque, setPlaque] = useState<PlaqueRow | null>(null);
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState(false);
  useEffect(() => { if (c.plaque_id && (c.next_step === "sent" || c.next_step === "approved")) api<PlaqueRow>(`/api/plaques/${c.plaque_id}`).then(setPlaque).catch(() => {}); }, [c.plaque_id, c.next_step]);
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
  if (c.next_step === "sent") return <div className="tk-row">
    {plaque && <PlaqueWhatsApp p={plaque} label onDone={() => reload()} />}
    <button onClick={() => move("awaiting_customer", "أُرسلت بطريقة أخرى")}>{t("tk_do_sent_other")}</button>
    <Link className="btn" to={`/plaque/${c.well_id}`}>{t("pla_open")}</Link>
  </div>;
  if (c.next_step === "approved") return <div className="tk-row">
    {!confirm ? <>
      <button className="primary tk-go" onClick={() => setConfirm(true)}><I.BadgeCheck size={16} /> {t("tk_do_approved")}</button>
      <button onClick={() => { const n = window.prompt(t("pla_note")) || ""; if (n.trim()) move("needs_changes", n); }}>{t("pla_changes")}</button>
      <span className="muted">{t("tk_waiting_customer")}</span>
    </> : <div className="tk-confirm">
      <b>{t("tk_confirm_q")}</b>
      <input placeholder={t("tk_confirm_how")} value={note} onChange={(e) => setNote(e.target.value)} />
      <button className="primary" disabled={!note.trim()} onClick={() => move("customer_approved", note.trim())}>{t("tk_confirm_yes")}</button>
      <button onClick={() => setConfirm(false)}>{t("cancel")}</button>
    </div>}
  </div>;
  return null;
}

// ---------------------------------------------------------------- غيداء
function DeliveryAction({ c, onChange }: { c: TaskCard; onChange: (c: TaskCard) => void }) {
  const { t } = useI18n();
  const { busy, tick, reload } = useTick(c, onChange);
  const video = (to: string) => api(`/api/videos/order/well/${c.well_id}/status`, { body: { to } }).then(reload).catch((e) => toast(e.message));
  if (c.next_step === "checked") return <div className="tk-check">
    <div className="tk-facts">
      <span>{t("tk_order_no")}: <b className="mono">{c.well_id}</b>{c.shopify_order ? <> · Shopify <b className="mono">{c.shopify_order}</b></> : null}</span>
      <span>{t("phone")}: <bdi dir="ltr" className="mono">{c.customer_phone_e164 || c.customer_phone || "—"}</bdi>{" "}
        {c.phone_ok ? <span className="badge ok">✓ {t("ph_valid")}</span> : <span className="badge bad">{t(c.customer_phone_status ? "ph_" + c.customer_phone_status : "tk_no_phone")}</span>}</span>
    </div>
    <div className="tk-row">
      <button className="primary tk-go" disabled={busy || !c.phone_ok} onClick={() => tick("checked")}><I.Check size={16} /> {t("tk_do_checked")}</button>
      {!c.phone_ok && <Link className="btn" to={`/projects/${c.well_id}`}>{t("tk_fix_phone")}</Link>}
    </div>
  </div>;
  if (c.next_step === "video") return <div className="tk-row">
    <Link className="btn primary tk-go" to={`/videos/well/${c.well_id}`}><I.Clapperboard size={16} /> {t("tk_do_video")}</Link>
    {c.construction_status !== "completed" && <span className="muted">{t("tk_waiting_contractor")}</span>}
  </div>;
  if (c.next_step === "ready") return <div className="tk-row">
    <Link className="btn" to={`/videos/well/${c.well_id}`}>{t("tk_watch_video")}</Link>
    <button className="primary tk-go" onClick={() => video("ready_for_delivery")}><I.BadgeCheck size={16} /> {t("tk_do_ready")}</button>
  </div>;
  if (c.next_step === "delivered") return <div className="tk-row">
    <Link className="btn primary tk-go" to={`/videos/well/${c.well_id}`}><I.Truck size={16} /> {t("tk_do_deliver")}</Link>
    <span className="muted">{t("tk_deliver_help")}</span>
  </div>;
  return null;
}
