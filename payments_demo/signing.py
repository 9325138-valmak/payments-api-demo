"""Webhook signing and verification.

Scheme (modelled on common payment providers): the header looks like
``t=<unix timestamp>,v1=<hex digest>`` where the digest is
HMAC-SHA256(secret, "<timestamp>." + raw_body).

Including the timestamp in the signed data lets the receiver reject replayed
requests; comparing digests in constant time avoids timing leaks.
"""

from __future__ import annotations

import hashlib
import hmac
import time


class SignatureError(Exception):
    """Raised when a webhook signature cannot be trusted."""


def _digest(payload: bytes, secret: str, timestamp: int) -> str:
    message = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    return f"t={ts},v1={_digest(payload, secret, ts)}"


def verify(
    header: str | None,
    payload: bytes,
    secret: str,
    *,
    tolerance: int = 300,
    now: int | None = None,
) -> None:
    """Raise SignatureError unless the header is valid for this exact payload."""
    if not header:
        raise SignatureError("missing signature header")
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        provided = parts["v1"]
    except (ValueError, KeyError) as exc:
        raise SignatureError("malformed signature header") from exc

    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance:
        raise SignatureError("timestamp outside tolerance (replay or clock skew)")

    if not hmac.compare_digest(_digest(payload, secret, timestamp), provided):
        raise SignatureError("signature mismatch")
