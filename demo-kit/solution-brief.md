# Solution brief: reliable card deposits for Northwind Brokerage

*Fictional prospect, prepared for a demo.*

## The situation

Northwind wants clients to fund their trading accounts by card. The payment provider is already chosen. The open question is the integration: what happens when the network or the provider misbehaves.

## The risks

| What goes wrong | Business impact |
|---|---|
| A request times out and the app retries | The client is **charged twice**, then calls support and asks for a refund |
| The provider has a short outage | Deposits fail at the moment clients want to trade |
| The provider sends the same "payment succeeded" event twice | The account is **credited twice**, creating a reconciliation break |
| Events arrive out of order | A refunded deposit shows as successful |
| Anyone can call the webhook URL | A forged "succeeded" event credits money that never arrived |

For a regulated broker each of these is also a compliance issue: client money records must match what actually moved.

## The approach

| Risk | How the integration handles it |
|---|---|
| Double charge on retry | Every request carries an idempotency key; a repeat returns the original payment instead of creating a new one |
| Provider outage | Automatic retries with exponential backoff, honouring the provider's Retry-After; clear failure after 4 attempts |
| Duplicate events | Each event ID is stored; a second delivery is acknowledged but changes nothing |
| Out-of-order events | Only valid status changes are applied (a refunded payment never moves back to succeeded) |
| Forged webhooks | HMAC-SHA256 signature on every event, constant-time comparison, events older than 5 minutes rejected |

## What Northwind gets

- **No double charges or double credits**, even under retries and duplicate events
- **Fewer support tickets** from failed or duplicated deposits
- **Clean reconciliation**: one payment record per client deposit, with a full event history
- **A small integration surface**: switching provider means changing one adapter, not the whole service

## Proposed next step

A two-week proof of concept against the provider's sandbox: connect the adapter, run the failure scenarios from the [demo script](demo-script.md) with Northwind's team, and agree success criteria up front (zero duplicate charges, zero duplicate credits, all forged events rejected).
