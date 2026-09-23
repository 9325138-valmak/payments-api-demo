"""The integration service: creates payments and receives webhooks."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import signing
from .config import Settings
from .provider import (
    ProviderAuthError,
    ProviderClient,
    ProviderRequestError,
    ProviderUnavailableError,
)
from .store import DuplicateKeyError, Store

log = logging.getLogger("payments_demo")


class PaymentGateway(Protocol):
    """The one method the service needs; lets tests swap in a stub."""

    def create_payment(
        self, amount: int, currency: str, idempotency_key: str
    ) -> dict[str, Any]: ...


class PaymentRequest(BaseModel):
    amount: int = Field(gt=0, description="Amount in minor units (cents)")
    currency: str = Field(min_length=3, max_length=3)


def create_app(settings: Settings | None = None, gateway: PaymentGateway | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.db_path)
    gateway = gateway or ProviderClient(settings.provider_base_url, settings.provider_api_key)
    app = FastAPI(title="payments-api-demo")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/payments", status_code=201)
    def create_payment(
        body: PaymentRequest,
        response: Response,
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise HTTPException(400, "Idempotency-Key header is required")

        # Same key twice: return the original payment, do not charge again.
        existing = store.get_payment_by_key(idempotency_key)
        if existing:
            response.status_code = 200
            response.headers["Idempotent-Replay"] = "true"
            return existing

        try:
            created = gateway.create_payment(body.amount, body.currency.upper(), idempotency_key)
        except ProviderAuthError as exc:
            log.error("provider auth failure: %s", exc)
            raise HTTPException(502, "provider rejected our credentials") from exc
        except ProviderUnavailableError as exc:
            log.error("provider unavailable: %s", exc)
            raise HTTPException(503, "provider unavailable, retry later") from exc
        except ProviderRequestError as exc:
            raise HTTPException(422, f"provider rejected the request: {exc}") from exc

        try:
            return store.insert_payment(
                created["id"],
                idempotency_key,
                body.amount,
                body.currency.upper(),
                created.get("status", "pending"),
            )
        except DuplicateKeyError:
            # A concurrent request with the same key won the race.
            winner = store.get_payment_by_key(idempotency_key)
            assert winner is not None
            response.status_code = 200
            response.headers["Idempotent-Replay"] = "true"
            return winner

    @app.get("/payments/{payment_id}")
    def get_payment(payment_id: str) -> dict[str, Any]:
        payment = store.get_payment(payment_id)
        if payment is None:
            raise HTTPException(404, "payment not found")
        return payment

    @app.post("/webhooks")
    async def receive_webhook(
        request: Request,
        provider_signature: str | None = Header(default=None),
    ) -> dict[str, str]:
        # Verify against the raw bytes: re-serialising parsed JSON would change them.
        raw = await request.body()
        try:
            signing.verify(
                provider_signature,
                raw,
                settings.webhook_secret,
                tolerance=settings.webhook_tolerance_seconds,
            )
        except signing.SignatureError as exc:
            log.warning("rejected webhook: %s", exc)
            raise HTTPException(400, f"invalid signature: {exc}") from exc

        try:
            event = json.loads(raw)
            event_id = event["id"]
            event_type = event["type"]
            payment_id = event["data"]["payment_id"]
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(400, "malformed event payload") from exc

        outcome = store.apply_event(event_id, event_type, payment_id)
        log.info("webhook %s (%s) -> %s", event_id, event_type, outcome)
        if outcome == "unknown_payment":
            # Non-2xx makes the provider retry later, when our row exists.
            raise HTTPException(404, "unknown payment, retry later")
        return {"status": outcome}

    return app


def main() -> FastAPI:  # pragma: no cover - used by uvicorn --factory
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return create_app()
