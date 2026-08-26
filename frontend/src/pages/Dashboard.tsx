import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, inr, type CaseSummary, type Dashboard as DashboardT } from "../api";
import { BandBadge, REASON_LABEL, StatusBadge, Tile, fmtDate } from "../components/shared";

export default function Dashboard() {
  const [dash, setDash] = useState<DashboardT | null>(null);
  const [queue, setQueue] = useState<CaseSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      api.dashboard(),
      api.cases({ status: "awaiting_review", limit: "8" }),
    ])
      .then(([d, c]) => { setDash(d); setQueue(c.cases); })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="banner banner-warn">API unavailable: {error}</div>;
  if (!dash) return <div className="spinner">Loading…</div>;

  return (
    <>
      <h1 className="page-title">Dispute overview</h1>
      <p className="page-sub">
        Live state of the chargeback queue. Recommendations are advisory —
        every action requires merchant approval.
      </p>

      <div className="grid tiles">
        <Tile label="Open cases" value={dash.open_cases} note={`${dash.total_cases} total`} />
        <Tile label="High risk" value={dash.high_risk} note="recommend contest" />
        <Tile label="Needs review" value={dash.review_band} note="uncertainty band" />
        <Tile label="Low risk" value={dash.low_risk} note="likely legitimate" />
        <Tile label="Awaiting your decision" value={dash.awaiting_review} />
        <Tile label="Not yet investigated" value={dash.uninvestigated} />
      </div>

      <div className="grid two-col section-gap">
        <div className="card">
          <h3>Financial exposure</h3>
          <div className="risk-hero">
            <div>
              <div className="tile-label">Open disputed amount</div>
              <div className="tile-value">{inr(dash.open_exposure_inr)}</div>
            </div>
            <div>
              <div className="tile-label">Estimated recovery (approved contests)</div>
              <div className="tile-value" style={{ color: "var(--good-text)" }}>
                {inr(dash.estimated_recovery_inr)}
              </div>
              <div className="tile-note">{dash.recovery_note}</div>
            </div>
          </div>
        </div>
        <div className="card">
          <h3>How to read this</h3>
          <p style={{ margin: 0, color: "var(--ink-2)" }}>
            Each case is scored by a calibrated XGBoost model trained on
            synthetic dispute data, then gated by an evidence policy: a high
            score alone never triggers a contest recommendation without
            strong contradicting evidence on file. Bands come from
            cost-tuned thresholds — see Model analytics for the held-out
            metrics behind them.
          </p>
        </div>
      </div>

      <div className="card section-gap">
        <h3>Awaiting your decision</h3>
        {queue.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>Nothing waiting.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Case</th><th>Reason</th><th className="num">Amount</th>
                <th>Risk</th><th>Recommendation</th><th>Status</th><th>Claimed</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((c) => (
                <tr key={c.case_id} className="rowlink" onClick={() => navigate(`/cases/${c.case_id}`)}>
                  <td><a href={`/cases/${c.case_id}`} onClick={(e) => e.preventDefault()}>{c.case_id}</a></td>
                  <td>{REASON_LABEL[c.reason] ?? c.reason}</td>
                  <td className="num">{inr(c.disputed_amount)}</td>
                  <td><BandBadge band={c.band} score={c.risk_score} /></td>
                  <td style={{ textTransform: "capitalize" }}>{c.recommendation ?? "—"}</td>
                  <td><StatusBadge status={c.status} /></td>
                  <td>{fmtDate(c.claim_ts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
