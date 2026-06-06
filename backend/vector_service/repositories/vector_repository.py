"""
Raw pgvector + full-text search queries using asyncpg directly.
Using asyncpg instead of SQLAlchemy ORM for maximum query performance.
Row-level org isolation enforced via parameterized org_id on every query.
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from vector_service.models.schemas import SearchFilters, SearchResult

logger = structlog.get_logger(__name__)


def _build_filter_clause(
    filters: SearchFilters,
    param_offset: int,
) -> tuple[str, list[Any], int]:
    """
    Construct a WHERE fragment + parameter list from SearchFilters.

    Returns (sql_fragment, params, next_param_index).
    param_offset: current $N counter so we don't collide with preceding params.
    """
    clauses: list[str] = []
    params: list[Any] = []
    idx = param_offset

    if filters.department:
        idx += 1
        clauses.append(f"d.department = ${idx}")
        params.append(filters.department)

    if filters.tags:
        idx += 1
        clauses.append(f"c.tags && ${idx}::text[]")
        params.append(filters.tags)

    if filters.doc_ids:
        idx += 1
        clauses.append(f"c.document_id = ANY(${idx}::uuid[])")
        params.append([str(did) for did in filters.doc_ids])

    if filters.date_from:
        idx += 1
        clauses.append(f"d.created_at >= ${idx}")
        params.append(filters.date_from)

    if filters.date_to:
        idx += 1
        clauses.append(f"d.created_at <= ${idx}")
        params.append(filters.date_to)

    fragment = (" AND " + " AND ".join(clauses)) if clauses else ""
    return fragment, params, idx


class VectorRepository:
    """
    All raw SQL against pgvector + full-text.
    Pool injected at startup — no connection-per-request overhead.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── Semantic search ────────────────────────────────────────────────────

    async def semantic_search(
        self,
        query_embedding: list[float],
        org_id: UUID,
        filters: SearchFilters,
        top_k: int,
        ivfflat_probes: int = 10,
    ) -> list[SearchResult]:
        """
        cosine similarity via pgvector operator <=>.
        Lower distance = higher similarity; score = 1 - distance.
        """
        filter_sql, filter_params, last_idx = _build_filter_clause(filters, param_offset=3)

        sql = f"""
            SELECT
                c.id                AS chunk_id,
                c.document_id,
                c.content,
                (1 - (c.embedding <=> $1::vector))  AS score,
                c.metadata,
                c.page_number,
                d.filename          AS doc_filename,
                d.title             AS doc_title,
                d.created_at,
                d.department,
                c.tags
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.org_id = $2
              AND c.embedding IS NOT NULL
              {filter_sql}
            ORDER BY c.embedding <=> $1::vector
            LIMIT $3
        """

        t0 = time.perf_counter()
        async with self._pool.acquire() as conn:
            # Set ivfflat scan probes for this session
            await conn.execute(f"SET ivfflat.probes = {ivfflat_probes}")
            rows = await conn.fetch(
                sql,
                json.dumps(query_embedding),
                str(org_id),
                top_k,
                *filter_params,
            )

        elapsed = (time.perf_counter() - t0) * 1000
        logger.debug(
            "semantic_search_completed",
            org_id=str(org_id),
            results=len(rows),
            latency_ms=round(elapsed, 2),
        )
        return [_row_to_result(row) for row in rows]

    # ── Keyword / full-text search ─────────────────────────────────────────

    async def keyword_search(
        self,
        query: str,
        org_id: UUID,
        filters: SearchFilters,
        top_k: int,
        fts_config: str = "english",
        normalization: int = 2,
    ) -> list[SearchResult]:
        """
        PostgreSQL full-text search using ts_rank.
        ts_rank normalization=2 divides rank by document length.
        """
        filter_sql, filter_params, last_idx = _build_filter_clause(filters, param_offset=3)

        sql = f"""
            SELECT
                c.id                AS chunk_id,
                c.document_id,
                c.content,
                ts_rank(
                    c.fts_vector,
                    plainto_tsquery('{fts_config}', $1),
                    {normalization}
                )                   AS score,
                c.metadata,
                c.page_number,
                d.filename          AS doc_filename,
                d.title             AS doc_title,
                d.created_at,
                d.department,
                c.tags
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.org_id = $2
              AND c.fts_vector @@ plainto_tsquery('{fts_config}', $1)
              {filter_sql}
            ORDER BY score DESC
            LIMIT $3
        """

        t0 = time.perf_counter()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, query, str(org_id), top_k, *filter_params)

        elapsed = (time.perf_counter() - t0) * 1000
        logger.debug(
            "keyword_search_completed",
            org_id=str(org_id),
            results=len(rows),
            latency_ms=round(elapsed, 2),
        )
        return [_row_to_result(row) for row in rows]

    # ── Chunk by ID ────────────────────────────────────────────────────────

    async def get_chunk_embedding(self, chunk_id: UUID, org_id: UUID) -> list[float] | None:
        """Fetch embedding vector for a specific chunk (used by /search/similar)."""
        sql = """
            SELECT c.embedding::text
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = $1 AND d.org_id = $2
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, str(chunk_id), str(org_id))

        if row is None:
            return None
        # asyncpg returns vector as string "[0.1,0.2,...]"
        raw = row["embedding"]
        return json.loads(raw)

    # ── Health ─────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Check database connectivity."""
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            logger.exception("db_ping_failed")
            return False


# ── Helpers ────────────────────────────────────────────────────────────────


def _row_to_result(row: asyncpg.Record) -> SearchResult:
    """Convert raw asyncpg Record → SearchResult."""
    raw_meta = row["metadata"]
    metadata: dict = json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})

    tags = row["tags"] or []

    return SearchResult(
        chunk_id=UUID(row["chunk_id"]),
        document_id=UUID(str(row["document_id"])),
        content=row["content"],
        score=float(row["score"]),
        metadata=metadata,
        page_number=row["page_number"],
        doc_filename=row["doc_filename"],
        doc_title=row.get("doc_title"),
        created_at=row.get("created_at"),
        department=row.get("department"),
        tags=list(tags),
    )
