"""
FastAPI dependencies for the Vector Service.
Provides DB pool, search service, reranker, and auth guard.
"""

from __future__ import annotations

from typing import AsyncGenerator

import asyncpg
import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from vector_service.config import get_settings
from vector_service.repositories.vector_repository import VectorRepository
from vector_service.services.reranker import CrossEncoderReranker, get_reranker
from vector_service.services.vector_search import VectorSearchService

logger = structlog.get_logger(__name__)

_INTERNAL_KEY_HEADER = APIKeyHeader(name="X-Internal-Api-Key", auto_error=False)


async def verify_internal_key(
    key: str | None = Security(_INTERNAL_KEY_HEADER),
) -> None:
    """Validate that caller presents the correct inter-service API key."""
    settings = get_settings()
    if not key or key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid internal API key",
        )


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Pull asyncpg pool from app state (set in lifespan)."""
    pool: asyncpg.Pool | None = request.app.state.db_pool
    if pool is None:
        raise RuntimeError("DB pool not initialised")
    return pool


async def get_vector_repo(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> AsyncGenerator[VectorRepository, None]:
    """Yield VectorRepository bound to the request pool."""
    yield VectorRepository(pool)


async def get_search_service(
    repo: VectorRepository = Depends(get_vector_repo),
) -> VectorSearchService:
    """Yield VectorSearchService for route handlers."""
    return VectorSearchService(repo)


def get_reranker_dep() -> CrossEncoderReranker:
    """Provide the global reranker singleton."""
    return get_reranker()
