# Demo script (5 minutes)

A live technical demo for the prospect's engineering lead and product owner. Each step shows one risk from the [solution brief](solution-brief.md) and how it is handled.

**Before the call:** run `bash demo-kit/run_demo.sh` once to check the environment. During the call, either run the script and talk over each step, or run the commands by hand in three terminals as in the main [README](../README.md#quick-start).

## Opening (30 seconds)

> "In discovery you said a timeout today can charge a client twice, and reconciliation takes your ops team an hour a day. I'll show the five failure cases that cause that, live, and how this integration handles each one. Stop me at any point."

## Step 1: the provider is down (1 minute)

The simulated provider is set to fail its first two requests with HTTP 503.

**Show:** the service log.

```text
WARNING provider returned 503, retrying in 0.5s
WARNING provider returned 503, retrying in 1.0s
-> 201 Created, status "pending"
```

> "The provider failed twice. The service waited, retried with backoff, and the client just sees the payment created. Every retry carried the same idempotency key, so even if one of those failed requests had actually gone through, there is still only one charge."

**Likely question:** *What if it's down for longer?* After 4 attempts the service returns a clear 503 to the app, and the app can retry later with the same key, still safely.

## Step 2: the app retries the same order (1 minute)

**Show:** the same request sent again with `Idempotency-Key: order-1001`.

```text
HTTP/1.1 200 OK
idempotent-replay: true
```

> "This is the double-charge scenario from discovery. Same order, same key: the service returns the original payment and does not call the provider again. One order, one charge."

## Step 3: duplicate webhooks (1 minute)

The provider is set to deliver every event twice.

**Show:** the log, then the payment.

```text
INFO webhook evt_... (payment.succeeded) -> applied
INFO webhook evt_... (payment.succeeded) -> duplicate
status: "succeeded"
```

> "Providers deliver at least once, so duplicates are normal. The event ID is stored, so the second delivery is acknowledged but changes nothing. The client's account is credited once. This is the reconciliation break you described."

## Step 4: a forged webhook (1 minute)

**Show:** a fake "payment.refunded" event sent without the shared secret.

```text
WARNING rejected webhook: signature mismatch
HTTP/1.1 400 Bad Request
```

> "Your webhook URL is public. Every event is signed with HMAC-SHA256 and a timestamp; anything unsigned, altered or older than five minutes is rejected. Nobody can credit or refund an account by calling the URL."

## Step 5: the result (30 seconds)

**Show:** the payment record.

> "One payment, status succeeded, charged once, credited once, with every event logged. That's the reconciliation your ops team wants to see."

## Close (30 seconds)

> "Connecting your provider means one adapter class; the reliability logic stays the same. I'd suggest a two-week proof of concept in your sandbox, with three success criteria: zero duplicate charges, zero duplicate credits, every forged event rejected. Who on your side should be part of that?"

## If something breaks during the demo

Say what happened, show the log, and move on. A demo that recovers calmly from an error is more convincing than one that never shows one.
