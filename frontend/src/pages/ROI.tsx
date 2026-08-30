import { useState } from "react";
import { inr } from "../api";

// Public 2026 success-fee pricing for chargeback-automation vendors:
// Chargeflow ~25% of recoveries, Stripe Smart Disputes 30%, Justt ~20-25%.
// ChargeLens is software the merchant runs, so it takes no cut of wins.
const VENDORS = [
  { name: "Chargeflow", fee: 0.25 },
  { name: "Stripe Smart Disputes", fee: 0.30 },
  { name: "Justt", fee: 0.225 },
];

function Field({ label, value, onChange, suffix, step = 1 }: {
  label: string; value: number; onChange: (v: number) => void;
  suffix?: string; step?: number;
}) {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      <div className="stat-label" style={{ marginBottom: 4 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input
          type="number" value={value} step={step} min={0}
          onChange={(e) => onChange(Math.max(0, Number(e.target.value)))}
          style={{ width: 160 }}
        />
        {suffix && <span style={{ color: "var(--muted)", fontSize: 12 }}>{suffix}</span>}
      </div>
    </label>
  );
}

export default function ROI() {
  const [volume, setVolume] = useState(400);      // disputes / month
  const [avgValue, setAvgValue] = useState(4500); // INR
  const [winRate, setWinRate] = useState(0.42);   // fraction contested & won
  const [contestShare, setContestShare] = useState(0.6); // share worth fighting
  const [feeInr, setFeeInr] = useState(1000);     // non-refundable dispute fee
  const [opsInr, setOpsInr] = useState(300);      // handling cost / contest

  const contested = volume * contestShare;
  const grossRecovered = contested * winRate * avgValue;
  // ChargeLens: merchant keeps recoveries, pays only the per-dispute
  // fee (sunk on every contest) and ops handling
  const contestCosts = contested * (feeInr + opsInr);
  const chargelensNet = grossRecovered - contestCosts;

  const rows = VENDORS.map((v) => {
    const vendorCut = grossRecovered * v.fee;
    // vendor still doesn't refund the network dispute fee
    const net = grossRecovered - vendorCut - contested * feeInr;
    return { ...v, vendorCut, net, delta: chargelensNet - net };
  });

  return (
    <>
      <h1 className="page-title">Recovery ROI</h1>
      <p className="page-sub">
        Net recovery on your dispute volume, ChargeLens (software you run,
        no success fee) versus vendors that take a cut of every win. All
        figures use net recovery — win rate × amount minus the
        non-refundable dispute fee and handling cost — not headline win rate.
      </p>

      <div className="grid two-col">
        <div className="card">
          <h3>Your numbers</h3>
          <Field label="Disputes per month" value={volume} onChange={setVolume} />
          <Field label="Average dispute value" value={avgValue} onChange={setAvgValue} suffix="INR" step={100} />
          <Field label="Share worth contesting" value={contestShare} onChange={setContestShare} suffix="0–1" step={0.05} />
          <Field label="Win rate on contested" value={winRate} onChange={setWinRate} suffix="0–1" step={0.01} />
          <Field label="Dispute fee (non-refundable)" value={feeInr} onChange={setFeeInr} suffix="INR" step={50} />
          <Field label="Ops cost per contest" value={opsInr} onChange={setOpsInr} suffix="INR" step={50} />
        </div>

        <div className="grid" style={{ gap: 14 }}>
          <div className="card">
            <h3>ChargeLens — net recovery / month</h3>
            <div className="stat-value" style={{ fontSize: 30, color: "var(--good)" }}>
              {inr(chargelensNet)}
            </div>
            <div className="footnote">
              {Math.round(contested)} disputes contested · {inr(grossRecovered)} gross
              recovered · {inr(contestCosts)} in fees + handling. No success fee.
            </div>
          </div>
          <div className="card">
            <h3>Versus success-fee vendors</h3>
            <table className="data">
              <thead>
                <tr><th>Vendor</th><th>Fee</th><th className="num">Their cut</th><th className="num">Your net</th><th className="num">ChargeLens edge</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name}>
                    <td>{r.name}</td>
                    <td>{(r.fee * 100).toFixed(1)}%</td>
                    <td className="num">{inr(r.vendorCut)}</td>
                    <td className="num">{inr(r.net)}</td>
                    <td className="num" style={{ color: r.delta >= 0 ? "var(--good)" : "var(--bad)" }}>
                      {r.delta >= 0 ? "+" : ""}{inr(r.delta)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="footnote">
              Annualised, the edge over a {`${(VENDORS[1].fee * 100).toFixed(0)}%`} vendor
              is {inr(rows[1].delta * 12)}. The dispute fee is deducted for every
              option — it is a sunk cost of contesting regardless of who runs it.
            </div>
          </div>
        </div>
      </div>

      <div className="card section-gap">
        <h3>Why this framing</h3>
        <p style={{ color: "var(--ink-2)", margin: 0, fontSize: 13 }}>
          Vendors quote win-rate uplift; merchants care about money kept.
          Success-fee pricing scales the vendor's take with your recovered
          value, so the more you win the more you pay. ChargeLens is
          software you operate: it improves which disputes you fight (the
          per-case expected-value decision), and keeps the recovery. The
          honest cost it still carries — the false-positive cost of the risk
          model and the non-refundable dispute fee — is shown on the Model
          performance page and in every case's economics.
        </p>
      </div>
    </>
  );
}
