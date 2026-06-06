"""
Search routes — proxied to search-service.

POST   /api/v1/search          semantic + keyword hybrid search
GET    /api/v1/search/suggest  autocomplete / query suggestions
"""

from __future__ import annotations

from typing import Any, Literal

import structlog
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from dependencies import (
    ActiveUserDep,
    RequestIdDep,
    SearchProxyDep,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SearchFilters(BaseModel):
    """Optional filters to narrow search scope."""

    department: str | None = None
    tags: list[str] | None = None
    doc_ids: list[str] | None = None
    org_id: str | None = None
    date_from: str | None = Field(None, description="ISO-8601 date, e.g. 2024-01-01")
    date_to: str | None = Field(None, description="ISO-8601 date")
    content_types: list[str] | None = None


class SearchRequest(BaseModel):
    """Semantic / hybrid search request payload."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language question or keyword query",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return",
    )
    search_type: Literal["semantic", "keyword", "hybrid"] = Field(
        default="hybrid",
        description="Search strategy to apply",
    )
    filters: SearchFilters | None = None
    include_content: bool = Field(
        default=True,
        description="Whether to include full chunk text in results",
    )
    rerank: bool = Field(
        default=True,
        description="Apply cross-encoder re-ranking to results",
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold",
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SearchResultItem(BaseModel):
    """A single document chunk returned from search."""

    chunk_id: str
    doc_id: str
    filename: str
    content: str | None
    score: float = Field(description="Similarity / relevance score 0–1")
    rerank_score: float | None = None
    department: str | None
    tags: list[str]
    page_number: int | None
    chunk_index: int
    metadata: dict[str, Any] | None


class SearchResponse(BaseModel):
    """Search results with metadata."""

    query: str
    results: list[SearchResultItem]
    total_found: int
    search_type: str
    took_ms: float
    filters_applied: dict[str, Any] | None


class SuggestResponse(BaseModel):
    """Query auto-complete suggestions."""

    query: str
    suggestions: list[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=SearchResponse,
    summary="Semantic / hybrid search over document corpus",
)
async def search(
    payload: SearchRequest,
    proxy: SearchProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> SearchResponse:
    """
    Perform a hybrid semantic + keyword search over the document corpus.

    Automatically scopes results to the user's organization unless the user
    is an admin (who can search across all orgs, or specify org_id in filters).

    Steps performed by search-service:
    1. Query embedding generation
    2. Vector similarity search (ANN)
    3. Optional BM25 keyword search
    4. Score fusion
    5. Optional cross-encoder re-ranking
    """
    log = logger.bind(
        request_id=request_id,
        user_id=current_user.user_id,
        search_type=payload.search_type,
        top_k=payload.top_k,
    )
    log.info("search_request", query_len=len(payload.query))

    # Auto-inject org scope for non-admins
    body = payload.model_dump(exclude_none=True)
    if current_user.role != "admin":
        filters = body.setdefault("filters", {})
        if not filters.get("org_id"):
            filters["org_id"] = current_user.org_id

    response = await proxy.request(
        "POST",
        "/search",
        json=body,
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    data = response.json()
    log.info("search_complete", total_found=data.get("total_found"))
    return SearchResponse(**data)


@router.get(
    "/suggest",
    response_model=SuggestResponse,
    summary="Get query auto-complete suggestions",
)
async def suggest(
    proxy: SearchProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
    q: str = Query(..., min_length=1, max_length=200, description="Partial query string"),
    limit: int = Query(default=5, ge=1, le=20),
) -> SuggestResponse:
    """
    Return query completion suggestions based on past queries and document titles.

    Used to power front-end autocomplete in the search bar.
    """
    params: dict[str, Any] = {
        "q": q,
        "limit": limit,
    }
    if current_user.role != "admin" and current_user.org_id:
        params["org_id"] = current_user.org_id

    response = await proxy.request(
        "GET",
        "/search/suggest",
        authorization=f"Bearer {current_user.token}",
        params=params,
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return SuggestResponse(**response.json())
