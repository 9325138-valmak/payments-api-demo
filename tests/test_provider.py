import httpx
import pytest

from payments_demo.provider import (
    ProviderAuthError,
    ProviderClient,
    ProviderRequestError,
    ProviderUnavailableError,
)

OK = {"id": "pay_1", "status": "pending", "amount": 500, "currency": "USD"}


def make_client(responses, sleeps, seen_keys=None):
    """Client whose transport replays `responses` (Response objects or exceptions)."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen_keys is not None:
            seen_keys.append(request.headers.get("Idempotency-Key"))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return ProviderClient(
        "http://provider.test",
        "sk_test",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        base_delay=0.5,
    )


def test_retries_503_with_backoff_and_reuses_idempotency_key():
    sleeps, keys = [], []
    client = make_client(
        [httpx.Response(503), httpx.Response(503), httpx.Response(200, json=OK)], sleeps, keys
    )
    assert client.create_payment(500, "USD", "key-1") == OK
    assert sleeps == [0.5, 1.0]  # exponential backoff
    assert keys == ["key-1", "key-1", "key-1"]  # same key on every attempt


def test_honours_retry_after_header_on_429():
    sleeps = []
    client = make_client(
        [httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json=OK)], sleeps
    )
    client.create_payment(500, "USD", "key-1")
    assert sleeps == [2.0]


def test_retries_network_errors():
    sleeps = []
    client = make_client([httpx.ConnectTimeout("slow"), httpx.Response(200, json=OK)], sleeps)
    assert client.create_payment(500, "USD", "key-1") == OK
    assert len(sleeps) == 1


def test_gives_up_after_max_attempts():
    sleeps = []
    client = make_client([httpx.Response(503)] * 4, sleeps)
    with pytest.raises(ProviderUnavailableError, match="after 4 attempts"):
        client.create_payment(500, "USD", "key-1")
    assert len(sleeps) == 3  # no sleep after the final attempt


def test_auth_errors_are_not_retried():
    sleeps = []
    client = make_client([httpx.Response(401)], sleeps)
    with pytest.raises(ProviderAuthError, match="PROVIDER_API_KEY"):
        client.create_payment(500, "USD", "key-1")
    assert sleeps == []


def test_other_client_errors_are_not_retried():
    sleeps = []
    client = make_client([httpx.Response(400, text="bad currency")], sleeps)
    with pytest.raises(ProviderRequestError, match="bad currency"):
        client.create_payment(500, "USD", "key-1")
    assert sleeps == []
