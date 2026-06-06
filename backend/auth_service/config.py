"""
Auth Service configuration.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service ──────────────────────────────────────────────────────────────
    service_name: str = "auth-service"
    service_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8001
    environment: str = Field(default="production", pattern="^(development|staging|production)$")
    log_level: str = "INFO"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: PostgresDsn = Field(..., description="PostgreSQL async DSN")

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_max_connections: int = 20

    # ── JWT (local fallback) ──────────────────────────────────────────────────
    jwt_secret_key: str = Field(..., min_length=32, description="HS256 signing secret")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── Keycloak ──────────────────────────────────────────────────────────────
    keycloak_enabled: bool = True
    keycloak_server_url: str = Field(default="http://keycloak:8080")
    keycloak_realm: str = "enterprise-rag"
    keycloak_client_id: str = Field(..., description="Keycloak client ID")
    keycloak_client_secret: str = Field(..., description="Keycloak client secret")
    keycloak_admin_username: str = Field(default="admin")
    keycloak_admin_password: str = Field(..., description="Keycloak admin password")

    # ── OAuth / SSO ───────────────────────────────────────────────────────────
    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")
    oauth_redirect_uri: str = "http://localhost:8001/auth/sso/callback"

    # ── Security ─────────────────────────────────────────────────────────────
    internal_api_key: str = Field(..., description="Shared inter-service secret")
    bcrypt_rounds: int = 12
    password_min_length: int = 8

    # ── Observability ────────────────────────────────────────────────────────
    otel_endpoint: str = "http://otel-collector:4317"
    otel_enabled: bool = True

    @field_validator("database_url", mode="before")
    @classmethod
    def _coerce_db(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def asyncpg_dsn(self) -> str:
        return str(self.database_url).replace("postgresql+asyncpg://", "postgresql://")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
