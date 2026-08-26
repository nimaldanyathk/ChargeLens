import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Cases from "./pages/Cases";
import CaseDetailPage from "./pages/CaseDetail";
import Analytics from "./pages/Analytics";

export default function App() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-name">ChargeLens</span>
          <span className="brand-tag">AI risk manager</span>
        </div>
        <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          Dashboard
        </NavLink>
        <NavLink to="/cases" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          Cases
        </NavLink>
        <NavLink to="/analytics" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          Model analytics
        </NavLink>
        <div className="sidebar-foot">
          Chargeback Risk &amp; Evidence Responder
          <br />
          Synthetic data · defense-only · human-in-the-loop
        </div>
      </aside>
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
  );
}
