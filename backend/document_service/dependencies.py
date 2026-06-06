"""
FastAPI dependency injection for Document Service.

Provides: DB sessions, storage client, scanner, service instances.
"""

from __future__ import annotations

from typing import Annotated, AsyncGenerator

import structlog
from aio_pika.abc import AbstractRobustConnection
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from document_service.config import DocumentServiceConfig, get_config
from document_service.repositories.document_repository import DocumentRepository
from document_service.services.document_service import DocumentService, StorageClient
from document_service.services.virus_scanner import VirusScannerService

logger = structlog.get_logger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────


def get_settings() -> DocumentServiceConfig:
    """Inject config singleton."""
    return get_config()


ConfigDep = Annotated[DocumentServiceConfig, Depends(get_settings)]


# ── Database session ──────────────────────────────────────────────────────────


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a scoped async DB session.

    Session is committed on success, rolled back on exception, always closed.
    The async_sessionmaker is stored on app.state during lifespan startup.
    """
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


# ── Infrastructure singletons from app.state ──────────────────────────────────


def get_storage_client(request: Request) -> StorageClient:
    """Inject storage client from app state."""
    return request.app.state.storage_client


def get_virus_scanner(request: Request) -> VirusScannerService:
    """Inject virus scanner from app state."""
    return request.app.state.virus_scanner


def get_rabbitmq_connection(request: Request) -> AbstractRobustConnection | None:
    """Inject RabbitMQ connection from app state (may be None if degraded)."""
    return getattr(request.app.state, "rabbitmq_connection", None)


StorageClientDep = Annotated[StorageClient, Depends(get_storage_client)]
VirusScannerDep = Annotated[VirusScannerService, Depends(get_virus_scanner)]
RabbitMQDep = Annotated[AbstractRobustConnection | None, Depends(get_rabbitmq_connection)]


# ── Repository ────────────────────────────────────────────────────────────────


def get_document_repository(session: DbSessionDep) -> DocumentRepository:
    """Create repository scoped to current DB session."""
    return DocumentRepository(session=session)


RepoDep = Annotated[DocumentRepository, Depends(get_document_repository)]


# ── Service ───────────────────────────────────────────────────────────────────


def get_document_service(
    repo: RepoDep,
    storage: StorageClientDep,
    scanner: VirusScannerDep,
    config: ConfigDep,
    rmq: RabbitMQDep,
) -> DocumentService:
    """Build DocumentService with all dependencies injected."""
    return DocumentService(
        repo=repo,
        storage=storage,
        virus_scanner=scanner,
        config=config,
        rabbitmq_connection=rmq,
    )


ServiceDep = Annotated[DocumentService, Depends(get_document_service)]
