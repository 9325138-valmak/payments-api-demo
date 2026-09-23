import json
import time

import pytest
from fastapi.testclient import TestClient

from payments_demo import signing
from payments_demo.app import create_app
from payments_demo.config import Settings
from payments_demo.provider import ProviderUnavailableError

SECRET = "whsec_test"


class StubGateway:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def create_payment(self, amount, currency, idempotency_key):
        self.calls += 1
        if self.fail:
            raise ProviderUnavailableError("down")
        return {"id": f"pay_{self.calls}", "status": "pending"}


@pytest.fixture
def gateway():
    return StubGateway()


@pytest.fixture
def client(tmp_path, gateway):
    settings = Settings(db_path=str(tmp_path / "test.db"), webhook_secret=SECRET)
    return TestClient(create_app(settings, gateway))


def create(client, key="key-1", amount=1000):
    return client.post(
        "/payments",
        json={"amount": amount, "currency": "usd"},
        headers={"Idempotency-Key": key},
    )


def webhook(client, event, secret=SECRET, timestamp=None):
    body = json.dumps(event).encode()
    header = signing.sign(body, secret, timestamp)
    return client.post(
        "/webhooks",
        content=body,
        headers={"Provider-Signature": header, "Content-Type": "application/json"},
    )


def event(event_id, event_type, payment_id):
    return {"id": event_id, "type": event_type, "data": {"payment_id": payment_id}}


def test_create_payment_returns_pending_payment(client):
    response = create(client)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["currency"] == "USD"


def test_same_idempotency_key_does_not_charge_twice(client, gateway):
    first = create(client)
    second = create(client)
    assert second.status_code == 200
    assert second.headers["Idempotent-Replay"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert gateway.calls == 1


def test_missing_idempotency_key_is_rejected(client):
    response = client.post("/payments", json={"amount": 1000, "currency": "usd"})
    assert response.status_code == 400


def test_invalid_amount_is_rejected(client):
    assert create(client, amount=0).status_code == 422


def test_provider_outage_returns_503_and_stores_nothing(client, gateway):
    gateway.fail = True
    assert create(client).status_code == 503
    gateway.fail = False
    assert create(client).status_code == 201  # the same key can be retried safely


def test_signed_webhook_updates_status(client):
    payment_id = create(client).json()["id"]
    response = webhook(client, event("evt_1", "payment.succeeded", payment_id))
    assert response.json() == {"status": "applied"}
    assert client.get(f"/payments/{payment_id}").json()["status"] == "succeeded"


def test_duplicate_webhook_is_acknowledged_but_not_reapplied(client):
    payment_id = create(client).json()["id"]
    evt = event("evt_1", "payment.succeeded", payment_id)
    assert webhook(client, evt).json() == {"status": "applied"}
    assert webhook(client, evt).json() == {"status": "duplicate"}  # still a 200
    assert client.get(f"/payments/{payment_id}").json()["status"] == "succeeded"


def test_out_of_order_event_cannot_move_status_backwards(client):
    payment_id = create(client).json()["id"]
    webhook(client, event("evt_1", "payment.succeeded", payment_id))
    webhook(client, event("evt_2", "payment.refunded", payment_id))
    late = webhook(client, event("evt_3", "payment.succeeded", payment_id))
    assert late.json() == {"status": "ignored"}
    assert client.get(f"/payments/{payment_id}").json()["status"] == "refunded"


def test_bad_signature_is_rejected(client):
    payment_id = create(client).json()["id"]
    response = webhook(client, event("evt_1", "payment.succeeded", payment_id), secret="wrong")
    assert response.status_code == 400
    assert client.get(f"/payments/{payment_id}").json()["status"] == "pending"


def test_stale_timestamp_is_rejected(client):
    payment_id = create(client).json()["id"]
    old = int(time.time()) - 3600
    response = webhook(client, event("evt_1", "payment.succeeded", payment_id), timestamp=old)
    assert response.status_code == 400
    assert "tolerance" in response.json()["detail"]


def test_webhook_for_unknown_payment_returns_404_so_provider_retries(client):
    response = webhook(client, event("evt_1", "payment.succeeded", "pay_missing"))
    assert response.status_code == 404
    # Nothing was recorded, so the same event is applied once the payment exists.
    payment_id = create(client).json()["id"]
    assert webhook(client, event("evt_1", "payment.succeeded", payment_id)).json() == {
        "status": "applied"
    }


def test_malformed_event_is_rejected(client):
    body = b'{"hello": "world"}'
    header = signing.sign(body, SECRET)
    response = client.post("/webhooks", content=body, headers={"Provider-Signature": header})
    assert response.status_code == 400
