// Small shared UI pieces: band badge, status badge, stat tile.

const BAND_META: Record<string, { label: string; cls: string }> = {
  high: { label: "High risk", cls: "badge-high" },
  review: { label: "Needs review", cls: "badge-review" },
  low: { label: "Low risk", cls: "badge-low" },
};

export function BandBadge({ band, score }: { band: string | null; score?: number | null }) {
  if (!band) return <span className="badge badge-neutral"><span className="dot" />Not scored</span>;
  const meta = BAND_META[band] ?? { label: band, cls: "badge-neutral" };
  return (
    <span className={`badge ${meta.cls}`}>
      <span className="dot" />
      {meta.label}
      {score != null && ` · ${(score * 100).toFixed(0)}%`}
    </span>
  );
}

const STATUS_LABEL: Record<string, string> = {
  received: "Received",
  investigating: "Investigating",
  awaiting_review: "Awaiting review",
  approved: "Approved",
  rejected: "Rejected",
  escalated: "Escalated",
};

export function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "awaiting_review" ? "badge-review"
    : status === "approved" ? "badge-low"
    : status === "escalated" ? "badge-high"
    : "badge-neutral";
  return (
    <span className={`badge ${cls}`}>
      <span className="dot" />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function Stat({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

export const REASON_LABEL: Record<string, string> = {
  product_not_received: "Product not received",
  unauthorized_transaction: "Unauthorized transaction",
  product_not_as_described: "Not as described",
};

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
