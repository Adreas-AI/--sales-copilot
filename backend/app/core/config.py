"""Application settings, loaded from environment variables (or a local .env file)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application -------------------------------------------------------------------
    environment: str = "development"
    log_level: str = "INFO"
    log_json: bool = False
    database_url: str = "sqlite:///./copilot.db"
    # When set, every internal /api/v1 endpoint requires the X-API-Key header.
    api_key: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    public_base_url: str = "http://localhost:8000"

    # --- Secrets for signed links and webhooks -----------------------------------------
    webhook_secret: str = "dev-webhook-secret-change-me"
    webhook_tolerance_seconds: int = 300
    unsubscribe_secret: str = "dev-unsubscribe-secret-change-me"

    # --- AI (optional; everything works on rules + templates without it) ---------------
    ai_enabled: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0

    # --- Qualification -------------------------------------------------------------------
    hot_threshold: int = 70
    warm_threshold: int = 40
    # The AI may move the rule score by at most this many points, and only with evidence.
    ai_max_adjustment: int = 15

    # --- Follow-up cadence ----------------------------------------------------------------
    # Days after the lead's submission at which follow-up drafts are prepared.
    followup_step_days: Annotated[list[int], NoDecode] = [2, 5]
    # Day on which an unanswered lead is handed to a person for manual review.
    manual_review_day: int = 10
    # Only leads with these temperatures get an automated follow-up sequence.
    followup_temperatures: Annotated[list[str], NoDecode] = ["hot", "warm"]
    # A pending draft older than this counts as an overdue follow-up.
    draft_review_sla_hours: int = 24
    # An inbound message without a response after this long counts as unanswered.
    unanswered_after_hours: int = 4

    # --- Outbound email -------------------------------------------------------------------
    sender_name: str = "Maya Chen"
    sender_title: str = "Account Executive"
    sender_email: str = "maya@bookflow.example"
    email_transport: Literal["log", "smtp"] = "log"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True

    # --- Job worker -----------------------------------------------------------------------
    worker_poll_seconds: float = 5.0
    worker_batch_size: int = 10
    job_lease_seconds: int = 300
    job_max_attempts: int = 5

    @field_validator("cors_origins", "followup_temperatures", mode="before")
    @classmethod
    def _split_str_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("followup_step_days", mode="before")
    @classmethod
    def _split_int_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        days = self.followup_step_days
        if any(d <= 0 for d in days) or days != sorted(set(days)):
            raise ValueError("FOLLOWUP_STEP_DAYS must be positive and strictly increasing")
        if days and self.manual_review_day <= days[-1]:
            raise ValueError("MANUAL_REVIEW_DAY must come after the last follow-up step")
        if not 0 < self.warm_threshold < self.hot_threshold <= 100:
            raise ValueError("Thresholds must satisfy 0 < WARM_THRESHOLD < HOT_THRESHOLD <= 100")
        unknown = set(self.followup_temperatures) - {"hot", "warm", "cold"}
        if unknown:
            raise ValueError(f"Unknown FOLLOWUP_TEMPERATURES: {sorted(unknown)}")
        return self

    @property
    def ai_configured(self) -> bool:
        return self.ai_enabled and bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
