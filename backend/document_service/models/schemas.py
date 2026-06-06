"""
Pydantic v2 schemas for the Document Service.

All request/response models with full validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────


class DocumentStatus(str, Enum):
    """Document lifecycle states."""

    PENDING = "pending"
    SCANNING = "scanning"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class StorageBackend(str, Enum):
    """Storage backend types."""

    MINIO = "minio"
    S3 = "s3"


# ── Request Models ─────────────────────────────────────────────────────────────


class DocumentCreate(BaseModel):
    """Metadata submitted alongside file upload."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(
        default=None,
        max_length=512,
        description="Human-readable title; defaults to filename if omitted",
    )
    description: str | None = Field(default=None, max_length=4096)
    department: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_url: str | None = Field(default=None, max_length=2048)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def deduplicate_tags(cls, v: list[str]) -> list[str]:
        """Remove duplicate tags, preserve order."""
        seen: set[str] = set()
        return [tag.strip().lower() for tag in v if tag.strip() and tag.strip().lower() not in seen and not seen.add(tag.strip().lower())]  # type: ignore[func-returns-value]


class DocumentListFilter(BaseModel):
    """Query params for paginated document listing."""

    model_config = ConfigDict(str_strip_whitespace=True)

    status: DocumentStatus | None = None
    department: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = Field(default=None, max_length=256)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_date_range(self) -> "DocumentListFilter":
        """Ensure date_from ≤ date_to when both provided."""
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before date_to")
        return self


# ── Response Models ────────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    """Full document representation returned by API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    department: str | None
    tags: list[str]
    source_url: str | None
    storage_key: str
    storage_backend: str
    chunk_count: int = 0
    page_count: int | None = None
    word_count: int | None = None
    error_message: str | None = None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None = None


class DocumentSummary(BaseModel):
    """Lightweight document representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    department: str | None
    tags: list[str]
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Paginated document list response."""

    items: list[DocumentSummary]
    total: int
    page: int
    page_size: int
    pages: int

    @model_validator(mode="after")
    def compute_pages(self) -> "DocumentListResponse":
        """Calculate total pages from total + page_size."""
        if self.page_size > 0:
            import math
            object.__setattr__(self, "pages", math.ceil(self.total / self.page_size))
        return self


class DocumentUploadResponse(BaseModel):
    """Response returned immediately after successful upload."""

    id: uuid.UUID
    title: str
    filename: str
    status: DocumentStatus
    storage_key: str
    message: str = "Document uploaded successfully. Processing queued."


class DocumentChunkResponse(BaseModel):
    """Single document chunk representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    page_number: int | None
    start_char: int | None
    end_char: int | None
    token_count: int | None
    metadata: dict[str, Any]
    created_at: datetime


class DocumentChunkListResponse(BaseModel):
    """Paginated chunk list."""

    items: list[DocumentChunkResponse]
    total: int
    page: int
    page_size: int


class PresignedUrlResponse(BaseModel):
    """Presigned download URL response."""

    document_id: uuid.UUID
    url: str
    expires_in_seconds: int
    filename: str


class DocumentStatusResponse(BaseModel):
    """Lightweight status check response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: DocumentStatus
    error_message: str | None
    chunk_count: int
    updated_at: datetime


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error: str
    detail: str | None = None
    request_id: str | None = None
