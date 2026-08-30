#!/usr/bin/env bash
# Fire a correctly-signed Razorpay dispute webhook at a running ChargeLens
# so a new dispute materializes in the queue live - the same path a real
# payment.dispute.created event takes.
#
# Usage:
#   CHARGELENS_RZP_WEBHOOK_SECRET=whsec_demo ./scripts/simulate_webhook.sh
#   ./scripts/simulate_webhook.sh won disp_AHfqOvkldwsbqt   # outcome event
#
# The server must be started with the SAME secret in its environment.
set -euo pipefail

BASE="${CHARGELENS_BASE:-http://localhost:8000}"
SECRET="${CHARGELENS_RZP_WEBHOOK_SECRET:-whsec_demo}"
EVENT="${1:-payment.dispute.created}"
[[ "$EVENT" != payment.dispute.* ]] && EVENT="payment.dispute.${EVENT}"
DISPUTE_ID="${2:-disp_$(head -c6 /dev/urandom | od -An -tx1 | tr -d ' \n')}"
RESPOND_BY=$(( $(date +%s) + 3*86400 ))   # 3 days out

read -r -d '' BODY <<JSON || true
{"entity":"event","event":"${EVENT}","account_id":"acc_demo","contains":["payment","dispute"],"payload":{"payment":{"entity":{"id":"pay_demo123","method":"card","status":"captured","contact":"+919812345678","amount":4250000,"currency":"INR"}},"dispute":{"entity":{"id":"${DISPUTE_ID}","entity":"dispute","payment_id":"pay_demo123","amount":4250000,"currency":"INR","reason_code":"10.4","reason_description":"Fraud - card absent environment","respond_by":${RESPOND_BY},"status":"open","phase":"chargeback","created_at":$(date +%s)}}}}
JSON

# HMAC-SHA256 over the RAW body, exactly as Razorpay signs it
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.*= //')

echo ">> POST ${BASE}/api/webhooks/razorpay"
echo ">> event=${EVENT} dispute=${DISPUTE_ID}"
echo ">> X-Razorpay-Signature=${SIG}"
echo

curl -sS -X POST "${BASE}/api/webhooks/razorpay" \
  -H "Content-Type: application/json" \
  -H "X-Razorpay-Signature: ${SIG}" \
  --data-raw "${BODY}"
echo
echo
echo ">> open ${BASE}/ - the dispute is now in the queue with a live deadline"
