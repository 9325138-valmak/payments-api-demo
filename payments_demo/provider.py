"""Client for the payments provider, with safe retries.

Every attempt for one logical payment reuses the same Idempotency-Key, so a
retry after a timeout can never create a second charge.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class ProviderError(Exception):
    """Base class for provider failures."""


class ProviderAuthError(ProviderError):
    """The provider rejected our credentials (HTTP 401/403). Not retried."""


class ProviderRequestError(ProviderError):
    """The provider rejected the request (other 4xx). Not retried."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"provider returned {status_code}: {body}")
        self.status_code = status_code


class ProviderUnavailableError(ProviderError):
    """Retries were exhausted (timeouts, 429 or 5xx)."""


class ProviderClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        max_attempts: int = 4,
        base_delay: float = 0.5,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._sleep = sleep

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after and retry_after.isdigit():
            return float(retry_after)  # the provider told us how long to wait
        delay: float = self._base_delay * 2 ** (attempt - 1)  # exponential backoff
        return delay

    def create_payment(self, amount: int, currency: str, idempotency_key: str) -> dict[str, Any]:
        payload = {"amount": amount, "currency": currency}
        headers = {"Idempotency-Key": idempotency_key}

        for attempt in range(1, self._max_attempts + 1):
            last_attempt = attempt == self._max_attempts
            try:
                response = self._client.post("/v1/payments", json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if last_attempt:
                    raise ProviderUnavailableError(
                        f"network error after {attempt} attempts"
                    ) from exc
                log.warning("network error on attempt %d, retrying", attempt)
                self._sleep(self._delay(attempt, None))
                continue

            if response.status_code in RETRYABLE_STATUSES:
                if last_attempt:
                    raise ProviderUnavailableError(
                        f"provider returned {response.status_code} after {attempt} attempts"
                    )
                delay = self._delay(attempt, response.headers.get("Retry-After"))
                log.warning("provider returned %d, retrying in %.1fs", response.status_code, delay)
                self._sleep(delay)
                continue

            if response.status_code in (401, 403):
                raise ProviderAuthError("provider rejected credentials; check PROVIDER_API_KEY")
            if response.status_code >= 400:
                raise ProviderRequestError(response.status_code, response.text)
            data: dict[str, Any] = response.json()
            return data

        raise ProviderUnavailableError("no attempts were made")  # pragma: no cover
