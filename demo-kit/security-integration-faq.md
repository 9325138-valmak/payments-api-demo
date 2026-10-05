# Security and integration FAQ

Answers in the style of an RFP or security questionnaire. Each answer states what this demo does today and, where relevant, what a production deployment would add.

**1. Does the service store card numbers or other card data?**
No. The service only sends an amount and currency to the provider and stores the provider's payment ID and status. Card details are collected by the provider, which keeps the integration out of most PCI DSS scope.

**2. How do you prevent a client being charged twice?**
Every create request must carry an `Idempotency-Key`. The key is stored with a UNIQUE database constraint and sent to the provider on every attempt, so retries from the client or from the service map to one payment. Covered by tests in `tests/test_api.py` and `tests/test_provider.py`.

**3. How are webhooks authenticated?**
HMAC-SHA256 over the timestamp and the raw request body, using a shared secret, compared in constant time. Missing, malformed or mismatched signatures are rejected with HTTP 400. See `payments_demo/signing.py`.

**4. How do you prevent replay attacks on the webhook endpoint?**
The signed data includes a timestamp; events older than 5 minutes (configurable with `WEBHOOK_TOLERANCE_SECONDS`) are rejected. Event IDs are also stored, so a replayed event inside the window changes nothing.

**5. What happens when the provider is unavailable?**
Timeouts, HTTP 429 and 5xx responses are retried up to 4 times with exponential backoff, honouring `Retry-After`. Authentication errors are never retried. After the last attempt the service returns HTTP 503, and the client can retry later with the same key safely.

**6. What if events arrive twice or out of order?**
Duplicate events are recognised by ID and acknowledged without effect. Status changes follow a fixed set of allowed transitions, so a late `succeeded` event cannot overwrite a `refunded` payment.

**7. How are secrets managed?**
In this demo, through environment variables (`PROVIDER_API_KEY`, `WEBHOOK_SECRET`), with test values in `.env.example`. A production deployment would load them from a secrets manager and rotate them on a schedule.

**8. What is logged, and is any sensitive data in the logs?**
Retries, rejected webhooks and each event outcome are logged with payment and event IDs. No card data or secrets are logged.

**9. How is the code tested?**
pytest covers idempotency, retries, signature checks, duplicate and out-of-order events; ruff and strict mypy run in CI on Python 3.10 and 3.12 for every push.

**10. How hard is it to connect a different provider?**
The service depends on one small interface, `PaymentGateway`, in `app.py`. A new provider means one adapter class for its endpoint, authentication, signature header and event names; the reliability logic does not change. See [Using a real provider](../README.md#using-a-real-provider) in the main README.
