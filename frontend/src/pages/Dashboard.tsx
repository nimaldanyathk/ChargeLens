import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, inr, type CaseSummary, type Dashboard as DashboardT } from "../api";
import { BandBadge, DeadlineChip, REASON_LABEL, Stat, StatusBadge } from "../components/shared";

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
      .then(([d, c]) => {
        setDash(d);
        // deadline-first: a missed respond_by is an automatic loss
        setQueue([...c.cases].sort((a, b) =>
          (a.respond_by ?? "9999").localeCompare(b.respond_by ?? "9999")));
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="banner banner-warn">API unavailable: {error}</div>;
  if (!dash) return <div className="spinner">Loading…</div>;

  return (
    <>
      <h1 className="page-title">Disputes overview</h1>
      <p className="page-sub">
        Recommendations are advisory — no dispute is contested, accepted or
        refunded without your approval.
      </p>

      <div className="stat-strip">
        <Stat label="Open disputes" value={dash.open_cases} note={`${dash.total_cases} total`} />
        <Stat label="High risk" value={dash.high_risk} note="contest recommended" />
        <Stat label="Needs review" value={dash.review_band} note="uncertainty band" />
        <Stat label="Low risk" value={dash.low_risk} note="likely legitimate" />
        <Stat label="Awaiting decision" value={dash.awaiting_review} />
        <Stat label="Not investigated" value={dash.uninvestigated} />
      </div>

      <div className="grid two-col section-gap">
        <div className="card">
          <h3>Amount under dispute</h3>
          <div className="stat-value" style={{ fontSize: 24 }}>{inr(dash.open_exposure_inr)}</div>
          <div className="footnote">Sum of disputed amounts across open cases.</div>
        </div>
        <div className="card">
          <h3>Expected recovery from approved contests</h3>
          <div className="stat-value" style={{ fontSize: 24, color: "var(--good)" }}>
            {inr(dash.estimated_recovery_inr)}
          </div>
          <div className="footnote">Estimate — {dash.recovery_note}.</div>
        </div>
      </div>

      <div className="card section-gap">
        <h3>
          Needs your decision
          <span className="h3-note">investigated by the agent, waiting on you</span>
        </h3>
        {queue.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>Nothing waiting.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Dispute</th><th>Reason</th><th className="num">Amount</th>
                <th>Risk</th><th>Recommendation</th><th>Status</th><th>Deadline</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((c) => (
                <tr
                  key={c.case_id} className="rowlink"
                  onClick={(e) => {
                    if (e.metaKey || e.ctrlKey) return;
                    const t = e.target as HTMLElement;
                    if (t.closest("a")) return;
                    navigate(`/cases/${c.case_id}`);
                  }}
                >
                  <td><Link to={`/cases/${c.case_id}`}>{c.case_id}</Link></td>
                  <td>{REASON_LABEL[c.reason] ?? c.reason}</td>
                  <td className="num">{inr(c.disputed_amount)}</td>
                  <td><BandBadge band={c.band} score={c.risk_score} /></td>
                  <td style={{ textTransform: "capitalize" }}>{c.recommendation ?? "—"}</td>
                  <td><StatusBadge status={c.status} /></td>
                  <td><DeadlineChip respondBy={c.respond_by} status={c.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="footnote">
          Scores come from a calibrated model with cost-tuned thresholds; a
          high score alone never triggers a contest recommendation without
          strong evidence on file. Details under Model performance.
        </div>
      </div>
    </>
  );
}
