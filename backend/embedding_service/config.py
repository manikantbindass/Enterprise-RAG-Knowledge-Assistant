"""Embedding Service — Configuration"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://rag_user:password@localhost:5432/rag_assistant"
    rabbitmq_url: str = "amqp://admin:password@localhost:5672/"

    # Provider selection
    default_embedding_provider: str = "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimensions: int = 1536

    # Azure OpenAI
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"

    # BGE (local)
    bge_model_name: str = "BAAI/bge-large-en-v1.5"

    # Processing
    embedding_batch_size: int = 128
    embedding_max_retries: int = 3
    embedding_retry_delay: float = 1.0

    # Cost tracking
    enable_cost_tracking: bool = True
    monthly_budget_usd: float = 500.0
    alert_budget_threshold_percent: float = 80.0

    # Queue
    queue_name: str = "doc.processed"
    result_exchange: str = "rag.events"
