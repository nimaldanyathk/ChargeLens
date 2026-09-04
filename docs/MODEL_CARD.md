# Model card: ChargeLens dispute-risk scorer

Consolidated reference for the model, its evaluation, and its
limitations. All quantitative figures are produced by the evaluation
pipeline (`backend/riskmodel/`) or the safety benchmarks
(`backend/scripts/eval_safety.py`); none are hand-entered. Regenerate
metrics with `python -m riskmodel.train && python -m riskmodel.evaluate`.

## Intended use

Advise a human dispute analyst on Razorpay chargebacks: score how likely
a dispute is abusive (friendly fraud) versus legitimate, assemble
source-cited evidence, and estimate whether contesting is worth its cost.
**Advisory only.** Every action (contest, accept, escalate) is taken by a
person. The system cannot move money, refund, ban, or submit anything;
those operations are structurally absent from its tool registry.

Out of scope: authorizing transactions, deciding disputes autonomously,
scoring anything other than post-dispute chargebacks, or any offensive
use. Defense-only by construction.

## Data

Synthetic (5,000 generated cases; provenance in
`backend/data/manifest.json`). No real customer or payment data is used
anywhere. Synthetic data measures the *discipline* of the pipeline
(leak-free splitting, calibration, cost-based thresholds), not real-world
performance; the numbers below should be read that way. The methodology
is what transfers to real data, not the specific scores.

Class balance and dispute-type mix are set to plausible ranges; the
honest limitation is that the generator also defines the labels, so the
model recovers patterns the generator embedded. External validation on a
real public dataset (IEEE-CIS) is the intended next step.

## Model

- Gradient-boosted trees, selected against a validation split by PR-AUC
  (leaderboard on the Model performance page).
- Probabilities are **isotonically calibrated**. The decision math
  (per-case thresholds, expected value) depends on calibrated
  probabilities, so calibration is not optional.
- **No resampling or SMOTE.** Resampling distorts calibration without
  improving discrimination (van den Goorbergh et al., JAMIA 2022); class
  imbalance is handled with class weighting plus post-hoc calibration.
- Per-case explanations via SHAP; attributions are associational, not
  causal.

Model version: 1.1.0.

## Metrics (held-out test split)

The test split was never used for training, model selection, calibration,
or threshold tuning.

| Metric | Value | 95% CI |
|---|---|---|
| ROC-AUC | 0.939 | 0.926 to 0.951 |
| PR-AUC | 0.898 | 0.876 to 0.918 |
| Precision (contest, at t_high=0.34) | 86.5% | 84.1 to 88.9% |
| Recall (contest) | 84.0% | 81.1 to 86.8% |
| F1 | 85.2% | 83.2 to 87.2% |
| Brier score | 0.080 | not computed |
| False-positive rate | 7.4% | not computed |

Intervals are 95% stratified percentile bootstrap (B=5,000) on the saved
per-case test outputs. Confusion matrix at the contest threshold: TP 545,
FP 85, FN 104, TN 1057.

**The false-positive cost is stated as prominently as the accuracy:** 85
honest customers would have been flagged, an estimated Rs 1.06L in
wrongful friction. The operating threshold is chosen to minimize total
rupee cost, not to maximize a leaderboard metric. AUC-PR is reported
alongside ROC-AUC because at dispute prevalence ROC-AUC is inflated by the
true-negative pool.

**Out-of-time robustness.** The primary split is customer-grouped
(leak-free by identity) but random in time. Because random splits can
overstate fraud-model performance, the same pipeline is also retrained on
a strict time-ordered split (earliest disputes train, latest disputes
test) and reported side by side (`riskmodel/robustness.py`, shown on the
Model performance page). On this dataset the out-of-time numbers hold
(ROC-AUC 0.945, PR-AUC 0.921, precision 84.3%, recall 91.0%): the
synthetic generator samples scenarios i.i.d. over time, so there is no
concept drift to degrade on. The honest reading is that the numbers are
stable *because the data is stationary*, not because drift was handled.
On real, non-stationary disputes a gap would appear, and this check is
the methodology that surfaces it.

## Decision layer

The contest/accept decision is expected value, not the raw score:

```
EV(contest) = p_win * (1 - pre_arb_haircut) * amount - ops_cost - dispute_fee
p_win       = min(p_calibrated, reason_cap) * evidence_factor
```

A calibrated fraud probability is deliberately **not** treated as a win
probability: winning also needs evidence the issuer accepts, so p_win is
capped by cited per-reason representment outcomes and scaled by evidence
strength. The dispute fee is treated as sunk (non-refundable on a win in
the Razorpay ecosystem). This is the example-dependent form of Elkan's
cost-sensitive threshold (t* = c_FP / (c_FP + c_FN)); the per-case
break-even probability is shown on every case.

## Safety layer (measured)

Both defenses run in CI (`scripts/eval_safety.py`); a regression fails
the build.

- **Grounding gate** (LLM drafts only): a perturbation benchmark over 100
  clean drafts across six corruption families catches **100% of in-scope
  corruptions with a 0% false-block rate.** Purely qualitative
  fabrications (no new number or ID) are out of scope for the numeric gate
  and reported separately rather than excluded, which is why the
  deterministic generator is the default and a human reviews every letter.
- **Prompt-injection red-team**: 17 hostile `claim_description` fixtures
  across 8 families (direct override, fake system tags, fence-break,
  markdown/HTML smuggling, base64/leetspeak, zero-width, Hinglish,
  authority/urgency) reach a **0% attack success rate.** Defenses: NFKC
  canonicalization, control/zero-width stripping, datamarking, and a
  per-request random boundary fence around all customer text.

## RBI FREE-AI alignment

RBI's FREE-AI framework (Aug 2025) sets seven Sutras for AI in Indian
finance. ChargeLens maps to them by construction:

| Sutra | In ChargeLens |
|---|---|
| Trust is the foundation | Every evidence item cites a source record; nothing ungrounded reaches output |
| People first | Human-in-the-loop on every decision; no autonomous action |
| Innovation over restraint | AI used where it adds value (drafting), not where it removes auditability (scoring) |
| Fairness and equity | False-positive cost surfaced as a first-class, honest metric |
| Accountability | Full audit trail: every tool call, score, economics, and human decision logged |
| Understandable by design | Calibrated probabilities, SHAP, and plain-language source-cited drafts |
| Safety, resilience, sustainability | Deterministic fallback on any LLM failure; injection-hardened; measured |

## Limitations

- Synthetic data; scores measure pipeline discipline, not field
  performance.
- Win-probability priors are cited industry anchors, not fitted values.
- The grounding gate validates numbers and identifiers, not qualitative
  phrasing.
- Metrics carry sampling uncertainty (95% CIs reported); the out-of-time
  check is clean only because the synthetic data is stationary. Real data
  would need ongoing drift monitoring.
- CE 3.0 eligibility reconstructs prior transactions from customer history
  for the demo; in production these come from the order and transaction
  store.
