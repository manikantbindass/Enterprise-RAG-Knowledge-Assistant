"""
Document Service Configuration.

All settings loaded from environment variables with sane defaults.
Never hardcode secrets — use .env or secrets manager.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DocumentServiceConfig(BaseSettings):
    """Document service settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_prefix="DOCUMENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Service ──────────────────────────────────────────────────────────────
    service_name: str = "document-service"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8001
    workers: int = 4

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/rag_documents",
        description="Async PostgreSQL DSN",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_echo: bool = False

    # ── File limits ───────────────────────────────────────────────────────────
    max_file_size_mb: int = Field(default=100, ge=1, le=2048)

    allowed_mime_types: list[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/webp",
    ]

    # ── Storage ───────────────────────────────────────────────────────────────
    storage_backend: Literal["minio", "s3"] = "minio"
    storage_bucket: str = "rag-documents"
    presigned_url_expiry_seconds: int = 3600

    # MinIO / S3 shared settings
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"

    # MinIO specific
    minio_endpoint: str = "localhost:9000"
    minio_secure: bool = False

    # S3 specific (only when storage_backend="s3")
    s3_endpoint_url: str | None = None

    # ── Virus scan ────────────────────────────────────────────────────────────
    virus_scan_enabled: bool = True
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    clamav_timeout: int = 30

    # ── RabbitMQ ──────────────────────────────────────────────────────────────
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "rag.events"
    rabbitmq_doc_uploaded_routing_key: str = "doc.uploaded"

    # ── Observability ─────────────────────────────────────────────────────────
    otlp_endpoint: str | None = None
    log_level: str = "INFO"

    # ── Pagination ────────────────────────────────────────────────────────────
    default_page_size: int = 20
    max_page_size: int = 100

    @field_validator("max_file_size_mb")
    @classmethod
    def validate_file_size(cls, v: int) -> int:
        """Ensure file size limit is reasonable."""
        if v > 2048:
            raise ValueError("max_file_size_mb cannot exceed 2048 MB")
        return v

    @property
    def max_file_size_bytes(self) -> int:
        """Max file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_config() -> DocumentServiceConfig:
    """Return cached config singleton."""
    return DocumentServiceConfig()
