import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Cases from "./pages/Cases";
import CaseDetailPage from "./pages/CaseDetail";
import Analytics from "./pages/Analytics";

const PAGE_TITLES: [RegExp, string][] = [
  [/^\/cases\/.+/, "Dispute detail"],
  [/^\/cases/, "Disputes"],
  [/^\/analytics/, "Model performance"],
  [/^\//, "Overview"],
];

function navCls({ isActive }: { isActive: boolean }) {
  return `nav-link${isActive ? " active" : ""}`;
}

export default function App() {
  const location = useLocation();
  const title =
    PAGE_TITLES.find(([re]) => re.test(location.pathname))?.[1] ?? "Overview";

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-name">
            <span className="brand-mark">C</span>
            ChargeLens
          </div>
          <div className="brand-tag">Dispute intelligence for Razorpay merchants</div>
        </div>
        <nav className="nav-group">
          <div className="nav-label">Risk console</div>
          <NavLink to="/" end className={navCls}>Overview</NavLink>
          <NavLink to="/cases" className={navCls}>Disputes</NavLink>
          <NavLink to="/analytics" className={navCls}>Model performance</NavLink>
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
          <div className="topbar-right">
            <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
              Acme Retail Pvt Ltd
            </span>
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
