"""
Pydantic v2 schemas for the Vector Service.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SearchType(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class SearchFilters(BaseModel):
    """Optional filters applied to search queries."""

    department: str | None = Field(None, max_length=128)
    tags: list[str] | None = Field(None, max_items=20)
    doc_ids: list[UUID] | None = Field(None, max_items=100)
    date_from: datetime | None = None
    date_to: datetime | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def _dedup_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return list(dict.fromkeys(v))  # preserve order, deduplicate


class SearchRequest(BaseModel):
    """Body for POST /search."""

    query: str = Field(..., min_length=1, max_length=4096)
    org_id: UUID
    top_k: int = Field(default=10, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    search_type: SearchType = SearchType.HYBRID
    alpha: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for semantic vs keyword (1.0 = pure semantic)",
    )
    rerank: bool = Field(default=True, description="Apply cross-encoder reranking")


class SimilarChunkRequest(BaseModel):
    """Body for POST /search/similar."""

    chunk_id: UUID
    org_id: UUID
    top_k: int = Field(default=10, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchResult(BaseModel):
    """Single result returned from search."""

    chunk_id: UUID
    document_id: UUID
    content: str
    score: float = Field(..., ge=0.0, le=1.0)
    rerank_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    page_number: int | None = None
    doc_filename: str
    doc_title: str | None = None
    created_at: datetime | None = None
    department: str | None = None
    tags: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Response envelope for search endpoints."""

    results: list[SearchResult]
    total: int
    query: str
    search_type: SearchType
    latency_ms: float
    reranked: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str
    db_connected: bool
    reranker_loaded: bool
