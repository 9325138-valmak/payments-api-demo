# Architecture

## Components

| Component | Role | Code |
|---|---|---|
| Client app | The prospect's app or backend; sends one request per order with an idempotency key | not included |
| Payments service | The integration: creates payments, receives and verifies webhooks | `payments_demo/app.py` |
| Provider client | Calls the provider with retries and backoff | `payments_demo/provider.py` |
| Store | SQLite; unique constraints enforce idempotency and event de-duplication | `payments_demo/store.py` |
| Signing | Webhook signature creation and verification | `payments_demo/signing.py` |
| Simulated provider | Local stand-in for a real provider, with failure injection | `payments_demo/mock_provider.py` |

## Creating a payment

```mermaid
sequenceDiagram
    participant C as Client app
    participant S as Payments service
    participant DB as Store (SQLite)
    participant P as Provider

    C->>S: POST /payments (Idempotency-Key: order-1001)
    S->>DB: Payment with this key already?
    alt Key already used
        DB-->>S: Original payment
        S-->>C: 200 OK, Idempotent-Replay: true
    else New key
        loop Up to 4 attempts, same key every time
            S->>P: POST /v1/payments
            P-->>S: 503 (retry with backoff) or 200
        end
        S->>DB: Insert payment (key is UNIQUE)
        S-->>C: 201 Created, status pending
    end
```

## Receiving a webhook

```mermaid
sequenceDiagram
    participant P as Provider
    participant S as Payments service
    participant DB as Store (SQLite)

    P->>S: POST /webhooks (Provider-Signature: t=...,v1=...)
    S->>S: Verify HMAC-SHA256 over timestamp + raw body
    alt Invalid or older than 5 minutes
        S-->>P: 400 rejected
    else Valid
        S->>DB: Payment exists?
        alt Not yet
            S-->>P: 404 (provider retries later)
        else Exists
            S->>DB: Record event ID (PRIMARY KEY)
            alt Seen before
                S-->>P: 200 duplicate, no change
            else New event
                S->>DB: Apply status change if allowed
                S-->>P: 200 applied or ignored
            end
        end
    end
```

## Payment status rules

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> succeeded
    pending --> failed
    succeeded --> refunded
```

Any other change, for example `succeeded` arriving after `refunded`, is ignored.

## What a production version would change

- PostgreSQL or another shared database instead of SQLite, so several service instances can run
- A queue between webhook receipt and processing, so slow processing never times out the provider
- Secrets from a secrets manager instead of environment variables
- Metrics and alerts on retry rates, rejected webhooks and payments stuck in `pending`
