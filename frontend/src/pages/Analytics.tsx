import { useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis, ReferenceLine, BarChart, Bar, Cell,
} from "recharts";
import { api, inr, pct, type Analytics as AnalyticsT } from "../api";
import { Tile } from "../components/shared";

const AXIS = { stroke: "var(--baseline)", fontSize: 11, fill: "var(--muted)" };

export default function Analytics() {
  const [data, setData] = useState<AnalyticsT | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.analytics().then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="banner banner-warn">{error}</div>;
  if (!data) return <div className="spinner">Loading…</div>;

  const m = data.metrics;
  const cd = m.contest_decision_at_t_high;
  const cm = cd.confusion_matrix;
  const cost = m.cost_analysis;
  const manifest = data.dataset_manifest;

  const policyRows = [
    { name: "Accept all disputes", value: cost.policy_costs_inr.accept_all_disputes },
    { name: "Contest all disputes", value: cost.policy_costs_inr.contest_all_disputes },
    { name: "Model (binary @ t_high)", value: cost.policy_costs_inr.model_binary_at_t_high },
    { name: "Model + human review band", value: cost.policy_costs_inr.model_three_band_with_human_review },
  ];

  return (
    <>
      <h1 className="page-title">Model analytics</h1>
      <p className="page-sub">
        Every number on this page was measured by the evaluation pipeline on
        the held-out test split — nothing is hand-entered.
      </p>

      <div className="banner banner-info">{m.disclosure}</div>

      <div className="grid tiles">
        <Tile label="Precision (contest)" value={pct(cd.precision)} note={`at t_high = ${m.thresholds.t_high}`} />
        <Tile label="Recall (contest)" value={pct(cd.recall)} />
        <Tile label="F1" value={pct(cd.f1)} />
        <Tile label="False-positive rate" value={pct(cd.false_positive_rate)} />
        <Tile label="ROC-AUC" value={m.threshold_free.roc_auc.toFixed(3)} />
        <Tile label="PR-AUC" value={m.threshold_free.pr_auc.toFixed(3)} />
      </div>

      <div className="grid two-col section-gap">
        <div className="card">
          <h3>Confusion matrix — held-out test ({m.test_set.n_cases} cases)</h3>
          <ConfusionMatrix tp={cm.tp} fp={cm.fp} fn={cm.fn} tn={cm.tn} />
          <div className="chart-note">
            Positive class = abusive dispute (recommend contest). Test
            abusive rate {pct(m.test_set.abusive_rate)}.
          </div>
        </div>
        <div className="card">
          <h3>False-positive cost — the honest number</h3>
          <dl className="kv">
            <dt>False positives (honest customers flagged)</dt>
            <dd>{cost.false_positive_count}</dd>
            <dt>Cost of those false positives</dt>
            <dd style={{ color: "var(--critical)", fontWeight: 700 }}>
              {inr(cost.false_positive_cost_inr)}
            </dd>
            <dt>False negatives (missed abuse)</dt>
            <dd>{cost.false_negative_count}</dd>
            <dt>Cost of missed abuse</dt>
            <dd>{inr(cost.false_negative_cost_inr)}</dd>
            <dt>Recovered by contesting true abuse</dt>
            <dd style={{ color: "var(--good-text)", fontWeight: 700 }}>
              {inr(cost.recovered_from_true_positives_inr)}
            </dd>
            <dt>Estimated savings vs accepting everything</dt>
            <dd style={{ color: "var(--good-text)", fontWeight: 700 }}>
              {inr(cost.estimated_savings_vs_accept_all_inr)}
            </dd>
          </dl>
          <div className="chart-note">
            Assumptions (stated, auditable): ops {inr(cost.assumptions.ops_cost_inr)}/case,
            goodwill {inr(cost.assumptions.goodwill_cost_inr)}/wrong contest, scheme
            fee {inr(cost.assumptions.chargeback_fee_inr)}, contest win
            rate {pct(cost.assumptions.contest_win_rate, 0)}, human
            review {inr(cost.review_ops_cost_inr_per_case)}/case.
          </div>
        </div>
      </div>

      <div className="grid two-col section-gap">
        <div className="card">
          <h3>Precision–recall curve (test)</h3>
          <CurveChart
            points={m.curves.precision_recall} xLabel="Recall" yLabel="Precision"
          />
        </div>
        <div className="card">
          <h3>ROC curve (test)</h3>
          <CurveChart points={m.curves.roc} xLabel="FPR" yLabel="TPR" diagonal />
        </div>
      </div>

      <div className="grid two-col section-gap">
        <div className="card">
          <h3>Calibration — predicted vs observed</h3>
          <ResponsiveContainer width="100%" height={230}>
            <LineChart
              data={m.curves.calibration}
              margin={{ top: 8, right: 12, bottom: 4, left: 0 }}
            >
              <CartesianGrid stroke="var(--grid)" strokeWidth={1} />
              <XAxis dataKey="mean_predicted" type="number" domain={[0, 1]}
                     tick={AXIS} tickFormatter={(v: number) => v.toFixed(1)}
                     label={{ value: "Mean predicted risk", position: "insideBottom", dy: 10, fontSize: 11, fill: "var(--muted)" }} />
              <YAxis type="number" domain={[0, 1]} tick={AXIS}
                     tickFormatter={(v: number) => v.toFixed(1)} width={34} />
              <Tooltip
                formatter={(v) => (typeof v === "number" ? v.toFixed(3) : String(v))}
                labelFormatter={(v) => `predicted ${Number(v).toFixed(3)}`}
              />
              <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
                             stroke="var(--baseline)" strokeDasharray="5 4" />
              <Line dataKey="observed_rate" name="Observed abusive rate"
                    stroke="var(--series-1)" strokeWidth={2}
                    dot={{ r: 3.5, fill: "var(--series-1)", strokeWidth: 0 }} />
            </LineChart>
          </ResponsiveContainer>
          <div className="chart-note">
            Isotonic calibration fitted on validation. Dashed line = perfectly
            calibrated. Brier score {m.threshold_free.brier_score.toFixed(3)}.
          </div>
        </div>
        <div className="card">
          <h3>Expected cost vs contest threshold (validation)</h3>
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={data.threshold_curve}
                       margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="var(--grid)" strokeWidth={1} />
              <XAxis dataKey="threshold" type="number" domain={[0, 1]} tick={AXIS} />
              <YAxis tick={AXIS} width={70}
                     tickFormatter={(v: number) => `${(v / 100000).toFixed(1)}L`} />
              <Tooltip formatter={(v) => inr(Number(v))}
                       labelFormatter={(v) => `threshold ${v}`} />
              <ReferenceLine x={m.thresholds.t_high} stroke="var(--critical)"
                             strokeDasharray="4 4"
                             label={{ value: `t_high ${m.thresholds.t_high}`, fontSize: 11, fill: "var(--critical)", position: "top" }} />
              <ReferenceLine x={m.thresholds.t_low} stroke="var(--warning)"
                             strokeDasharray="4 4"
                             label={{ value: `t_low ${m.thresholds.t_low}`, fontSize: 11, fill: "#7a5200", position: "top" }} />
              <Line dataKey="expected_cost_inr" name="Expected cost (INR)"
                    stroke="var(--series-1)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="chart-note">
            t_high minimises expected business cost subject to a precision
            floor of 85% on validation; t_low keeps the auto-accept band ≥96%
            legitimate. Y axis in lakh INR.
          </div>
        </div>
      </div>

      <div className="grid two-col section-gap">
        <div className="card">
          <h3>Policy comparison — net cost on the test set</h3>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={policyRows} layout="vertical"
                      margin={{ top: 4, right: 24, bottom: 4, left: 10 }}>
              <CartesianGrid stroke="var(--grid)" strokeWidth={1} horizontal={false} />
              <XAxis type="number" tick={AXIS}
                     tickFormatter={(v: number) => `${(v / 100000).toFixed(0)}L`} />
              <YAxis type="category" dataKey="name" width={170}
                     tick={{ ...AXIS, fill: "var(--ink-2)", fontSize: 12 }} />
              <Tooltip formatter={(v) => inr(Number(v))} />
              <ReferenceLine x={0} stroke="var(--baseline)" />
              <Bar dataKey="value" name="Net cost" radius={[0, 4, 4, 0]} barSize={18}>
                {policyRows.map((row) => (
                  <Cell key={row.name} fill="var(--series-1)"
                        opacity={row.name.startsWith("Model + human") ? 1 : 0.55} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="chart-note">
            Negative = net recovery for the merchant. {cost.three_band_assumption}.
          </div>
        </div>
        <div className="card">
          <h3>Model selection (validation PR-AUC)</h3>
          <table className="data">
            <thead>
              <tr><th>Candidate</th><th className="num">PR-AUC</th><th className="num">ROC-AUC</th></tr>
            </thead>
            <tbody>
              {data.model_selection.leaderboard.map((r) => (
                <tr key={r.model}
                    style={r.model === data.model_selection.selected_model
                      ? { fontWeight: 700 } : undefined}>
                  <td>{r.model}{r.model === data.model_selection.selected_model && " ← selected"}</td>
                  <td className="num">{r.val_pr_auc.toFixed(4)}</td>
                  <td className="num">{r.val_roc_auc.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="chart-note">
            Selected on validation only; {data.model_selection.calibration}.
          </div>
        </div>
      </div>

      <div className="grid two-col section-gap">
        <div className="card">
          <h3>Global feature importance (mean |SHAP|)</h3>
          <ImportanceBars rows={data.global_importance.top_features.slice(0, 12)} />
          <div className="chart-note">
            {data.global_importance.method} · n={data.global_importance.sample_size}
          </div>
        </div>
        <div className="card">
          <h3>Routing bands on the test set</h3>
          <table className="data">
            <thead>
              <tr><th>Band</th><th className="num">Cases</th><th className="num">Share</th><th className="num">Actually abusive</th></tr>
            </thead>
            <tbody>
              {(["high", "review", "low"] as const).map((b) => (
                <tr key={b}>
                  <td style={{ textTransform: "capitalize" }}>{b}</td>
                  <td className="num">{m.bands[b].count}</td>
                  <td className="num">{pct(m.bands[b].share)}</td>
                  <td className="num">{m.bands[b].abusive_rate != null ? pct(m.bands[b].abusive_rate) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {manifest && (
            <div className="chart-note">
              Dataset: {manifest.n_cases.toLocaleString()} synthetic cases,
              seed {manifest.seed}, {pct(manifest.class_balance.abusive_rate)} abusive ·
              split {manifest.split_strategy} ·
              train/val/test {manifest.splits.train}/{manifest.splits.val}/{manifest.splits.test}.
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function CurveChart({ points, xLabel, yLabel, diagonal }: {
  points: { x: number; y: number }[]; xLabel: string; yLabel: string;
  diagonal?: boolean;
}) {
  return (
    <>
      <ResponsiveContainer width="100%" height={230}>
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" strokeWidth={1} />
          <XAxis dataKey="x" type="number" domain={[0, 1]} tick={AXIS}
                 tickFormatter={(v: number) => v.toFixed(1)}
                 label={{ value: xLabel, position: "insideBottom", dy: 10, fontSize: 11, fill: "var(--muted)" }} />
          <YAxis type="number" domain={[0, 1]} tick={AXIS}
                 tickFormatter={(v: number) => v.toFixed(1)} width={34} />
          <Tooltip
            formatter={(v) => (typeof v === "number" ? v.toFixed(3) : String(v))}
            labelFormatter={(v) => `${xLabel} ${Number(v).toFixed(3)}`}
          />
          {diagonal && (
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
                           stroke="var(--baseline)" strokeDasharray="5 4" />
          )}
          <Line dataKey="y" name={yLabel} stroke="var(--series-1)"
                strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

function ConfusionMatrix({ tp, fp, fn, tn }: { tp: number; fp: number; fn: number; tn: number }) {
  const max = Math.max(tp, fp, fn, tn);
  // sequential blue ramp: tint by magnitude, ink switches for dark cells
  const cell = (n: number) => {
    const t = n / max;
    const bg = ["#f1f6fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf"][
      Math.min(5, Math.floor(t * 6))
    ];
    const ink = t > 0.5 ? "#fff" : "var(--ink)";
    return { background: bg, color: ink };
  };
  return (
    <div className="cm-grid">
      <div />
      <div className="cm-head">Actual abusive</div>
      <div className="cm-head">Actual legitimate</div>
      <div className="cm-head">Predicted<br />contest</div>
      <div className="cm-cell" style={cell(tp)}>
        <div className="cm-n">{tp}</div><div className="cm-l">true positive</div>
      </div>
      <div className="cm-cell" style={cell(fp)}>
        <div className="cm-n">{fp}</div><div className="cm-l">false positive</div>
      </div>
      <div className="cm-head">Predicted<br />accept</div>
      <div className="cm-cell" style={cell(fn)}>
        <div className="cm-n">{fn}</div><div className="cm-l">false negative</div>
      </div>
      <div className="cm-cell" style={cell(tn)}>
        <div className="cm-n">{tn}</div><div className="cm-l">true negative</div>
      </div>
    </div>
  );
}

function ImportanceBars({ rows }: { rows: { feature: string; mean_abs_shap: number }[] }) {
  const max = Math.max(...rows.map((r) => r.mean_abs_shap), 1e-9);
  return (
    <div>
      {rows.map((r) => (
        <div className="factor-row" key={r.feature}
             style={{ gridTemplateColumns: "230px 1fr" }}>
          <div className="factor-label" style={{ fontSize: 12.5 }}>{r.feature}</div>
          <div className="factor-bar-track">
            <div className="factor-bar"
                 style={{ width: `${(r.mean_abs_shap / max) * 100}%`, background: "var(--series-1)" }}
                 title={r.mean_abs_shap.toFixed(4)} />
          </div>
        </div>
      ))}
    </div>
  );
}
