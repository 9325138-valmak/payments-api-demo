"""A small simulated payments provider for local development and demos.

It is NOT a real provider. It reproduces the behaviours an integration has to
survive: auth errors, idempotency keys, transient 503s, and signed webhooks
that can arrive twice.

Environment variables:
    MOCK_API_KEY            expected bearer token (default sk_test_demo)
    MOCK_FAIL_FIRST_N       return 503 for the first N create requests
    MOCK_WEBHOOK_URL        where to deliver webhooks (default: none)
    MOCK_WEBHOOK_SECRET     secret used to sign webhooks (default whsec_demo)
    MOCK_DUPLICATE_WEBHOOKS set to 1 to deliver every webhook twice
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from . import signing


def deliver_webhook(url: str, secret: str, event: dict[str, Any], times: int = 1) -> None:
    body = json.dumps(event).encode()
    for _ in range(times):
        header = signing.sign(body, secret)
        try:
            httpx.post(
                url,
                content=body,
                headers={"Provider-Signature": header, "Content-Type": "application/json"},
                timeout=5,
            )
        except httpx.HTTPError:
            pass  # a real provider would retry later


def create_mock_app(
    api_key: str = "sk_test_demo",
    fail_first_n: int = 0,
    webhook_url: str | None = None,
    webhook_secret: str = "whsec_demo",
    duplicate_webhooks: bool = False,
) -> FastAPI:
    app = FastAPI(title="mock-payments-provider")
    lock = threading.Lock()
    state: dict[str, Any] = {"requests": 0, "by_key": {}}

    @app.post("/v1/payments")
    def create(
        body: dict[str, Any],
        background: BackgroundTasks,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> JSONResponse:
        if authorization != f"Bearer {api_key}":
            raise HTTPException(401, "invalid api key")
        if not idempotency_key:
            raise HTTPException(400, "Idempotency-Key header is required")

        with lock:
            state["requests"] += 1
            if state["requests"] <= fail_first_n:
                return JSONResponse({"error": "temporarily unavailable"}, status_code=503)
            if idempotency_key in state["by_key"]:
                return JSONResponse(state["by_key"][idempotency_key])
            payment = {
                "id": f"pay_{uuid.uuid4().hex[:12]}",
                "status": "pending",
                "amount": body.get("amount"),
                "currency": body.get("currency"),
            }
            state["by_key"][idempotency_key] = payment

        if webhook_url:
            event = {
                "id": f"evt_{uuid.uuid4().hex[:12]}",
                "type": "payment.succeeded",
                "data": {"payment_id": payment["id"]},
            }
            background.add_task(
                _delayed_delivery, webhook_url, webhook_secret, event, duplicate_webhooks
            )
        return JSONResponse(payment)

    return app


def _delayed_delivery(url: str, secret: str, event: dict[str, Any], duplicate: bool) -> None:
    time.sleep(1)  # simulate the provider settling the payment
    deliver_webhook(url, secret, event, times=2 if duplicate else 1)


def main() -> FastAPI:  # pragma: no cover - used by uvicorn --factory
    return create_mock_app(
        api_key=os.getenv("MOCK_API_KEY", "sk_test_demo"),
        fail_first_n=int(os.getenv("MOCK_FAIL_FIRST_N", "0")),
        webhook_url=os.getenv("MOCK_WEBHOOK_URL"),
        webhook_secret=os.getenv("MOCK_WEBHOOK_SECRET", "whsec_demo"),
        duplicate_webhooks=os.getenv("MOCK_DUPLICATE_WEBHOOKS") == "1",
    )
