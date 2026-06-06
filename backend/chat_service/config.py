"""
Chat Service configuration.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service ──────────────────────────────────────────────────────────────
    service_name: str = "chat-service"
    service_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8004
    environment: str = Field(default="production", pattern="^(development|staging|production)$")
    log_level: str = "INFO"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: PostgresDsn = Field(...)

    # ── LLM providers ─────────────────────────────────────────────────────────
    default_llm_provider: LLMProvider = LLMProvider.OPENAI

    # OpenAI
    openai_api_key: str = Field(default="")
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.2

    # Anthropic
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    anthropic_max_tokens: int = 4096

    # Azure OpenAI
    azure_openai_api_key: str = Field(default="")
    azure_openai_endpoint: str = Field(default="")
    azure_openai_deployment: str = Field(default="gpt-4o")
    azure_openai_api_version: str = "2024-02-01"

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: float = 120.0

    # ── Context window ────────────────────────────────────────────────────────
    max_context_tokens: int = 8192
    max_history_messages: int = 20
    context_overlap_tokens: int = 200

    # ── Vector service ────────────────────────────────────────────────────────
    vector_service_url: str = "http://vector-service:8003"
    vector_service_api_key: str = Field(...)
    vector_search_top_k: int = 20
    vector_search_alpha: float = 0.7

    # ── RAG pipeline ──────────────────────────────────────────────────────────
    enable_query_rewriting: bool = True
    enable_hyde: bool = True
    enable_reranking: bool = True
    min_relevance_score: float = 0.3

    # ── Observability ────────────────────────────────────────────────────────
    otel_endpoint: str = "http://otel-collector:4317"
    otel_enabled: bool = True

    # ── Security ─────────────────────────────────────────────────────────────
    internal_api_key: str = Field(...)

    @field_validator("database_url", mode="before")
    @classmethod
    def _coerce_db(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
