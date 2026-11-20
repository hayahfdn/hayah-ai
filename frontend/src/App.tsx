import { createContext, lazy, Suspense, useContext, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, getToken, setToken, User } from "./api";
import { useI18n } from "./i18n";
import { ErrorBox, Field } from "./ui";
import ChangePassword from "./admin/ChangePassword";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
const Sheet = lazy(() => import("./pages/Sheet"));
const Workbook = lazy(() => import("./book/Workbook"));
const PromptBar = lazy(() => import("./book/PromptBar"));
const HelpChat = lazy(() => import("./HelpChat"));
const PlaqueDesigner = lazy(() => import("./plaque/PlaqueDesigner"));
const CertificatePage = lazy(() => import("./certificate/Certificate"));
const PlaqueLists = lazy(() => import("./pages/PlaqueLists"));
const Tasks = lazy(() => import("./pages/Tasks"));
const Inbox = lazy(() => import("./pages/Inbox"));
const FinalVideos = lazy(() => import("./pages/FinalVideos"));
const FinalVideoPage = lazy(() => import("./pages/FinalVideos").then((m) => ({ default: m.FinalVideoPage })));
import ProjectDetail from "./pages/ProjectDetail";
import Construction from "./pages/Construction";
import Delivery from "./pages/Delivery";
import Maintenance from "./pages/Maintenance";
import MediaLibrary from "./pages/MediaLibrary";
import Review from "./pages/Review";
import Contractors from "./pages/Contractors";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import { MonthWells, MonthSacrifices, ContractorWells } from "./pages/WellPages";
import { BottomBar, NavProvider, SideNav } from "./nav";
import { useZoom, ZoomControl } from "./Zoom";
import Header, { initials } from "./Header";
import * as I from "./icons";

type AuthCtx = { user: User; can: (...roles: string[]) => boolean; logout: () => void; counts: Record<string, number>; refreshCounts: () => void; ops: Ops };
/** Live operations counts (no money): plaques, final videos, new orders. Empty for roles that do not use them. */
export type Ops = { team?: Record<string, number>; plaques?: Record<string, number>; videos?: Record<string, number>; orders?: Record<string, number>;
  whatsapp?: { unread_messages?: number; unread_chats?: number; waiting_reply?: number; unassigned?: number; enabled?: boolean } };
const Auth = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Auth);
export const MANAGERS = ["super_admin", "operations_manager"];
// Can add and edit wells (with selling price). Costs and finance stay with MANAGERS.
export const EDITORS = [...MANAGERS, "staff"];

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const { t, lang, setLang } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const r = await api<{ access_token: string; user: User }>("/api/auth/login", { body: { email, password } });
      setToken(r.access_token); onLogin(r.user);
    } catch (err: any) { setError(err.message || t("login_failed")); } finally { setBusy(false); }
  };
  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <div className="brand"><img className="logo" src="/hayah-logo.png" alt="HAYAH" /><div><b>{t("app_name")}</b><small className="muted">{t("app_sub")}</small></div></div>
        <h2>{t("login_title")}</h2>
        <div className="grid">
          <Field label={t("email")}><input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
          <Field label={t("password")}><input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
        </div>
        <ErrorBox error={error} />
        <div className="actions" style={{ justifyContent: "space-between" }}>
          <button type="button" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{t("language")}</button>
          <button className="primary" disabled={busy}>{t("login")}</button>
        </div>
      </form>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { t, lang, setLang } = useI18n();
  const { user, logout, can, counts } = useAuth();
  const [pw, setPw] = useState(false);
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);
  useStackedTables();
  const zoom = useZoom(user);
  return (
    <NavProvider>
      <div className="mobile-bar">
        <span className="brand-mini"><img src="/hayah-logo.png" alt="" /><b>{t("app_name")}</b></span>
        <ZoomControl zoom={zoom} compact />
        <button className="sm" onClick={() => setOpen(!open)} aria-label={t("nav_menu")} aria-expanded={open}>☰</button>
      </div>
      <div className="shell">
        {open && <div className="side-scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
        <aside className={`side ${open ? "open" : ""}`}>
          <div className="brand"><img className="logo" src="/hayah-logo.png" alt="HAYAH" /><div><b>{t("app_name")}</b><small>{t("app_sub")}</small></div></div>
          <div className="side-user">
            <span className="avatar">{initials(user.full_name)}</span>
            <div><b>{user.full_name}</b><small>{t("role_" + user.role)}</small></div>
          </div>
          <SideNav counts={counts} />
          <div className="side-foot">
            <button className="side-act" onClick={() => setLang(lang === "ar" ? "en" : "ar")}><I.Languages size={16} /> {t("language")}</button>
            <button className="side-act" onClick={() => setPw(true)}><I.KeyRound size={16} /> {t("pw_title")}</button>
            <button className="side-act" onClick={logout}><I.LogOut size={16} /> {t("logout")}</button>
            {pw && <ChangePassword onClose={() => setPw(false)} />}
          </div>
        </aside>
        <main className="main"><Header zoom={zoom} /><div className="page">{children}</div></main>
        {can(...MANAGERS) && <Suspense fallback={null}><PromptBar /></Suspense>}
        <Suspense fallback={null}><HelpChat /></Suspense>
      </div>
      <BottomBar onMenu={() => setOpen(true)} />
    </NavProvider>
  );
}

/** On a phone, plain tables become one card per row: each cell gets its column name as a label. */
function useStackedTables() {
  useEffect(() => {
    const label = () => document.querySelectorAll<HTMLTableElement>(".main .table-wrap table").forEach((tb) => {
      const heads = Array.from(tb.querySelectorAll("thead th")).map((th) => th.textContent?.trim() || "");
      tb.querySelectorAll("tbody tr").forEach((tr) => Array.from(tr.children).forEach((td, i) => {
        if (heads[i] && td.getAttribute("data-label") !== heads[i]) td.setAttribute("data-label", heads[i]);
      }));
    });
    label();
    let raf = 0;
    const mo = new MutationObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(label); });
    const main = document.querySelector(".main");
    if (main) mo.observe(main, { childList: true, subtree: true });
    return () => { mo.disconnect(); cancelAnimationFrame(raf); };
  }, []);
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const { setLang } = useI18n();
  const [ops, setOps] = useState<Ops>({});
  // Plaque counts are small and change often: re-read every 10 s while the tab is open (no websockets on the small server).
  const refreshOps = () => { api<Ops>("/api/ops/counts").then(setOps).catch(() => {}); };
  const refreshCounts = () => { api("/api/dashboard").then((d) => setCounts(d.kpis)).catch(() => {}); refreshOps(); };
  useEffect(() => {
    if (!getToken()) { setChecked(true); return; }
    api<User>("/api/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setChecked(true));
  }, []);
  useEffect(() => { const h = () => setUser(null); window.addEventListener("hayah:logout", h); return () => window.removeEventListener("hayah:logout", h); }, []);
  useEffect(() => { if (user) refreshCounts(); }, [user]);
  useEffect(() => {
    if (!user) return;
    const id = window.setInterval(() => { if (document.visibilityState === "visible") refreshOps(); }, 10000);
    return () => window.clearInterval(id);
  }, [user]);
  if (!checked) return null;
  if (!user) return <Login onLogin={(u) => { setUser(u); setLang(u.preferred_lang); }} />;
  const ctx: AuthCtx = { user, can: (...r) => r.includes(user.role), logout: () => { setToken(null); setUser(null); }, counts: { ...counts, ...(ops.plaques ? { pl_confirm: ops.plaques.needs_confirmation, pl_ready: ops.plaques.ready_for_contractor } : {}),
    ...(ops.videos ? { vid_ready: ops.videos.ready_for_delivery + ops.videos.uploaded } : {}),
    ...(ops.whatsapp ? { wa_unread: ops.whatsapp.unread_chats || 0 } : {}),
    ...(ops.team ? { tasks_mine: ops.team.mine || 0 } : {}) }, refreshCounts, ops };
  return (
    <Auth.Provider value={ctx}>
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/book" element={<Suspense fallback={null}><Workbook /></Suspense>} />
            <Route path="/book/:kind/:id" element={<Suspense fallback={null}><Workbook /></Suspense>} />
            <Route path="/sheet" element={<Suspense fallback={null}><Sheet /></Suspense>} />
            <Route path="/projects/:wellId" element={<ProjectDetail />} />
            <Route path="/wells/:month" element={<MonthWells />} />
            <Route path="/sacrifices/:month" element={<MonthSacrifices />} />
            <Route path="/contractor/:code" element={<ContractorWells />} />
            <Route path="/plaque" element={<Suspense fallback={null}><PlaqueDesigner key="well" /></Suspense>} />
            <Route path="/plaque/sacrifice" element={<Suspense fallback={null}><PlaqueDesigner kind="sacrifice" key="sac" /></Suspense>} />
            <Route path="/plaque/sacrifice/:no" element={<Suspense fallback={null}><PlaqueDesigner kind="sacrifice" key="sac" /></Suspense>} />
            <Route path="/plaque/:wellId" element={<Suspense fallback={null}><PlaqueDesigner key="well" /></Suspense>} />
            <Route path="/certificate/:wellId" element={<Suspense fallback={null}><CertificatePage /></Suspense>} />
            <Route path="/plaques/confirm" element={<Suspense fallback={null}><PlaqueLists mode="confirm" key="c" /></Suspense>} />
            <Route path="/plaques/approved" element={<Suspense fallback={null}><PlaqueLists mode="approved" key="a" /></Suspense>} />
            <Route path="/videos" element={<Suspense fallback={null}><FinalVideos /></Suspense>} />
            <Route path="/videos/:kind/:no" element={<Suspense fallback={null}><FinalVideoPage /></Suspense>} />
            <Route path="/tasks" element={<Suspense fallback={null}><Tasks /></Suspense>} />
            <Route path="/inbox" element={<Suspense fallback={null}><Inbox /></Suspense>} />
            <Route path="/inbox/:id" element={<Suspense fallback={null}><Inbox /></Suspense>} />
            <Route path="/construction" element={<Construction />} />
            <Route path="/delivery" element={<Delivery />} />
            <Route path="/maintenance" element={<Maintenance />} />
            <Route path="/media" element={<MediaLibrary />} />
            <Route path="/review" element={<Review />} />
            <Route path="/contractors" element={<Contractors />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </Auth.Provider>
  );
}
