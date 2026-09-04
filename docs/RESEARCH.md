# Domain research and references

The design decisions in ChargeLens are grounded in published card-network
rules, Indian payments regulation, fraud-ML methodology, and the
economics of dispute representment. This document records what that
research established and the sources behind it. All figures here are
industry-reported context and priors, not measurements of ChargeLens;
the product's own numbers live in the model card and on the Model
performance page.

## 1. The economics of contesting a dispute

Contesting is worth it only when the expected recovery beats its cost, so
the decision is an expected-value comparison that uses each case's own
amount:

```
EV(contest) = p_win * (1 - pre_arb_haircut) * amount - ops_cost - dispute_fee
```

Two facts shape this. First, in the Razorpay ecosystem the per-dispute
fee is charged for handling the chargeback and is not refunded even when
the merchant wins, so it is a sunk cost of contesting. Second, a
calibrated fraud probability is not a win probability: winning
representment also requires evidence the issuer accepts. Industry
outcomes are far below model-style optimism: average representment win
rates around 20%, roughly 43.8% of cases won among those merchants choose
to fight, and net dollar recovery near 10.7% after second-cycle disputes
and fees; true-fraud reason codes win far less often than suspected
friendly fraud. ChargeLens therefore models `p_win` as the calibrated
probability capped by a cited per-reason prior and scaled by an
evidence-strength factor.

This is the example-dependent form of Elkan's cost-sensitive threshold
(t* = c_FP / (c_FP + c_FN)): because the false-negative cost is the
case's own amount, a large dispute is worth contesting at a lower
probability than a small one.

Sources: cseweb.ucsd.edu/~elkan/rescale.pdf; Bahnsen et al.,
CostSensitiveClassification; Vanderschueren et al., EJOR 2021;
chargebacks911.com/chargeback-stats/;
chargebackgurus.com; chargeflow.io/blog/forecast-chargeback-recovery-rate;
razorpay.com/blog/chargebacks/.

## 2. Fraud-ML methodology

Metrics on fraud data are easy to overstate. Random splits can leak
temporally correlated cases and inflate results, so ChargeLens also
retrains on a strict time-ordered split and reports it beside the primary
numbers. At fraud prevalence, ROC-AUC is inflated by the true-negative
pool, so average precision (PR-AUC) is reported alongside it. Point
estimates carry sampling uncertainty, so every headline metric is
reported with a 95% stratified bootstrap confidence interval.

Resampling methods such as SMOTE distort calibration without improving
discrimination (van den Goorbergh et al., JAMIA 2022); because the
decision math depends on calibrated probabilities, ChargeLens uses class
weighting plus post-hoc isotonic calibration rather than resampling.
Customer-history features are computed as of the dispute-creation time to
avoid using information that would not exist at scoring time.

A public real-data proxy for future validation is the IEEE-CIS Fraud
Detection dataset, whose label is chargeback-derived; well-tuned single
models there typically reach ROC-AUC in the 0.88 to 0.93 range.

Sources: van den Goorbergh et al., JAMIA 2022; kaggle.com IEEE-CIS Fraud
Detection; standard cost-sensitive fraud literature above.

## 3. Indian payment rails

UPI is roughly 85% of Indian digital-payment volume (RBI, H2 2025), so
the data model treats payment rail as first-class. UPI disputes follow
NPCI's URCS process with a uniform 45-day customer chargeback window and
automated accept/reject via TCC/RET, which differs from card
representment. Practical merchant response windows in India are short
(around 3 business days per acquirer guidance, and about 7 working days
for NPCI/RuPay and UPI), which is why the queue is deadline-first and the
`respond_by` value from the dispute record is the runtime source of
truth.

RBI's Harmonisation of Turn Around Time circular auto-reverses failed and
duplicate transactions with daily compensation, so genuine
failed-transaction complaints should be accepted, not contested. RBI's
2017 limited-liability circular means issuers lean toward customers on
unauthorised claims, so the winning defense in the fraud phase is proof
the genuine customer authorised the transaction.

Sources: ibef.org (RBI UPI volume, H2 2025); NPCI circular OC 198/2023-24
and URCS/UDIR documentation; RBI TAT Harmonisation circular; RBI
limiting-liability circular 2017; razorpay.com/docs disputes.

## 4. Card-network evidence rules

Visa Compelling Evidence 3.0 (reason code 10.4) lets a merchant reverse a
card-absent fraud chargeback by showing at least two prior undisputed
transactions on the same credential, aged 120 to 365 days, that share
data elements with the disputed transaction: two main elements (purchase
IP, device ID) or one main plus one secondary (shipping address, account
ID or email). Qualification shifts liability to the issuer. Mastercard's
First-Party Trust program is the analogue for its fraud code 4837 with a
different one-of-each-category rule.

Winning evidence differs by reason code: item-not-received disputes turn
on signed proof of delivery and tracking to a verified address, while
card-absent fraud turns on authentication records and device/IP history.
Base-rate context: first-party (friendly) fraud is roughly 20% of
disputes, and a large share of consumers admit to disputing a charge they
later recognised.

Sources: Visa CE3.0 merchant guidance; docs.stripe.com/disputes;
mastercard.com First-Party Trust; chargebacks911.com and
chargebackgurus.com reason-code references; Mastercard/Datos Insights
first-party-fraud reporting.

## 5. LLM grounding and injection defense

The disputing customer's claim text is attacker-controlled input to the
drafting step, which makes it an indirect prompt-injection vector (OWASP
LLM01). ChargeLens canonicalizes it (NFKC, control- and
zero-width-character stripping, length cap), datamarks it, and fences it
with a per-request random boundary, following the spotlighting technique
(Hines et al. 2024; Microsoft MSRC 2025). Generated drafts pass a
grounding check so that numbers and identifiers not present in the trusted
facts are rejected in favour of the deterministic letter. Both the
grounding gate and the injection defenses are measured by benchmarks that
run in CI.

Stronger natural-language entailment verifiers (for example MiniCheck,
EMNLP 2024) are a documented option for extending grounding beyond
numeric and identifier checks to qualitative claims.

Sources: genai.owasp.org LLM01; Hines et al. 2024 (spotlighting);
microsoft.com MSRC 2025; github.com/Liyan06/MiniCheck.

## 6. Product context

Commercial chargeback-automation tools price on success fees (around 25%
to 30% of recovered value), which is the basis for the ROI comparison in
the app. Pre-dispute alert networks (Verifi, Ethoca) prevent some
chargebacks but cost the full transaction amount plus a per-alert fee and
do not cover India's UPI and RuPay rails, so representment remains the
path that recovers revenue. Razorpay has publicly described a dispute
auto-responder of its own; ChargeLens is positioned as the risk-managed
layer around such automation: calibrated win-probability scoring,
cost-based fight-or-accept economics, grounding-verified drafts with a
deterministic fallback, human-approved submissions, and a full audit
trail.

Sources: published 2026 pricing for Chargeflow, Stripe Smart Disputes,
and Justt; chargeblast.com and chargeback.io alert-network comparisons;
public statements on Razorpay's dispute automation.
