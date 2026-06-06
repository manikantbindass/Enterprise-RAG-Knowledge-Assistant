"""
Search route handlers for the Vector Service.
Handles query embedding generation, search dispatch, and reranking.
"""

from __future__ import annotations

import time
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sentence_transformers import SentenceTransformer

from vector_service.dependencies import get_search_service, get_reranker_dep, verify_internal_key
from vector_service.models.schemas import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchType,
    SimilarChunkRequest,
)
from vector_service.services.query_processor import QueryProcessor
from vector_service.services.reranker import CrossEncoderReranker
from vector_service.services.vector_search import VectorSearchService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

# Embedding model — loaded once at module import (lazy singleton pattern)
_embedding_model: SentenceTransformer | None = None
_query_processor = QueryProcessor()


def _get_embedding_model() -> SentenceTransformer:
    """Lazy-load embedding model for query encoding."""
    global _embedding_model
    if _embedding_model is None:
        logger.info("embedding_model_loading")
        _embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        logger.info("embedding_model_loaded")
    return _embedding_model


def _embed_query(query: str) -> list[float]:
    """Encode query text to embedding vector."""
    model = _get_embedding_model()
    vector = model.encode(query, normalize_embeddings=True)
    return vector.tolist()


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=SearchResponse,
    summary="Hybrid / semantic / keyword search",
    dependencies=[Depends(verify_internal_key)],
)
async def search(
    body: SearchRequest,
    svc: VectorSearchService = Depends(get_search_service),
    reranker: CrossEncoderReranker = Depends(get_reranker_dep),
) -> SearchResponse:
    """
    Main search endpoint.

    - Preprocesses query (normalize, expand abbreviations).
    - Encodes query to embedding vector for semantic/hybrid modes.
    - Dispatches to semantic / keyword / hybrid search.
    - Optionally applies cross-encoder reranking.
    """
    t0 = time.perf_counter()

    processed = _query_processor.process(body.query)
    search_query = processed.expanded  # Use abbreviation-expanded query

    log = logger.bind(
        org_id=str(body.org_id),
        search_type=body.search_type,
        top_k=body.top_k,
        rerank=body.rerank,
    )

    # Generate embedding for semantic / hybrid modes
    query_embedding: list[float] = []
    if body.search_type in (SearchType.SEMANTIC, SearchType.HYBRID):
        query_embedding = _embed_query(search_query)

    # Dispatch search
    if body.search_type == SearchType.SEMANTIC:
        results = await svc.semantic_search(
            query_embedding=query_embedding,
            org_id=body.org_id,
            filters=body.filters,
            top_k=body.top_k * 3 if body.rerank else body.top_k,
        )
    elif body.search_type == SearchType.KEYWORD:
        results = await svc.keyword_search(
            query=search_query,
            org_id=body.org_id,
            filters=body.filters,
            top_k=body.top_k * 3 if body.rerank else body.top_k,
        )
    else:  # HYBRID
        results = await svc.hybrid_search(
            query=search_query,
            query_embedding=query_embedding,
            org_id=body.org_id,
            filters=body.filters,
            top_k=body.top_k * 3 if body.rerank else body.top_k,
            alpha=body.alpha,
        )

    # Rerank if requested and model loaded
    reranked = False
    if body.rerank and reranker.is_loaded and results:
        results = await reranker.rerank(
            query=body.query,
            results=results,
            top_k=body.top_k,
        )
        reranked = True
    else:
        results = results[: body.top_k]

    latency = (time.perf_counter() - t0) * 1000
    log.info("search_completed", results=len(results), latency_ms=round(latency, 2))

    return SearchResponse(
        results=results,
        total=len(results),
        query=body.query,
        search_type=body.search_type,
        latency_ms=round(latency, 2),
        reranked=reranked,
    )


@router.post(
    "/similar",
    response_model=SearchResponse,
    summary="Find similar chunks to a given chunk_id",
    dependencies=[Depends(verify_internal_key)],
)
async def find_similar(
    body: SimilarChunkRequest,
    svc: VectorSearchService = Depends(get_search_service),
    reranker: CrossEncoderReranker = Depends(get_reranker_dep),
) -> SearchResponse:
    """
    Find chunks semantically similar to a known chunk.
    Useful for 'more like this' features in the UI.
    """
    t0 = time.perf_counter()

    results = await svc.find_similar(
        chunk_id=body.chunk_id,
        org_id=body.org_id,
        filters=body.filters,
        top_k=body.top_k,
    )

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chunk {body.chunk_id} not found or has no embedding",
        )

    latency = (time.perf_counter() - t0) * 1000
    return SearchResponse(
        results=results,
        total=len(results),
        query=f"similar:chunk_id={body.chunk_id}",
        search_type=SearchType.SEMANTIC,
        latency_ms=round(latency, 2),
        reranked=False,
    )
