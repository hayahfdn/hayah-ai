import { createContext, lazy, Suspense, useContext, useEffect, useState } from "react";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, getToken, setToken, User } from "./api";
import { useI18n } from "./i18n";
import { ErrorBox, Field } from "./ui";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
const Sheet = lazy(() => import("./pages/Sheet"));
const Workbook = lazy(() => import("./book/Workbook"));
const PromptBar = lazy(() => import("./book/PromptBar"));
import ProjectDetail from "./pages/ProjectDetail";
import Construction from "./pages/Construction";
import Delivery from "./pages/Delivery";
import Maintenance from "./pages/Maintenance";
import MediaLibrary from "./pages/MediaLibrary";
import Review from "./pages/Review";
import Contractors from "./pages/Contractors";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

type AuthCtx = { user: User; can: (...roles: string[]) => boolean; logout: () => void; counts: Record<string, number>; refreshCounts: () => void };
const Auth = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Auth);
export const MANAGERS = ["super_admin", "operations_manager"];

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
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  const items: [string, string, boolean, number?][] = [
    ["/", "nav_dashboard", true], ["/book", "nav_book", can(...MANAGERS)], ["/sheet", "nav_sheet", true], ["/projects", "nav_projects", true], ["/construction", "nav_construction", true],
    ["/delivery", "nav_delivery", true, counts.pending_delivery_approvals], ["/maintenance", "nav_maintenance", true],
    ["/media", "nav_media", true], ["/review", "nav_review", can(...MANAGERS), counts.pending_review],
    ["/contractors", "nav_contractors", true], ["/reports", "nav_reports", true], ["/settings", "nav_settings", can(...MANAGERS)],
  ];
  return (
    <>
      <div className="mobile-bar"><b>{t("app_name")}</b><button className="sm" onClick={() => setOpen(!open)} aria-label="menu">☰</button></div>
      <div className="shell">
        <aside className={`side ${open ? "open" : ""}`}>
          <div className="brand"><img className="logo" src="/hayah-logo.png" alt="HAYAH" /><div><b>{t("app_name")}</b><small>{t("app_sub")}</small></div></div>
          <nav className="nav">
            {items.filter((i) => i[2]).map(([to, key, , n]) => (
              <NavLink key={to} to={to} end={to === "/"}>{t(key)}{n ? <span className="count">{n}</span> : null}</NavLink>
            ))}
          </nav>
          <div className="side-foot">
            <div style={{ color: "#fff" }}>{user.full_name}</div>
            <div>{t("role_" + user.role)}</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button className="sm" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{t("language")}</button>
              <button className="sm" onClick={logout}>{t("logout")}</button>
            </div>
          </div>
        </aside>
        <main className="main">{children}</main>
        {can(...MANAGERS) && <Suspense fallback={null}><PromptBar /></Suspense>}
      </div>
    </>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const { setLang } = useI18n();
  const refreshCounts = () => { api("/api/dashboard").then((d) => setCounts(d.kpis)).catch(() => {}); };
  useEffect(() => {
    if (!getToken()) { setChecked(true); return; }
    api<User>("/api/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setChecked(true));
  }, []);
  useEffect(() => { const h = () => setUser(null); window.addEventListener("hayah:logout", h); return () => window.removeEventListener("hayah:logout", h); }, []);
  useEffect(() => { if (user) refreshCounts(); }, [user]);
  if (!checked) return null;
  if (!user) return <Login onLogin={(u) => { setUser(u); setLang(u.preferred_lang); }} />;
  const ctx: AuthCtx = { user, can: (...r) => r.includes(user.role), logout: () => { setToken(null); setUser(null); }, counts, refreshCounts };
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
