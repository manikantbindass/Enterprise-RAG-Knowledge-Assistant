"""
Base configuration for Enterprise RAG Knowledge Assistant services.

All services inherit from BaseConfig. Values come from environment variables
or .env file. No secrets hardcoded — production secrets from vault/env.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import AnyUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """Allowed log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class BaseConfig(BaseSettings):
    """
    Base configuration shared across all microservices.

    Load order: environment variables > .env file > defaults.
    All sensitive fields have no defaults — must be set explicitly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # App                                                                   #
    # ------------------------------------------------------------------ #
    SERVICE_NAME: str = Field(default="rag-service", description="Identifies service in logs/traces")
    ENVIRONMENT: Environment = Field(default=Environment.DEVELOPMENT)
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: LogLevel = Field(default=LogLevel.INFO)
    API_V1_PREFIX: str = Field(default="/api/v1")

    # ------------------------------------------------------------------ #
    # Database                                                              #
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = Field(
        description="PostgreSQL async DSN. Format: postgresql+asyncpg://user:pass@host:port/db"
    )
    DATABASE_POOL_SIZE: int = Field(default=20, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=40, ge=0, le=200)
    DATABASE_POOL_PRE_PING: bool = Field(default=True)
    DATABASE_POOL_RECYCLE: int = Field(default=3600, description="Seconds before recycling connections")
    DATABASE_ECHO: bool = Field(default=False, description="Log all SQL statements — dev only")

    # ------------------------------------------------------------------ #
    # Redis                                                                 #
    # ------------------------------------------------------------------ #
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis DSN. Format: redis://[:password@]host:port/db",
    )
    REDIS_MAX_CONNECTIONS: int = Field(default=50)
    REDIS_SOCKET_TIMEOUT: float = Field(default=5.0)
    REDIS_SOCKET_CONNECT_TIMEOUT: float = Field(default=2.0)

    # ------------------------------------------------------------------ #
    # RabbitMQ                                                              #
    # ------------------------------------------------------------------ #
    RABBITMQ_URL: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        description="AMQP DSN for RabbitMQ",
    )
    RABBITMQ_PREFETCH_COUNT: int = Field(default=10)
    RABBITMQ_RECONNECT_INTERVAL: float = Field(default=5.0)

    # ------------------------------------------------------------------ #
    # JWT / Security                                                        #
    # ------------------------------------------------------------------ #
    SECRET_KEY: str = Field(description="HMAC secret — minimum 32 chars, generate with: openssl rand -hex 32")
    JWT_SECRET_KEY: str = Field(description="Dedicated JWT signing secret")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1)
    JWT_ISSUER: str = Field(default="rag-knowledge-assistant")
    JWT_AUDIENCE: str = Field(default="rag-api")

    # ------------------------------------------------------------------ #
    # CORS                                                                  #
    # ------------------------------------------------------------------ #
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins. Use ['*'] only in development.",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)
    CORS_ALLOW_METHODS: list[str] = Field(default=["*"])
    CORS_ALLOW_HEADERS: list[str] = Field(default=["*"])

    # ------------------------------------------------------------------ #
    # Storage (MinIO / S3)                                                  #
    # ------------------------------------------------------------------ #
    STORAGE_BACKEND: str = Field(default="minio", pattern="^(minio|s3)$")
    MINIO_ENDPOINT: str = Field(default="localhost:9000")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin")
    MINIO_SECRET_KEY: str = Field(default="minioadmin")
    MINIO_SECURE: bool = Field(default=False)
    MINIO_BUCKET_DOCUMENTS: str = Field(default="documents")
    AWS_ACCESS_KEY_ID: str = Field(default="")
    AWS_SECRET_ACCESS_KEY: str = Field(default="")
    AWS_REGION: str = Field(default="us-east-1")
    AWS_S3_BUCKET: str = Field(default="rag-documents")

    # ------------------------------------------------------------------ #
    # Rate Limiting                                                         #
    # ------------------------------------------------------------------ #
    RATE_LIMIT_PER_USER: int = Field(default=100, description="Requests per window per user")
    RATE_LIMIT_PER_IP: int = Field(default=200, description="Requests per window per IP")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)

    # ------------------------------------------------------------------ #
    # OpenTelemetry                                                         #
    # ------------------------------------------------------------------ #
    OTEL_ENABLED: bool = Field(default=False)
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(default="http://localhost:4317")
    OTEL_SERVICE_NAME: str = Field(default="")

    # ------------------------------------------------------------------ #
    # Prometheus                                                            #
    # ------------------------------------------------------------------ #
    METRICS_ENABLED: bool = Field(default=True)
    METRICS_PORT: int = Field(default=9090)

    # ------------------------------------------------------------------ #
    # Validators                                                            #
    # ------------------------------------------------------------------ #
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use 'postgresql+asyncpg://' scheme for async operation"
            )
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def production_safety_checks(self) -> "BaseConfig":
        if self.ENVIRONMENT == Environment.PRODUCTION:
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Wildcard CORS not allowed in production")
            if self.DATABASE_ECHO:
                raise ValueError("DATABASE_ECHO must be False in production")
        if not self.OTEL_SERVICE_NAME:
            self.OTEL_SERVICE_NAME = self.SERVICE_NAME
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == Environment.DEVELOPMENT


@lru_cache(maxsize=1)
def get_settings() -> BaseConfig:
    """
    Cached settings singleton. Import and call this everywhere.

    Usage:
        from shared.config import get_settings
        settings = get_settings()
    """
    return BaseConfig()  # type: ignore[call-arg]
