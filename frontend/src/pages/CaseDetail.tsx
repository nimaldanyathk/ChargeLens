import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, inr, pct, type CaseDetail, type CE3, type Economics, type EvidenceItemT, type Factor } from "../api";
import { BandBadge, DeadlineChip, RAIL_LABEL, REASON_LABEL, StatusBadge, fmtDate } from "../components/shared";

const BAND_COLOR: Record<string, string> = {
  high: "var(--critical)", review: "var(--warning)", low: "var(--good)",
};

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<CaseDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    if (!id) return;
    api.caseDetail(id).then(setData).catch((e) => setError(String(e)));
  }, [id]);
  useEffect(reload, [reload]);

  const investigate = async () => {
    if (!id) return;
    setBusy(true); setError(null);
    try { setData(await api.investigate(id)); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };

  const decide = async (action: string) => {
    if (!id) return;
    setBusy(true); setError(null);
    try { setData(await api.decide(id, action, note)); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };

  if (error && !data) return <div className="banner banner-warn">{error}</div>;
  if (!data) return <div className="spinner">Loading…</div>;

  const risk = data.risk;

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <h1 className="page-title" style={{ margin: 0 }}>{data.case_id}</h1>
        <StatusBadge status={data.status} />
        <BandBadge band={data.band} score={data.risk_score} />
        <DeadlineChip respondBy={data.respond_by} status={data.status} />
        <span style={{ marginLeft: "auto", color: "var(--ink-2)" }}>
          {RAIL_LABEL[data.rail] ?? data.rail}
          {data.network && data.network !== data.rail ? ` (${data.network})` : ""}
          {" · "}
          {REASON_LABEL[data.reason] ?? data.reason} · {inr(data.disputed_amount)}
        </span>
      </div>
      <p className="page-sub" style={{ marginTop: 6 }}>
        “{data.claim_description}” — filed {fmtDate(data.claim_ts)}
        {data.claim_delay_days != null && ` (${data.claim_delay_days.toFixed(1)} days after fulfilment event)`}
      </p>

      {error && <div className="banner banner-warn">{error}</div>}

      {data.status === "received" && (
        <div className="banner banner-info" style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ flex: 1 }}>
            This case has not been investigated yet. The agent will retrieve
            records, score risk, collect evidence and draft a response — then
            wait for your decision.
          </span>
          <button className="btn btn-primary" onClick={investigate} disabled={busy}>
            {busy ? "Investigating…" : "Run investigation"}
          </button>
        </div>
      )}

      <div className="grid two-col">
        <RecordCards data={data} />
        <div className="grid" style={{ gap: 14 }}>
          {risk && <RiskCard risk={risk} />}
          {risk?.economics && <EconomicsCard econ={risk.economics} caseId={data.case_id} rec={data.recommendation} />}
          {risk?.ce3 && risk.ce3.status !== "not_applicable" && <CE3Card ce3={risk.ce3} />}
          {data.recommendation && (
            <RecommendationCard
              data={data} busy={busy} note={note} setNote={setNote} decide={decide}
            />
          )}
        </div>
      </div>

      {data.evidence.length > 0 && <EvidenceCard items={data.evidence} />}

      {data.status !== "received" && (
        <div className="banner banner-info" style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ flex: 1 }}>
            Evidence dossier — a representment packet (summary, economics,
            CE3.0 status, and every exhibit with its source) ready for
            issuer review. Nothing is submitted automatically.
          </span>
          <a className="btn btn-primary" href={`/api/cases/${data.case_id}/dossier.pdf`}
             target="_blank" rel="noreferrer">
            Download dossier (PDF)
          </a>
        </div>
      )}

      {data.generated_response && (
        <div className="card section-gap">
          <h3>
            Generated response
            <span style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0, marginLeft: 8 }}>
              ({data.response_generator === "deterministic"
                ? "grounded template — every fact cites a record"
                : data.response_generator})
            </span>
          </h3>
          <pre className="response-pre">{data.generated_response}</pre>
        </div>
      )}

      {data.audit.length > 0 && (
        <div className="card section-gap">
          <h3>Audit trail</h3>
          {data.audit.map((a, i) => (
            <div className="audit-row" key={i}>
              <span className="audit-ts">{fmtDate(a.ts)}</span>
              <span className={`audit-actor ${a.actor}`}>{a.actor}</span>
              <span>
                <strong>{a.event_type.replace(/_/g, " ")}</strong>
                {" — "}
                {summariseDetail(a.detail)}
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function summariseDetail(detail: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(detail)) {
    if (v === null || v === undefined) continue;
    if (typeof v === "object") continue;
    parts.push(`${k.replace(/_/g, " ")}: ${String(v)}`);
  }
  return parts.join(" · ") || "—";
}

function RecordCards({ data }: { data: CaseDetail }) {
  const { transaction: t, order: o, delivery: d, customer: c } = data;
  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="card">
        <h3>Transaction &amp; order</h3>
        <dl className="kv">
          <dt>Transaction</dt><dd>{t?.id}</dd>
          <dt>Amount</dt><dd>{t ? inr(t.amount) : "—"}</dd>
          <dt>Payment</dt><dd>{t?.payment_method.replace(/_/g, " ")} · {t?.payment_status}</dd>
          <dt>Product</dt><dd>{o?.product_name} ×{o?.quantity}</dd>
          <dt>Shipping</dt><dd>{o?.shipping_city}</dd>
          <dt>Billing</dt>
          <dd>{o?.billing_city} {o?.shipping_billing_match ? "(match)" : "(mismatch)"}</dd>
          <dt>Device seen before</dt><dd>{t?.device_seen_before ? "yes" : "no"}</dd>
          <dt>Txns last 24h</dt><dd>{t?.txns_last_24h}</dd>
          <dt>IP distance</dt><dd>{t ? `${t.ip_geo_distance_km.toFixed(0)} km` : "—"}</dd>
        </dl>
      </div>
      <div className="card">
        <h3>Delivery</h3>
        <dl className="kv">
          <dt>Status</dt><dd>{d?.delivery_status.replace(/_/g, " ") ?? "no record"}</dd>
          <dt>Confirmation</dt><dd>{d?.delivery_confirmation ?? "—"}</dd>
          <dt>Carrier</dt><dd>{d?.carrier ?? "—"}</dd>
          <dt>Tracking</dt><dd>{d?.tracking_number ?? "none on file"}</dd>
          <dt>Shipped</dt><dd>{fmtDate(d?.shipped_ts)}</dd>
          <dt>Delivered</dt><dd>{fmtDate(d?.delivered_ts)}</dd>
        </dl>
      </div>
      <div className="card">
        <h3>Customer</h3>
        <dl className="kv">
          <dt>Customer</dt><dd>{c?.id}</dd>
          <dt>Account age</dt><dd>{c ? `${(c.account_age_days / 30).toFixed(0)} months` : "—"}</dd>
          <dt>Previous orders</dt><dd>{c?.previous_orders}</dd>
          <dt>Previous chargebacks</dt><dd>{c?.previous_chargebacks}</dd>
          <dt>Previous returns</dt><dd>{c?.previous_returns}</dd>
          <dt>Failed payments</dt><dd>{c?.previous_failed_payments}</dd>
          <dt>Avg order value</dt><dd>{c ? inr(c.avg_order_value) : "—"}</dd>
        </dl>
      </div>
    </div>
  );
}

function RiskCard({ risk }: { risk: NonNullable<CaseDetail["risk"]> }) {
  const color = BAND_COLOR[risk.band] ?? "var(--baseline)";
  return (
    <div className="card">
      <h3>Model risk assessment</h3>
      <div className="risk-hero">
        <div className="risk-score" style={{ color }}>
          {(risk.risk_score * 100).toFixed(0)}%
        </div>
        <div style={{ flex: 1 }}>
          <div className="risk-meter">
            <div
              className="risk-meter-fill"
              style={{ width: `${Math.max(risk.risk_score * 100, 2)}%`, background: color }}
            />
          </div>
          <div className="chart-note">
            Calibrated probability that this dispute is abusive ·
            model v{risk.model_version}
          </div>
        </div>
      </div>
      <div className="section-gap">
        <FactorBars factors={risk.top_factors} />
      </div>
      <div className="chart-note">
        SHAP attributions for this case — associational, not causal.
      </div>
    </div>
  );
}

function FactorBars({ factors }: { factors: Factor[] }) {
  const max = useMemo(
    () => Math.max(...factors.map((f) => Math.abs(f.shap)), 1e-6),
    [factors],
  );
  return (
    <div>
      {factors.map((f) => (
        <div className="factor-row" key={f.feature}>
          <div className="factor-label">
            {f.direction === "raises_risk" ? "▲" : "▼"} {f.label}
            <span className="factor-value">({f.value})</span>
          </div>
          <div className="factor-bar-track">
            <div
              className="factor-bar"
              style={{
                width: `${(Math.abs(f.shap) / max) * 100}%`,
                left: 0,
                background: f.direction === "raises_risk" ? "var(--critical)" : "var(--series-1)",
              }}
              title={`SHAP ${f.shap.toFixed(3)}`}
            />
          </div>
        </div>
      ))}
      <div className="chart-note">
        ▲ raises modelled risk (red) · ▼ lowers it (blue)
      </div>
    </div>
  );
}

function CE3Card({ ce3 }: { ce3: CE3 }) {
  const qualified = ce3.status === "qualified";
  return (
    <div className="card">
      <h3>
        Visa Compelling Evidence 3.0
        <span className="h3-note">reason code {ce3.reason_code}</span>
      </h3>
      <div className={`rec-box ${qualified ? "contest" : "review"}`}>
        <div className="rec-title" style={{ color: qualified ? "var(--good)" : "var(--warn)" }}>
          {qualified ? "Qualified — liability shifts to issuer" : "Requires action"}
        </div>
        <div style={{ color: "var(--ink-2)" }}>{ce3.note}</div>
      </div>
      <dl className="kv" style={{ marginTop: 12 }}>
        {ce3.matched_main.length > 0 && (
          <>
            <dt>Matched main elements</dt>
            <dd>{ce3.matched_main.join(", ")}</dd>
          </>
        )}
        {ce3.matched_secondary.length > 0 && (
          <>
            <dt>Matched secondary</dt>
            <dd>{ce3.matched_secondary.join(", ")}</dd>
          </>
        )}
        {ce3.qualifying_transactions.length > 0 && (
          <>
            <dt>Qualifying prior txns</dt>
            <dd>{ce3.qualifying_transactions.join(", ")}</dd>
          </>
        )}
        {ce3.missing.length > 0 && (
          <>
            <dt>Missing to qualify</dt>
            <dd>{ce3.missing.join("; ")}</dd>
          </>
        )}
      </dl>
      <div className="chart-note">
        CE3.0 needs two prior undisputed transactions (120–365 days) sharing
        device/IP or address with the disputed one. Deterministic rules
        check — not a model prediction.
      </div>
    </div>
  );
}

function EconomicsCard({ econ, caseId, rec }: {
  econ: Economics; caseId: string; rec: string | null;
}) {
  return (
    <div className="card">
      <h3>
        Dispute economics
        <span className="h3-note">is this contest worth fighting?</span>
      </h3>
      <dl className="kv">
        <dt>Modeled win probability</dt>
        <dd>{pct(econ.p_win, 0)}</dd>
        <dt style={{ paddingLeft: 12 }}>= calibrated risk</dt>
        <dd>{pct(econ.p_cal, 0)}, capped at {pct(econ.prior_cap, 0)} for this reason type</dd>
        <dt style={{ paddingLeft: 12 }}>× evidence factor</dt>
        <dd>{econ.evidence_factor} ({econ.evidence_strength} evidence)</dd>
        <dt>Expected recovery</dt><dd>{inr(econ.expected_recovery_inr)}</dd>
        <dt>Cost to contest</dt>
        <dd>{inr(econ.contest_cost_inr)} (fee not refunded on a win)</dd>
        <dt>Expected value</dt>
        <dd style={{ color: econ.economic ? "var(--good)" : "var(--bad)" }}>
          {inr(econ.ev_contest_inr)} — {econ.economic ? "worth contesting" : "uneconomic"}
        </dd>
        <dt>Break-even win probability</dt>
        <dd>{pct(econ.break_even_p_win, 1)} at this amount</dd>
      </dl>
      {rec === "contest" && (
        <div className="chart-note" style={{ marginTop: 8 }}>
          <a href={`/api/cases/${caseId}/contest-payload`} target="_blank" rel="noreferrer">
            View Razorpay contest payload
          </a>{" "}
          — matches PATCH /v1/disputes/:id/contest, action stays "draft".
        </div>
      )}
      <div className="chart-note">
        Win probabilities are anchored to industry representment outcomes,
        not model confidence alone. Assumptions: fee {inr(econ.assumptions.dispute_fee_inr)},
        ops {inr(econ.assumptions.ops_cost_inr)}, pre-arbitration haircut{" "}
        {pct(econ.assumptions.pre_arb_haircut, 1)}.
      </div>
    </div>
  );
}

const REC_TITLE: Record<string, string> = {
  contest: "Contest the chargeback",
  accept: "Accept the dispute",
  review: "Human review required",
};

function RecommendationCard({ data, busy, note, setNote, decide }: {
  data: CaseDetail; busy: boolean; note: string;
  setNote: (v: string) => void; decide: (a: string) => void;
}) {
  const rec = data.recommendation!;
  const decided = ["approved", "rejected", "escalated"].includes(data.status);
  return (
    <div className="card">
      <h3>Agent recommendation</h3>
      <div className={`rec-box ${rec}`}>
        <div className="rec-title">{REC_TITLE[rec] ?? rec}</div>
        <div style={{ color: "var(--ink-2)" }}>{data.recommendation_reason}</div>
      </div>
      {decided ? (
        <div className={`banner ${data.status === "approved" ? "banner-good" : "banner-warn"}`}
             style={{ marginTop: 14, marginBottom: 0 }}>
          Merchant {data.status} this recommendation
          {data.human_decision_note && ` — “${data.human_decision_note}”`}
          {" "}({fmtDate(data.human_decision_ts)})
        </div>
      ) : data.status === "awaiting_review" ? (
        <div className="section-gap">
          <input
            type="text" placeholder="Decision note (optional)" value={note}
            onChange={(e) => setNote(e.target.value)}
            style={{ width: "100%", marginBottom: 10 }}
          />
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button className="btn btn-approve" disabled={busy} onClick={() => decide("approve")}>
              Approve
            </button>
            <button className="btn btn-danger" disabled={busy} onClick={() => decide("reject")}>
              Reject
            </button>
            <button className="btn" disabled={busy} onClick={() => decide("escalate")}>
              Escalate
            </button>
          </div>
          <div className="chart-note">
            Nothing is submitted or refunded until you decide. The agent
            cannot move money, ban customers, or alter records.
          </div>
        </div>
      ) : null}
    </div>
  );
}

const EV_META: Record<EvidenceItemT["supports"], { icon: string; cls: string; title: string }> = {
  merchant: { icon: "✓", cls: "ev-merchant", title: "Supports the merchant" },
  customer: { icon: "◆", cls: "ev-customer", title: "Supports the customer" },
  neutral: { icon: "•", cls: "ev-neutral", title: "Context" },
  missing: { icon: "!", cls: "ev-missing", title: "Missing evidence" },
};

function EvidenceCard({ items }: { items: EvidenceItemT[] }) {
  const order: EvidenceItemT["supports"][] = ["merchant", "customer", "missing", "neutral"];
  const sorted = [...items].sort(
    (a, b) => order.indexOf(a.supports) - order.indexOf(b.supports),
  );
  return (
    <div className="card section-gap">
      <h3>Evidence ({items.length} items, each cites a source record)</h3>
      {sorted.map((e) => {
        const meta = EV_META[e.supports];
        return (
          <div className="evidence-item" key={e.key + e.source}>
            <div className={`evidence-icon ${meta.cls}`} title={meta.title}>{meta.icon}</div>
            <div style={{ flex: 1 }}>
              <div>{e.statement}</div>
              <div className="evidence-src">
                {meta.title.toLowerCase()} · {e.strength} · source {e.source}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
