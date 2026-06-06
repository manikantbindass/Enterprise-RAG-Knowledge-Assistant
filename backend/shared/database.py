"""
Async SQLAlchemy database setup for Enterprise RAG Knowledge Assistant.

Provides:
- AsyncEngine with connection pool tuned for production
- async_sessionmaker for session factory
- Base declarative base
- get_db() FastAPI dependency
- set_tenant_context() for PostgreSQL RLS
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool

if TYPE_CHECKING:
    from shared.config import BaseConfig

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Declarative base — all models import from here
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base.

    All ORM models must inherit from this class. Supports type-annotated
    mapping style (SQLAlchemy 2.0).
    """

    pass


# ---------------------------------------------------------------------------
# Module-level singletons (initialized in create_database_engine)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_database_engine(config: "BaseConfig") -> AsyncEngine:
    """
    Create and configure the async SQLAlchemy engine.

    Called once at application startup via lifespan. Stores engine
    in module-level singleton for get_db() to access.

    Args:
        config: Service configuration containing DATABASE_URL and pool settings.

    Returns:
        Configured AsyncEngine instance.
    """
    global _engine, _session_factory

    engine = create_async_engine(
        config.DATABASE_URL,
        echo=config.DATABASE_ECHO,
        pool_size=config.DATABASE_POOL_SIZE,
        max_overflow=config.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=config.DATABASE_POOL_PRE_PING,
        pool_recycle=config.DATABASE_POOL_RECYCLE,
        poolclass=AsyncAdaptedQueuePool,
        connect_args={
            "server_settings": {
                "application_name": config.SERVICE_NAME,
                "jit": "off",  # disable JIT for OLTP workloads
            },
            "command_timeout": 60,
        },
    )

    _engine = engine
    _session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    logger.info(
        "database_engine_created",
        pool_size=config.DATABASE_POOL_SIZE,
        max_overflow=config.DATABASE_MAX_OVERFLOW,
        url=_redact_url(config.DATABASE_URL),
    )

    return engine


def get_engine() -> AsyncEngine:
    """Return the module-level engine. Raises if not initialized."""
    if _engine is None:
        raise RuntimeError(
            "Database engine not initialized. Call create_database_engine() during app startup."
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level session factory. Raises if not initialized."""
    if _session_factory is None:
        raise RuntimeError(
            "Session factory not initialized. Call create_database_engine() during app startup."
        )
    return _session_factory


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yields an async database session.

    Automatically rolls back on exception, always closes session.

    Usage:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Tenant context (Row-Level Security)
# ---------------------------------------------------------------------------


async def set_tenant_context(session: AsyncSession, org_id: str) -> None:
    """
    Set PostgreSQL session variable for Row-Level Security.

    Must be called at the start of each request after authentication.
    PostgreSQL RLS policies read app.current_org_id to filter rows.

    Uses SET LOCAL so the variable is scoped to the current transaction
    and automatically cleared when the transaction ends.

    Args:
        session: Active async SQLAlchemy session.
        org_id: Organization UUID string to set as tenant context.
    """
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)},
    )
    logger.debug("tenant_context_set", org_id=org_id)


async def clear_tenant_context(session: AsyncSession) -> None:
    """
    Clear tenant context — sets org_id to empty string.

    Call this for internal/admin operations that bypass RLS.
    """
    await session.execute(
        text("SELECT set_config('app.current_org_id', '', true)"),
    )


# ---------------------------------------------------------------------------
# Database lifecycle helpers
# ---------------------------------------------------------------------------


async def create_all_tables(engine: AsyncEngine) -> None:
    """
    Create all tables defined in models. Use only in tests / local dev.

    Production: use Alembic migrations.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("all_tables_created")


async def drop_all_tables(engine: AsyncEngine) -> None:
    """
    Drop all tables. DESTRUCTIVE — use only in tests.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("all_tables_dropped")


@contextlib.asynccontextmanager
async def get_db_context(config: "BaseConfig") -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for getting a DB session outside of FastAPI request context.

    Useful in CLI scripts, background workers, and tests.

    Usage:
        async with get_db_context(config) as session:
            result = await session.execute(select(User))
    """
    if _session_factory is None:
        create_database_engine(config)

    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _redact_url(url: str) -> str:
    """Remove password from DSN for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username}:***@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return url
