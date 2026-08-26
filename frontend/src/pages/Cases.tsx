import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, inr, type CaseSummary } from "../api";
import { BandBadge, REASON_LABEL, StatusBadge, fmtDate } from "../components/shared";

export default function Cases() {
  const [params, setParams] = useSearchParams();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const status = params.get("status") ?? "";
  const band = params.get("band") ?? "";
  const q = params.get("q") ?? "";

  useEffect(() => {
    const filter: Record<string, string> = {};
    if (status) filter.status = status;
    if (band) filter.band = band;
    if (q) filter.q = q;
    setLoading(true);
    api.cases(filter)
      .then((r) => setCases(r.cases))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [status, band, q]);

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <>
      <h1 className="page-title">Cases</h1>
      <p className="page-sub">All chargeback cases in the system.</p>

      <div className="filter-row">
        <select value={status} onChange={(e) => update("status", e.target.value)}>
          <option value="">Any status</option>
          <option value="received">Received</option>
          <option value="awaiting_review">Awaiting review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="escalated">Escalated</option>
        </select>
        <select value={band} onChange={(e) => update("band", e.target.value)}>
          <option value="">Any risk band</option>
          <option value="high">High</option>
          <option value="review">Review</option>
          <option value="low">Low</option>
        </select>
        <input
          type="text" placeholder="Search case / customer id" defaultValue={q}
          onKeyDown={(e) => {
            if (e.key === "Enter") update("q", (e.target as HTMLInputElement).value);
          }}
        />
      </div>

      <div className="card">
        {error && <div className="banner banner-warn">{error}</div>}
        {loading ? (
          <div className="spinner">Loading…</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Case</th><th>Customer</th><th>Reason</th>
                <th className="num">Amount</th><th>Risk</th>
                <th>Recommendation</th><th>Status</th><th>Claimed</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.case_id} className="rowlink" onClick={() => navigate(`/cases/${c.case_id}`)}>
                  <td>{c.case_id}</td>
                  <td>{c.customer_id}</td>
                  <td>{REASON_LABEL[c.reason] ?? c.reason}</td>
                  <td className="num">{inr(c.disputed_amount)}</td>
                  <td><BandBadge band={c.band} score={c.risk_score} /></td>
                  <td style={{ textTransform: "capitalize" }}>{c.recommendation ?? "—"}</td>
                  <td><StatusBadge status={c.status} /></td>
                  <td>{fmtDate(c.claim_ts)}</td>
                </tr>
              ))}
              {cases.length === 0 && (
                <tr><td colSpan={8} style={{ color: "var(--muted)" }}>No cases match.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
