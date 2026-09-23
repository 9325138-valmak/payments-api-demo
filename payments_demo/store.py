"""SQLite storage for payments and processed webhook events.

Two tables carry the reliability guarantees:

* ``payments.idempotency_key`` is UNIQUE, so a repeated create request maps to
  the same payment instead of a second one.
* ``processed_events.event_id`` is the PRIMARY KEY, so a webhook the provider
  delivers twice changes state only once.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    received_at TEXT NOT NULL
);
"""

# Which webhook event moves a payment to which status.
EVENT_TO_STATUS = {
    "payment.succeeded": "succeeded",
    "payment.failed": "failed",
    "payment.refunded": "refunded",
}

# Allowed status changes. Anything else (for example "succeeded" arriving after
# "refunded" because events were delivered out of order) is ignored.
ALLOWED_TRANSITIONS = {
    "pending": {"succeeded", "failed"},
    "succeeded": {"refunded"},
    "failed": set(),
    "refunded": set(),
}


class DuplicateKeyError(Exception):
    """Raised when a payment with this idempotency key already exists."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str) -> None:
        self._path = path
        with self._tx() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_payment(self, payment_id: str) -> dict[str, Any] | None:
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        return dict(row) if row else None

    def get_payment_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT * FROM payments WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
        return dict(row) if row else None

    def insert_payment(
        self, payment_id: str, idempotency_key: str, amount: int, currency: str, status: str
    ) -> dict[str, Any]:
        now = _now()
        try:
            with self._tx() as conn:
                conn.execute(
                    "INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (payment_id, idempotency_key, amount, currency, status, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateKeyError(idempotency_key) from exc
        payment = self.get_payment(payment_id)
        assert payment is not None
        return payment

    def apply_event(self, event_id: str, event_type: str, payment_id: str) -> str:
        """Apply one webhook event and return what happened.

        Returns one of: "applied", "duplicate", "ignored", "unknown_payment".
        Everything happens in one transaction, so the event is recorded as
        processed only if the payment update succeeded too.
        """
        with self._tx() as conn:
            row = conn.execute("SELECT status FROM payments WHERE id = ?", (payment_id,)).fetchone()
            if row is None:
                # Nothing is recorded, so the provider's retry can succeed once
                # the payment row exists (the webhook can beat our own write).
                return "unknown_payment"

            try:
                conn.execute(
                    "INSERT INTO processed_events VALUES (?, ?, ?)",
                    (event_id, event_type, _now()),
                )
            except sqlite3.IntegrityError:
                return "duplicate"

            new_status = EVENT_TO_STATUS.get(event_type)
            if new_status is None or new_status not in ALLOWED_TRANSITIONS[row["status"]]:
                return "ignored"

            conn.execute(
                "UPDATE payments SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, _now(), payment_id),
            )
            return "applied"
