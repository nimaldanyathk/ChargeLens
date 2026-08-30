# Model card — ChargeLens dispute-risk scorer

Consolidated reference for the model, its evaluation, and its
limitations. All quantitative figures are produced by the evaluation
pipeline (`backend/riskmodel/`) or the safety benchmarks
(`backend/scripts/eval_safety.py`); none are hand-entered. Regenerate
metrics with `python -m riskmodel.train && python -m riskmodel.evaluate`.

## Intended use

Advise a human dispute analyst on Razorpay chargebacks: score how likely
a dispute is abusive (friendly fraud) versus legitimate, assemble
source-cited evidence, and estimate whether contesting is worth its cost.
**Advisory only.** Every action — contest, accept, escalate — is taken by
a person. The system cannot move money, refund, ban, or submit anything;
those operations are structurally absent from its tool registry.

Out of scope: authorizing transactions, deciding disputes autonomously,
scoring anything other than post-dispute chargebacks, or any offensive
use. Defense-only by construction.

## Data

Synthetic (5,000 generated cases; provenance in
`backend/data/manifest.json`). No real customer or payment data is used
anywhere. Synthetic data measures the *discipline* of the pipeline —
leak-free splitting, calibration, cost-based thresholds — not real-world
performance; the numbers below should be read that way. The methodology
is what transfers to real data, not the specific scores.

Class balance and dispute-type mix are set to plausible ranges; the
honest limitation is that the generator also defines the labels, so the
model recovers patterns the generator embedded. The roadmap
(`docs/RESEARCH.md`) covers external validation on a real public dataset
(IEEE-CIS) as the next step.

## Model

- Gradient-boosted trees, selected against a validation split by PR-AUC
  (leaderboard in the Model performance page).
- Probabilities are **isotonically calibrated** — the decision math
  (per-case thresholds, expected value) depends on calibrated
  probabilities, so calibration is not optional.
- **No resampling / SMOTE.** Resampling distorts calibration without
  improving discrimination (van den Goorbergh et al., JAMIA 2022); class
  imbalance is handled with class weighting plus post-hoc calibration.
- Per-case explanations via SHAP; attributions are associational, not
  causal.

Model version: 1.1.0.

## Metrics (held-out test split)

The test split was never used for training, model selection, calibration,
or threshold tuning.

| Metric | Value |
|---|---|
| ROC-AUC | 0.939 |
| PR-AUC | 0.898 |
| Brier score | 0.080 |
| Precision (contest, at t_high=0.34) | 86.5% |
| Recall (contest) | 84.0% |
| F1 | 85.2% |
| False-positive rate | 7.4% |

Confusion matrix at the contest threshold: TP 545, FP 85, FN 104,
TN 1057.

**The false-positive cost is stated as prominently as the accuracy:** 85
honest customers would have been flagged, an estimated ₹1.06L in wrongful
friction. The operating threshold is chosen to minimize total rupee cost,
not to maximize a leaderboard metric. AUC-PR is reported alongside ROC-AUC
because at dispute prevalence ROC-AUC is inflated by the true-negative
pool.

Known reporting limitation: the current split is random, not temporal.
Random splits overstate fraud-model performance; an out-of-time split
(reported side-by-side, with the honest degradation shown) is the next
metrics change on the roadmap.

## Decision layer

The contest/accept decision is expected value, not the raw score:

```
EV(contest) = p_win · (1 − pre_arb_haircut) · amount − ops_cost − dispute_fee
p_win       = min(p_calibrated, reason_cap) · evidence_factor
```

A calibrated fraud probability is deliberately **not** treated as a win
probability — winning also needs evidence the issuer accepts, so p_win is
capped by cited per-reason representment outcomes and scaled by evidence
strength. The dispute fee is treated as sunk (non-refundable on a win in
the Razorpay ecosystem). This is the example-dependent form of Elkan's
cost-sensitive threshold (t* = c_FP/(c_FP+c_FN)); the per-case break-even
probability is shown on every case.

## Safety layer (measured)

Both defenses run in CI (`scripts/eval_safety.py`); a regression fails
the build.

- **Grounding gate** (LLM drafts only): perturbation benchmark over 100
  clean drafts × six corruption families → **100% catch on in-scope
  corruptions, 0% false-block rate.** Purely qualitative fabrications
  (no new number/ID) are out of scope for the numeric gate and reported
  separately rather than excluded — which is why the deterministic
  generator is the default and a human reviews every letter.
- **Prompt-injection red-team**: 17 hostile `claim_description` fixtures
  across 8 families (direct override, fake system tags, fence-break,
  markdown/HTML smuggling, base64/leetspeak, zero-width, Hinglish,
  authority/urgency) → **0% attack success rate.** Defenses: NFKC
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
| Fairness & equity | False-positive cost surfaced as a first-class, honest metric |
| Accountability | Full audit trail: every tool call, score, economics, and human decision logged |
| Understandable by design | Calibrated probabilities + SHAP + plain-language, source-cited drafts |
| Safety, resilience, sustainability | Deterministic fallback on any LLM failure; injection-hardened; measured |

## Limitations

- Synthetic data; scores measure pipeline discipline, not field
  performance.
- Win-probability priors are cited industry anchors, not fitted values.
- The grounding gate validates numbers and identifiers, not qualitative
  phrasing.
- Random (not yet temporal) test split.
- CE3.0 eligibility reconstructs prior transactions from customer history
  for the demo; in production these come from the order/transaction store.

Each item has a corresponding entry in the roadmap
(`docs/RESEARCH.md`).
