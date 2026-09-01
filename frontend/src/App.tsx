import { useEffect, useState } from "react";
import {
  NavLink, Navigate, Route, Routes, useLocation, useNavigate,
} from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Cases from "./pages/Cases";
import CaseDetailPage from "./pages/CaseDetail";
import Analytics from "./pages/Analytics";
import { Splash, Wordmark } from "./components/Wordmark";

const PAGE_TITLES: [RegExp, string][] = [
  [/^\/cases\/.+/, "Dispute detail"],
  [/^\/cases/, "Disputes"],
  [/^\/analytics/, "Model performance"],
  [/^\//, "Overview"],
];

const ICONS = {
  overview: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1.5" y="1.5" width="5.4" height="5.4" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="9.1" y="1.5" width="5.4" height="5.4" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="1.5" y="9.1" width="5.4" height="5.4" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="9.1" y="9.1" width="5.4" height="5.4" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  ),
  disputes: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 1.8 L13.6 3.9 V8 C13.6 11.2 11.3 13.4 8 14.4 C4.7 13.4 2.4 11.2 2.4 8 V3.9 Z"
            stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M5.7 8 L7.3 9.6 L10.4 6.4" stroke="currentColor" strokeWidth="1.4"
            strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  analytics: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M2 14 H14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="3" y="8.2" width="2.4" height="3.6" rx="0.7" stroke="currentColor" strokeWidth="1.3" />
      <rect x="6.8" y="5.4" width="2.4" height="6.4" rx="0.7" stroke="currentColor" strokeWidth="1.3" />
      <rect x="10.6" y="2.6" width="2.4" height="9.2" rx="0.7" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
};

function navCls({ isActive }: { isActive: boolean }) {
  return `nav-link${isActive ? " active" : ""}`;
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [splashHiding, setSplashHiding] = useState(false);
  const [splashDone, setSplashDone] = useState(false);
  const title =
    PAGE_TITLES.find(([re]) => re.test(location.pathname))?.[1] ?? "Overview";

  useEffect(() => {
    const t1 = window.setTimeout(() => setSplashHiding(true), 1900);
    const t2 = window.setTimeout(() => setSplashDone(true), 2500);
    return () => { window.clearTimeout(t1); window.clearTimeout(t2); };
  }, []);

  return (
    <div className="layout">
      {!splashDone && <Splash hiding={splashHiding} />}
      <aside className="sidebar">
        <div className="brand">
          <Wordmark />
          <div className="brand-tag">Dispute intelligence · Razorpay merchants</div>
        </div>
        <nav className="nav-group">
          <div className="nav-label">Risk console</div>
          <NavLink to="/" end className={navCls}>
            {ICONS.overview}<span>Overview</span>
          </NavLink>
          <NavLink to="/cases" className={navCls}>
            {ICONS.disputes}<span>Disputes</span>
          </NavLink>
          <NavLink to="/analytics" className={navCls}>
            {ICONS.analytics}<span>Model performance</span>
          </NavLink>
        </nav>
        <div className="sidebar-foot">
          Synthetic demo data
          <br />
          Defense-only · human-in-the-loop
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <span className="topbar-title">{title}</span>
          <span className="mode-badge">TEST MODE</span>
          <div className="topbar-search">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="7" cy="7" r="4.6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10.6 10.6 L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <input
              type="text" placeholder="Search dispute or customer ID"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && search.trim()) {
                  navigate(`/cases?q=${encodeURIComponent(search.trim())}`);
                  setSearch("");
                }
              }}
            />
          </div>
          <div className="topbar-right">
            <span className="merchant-name">Acme Retail Pvt Ltd</span>
            <span className="avatar">AR</span>
          </div>
        </header>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/cases" element={<Cases />} />
            <Route path="/cases/:id" element={<CaseDetailPage />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
