"""
Processing Service Configuration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProcessingServiceConfig(BaseSettings):
    """Processing service settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_prefix="PROCESSING_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Service ───────────────────────────────────────────────────────────────
    service_name: str = "processing-service"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8002

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/rag_documents",
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # ── Storage ───────────────────────────────────────────────────────────────
    storage_backend: Literal["minio", "s3"] = "minio"
    storage_bucket: str = "rag-documents"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"
    minio_endpoint: str = "localhost:9000"
    minio_secure: bool = False
    s3_endpoint_url: str | None = None

    # ── RabbitMQ ──────────────────────────────────────────────────────────────
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "rag.events"
    rabbitmq_doc_uploaded_queue: str = "doc.uploaded"
    rabbitmq_doc_processed_routing_key: str = "doc.processed"
    rabbitmq_prefetch_count: int = 4

    # ── OCR ───────────────────────────────────────────────────────────────────
    ocr_engine: Literal["tesseract", "azure", "disabled"] = "tesseract"
    tesseract_path: str | None = None  # None = auto-detect from PATH
    tesseract_lang: str = "eng"
    azure_form_recognizer_endpoint: str | None = None
    azure_form_recognizer_key: str | None = None

    # ── Chunking ──────────────────────────────────────────────────────────────
    default_chunking_strategy: Literal[
        "fixed", "recursive", "semantic", "parent_child"
    ] = "recursive"
    chunk_size: int = Field(default=512, ge=64, le=8192)
    chunk_overlap: int = Field(default=64, ge=0, le=512)
    parent_chunk_size: int = Field(default=2048, ge=256, le=16384)
    child_chunk_size: int = Field(default=256, ge=32, le=2048)

    # Semantic chunker settings
    semantic_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    semantic_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    # ── Text extraction ───────────────────────────────────────────────────────
    max_pages_per_document: int = 5000
    pdf_fallback_to_pdfplumber: bool = True
    extract_images_from_pdf: bool = False  # future: image extraction

    # ── Observability ─────────────────────────────────────────────────────────
    otlp_endpoint: str | None = None
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_config() -> ProcessingServiceConfig:
    """Return cached config singleton."""
    return ProcessingServiceConfig()
