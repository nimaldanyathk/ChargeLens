# ChargeLens robustness research

Research notes compiled 23 Aug 2026 to drive the pre-submission build sprint
(27 Aug – 5 Sep). Six angles: decision mathematics, fraud-ML methodology,
India payment rails, card-network dispute rules, LLM grounding/safety, and
the commercial product bar. Every claim carries its source; numbers are
industry-reported figures, not our measurements, and are used as priors and
context — never as our own results.

Priorities: **[must]** ships before submission, **[should]** ships if time
allows, **[could]** is documented as roadmap.

---

## 1. Decision mathematics — make the money claims survive a quant

**[must] Per-case expected value, not a global rule.**
The contest/accept decision is an EV comparison using the case's own amount:

```
EV(contest) = p_win · A − c_ops − c_fee        EV(accept) = 0
```

India-specific: the dispute fee (~₹500–2,000 in the Razorpay ecosystem) is
**not refunded even on a win** — it is a sunk cost of contesting, not a cost
of losing. Display EV in rupees on every case; recommend Accept whenever
EV < 0 regardless of risk score.
(chargeflow.io/blog/forecast-chargeback-recovery-rate, razorpay.com/blog/chargebacks/)

**[must] Example-dependent Bayes threshold.** Under calibrated probabilities
the optimal threshold is t\* = c_FP/(c_FP + c_FN) (Elkan 2001). Because the
false-negative cost is the case's own amount A_i, the threshold is
per-instance:

```
t_i = (c_ops + c_fee) / (c_ops + c_fee + A_i)
```

A ₹50,000 dispute should be contested at a far lower probability than a
₹800 one. Algebraically identical to EV > 0 — implement once, present both
ways. Global thresholds remain only for the review band.
(cseweb.ucsd.edu/~elkan/rescale.pdf; Bahnsen; Vanderschueren et al., EJOR 2021)

**[must] Decompose p_win — a calibrated fraud probability is NOT a win
probability.** Winning also requires evidence the issuer accepts. Industry
anchors: average representment win rate ~20%; merchants win ~43.8% of cases
they *choose* to fight but net dollar recovery is only ~10.7%; true-fraud
codes win ~17% vs ~44% for suspected friendly fraud; disciplined programs
target 55–65%. Vendor claims of ~75% reflect case selection. v1 model:

```
p_win_i = p_cal(abusive)_i × e_i × prior(reason_category)
```

where e_i ∈ [0.3, 1.0] is a deterministic evidence-strength multiplier and
the reason-category priors live in a citable JSON table (source URL stored
per entry, shown in the UI tooltip).
(chargebackgurus.com, chargebacks911.com/chargeback-stats/, chargeflow.io)

**[must] Net recovery is the honest KPI.** ~23% of representment wins are
challenged again in pre-arbitration (fees $25–50 filing, up to $500+$600 at
arbitration). Primary KPI: `expected net recovery = A·p_win·p(no pre-arb
loss) − fees − ops`. Lead the metrics page with the Savings score vs the
best naive policy (costcla): `savings = (C_baseline − C_model)/C_baseline`
with the full per-case cost matrix.
(albahnsen.github.io/CostSensitiveClassification; chargebacks911.com)

**[must] Bootstrap 95% CIs on every headline number.** Stratified bootstrap
(resample within class), B ≥ 5,000, percentile intervals; report
"Precision 86.5% [83.9, 89.0]" style, including the rupee-savings interval.
(github.com/luferrer/ConfidenceIntervals; Raschka 2022)

**[should] Conformal review band.** Use conformal risk control (Angelopoulos
et al., ICLR 2024) to pick the auto-decide region so the expected
missed-winnable rate among auto-decisions is ≤ α (e.g. 5%) with a
distribution-free finite-sample guarantee; α becomes a product setting
("risk tolerance"). (arxiv.org/abs/2208.02814)

**[should] Calibration evidence panel.** Reliability diagram with
equal-mass bins + per-bin counts, ECE and Brier with CIs, one-line
justification of isotonic given calibration-set size.
(arxiv.org/pdf/2112.10327)

**[should] Sensitivity analysis.** Tornado chart varying c_fee ₹500–2,000,
c_ops ₹100–1,000, ±10% calibration error, dispute mix — recomputing
*decisions* at each setting, base case marked. Plus a threshold-stability
plot: savings-vs-threshold curve with bootstrap ribbon showing the operating
point sits on a plateau, and the IQR of bootstrap-retuned thresholds.

**[could] One-page decision-theory appendix** in the model card tying the
chain: calibrated probability → example-dependent costs → Bayes per-case
decision → guaranteed deferral band → uncertainty-quantified savings →
sensitivity. This is exactly how cost-sensitive fraud papers structure
evaluation (Bahnsen 2014; Vanderschueren 2021).

---

## 2. Fraud-ML methodology — survive expert scrutiny

**[must] Temporal (out-of-time) split.** Random splits leak temporally
correlated cases and overstate fraud-model performance (published example:
ROC-AUC 0.977→0.853, AP 0.925→0.537 moving from random to out-of-time).
Re-split chronologically ~60/20/20, tune thresholds on the middle window,
report only the future window — and show random-split vs OOT side by side.
The honest degradation is itself a differentiator.

**[must] AUC-PR as headline metric.** At fraud prevalence ROC-AUC is
inflated by the true-negative pool; AP exposes degradation ROC hides.
Report the quadruple ROC-AUC / AUC-PR / Brier / expected-cost-at-threshold.

**[must] Leakage audit + point-in-time features.** List every feature with
its availability timestamp relative to dispute creation; rebuild customer
history (prior disputes, orders, account age) via as-of joins at the
dispute-created timestamp; publish the feature-availability table as a
"no future information" guarantee.

**[must] No SMOTE — and say why.** Resampling distorts calibration without
improving discrimination (van den Goorbergh et al., JAMIA 2022). Our
scale_pos_weight + isotonic architecture is the current consensus; add the
citation and Brier/log-loss to preempt the most common reviewer question.

**[should] IEEE-CIS external validation.** Its label is literally
chargeback-derived; a 1-day adapter mapping columns into our pipeline with a
time-ordered split gives a real-data transfer number against the published
XGBoost bar of ROC-AUC ~0.88–0.93.

**[should] Velocity / entity-sharing features.** disputes_per_customer
{7,30,90}d, disputes_per_device_30d, distinct_customers_sharing_device /
_address, distinct_instruments_per_customer — computed point-in-time; plant
2–3 abuse rings in the generator so they demonstrably fire. Rings reuse
devices and instruments even when names/emails rotate.

**[should] Drift endpoint.** PSI per feature and score decile vs training
baseline (<0.1 stable, 0.1–0.25 moderate, >0.25 action) + per-decile
predicted-vs-realized rate; documented retrain trigger.

**[could] Gameability registry + monotone constraints.** Tag features
customer-controllable vs immutable; XGBoost monotone_constraints so prior
disputes can never lower risk and tenure can never raise it.

---

## 3. India rails — not a US clone

**[must] UPI-first data model.** UPI is ~85% of Indian digital-payment
volume (H2 2025, RBI/IBEF). Add `rail` (upi|card|netbanking|wallet); for
UPI disputes use URCS semantics: uniform 45-day customer chargeback window
(NPCI OC 198/2023-24), URCS auto-accept/reject via TCC/RET since 15 Feb
2025, complaints arriving via UDIR. Rebalance synthetic data to ~80–85% UPI.

**[must] Mirror Razorpay's dispute entity exactly.** Phases fraud/
retrieval/chargeback/pre_arbitration/arbitration; statuses open/
under_review/won/lost/closed; the ten named evidence keys (shipping_proof,
billing_proof, cancellation_proof, customer_communication, proof_of_service,
explanation_letter, refund_confirmation, access_activity_log,
refund_cancellation_policy, term_and_conditions) + others[]; contest
requires ≥1 document uploaded via the Documents API (purpose=
dispute_evidence). Emit a contest-ready payload that would validate against
the real API.

**[must] The six real webhooks.** payment.dispute.{created, won, lost,
closed, under_review, action_required}; verify X-Razorpay-Signature over the
**raw** body; treat action_required as a high-priority queue trigger.

**[must] Deadline triage.** Practical representment windows in India are
days (~3 business days per acquirer guidance; NPCI/RuPay and UPI ~7 working
days; Visa's global windows compressed to ~9–18 days in Jul 2025 while
Mastercard allows 45). Queue sorted by (time-to-deadline, A×p_win);
deadline-missed logged as an explicit audit outcome. respond_by from the
API is the runtime source of truth.

**[should] RBI TAT gate.** Failed/duplicate/timeout transactions auto-
reverse under RBI's TAT Harmonisation circular (T+1..T+5, ₹100/day
compensation) — route them to "recommend accept, auto-reversal expected"
instead of drafting a defense.

**[should] Fraud-phase = authorization-proof narrative.** Under RBI's 2017
limited-liability circular issuers lean toward customers on unauthorised
claims; the winning merchant defense is proof the genuine customer
authorized (device match, history, 2FA/UPI PIN completion,
access_activity_log).

**[should] RTO/COD credibility features.** India RTO runs ~25–35% (COD
~26–35% vs <8% prepaid; ₹150–300 loss per failed order). Past-RTO count and
COD refusal rate become customer-credibility evidence; one dashboard stat
frames RTO as the India loss class. No separate RTO product.

**[must] FREE-AI alignment section.** RBI's FREE-AI report (Aug 2025) —
seven Sutras — maps directly onto shipped features: People First → human-
in-the-loop; Accountability → audit log; Understandable by Design →
calibrated scores + grounded drafts; Safety/Resilience → deterministic
fallback; Fairness → honest FP-cost metrics. One model-card page.

---

## 4. Card-network evidence rules

**[must] Visa CE3.0 eligibility checker** (reason code 10.4 only): ≥2 prior
paid, undisputed transactions on the same payment method aged 120–364 days;
disputed + both priors share two "main" elements (purchase IP, device
ID/fingerprint — note device fingerprint + device ID is NOT a valid pair)
or one main + one secondary (shipping address, email, account ID); product
descriptions required for all three. Qualified → liability shifts to
issuer. Emit qualified/requires_action with missing fields listed; badge in
UI; raises win-probability tier.

**[should] Mastercard First-Party Trust checker** (4837): one data point
from each of three categories — device identity, delivery information,
additional identity factor. Different logic from Visa; show which program a
case can invoke.

**[should] Canonical reason-code taxonomy.** Map Visa 10.x/11.x/12.x/13.x
and MC 4808/4834/4837/4853 into ~8 canonical categories
(10.4≈4837, 13.1≈4853-not-received, 13.3≈4853-not-as-described); scorer and
templates condition on the canonical category.

**[must] Reason-code-specific evidence templates** with weighted
completeness: INR (13.1/4853) → signed POD, tracking to verified address,
service/access logs; card-absent fraud (10.4/4837) → 3DS/AVS/CVV records,
IP+device history, login data, prior orders; not-as-described (13.3) →
product description as sold, customer comms, accepted refund policy. Add
refund-policy-disclosure and customer-comms-log as first-class evidence
fields. Readiness badge per dispute (Ready / Needs evidence / Weak) with a
"what's missing to win" checklist (Stripe recommended_evidence pattern).

**[should] Recalibrate generator class mix to cited base rates:** first-
party (friendly) fraud ~20% of disputes (Mastercard/Datos 2025); ~48% of
consumers admit disputing a legitimate charge; digital-goods fraud ~75%
first-party.

**[could] VAMP panel.** From 1 Apr 2026 Visa's combined fraud+dispute ratio
threshold tightens to 1.5% with $8/dispute in the excessive tier — and
winning a representment does NOT remove the dispute from the ratio. Honest
caveat: defense recovers revenue; it does not repair network standing.

---

## 5. LLM grounding & injection defense

**[must] Second gate: NLI verifier.** MiniCheck (EMNLP 2024, Apache-2.0):
RoBERTa-Large variant runs on CPU; per-sentence entailment against the
evidence pack rendered as grounding text; any sentence below threshold →
existing deterministic fallback. Keeps numeric gate as gate 1.
(github.com/Liyan06/MiniCheck)

**[must] Perturbation benchmark** (scripts/eval_grounding.py): ~100 cases →
~400 corrupted drafts across six classes (numeric swap, off-by-one date,
entity swap, fabricated event, unsupported strengthener, negation flip);
report per-class catch rate AND false-block rate on clean drafts (the FP
cost of the safety gate — same honesty bar as the scorer).

**[must] Spotlight claim_description.** It is attacker-controlled text
(OWASP LLM01 #1 risk). NFKC canonicalization, strip control/zero-width
chars, length cap; wrap in a labeled untrusted-data block with a random
per-request boundary token; datamark; system-prompt rule that the block has
zero instruction authority. (Hines et al. 2024; Microsoft MSRC 2025)

**[should] Injection red-team suite in CI.** 30–50 hostile
claim_descriptions (direct instructions, roleplay, fake system tags,
markdown/HTML smuggling, encodings, Hindi/Hinglish variants); assert no
canary token, no concession language; report attack-success-rate
before/after spotlighting.

**[should] Sentence-level citations in the review UI.** Each draft sentence
hover-links to the evidence fields it was verified against. No commercial
tool (Chargeflow, Justt, Stripe Smart Disputes) discloses its grounding
method — verifiable grounding is our differentiator.

**[should] Audit completeness per FREE-AI.** Each draft logs model+version,
prompt-template hash, both gate results per sentence, fallback events, and
the approving human + timestamp. No submission without an explicit human
approval event.

**[could] Output allowlist validator.** Every URL/email/ID/entity in a
draft must exist in the evidence pack; enforce letter structure; reject
markdown/HTML. Deterministic post-filter, independent of the NLI gate.

---

## 6. Product bar & positioning

**[must] Evidence dossier PDF export.** The universal commercial
deliverable: cover letter + reason-code-matched exhibits (transaction
verification, POD, comms, policies), one click, and the same file feeds the
Razorpay Documents API upload. The single most judge-visible artifact.

**[must] Position against Razorpay's own beta auto-responder.** Razorpay
has publicly announced a dispute auto-responder agent (co-founder Shashank
Kumar, already handling thousands of responses). A pure "we auto-draft"
pitch collides with their roadmap. ChargeLens is the **risk-managed layer**
an auto-responder lacks: calibrated win probability, cost-tuned fight/accept
economics, grounding-verified drafts with deterministic fallback,
human-approved submissions, audit trail. One pitch slide contrasts the two.

**[must] ROI calculator.** Public 2026 pricing: Chargeflow 25% of
recoveries (+$29/alert), Stripe Smart Disputes 30% of recoveries, Justt
~20–25%. Given volume, average value, and our honest win rate: net recovery
under ChargeLens vs a success-fee vendor, with the scorer's FP cost in the
same table.

**[should] Prevention-vs-representment explainer.** Verifi CDRN/RDR and
Ethoca alerts prevent ~40–70% of alerted chargebacks but every prevented
case = 100% revenue loss + per-alert fee (~$15–30), and coverage gaps on
India's UPI/RuPay rails. ChargeLens is the recovery layer that complements
alerts.

**[should] Deadline safety net (opt-in).** Stripe's flagship pattern:
if no human decision by N hours before respond_by, submit the deterministic
(never LLM) draft — only when the merchant has explicitly pre-authorized
the behavior in settings, and always logged. Default remains human-in-the-
loop.

---

## Sprint order (27 Aug → 5 Sep)

Day 1–2: Razorpay integration (entity mirror, six webhooks + raw-body HMAC,
contest payload, Documents API) + rail field + deadline triage queue.
Day 3: Decision math core (EV, per-case threshold, p_win decomposition,
net-recovery KPI, priors table) — mostly formulas over existing plumbing.
Day 4: Metrics honesty layer (temporal split retrain, AUC-PR, bootstrap
CIs, savings score, calibration panel, leakage audit).
Day 5: Evidence engine (reason-code templates, CE3.0 + MC FPT checkers,
readiness badges) + dossier PDF export.
Day 6: Grounding v2 (MiniCheck gate, perturbation benchmark, spotlighting,
injection suite) + audit completeness.
Day 7: README, model card (FREE-AI page, decision-theory appendix), CI,
run.sh + Dockerfile, deploy.
Day 8: ROI calculator, sensitivity charts, agreement tracking, polish.
Day 9–10: Pitch video + form answers + buffer.

Stretch (only if ahead): conformal band, IEEE-CIS transfer run, drift
endpoint, VAMP panel.
