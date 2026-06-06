"""
User Service Configuration.

All settings loaded from environment variables with sane defaults.
Never hardcode secrets — use .env or secrets manager.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class UserServiceConfig(BaseSettings):
    """User service settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_prefix="USER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Service ──────────────────────────────────────────────────────────────
    service_name: str = "user-service"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8003
    workers: int = 4

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/rag_db",
        description="Async PostgreSQL DSN",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_echo: bool = False

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    # These are consumed by the service to validate tokens issued by auth-service
    jwt_secret_key: str = Field(
        default="change-me-in-production-use-256-bit-key",
        description="Shared JWT secret — load from secrets manager in prod",
    )
    jwt_algorithm: str = "HS256"
    jwt_audience: str = "rag-api"
    jwt_issuer: str = "rag-auth-service"

    # ── Password hashing ──────────────────────────────────────────────────────
    bcrypt_rounds: int = 12

    # ── RabbitMQ ──────────────────────────────────────────────────────────────
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "rag.events"
    user_events_routing_key: str = "user.events"

    # ── Org limits (defaults, can be overridden per org) ─────────────────────
    default_max_users: int = 50
    default_max_documents: int = 10_000
    default_max_storage_gb: float = 100.0
    default_max_queries_per_month: int = 100_000

    # ── Pagination ────────────────────────────────────────────────────────────
    default_page_size: int = 20
    max_page_size: int = 100

    # ── Observability ─────────────────────────────────────────────────────────
    otlp_endpoint: str | None = None
    log_level: str = "INFO"

    @field_validator("bcrypt_rounds")
    @classmethod
    def validate_bcrypt_rounds(cls, v: int) -> int:
        """Keep bcrypt rounds in secure but performant range."""
        if not 10 <= v <= 16:
            raise ValueError("bcrypt_rounds must be between 10 and 16")
        return v

    @property
    def database_url_sync(self) -> str:
        """Sync DSN for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache(maxsize=1)
def get_config() -> UserServiceConfig:
    """Return cached config singleton."""
    return UserServiceConfig()
