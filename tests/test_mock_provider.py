from fastapi.testclient import TestClient

from payments_demo.mock_provider import create_mock_app

HEADERS = {"Authorization": "Bearer sk_test_demo", "Idempotency-Key": "k1"}
BODY = {"amount": 500, "currency": "USD"}


def test_wrong_api_key_returns_401():
    client = TestClient(create_mock_app())
    response = client.post(
        "/v1/payments", json=BODY, headers={**HEADERS, "Authorization": "Bearer nope"}
    )
    assert response.status_code == 401


def test_same_idempotency_key_returns_same_payment():
    client = TestClient(create_mock_app())
    first = client.post("/v1/payments", json=BODY, headers=HEADERS).json()
    second = client.post("/v1/payments", json=BODY, headers=HEADERS).json()
    assert first["id"] == second["id"]


def test_fails_first_n_requests_then_succeeds():
    client = TestClient(create_mock_app(fail_first_n=2))
    codes = [client.post("/v1/payments", json=BODY, headers=HEADERS).status_code for _ in range(3)]
    assert codes == [503, 503, 200]
