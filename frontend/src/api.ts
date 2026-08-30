// Typed client for the ChargeLens API.

const BASE = "";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export interface CaseSummary {
  case_id: string;
  customer_id: string;
  reason: string;
  disputed_amount: number;
  claim_ts: string | null;
  status: string;
  recommendation: string | null;
  risk_score: number | null;
  band: string | null;
  rail: string;
  network: string | null;
  respond_by: string | null;
  external_ref: string | null;
  external_status: string | null;
}

export interface Economics {
  p_cal: number;
  evidence_strength: string;
  evidence_factor: number;
  prior_cap: number;
  p_win: number;
  expected_recovery_inr: number;
  contest_cost_inr: number;
  ev_contest_inr: number;
  break_even_p_win: number;
  economic: boolean;
  assumptions: {
    dispute_fee_inr: number;
    ops_cost_inr: number;
    pre_arb_haircut: number;
    note: string;
  };
}

export interface CE3 {
  status: "qualified" | "requires_action" | "not_applicable";
  reason_code: string;
  matched_main: string[];
  matched_secondary: string[];
  qualifying_transactions: string[];
  missing: string[];
  note: string;
}

export interface Factor {
  feature: string;
  label: string;
  shap: number;
  direction: "raises_risk" | "lowers_risk";
  value: string;
}

export interface EvidenceItemT {
  key: string;
  statement: string;
  value: string;
  source: string;
  supports: "merchant" | "customer" | "neutral" | "missing";
  strength: "strong" | "moderate" | "weak";
}

export interface AuditEntry {
  ts: string | null;
  actor: string;
  event_type: string;
  detail: Record<string, unknown>;
}

export interface CaseDetail extends CaseSummary {
  claim_description: string;
  claim_delay_days: number | null;
  recommendation_reason: string | null;
  generated_response: string | null;
  response_generator: string | null;
  human_decision: string | null;
  human_decision_note: string | null;
  human_decision_ts: string | null;
  transaction: {
    id: string; amount: number; currency: string; payment_method: string;
    payment_status: string; device_seen_before: boolean;
    device_shared_accounts: number; ip_geo_distance_km: number;
    txns_last_24h: number; ts: string | null;
  } | null;
  order: {
    id: string; product_name: string; product_category: string;
    quantity: number; shipping_city: string; billing_city: string;
    shipping_billing_match: boolean; order_ts: string | null;
  } | null;
  delivery: {
    carrier: string; tracking_number: string | null; has_tracking: boolean;
    delivery_status: string; delivery_confirmation: string;
    shipped_ts: string | null; delivered_ts: string | null;
  } | null;
  customer: {
    id: string; account_age_days: number; previous_orders: number;
    previous_chargebacks: number; previous_returns: number;
    previous_failed_payments: number; avg_order_value: number;
  } | null;
  risk: {
    risk_score: number; band: string; model_version: string;
    top_factors: Factor[]; scored_at: string | null;
    economics: Economics | null;
    ce3: CE3 | null;
  } | null;
  evidence: EvidenceItemT[];
  audit: AuditEntry[];
}

export interface Dashboard {
  total_cases: number;
  open_cases: number;
  high_risk: number;
  review_band: number;
  low_risk: number;
  awaiting_review: number;
  uninvestigated: number;
  open_exposure_inr: number;
  estimated_recovery_inr: number;
  estimated_net_ev_inr: number;
  contestable_cases: number;
  recovery_note: string;
}

export interface Analytics {
  metrics: {
    disclosure: string;
    model_version: string;
    evaluated_at: string;
    test_set: { n_cases: number; n_abusive: number; n_legitimate: number; abusive_rate: number };
    thresholds: { t_low: number; t_high: number };
    contest_decision_at_t_high: {
      precision: number; recall: number; f1: number;
      false_positive_rate: number; false_negative_rate: number;
      confusion_matrix: { tp: number; fp: number; fn: number; tn: number };
    };
    threshold_free: { roc_auc: number; pr_auc: number; brier_score: number };
    bands: Record<string, { count: number; share: number; abusive_rate: number | null }>;
    cost_analysis: {
      assumptions: Record<string, number>;
      false_positive_count: number;
      false_positive_cost_inr: number;
      false_negative_count: number;
      false_negative_cost_inr: number;
      recovered_from_true_positives_inr: number;
      net_cost_inr: number;
      review_ops_cost_inr_per_case: number;
      policy_costs_inr: Record<string, number>;
      three_band_assumption: string;
      estimated_savings_vs_accept_all_inr: number;
    };
    curves: {
      precision_recall: { x: number; y: number }[];
      roc: { x: number; y: number }[];
      calibration: { bin: string; mean_predicted: number; observed_rate: number; count: number }[];
    };
  };
  model_selection: {
    selected_model: string;
    selection_metric: string;
    leaderboard: { model: string; val_pr_auc: number; val_roc_auc: number }[];
    calibration: string;
    trained_at: string;
  };
  global_importance: {
    method: string;
    sample_size: number;
    top_features: { feature: string; mean_abs_shap: number; mean_shap: number }[];
  };
  threshold_curve: { threshold: number; precision: number; expected_cost_inr: number }[];
  dataset_manifest: {
    synthetic: boolean; disclosure: string; n_cases: number; seed: number;
    class_balance: { abusive: number; legitimate: number; abusive_rate: number };
    splits: Record<string, number>;
    split_strategy: string;
  } | null;
}

export const api = {
  dashboard: () => get<Dashboard>("/api/dashboard"),
  cases: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return get<{ cases: CaseSummary[] }>(`/api/cases${qs ? `?${qs}` : ""}`);
  },
  caseDetail: (id: string) => get<CaseDetail>(`/api/cases/${id}`),
  investigate: (id: string) => post<CaseDetail>(`/api/cases/${id}/investigate`),
  decide: (id: string, action: string, note: string) =>
    post<CaseDetail>(`/api/cases/${id}/decision`, { action, note }),
  analytics: () => get<Analytics>("/api/analytics"),
};

export const inr = (v: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 0,
  }).format(v);

export const pct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)}%`;
