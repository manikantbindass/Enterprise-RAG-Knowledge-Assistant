"""
VectorSearchService — orchestrates semantic, keyword, and hybrid search.
Hybrid search uses Reciprocal Rank Fusion (RRF) to merge ranked lists.
"""

from __future__ import annotations

import time
from uuid import UUID

import structlog

from vector_service.config import get_settings
from vector_service.models.schemas import SearchFilters, SearchResult, SearchType
from vector_service.repositories.vector_repository import VectorRepository

logger = structlog.get_logger(__name__)

settings = get_settings()


class VectorSearchService:
    """
    Business logic for all search modes.
    Repository injected — no direct DB calls here.
    Embedding generation is the caller's responsibility (API gateway / ingestion
    service already stored embeddings; at query time we call the embedding model
    externally and pass the vector in).
    """

    def __init__(self, repo: VectorRepository) -> None:
        self._repo = repo

    # ── Public API ─────────────────────────────────────────────────────────

    async def semantic_search(
        self,
        query_embedding: list[float],
        org_id: UUID,
        filters: SearchFilters,
        top_k: int,
    ) -> list[SearchResult]:
        """Pure vector cosine-similarity search via pgvector."""
        t0 = time.perf_counter()
        results = await self._repo.semantic_search(
            query_embedding=query_embedding,
            org_id=org_id,
            filters=filters,
            top_k=top_k,
            ivfflat_probes=settings.ivfflat_probes,
        )
        logger.info(
            "semantic_search",
            org_id=str(org_id),
            top_k=top_k,
            results=len(results),
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
        return results

    async def keyword_search(
        self,
        query: str,
        org_id: UUID,
        filters: SearchFilters,
        top_k: int,
    ) -> list[SearchResult]:
        """Full-text BM25-style search using PostgreSQL ts_rank."""
        t0 = time.perf_counter()
        results = await self._repo.keyword_search(
            query=query,
            org_id=org_id,
            filters=filters,
            top_k=top_k,
            fts_config=settings.fts_language,
            normalization=settings.fts_normalization,
        )
        logger.info(
            "keyword_search",
            org_id=str(org_id),
            top_k=top_k,
            results=len(results),
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
        return results

    async def hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        org_id: UUID,
        filters: SearchFilters,
        top_k: int,
        alpha: float = 0.7,
    ) -> list[SearchResult]:
        """
        Hybrid search via Reciprocal Rank Fusion (RRF).

        alpha controls semantic weight:
          alpha=1.0 → pure semantic
          alpha=0.0 → pure keyword
          default 0.7 → semantic-heavy hybrid

        RRF formula: score(d) = Σ 1/(k + rank(d))
        where k=60 prevents high-rank docs from dominating.
        """
        t0 = time.perf_counter()

        # Fetch more candidates than needed — RRF will re-rank
        fetch_k = min(top_k * 3, settings.max_top_k)

        import asyncio

        sem_results, kw_results = await asyncio.gather(
            self._repo.semantic_search(
                query_embedding=query_embedding,
                org_id=org_id,
                filters=filters,
                top_k=fetch_k,
                ivfflat_probes=settings.ivfflat_probes,
            ),
            self._repo.keyword_search(
                query=query,
                org_id=org_id,
                filters=filters,
                top_k=fetch_k,
                fts_config=settings.fts_language,
                normalization=settings.fts_normalization,
            ),
        )

        fused = self._rrf_fuse(
            semantic_results=sem_results,
            keyword_results=kw_results,
            alpha=alpha,
            k=settings.rrf_k,
            top_k=top_k,
        )

        logger.info(
            "hybrid_search",
            org_id=str(org_id),
            alpha=alpha,
            sem_count=len(sem_results),
            kw_count=len(kw_results),
            fused_count=len(fused),
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
        return fused

    async def find_similar(
        self,
        chunk_id: UUID,
        org_id: UUID,
        filters: SearchFilters,
        top_k: int,
    ) -> list[SearchResult]:
        """Find chunks similar to a given chunk using its stored embedding."""
        embedding = await self._repo.get_chunk_embedding(chunk_id, org_id)
        if embedding is None:
            logger.warning("chunk_not_found_or_no_embedding", chunk_id=str(chunk_id))
            return []

        results = await self._repo.semantic_search(
            query_embedding=embedding,
            org_id=org_id,
            filters=filters,
            top_k=top_k + 1,  # +1 because the source chunk itself will appear
            ivfflat_probes=settings.ivfflat_probes,
        )
        # Exclude the source chunk from results
        return [r for r in results if r.chunk_id != chunk_id][:top_k]

    # ── RRF implementation ─────────────────────────────────────────────────

    @staticmethod
    def _rrf_fuse(
        semantic_results: list[SearchResult],
        keyword_results: list[SearchResult],
        alpha: float,
        k: int,
        top_k: int,
    ) -> list[SearchResult]:
        """
        Reciprocal Rank Fusion with alpha weighting.

        rrf_score = alpha * (1/(k+sem_rank)) + (1-alpha) * (1/(k+kw_rank))
        """
        scores: dict[UUID, float] = {}
        result_map: dict[UUID, SearchResult] = {}

        # Semantic ranked list
        for rank, result in enumerate(semantic_results, start=1):
            cid = result.chunk_id
            scores[cid] = scores.get(cid, 0.0) + alpha * (1.0 / (k + rank))
            result_map[cid] = result

        # Keyword ranked list
        for rank, result in enumerate(keyword_results, start=1):
            cid = result.chunk_id
            scores[cid] = scores.get(cid, 0.0) + (1.0 - alpha) * (1.0 / (k + rank))
            if cid not in result_map:
                result_map[cid] = result

        # Sort by fused RRF score descending
        sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

        fused: list[SearchResult] = []
        for cid in sorted_ids[:top_k]:
            original = result_map[cid]
            fused.append(original.model_copy(update={"score": round(scores[cid], 6)}))

        return fused
