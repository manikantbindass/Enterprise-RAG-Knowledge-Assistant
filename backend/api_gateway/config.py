"""
API Gateway configuration.

Reads from environment variables (and optional .env file).
All secrets via env vars — no hardcoded values.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewayConfig(BaseSettings):
    """
    Central config for API Gateway.

    Env prefix: GATEWAY_ (e.g. GATEWAY_AUTH_SERVICE_URL).
    Shared infra vars (DB, Redis, etc.) have no prefix.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------------------
    # Application
    # ---------------------------------------------------------------------------
    app_name: str = Field(default="Enterprise RAG Knowledge Assistant - API Gateway")
    app_version: str = Field(default="1.0.0")
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # ---------------------------------------------------------------------------
    # Server
    # ---------------------------------------------------------------------------
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    workers: int = Field(default=4)
    root_path: str = Field(default="")

    # ---------------------------------------------------------------------------
    # Security
    # ---------------------------------------------------------------------------
    secret_key: str = Field(
        ...,
        description="JWT signing secret — must be set in env",
    )
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_days: int = Field(default=7)

    # ---------------------------------------------------------------------------
    # CORS
    # ---------------------------------------------------------------------------
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: list[str] = Field(default=["*"])
    cors_allow_headers: list[str] = Field(default=["*"])

    # ---------------------------------------------------------------------------
    # Trusted hosts
    # ---------------------------------------------------------------------------
    allowed_hosts: list[str] = Field(
        default=["*"],
        description="TrustedHostMiddleware whitelist",
    )

    # ---------------------------------------------------------------------------
    # Rate limiting
    # ---------------------------------------------------------------------------
    rate_limit_requests: int = Field(default=100, description="Requests per window")
    rate_limit_window_seconds: int = Field(default=60)
    rate_limit_enabled: bool = Field(default=True)

    # ---------------------------------------------------------------------------
    # Database (PostgreSQL)
    # ---------------------------------------------------------------------------
    database_url: str = Field(
        ...,
        description="Async PostgreSQL DSN: postgresql+asyncpg://user:pass@host/db",
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)
    db_pool_timeout: int = Field(default=30)
    db_echo: bool = Field(default=False)

    # ---------------------------------------------------------------------------
    # Redis
    # ---------------------------------------------------------------------------
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_max_connections: int = Field(default=50)
    redis_socket_timeout: float = Field(default=5.0)
    redis_connect_timeout: float = Field(default=2.0)

    # ---------------------------------------------------------------------------
    # RabbitMQ
    # ---------------------------------------------------------------------------
    rabbitmq_url: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        description="RabbitMQ AMQP connection URL",
    )

    # ---------------------------------------------------------------------------
    # Microservice URLs
    # ---------------------------------------------------------------------------
    auth_service_url: AnyHttpUrl = Field(
        default="http://auth-service:8001",
        description="Auth microservice base URL",
    )
    user_service_url: AnyHttpUrl = Field(
        default="http://user-service:8002",
        description="User management microservice base URL",
    )
    document_service_url: AnyHttpUrl = Field(
        default="http://document-service:8003",
        description="Document ingestion & storage microservice base URL",
    )
    search_service_url: AnyHttpUrl = Field(
        default="http://search-service:8004",
        description="Vector search microservice base URL",
    )
    chat_service_url: AnyHttpUrl = Field(
        default="http://chat-service:8005",
        description="Conversation / LLM microservice base URL",
    )
    organization_service_url: AnyHttpUrl = Field(
        default="http://organization-service:8006",
        description="Organization management microservice base URL",
    )
    notification_service_url: AnyHttpUrl = Field(
        default="http://notification-service:8007",
        description="Notification microservice base URL",
    )
    analytics_service_url: AnyHttpUrl = Field(
        default="http://analytics-service:8008",
        description="Analytics / metrics microservice base URL",
    )

    # ---------------------------------------------------------------------------
    # Proxy / HTTP client
    # ---------------------------------------------------------------------------
    proxy_timeout_connect: float = Field(
        default=5.0,
        description="Seconds to wait for upstream TCP connect",
    )
    proxy_timeout_read: float = Field(
        default=60.0,
        description="Seconds to wait for upstream response (long for streaming)",
    )
    proxy_timeout_write: float = Field(
        default=10.0,
        description="Seconds to wait for upstream write",
    )
    proxy_timeout_pool: float = Field(
        default=5.0,
        description="Seconds to wait for a connection from pool",
    )
    proxy_max_retries: int = Field(
        default=3,
        description="Max retry attempts on 503 / connection error",
    )
    proxy_retry_backoff_factor: float = Field(
        default=0.5,
        description="Exponential backoff factor between retries",
    )
    proxy_max_connections: int = Field(default=100)
    proxy_max_keepalive_connections: int = Field(default=20)

    # ---------------------------------------------------------------------------
    # OpenTelemetry
    # ---------------------------------------------------------------------------
    otel_enabled: bool = Field(default=True)
    otel_service_name: str = Field(default="api-gateway")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://otel-collector:4317",
        description="OTLP gRPC endpoint",
    )

    # ---------------------------------------------------------------------------
    # Prometheus
    # ---------------------------------------------------------------------------
    metrics_enabled: bool = Field(default=True)

    # ---------------------------------------------------------------------------
    # Feature flags
    # ---------------------------------------------------------------------------
    streaming_enabled: bool = Field(
        default=True,
        description="Enable SSE streaming for chat responses",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Accept comma-separated string or JSON list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v

    @property
    def is_production(self) -> bool:
        """True when running in production environment."""
        return self.environment.lower() == "production"

    @property
    def auth_service_base(self) -> str:
        """Auth service URL as plain string (no trailing slash)."""
        return str(self.auth_service_url).rstrip("/")

    @property
    def user_service_base(self) -> str:
        return str(self.user_service_url).rstrip("/")

    @property
    def document_service_base(self) -> str:
        return str(self.document_service_url).rstrip("/")

    @property
    def search_service_base(self) -> str:
        return str(self.search_service_url).rstrip("/")

    @property
    def chat_service_base(self) -> str:
        return str(self.chat_service_url).rstrip("/")

    @property
    def organization_service_base(self) -> str:
        return str(self.organization_service_url).rstrip("/")

    @property
    def analytics_service_base(self) -> str:
        return str(self.analytics_service_url).rstrip("/")


@lru_cache(maxsize=1)
def get_config() -> GatewayConfig:
    """Return singleton GatewayConfig. Cached after first call."""
    return GatewayConfig()  # type: ignore[call-arg]
