"""
Audit Service Configuration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuditServiceConfig(BaseSettings):
    """Audit service settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_prefix="AUDIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Service ──────────────────────────────────────────────────────────────
    service_name: str = "audit-service"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8005
    workers: int = 2

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/rag_db",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_echo: bool = False

    # ── RabbitMQ ──────────────────────────────────────────────────────────────
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "rag.events"
    audit_queue: str = "audit.events"
    audit_routing_key: str = "audit.event"

    # ── Worker ────────────────────────────────────────────────────────────────
    # Batch insert for efficiency — flush every N events or every M seconds
    bulk_insert_batch_size: int = 100
    bulk_insert_flush_interval_seconds: float = 2.0
    worker_prefetch_count: int = 50

    # ── Export ────────────────────────────────────────────────────────────────
    export_max_rows: int = 100_000
    export_temp_dir: str = "/tmp/audit_exports"

    # ── Auth ──────────────────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production-use-256-bit-key"
    jwt_algorithm: str = "HS256"
    jwt_audience: str = "rag-api"
    jwt_issuer: str = "rag-auth-service"

    # ── Pagination ────────────────────────────────────────────────────────────
    default_page_size: int = 50
    max_page_size: int = 500

    # ── Observability ─────────────────────────────────────────────────────────
    otlp_endpoint: str | None = None
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_config() -> AuditServiceConfig:
    return AuditServiceConfig()
