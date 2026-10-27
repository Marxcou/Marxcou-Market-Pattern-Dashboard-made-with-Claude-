import logging
from functools import lru_cache
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    """All configuration comes from environment variables (.env). Never keys in code."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    demo_mode: bool = False
    timezone: str = "Europe/Berlin"
    database_url: str = "sqlite:///./marktmuster.db"

    session_secret: str = "change-me-to-a-long-random-string"
    session_ttl_hours: int = 168
    cookie_secure: bool = False
    admin_email: str = ""
    admin_password: str = ""

    # Keys of the data sources (adapters read them via get_settings(), never from code)
    alpaca_api_key_id: str = ""
    alpaca_api_secret_key: str = ""
    finnhub_api_key: str = ""
    stooq_api_key: str = ""
    openfigi_api_key: str = ""
    yahoo_enabled: bool = False
    sec_edgar_contact_email: str = ""
    eqs_rss_url: str = ""  # feed address of EQS news (check the terms of use first)
    ir_feeds: str = ""  # "SYMBOL|https://feed,..." investor relations feeds (check the terms of use first)
    rss_enabled_feeds: str = ""  # comma list of feed IDs (see adapters/rss.py) or "all"
    marketaux_api_key: str = ""
    alphavantage_api_key: str = ""
    anthropic_api_key: str = ""
    claude_monthly_budget_usd: float = 10.0
    claude_use_batch: bool = True  # sentiment via batch API (half price, result after minutes to hours)
    news_retention_days: int = 90  # older items are deleted; 0 = never delete

    @model_validator(mode="after")
    def _production_needs_real_secrets(self) -> "Settings":
        """In production the app does not start with the sample values from .env.example."""
        if self.app_env == "production":
            problems = []
            if self.session_secret.startswith("change-me") or len(self.session_secret) < 32:
                problems.append("SESSION_SECRET (mindestens 32 Zeichen, z. B. openssl rand -hex 32)")
            if self.admin_password.startswith("change-me"):
                problems.append("ADMIN_PASSWORD")
            if problems:
                raise ValueError("APP_ENV=production, but sample values are still set: " + ", ".join(problems))
        return self

    @model_validator(mode="before")
    @classmethod
    def _ignore_comment_values(cls, data: Any) -> Any:
        """A value starting with "#" is a comment that Docker Compose passes as the value for "KEY=   # text".
        It counts as not set (default value). Only the name is logged, never the value."""
        if not isinstance(data, dict):
            return data
        cleaned = {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip().startswith("#"))}
        for k in sorted(set(data) - set(cleaned)):
            log.warning("%s contains only a comment (starts with '#') and counts as not set. "
                        "Do not write comments after the value in .env.", k.upper())
        return cleaned


@lru_cache
def get_settings() -> Settings:
    return Settings()
