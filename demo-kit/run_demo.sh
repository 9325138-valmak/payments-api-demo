#!/usr/bin/env bash
# Runs the full 5-minute demo end to end: provider outage, safe retries,
# idempotent replay, duplicate webhooks and a forged webhook being rejected.
# Usage (from the repo root, inside your virtual environment):
#   bash demo-kit/run_demo.sh
set -euo pipefail

SERVICE=http://127.0.0.1:8000
export DB_PATH="$(mktemp -d)/demo.db"

cleanup() { kill "${MOCK_PID:-}" "${SVC_PID:-}" 2>/dev/null || true; }
trap cleanup EXIT

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "Starting the simulated provider (fails the first 2 requests, sends every webhook twice)"
MOCK_FAIL_FIRST_N=2 MOCK_DUPLICATE_WEBHOOKS=1 MOCK_WEBHOOK_URL="$SERVICE/webhooks" \
  uvicorn payments_demo.mock_provider:main --factory --port 8001 --log-level warning &
MOCK_PID=$!

step "Starting the payments service"
uvicorn payments_demo.app:main --factory --port 8000 --log-level warning &
SVC_PID=$!

for _ in $(seq 1 50); do
  curl -sf "$SERVICE/health" >/dev/null 2>&1 && break
  sleep 0.2
done

step "1. Create a payment while the provider is failing (watch the retries)"
RESPONSE=$(curl -s -i -X POST "$SERVICE/payments" \
  -H 'Idempotency-Key: order-1001' -H 'Content-Type: application/json' \
  -d '{"amount": 2500, "currency": "usd"}')
echo "$RESPONSE" | sed -n '1p;$p'
PAYMENT_ID=$(echo "$RESPONSE" | tail -1 | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

step "2. The client times out and retries the same order (same Idempotency-Key)"
curl -s -i -X POST "$SERVICE/payments" \
  -H 'Idempotency-Key: order-1001' -H 'Content-Type: application/json' \
  -d '{"amount": 2500, "currency": "usd"}' | grep -iE '^HTTP|^idempotent-replay|^\{'

step "3. Wait for the provider's webhook (delivered twice on purpose)"
sleep 2
curl -s "$SERVICE/payments/$PAYMENT_ID"; echo

step "4. Someone forges a webhook without the shared secret"
curl -s -i -X POST "$SERVICE/webhooks" \
  -H "Provider-Signature: t=$(date +%s),v1=forged" -H 'Content-Type: application/json' \
  -d "{\"id\": \"evt_fake\", \"type\": \"payment.refunded\", \"data\": {\"payment_id\": \"$PAYMENT_ID\"}}" \
  | sed -n '1p;$p'; echo

step "5. The payment is unchanged: still succeeded, charged once"
curl -s "$SERVICE/payments/$PAYMENT_ID"; echo
