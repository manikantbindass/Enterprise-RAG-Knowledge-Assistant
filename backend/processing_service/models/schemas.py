"""
Processing Service schemas — PageContent, Chunk, ProcessingResult.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PageContent(BaseModel):
    """Extracted content from a single page/section."""

    page_num: int
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    extraction_method: str = "direct"  # direct | ocr | fallback


class Chunk(BaseModel):
    """A single text chunk ready for embedding."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    chunk_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    content: str
    chunk_index: int
    start_char: int | None = None
    end_char: int | None = None
    page_number: int | None = None
    token_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProcessingResult(BaseModel):
    """Final result of the full processing pipeline for a document."""

    document_id: uuid.UUID
    pages: list[PageContent]
    chunks: list[Chunk]
    total_pages: int
    total_words: int
    total_chars: int
    language: str | None = None
    processing_errors: list[str] = Field(default_factory=list)
    extraction_method: str = "direct"


class DocUploadedEvent(BaseModel):
    """RabbitMQ event payload for doc.uploaded."""

    document_id: str
    storage_key: str
    storage_backend: str
    content_type: str
    filename: str
    size_bytes: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocProcessedEvent(BaseModel):
    """RabbitMQ event payload for doc.processed."""

    document_id: str
    chunk_count: int
    page_count: int
    word_count: int
    storage_key: str
