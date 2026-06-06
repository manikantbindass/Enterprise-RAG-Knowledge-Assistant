"""
Vector Service configuration.
All settings loaded from environment variables — no hardcoded secrets.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorBackend(str, Enum):
    PGVECTOR = "pgvector"


class RerankerModel(str, Enum):
    MS_MARCO_MINILM = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    MS_MARCO_ELECTRA = "cross-encoder/ms-marco-electra-base"
    NONE = "none"


class Settings(BaseSettings):
    """Vector service runtime settings."""

    model_config = SettingsConfigDict(
        env_prefix="VECTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service ──────────────────────────────────────────────────────────────
    service_name: str = "vector-service"
    service_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8003
    workers: int = 4
    log_level: str = "INFO"
    environment: str = Field(default="production", pattern="^(development|staging|production)$")

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: PostgresDsn = Field(
        ...,
        description="asyncpg-compatible PostgreSQL DSN, e.g. postgresql://user:pass@host/db",
    )
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20
    db_command_timeout: float = 30.0

    # ── pgvector ──────────────────────────────────────────────────────────────
    vector_backend: VectorBackend = VectorBackend.PGVECTOR
    embedding_dim: int = 1536  # OpenAI text-embedding-3-small default
    vector_index_type: str = "ivfflat"  # ivfflat | hnsw
    ivfflat_probes: int = 10  # Increase for better recall at cost of latency

    # ── BM25 / Full-text ─────────────────────────────────────────────────────
    fts_language: str = "english"  # PostgreSQL text search config
    fts_normalization: int = 2  # ts_rank normalization option

    # ── Hybrid search ────────────────────────────────────────────────────────
    default_alpha: float = Field(default=0.7, ge=0.0, le=1.0)
    rrf_k: int = 60  # RRF constant
    default_top_k: int = 10
    max_top_k: int = 100

    # ── Reranker ─────────────────────────────────────────────────────────────
    reranker_model: RerankerModel = RerankerModel.MS_MARCO_MINILM
    reranker_batch_size: int = 32
    reranker_max_length: int = 512
    reranker_device: str = "cpu"  # cpu | cuda | mps

    # ── Observability ────────────────────────────────────────────────────────
    otel_endpoint: str = "http://otel-collector:4317"
    otel_enabled: bool = True
    metrics_enabled: bool = True

    # ── Security ─────────────────────────────────────────────────────────────
    internal_api_key: str = Field(..., description="Shared secret for inter-service calls")

    @field_validator("database_url", mode="before")
    @classmethod
    def _coerce_db_url(cls, v: str) -> str:
        """Accept both postgresql:// and postgresql+asyncpg:// schemes."""
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def asyncpg_dsn(self) -> str:
        """Plain asyncpg DSN (no +asyncpg driver prefix)."""
        raw = str(self.database_url)
        return raw.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
