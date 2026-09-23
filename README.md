# Payments API Integration Demo

A small Python service that shows how to integrate with a payments provider **reliably**: idempotent requests, safe retries, and signed webhooks that can arrive twice or out of order.

It ships with a simulated provider so everything runs locally with no accounts or API keys. The provider is a mock written for this repo. It is not affiliated with any real payments company, and the code has not been run against a live provider.

## What it demonstrates

| Problem in real integrations | How this service handles it |
|---|---|
| A network timeout leaves you unsure whether the charge happened | Every attempt sends the same `Idempotency-Key`, so a retry can never create a second payment |
| The provider returns `429` or `503` | Retries with exponential backoff, honours `Retry-After`, gives up after 4 attempts |
| Your own client retries the same order | The service stores the key and replays the original result (`Idempotent-Replay: true`) |
| Anyone can POST to your webhook URL | HMAC-SHA256 signature over `timestamp.body`, constant-time compare |
| An old webhook is captured and replayed | Signatures older than 5 minutes are rejected |
| The provider delivers the same event twice | Event IDs are stored; the second delivery gets a `200` but changes nothing |
| Events arrive out of order (`succeeded` after `refunded`) | Only valid status transitions are applied |
| A webhook arrives before your database row exists | Returns `404` without recording the event, so the provider's retry succeeds |

## Architecture

```
 client ──POST /payments──▶  service (FastAPI)  ──POST /v1/payments──▶  provider
                                  │  ▲                                   │
                              SQLite  └────── POST /webhooks (signed) ◀───┘
```

- `payments_demo/app.py`: the API (`POST /payments`, `GET /payments/{id}`, `POST /webhooks`, `GET /health`)
- `payments_demo/provider.py`: provider client with retry and backoff
- `payments_demo/signing.py`: webhook signing and verification
- `payments_demo/store.py`: SQLite storage; the unique constraints enforce idempotency
- `payments_demo/mock_provider.py`: the simulated provider, with failure injection

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/9325138-valmak/payments-api-demo
cd payments-api-demo
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Start the simulated provider. Here it fails its first 2 requests with `503` and delivers every webhook twice, to show the retry and duplicate handling:

```bash
MOCK_FAIL_FIRST_N=2 MOCK_DUPLICATE_WEBHOOKS=1 MOCK_WEBHOOK_URL=http://127.0.0.1:8000/webhooks \
  uvicorn payments_demo.mock_provider:main --factory --port 8001
```

In a second terminal, start the service:

```bash
uvicorn payments_demo.app:main --factory --port 8000
```

In a third terminal, create a payment:

```bash
curl -i -X POST localhost:8000/payments \
  -H 'Idempotency-Key: order-1001' -H 'Content-Type: application/json' \
  -d '{"amount": 2500, "currency": "usd"}'
```

Send the same request again. You get the original payment back with `Idempotent-Replay: true`, and the provider is not called a second time.

After about a second the webhook arrives. Check the status:

```bash
curl localhost:8000/payments/<id from the first response>
```

### Example run

```
POST /payments  (provider returns 503, 503, then 200)
  WARNING provider returned 503, retrying in 0.5s
  WARNING provider returned 503, retrying in 1.0s
  -> 201 Created, status "pending"

POST /payments  (same Idempotency-Key)
  -> 200 OK, Idempotent-Replay: true      (provider saw 3 requests in total, not 4)

webhooks (delivered twice by the provider)
  INFO webhook evt_36b8... (payment.succeeded) -> applied
  INFO webhook evt_36b8... (payment.succeeded) -> duplicate

GET /payments/<id>
  -> status "succeeded"
```

## Configuration

Copy `.env.example` and export the values, or set them in your shell.

| Variable | Default | Purpose |
|---|---|---|
| `PROVIDER_BASE_URL` | `http://127.0.0.1:8001` | Where the provider lives |
| `PROVIDER_API_KEY` | `sk_test_demo` | Sent as a bearer token |
| `WEBHOOK_SECRET` | `whsec_demo` | Shared secret for verifying webhooks |
| `DB_PATH` | `payments.db` | SQLite file |
| `WEBHOOK_TOLERANCE_SECONDS` | `300` | Maximum webhook age |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `POST /payments` returns `400 Idempotency-Key header is required` | Header missing | Send a unique key per order, and reuse it only when retrying that same order |
| `POST /payments` returns `502 provider rejected our credentials` | Wrong or missing API key | Check `PROVIDER_API_KEY` matches what the provider expects. Auth errors are never retried |
| `POST /payments` returns `503 provider unavailable` | Provider returned `429`/`5xx` or timed out 4 times in a row | Retry later with the **same** `Idempotency-Key`. Check the service log for the status codes seen |
| Webhook rejected: `signature mismatch` | Different secrets on each side, or the body was altered before verification | Confirm `WEBHOOK_SECRET` matches. Verify the raw request bytes, never re-serialised JSON |
| Webhook rejected: `timestamp outside tolerance` | Clock skew, or a replayed old request | Sync the server clock (NTP). Raise `WEBHOOK_TOLERANCE_SECONDS` only if skew is unavoidable |
| Webhook rejected: `malformed signature header` | Header name or format differs from this scheme | Check the provider's docs for the exact header and format, then adapt `signing.py` |
| Webhook returns `404 unknown payment` | The event arrived before the payment row was saved | Expected. The provider retries and the event is applied once the payment exists |
| Same event processed twice | The event ID is not being stored | Check the `processed_events` table. Response `{"status": "duplicate"}` means dedupe worked |
| Status stays `pending` | No webhook received yet, or it was rejected | Look for `rejected webhook` warnings in the log. Confirm the provider can reach your `/webhooks` URL |
| Status did not change on an event | The event was out of order and ignored | Expected. A payment never moves backwards, for example `refunded` back to `succeeded` |

## Using a real provider

The service depends only on the small `PaymentGateway` interface in `app.py`, so a real provider is one adapter class. Things that will differ and need checking against the provider's documentation:

- the endpoint path, request body and authentication scheme
- the signature header name and how the signed string is built
- the event names and payload shape
- which requests the provider treats as idempotent, and for how long a key is remembered

## Tests and checks

```bash
pytest --cov=payments_demo
ruff check . && ruff format --check .
mypy payments_demo
```

CI runs all of these on Python 3.10 and 3.12.

## Limitations

- SQLite and a single process. A production version would use a shared database and a queue for webhook processing.
- Only the create-payment call and three event types are modelled.
- The provider is a local mock. Behaviour against a real provider must be verified.

## License

MIT
