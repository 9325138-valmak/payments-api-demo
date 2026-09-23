"""Configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    provider_base_url: str = "http://127.0.0.1:8001"
    provider_api_key: str = "sk_test_demo"
    webhook_secret: str = "whsec_demo"
    db_path: str = "payments.db"
    webhook_tolerance_seconds: int = 300

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            provider_base_url=os.getenv("PROVIDER_BASE_URL", defaults.provider_base_url),
            provider_api_key=os.getenv("PROVIDER_API_KEY", defaults.provider_api_key),
            webhook_secret=os.getenv("WEBHOOK_SECRET", defaults.webhook_secret),
            db_path=os.getenv("DB_PATH", defaults.db_path),
            webhook_tolerance_seconds=int(
                os.getenv("WEBHOOK_TOLERANCE_SECONDS", str(defaults.webhook_tolerance_seconds))
            ),
        )
