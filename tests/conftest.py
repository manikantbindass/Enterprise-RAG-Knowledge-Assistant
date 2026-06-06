"""
Global pytest fixtures for Enterprise RAG Knowledge Assistant test suite.

Provides:
- async_client: httpx.AsyncClient against the FastAPI app
- db_session: async DB session with per-test transaction rollback
- test_org / test_user / test_document: seeded ORM objects
- auth_headers: Bearer token dict for the test admin user
- redis_client: fake/real Redis client for testing
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Event loop — one loop per test session (required for asyncio mode=auto)
# ---------------------------------------------------------------------------

# Use asyncio_mode = auto from pytest.ini — no explicit event_loop fixture needed
# in pytest-asyncio >= 0.21. The fixture below is kept for legacy compatibility.


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/rag_test",
)


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """
    Session-scoped async engine pointing at the test database.

    Creates all tables once per session and drops them at teardown.
    """
    from shared.database import Base

    # Import all models so metadata is populated
    import shared.models.audit  # noqa: F401
    import shared.models.conversation  # noqa: F401
    import shared.models.document  # noqa: F401
    import shared.models.organization  # noqa: F401
    import shared.models.user  # noqa: F401

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Function-scoped DB session with savepoint rollback.

    Each test runs inside a nested transaction (SAVEPOINT) that is
    rolled back at the end — database stays clean between tests.
    """
    connection: AsyncConnection = await db_engine.connect()
    await connection.begin()

    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    session = session_factory()

    # Start nested SAVEPOINT so individual test rollback does not affect outer tx
    await session.begin_nested()

    yield session

    await session.rollback()
    await session.close()
    await connection.rollback()
    await connection.close()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def test_org(db_session: AsyncSession):
    """Seeded Organization fixture."""
    from shared.models.organization import Organization

    org = Organization(
        id=uuid.uuid4(),
        name="Test Corp",
        slug=f"test-corp-{uuid.uuid4().hex[:8]}",
        plan="enterprise",
        is_active=True,
        max_documents=10_000,
        max_users=100,
        max_storage_gb=100,
        settings={},
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture()
async def test_user(db_session: AsyncSession, test_org):
    """Seeded admin User fixture."""
    import bcrypt

    from shared.models.user import User, UserRole

    hashed = bcrypt.hashpw(b"TestPass123!", bcrypt.gensalt()).decode()

    user = User(
        id=uuid.uuid4(),
        org_id=test_org.id,
        email=f"admin-{uuid.uuid4().hex[:8]}@testcorp.com",
        full_name="Test Admin",
        hashed_password=hashed,
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
        api_key_hash=hashlib.sha256(b"test-api-key-secret").hexdigest(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture()
async def test_document(db_session: AsyncSession, test_org, test_user):
    """Seeded Document fixture in INDEXED status."""
    from shared.models.document import Document, DocumentStatus

    doc = Document(
        id=uuid.uuid4(),
        org_id=test_org.id,
        title="Test Policy Document",
        filename="policy.pdf",
        content_type="application/pdf",
        file_size_bytes=102_400,
        storage_path=f"documents/{test_org.id}/policy.pdf",
        storage_bucket="documents",
        status=DocumentStatus.INDEXED,
        page_count=10,
        chunk_count=42,
        language="en",
        tags=["policy", "hr"],
        doc_metadata={"author": "HR Team", "year": 2024},
        uploaded_by=test_user.id,
        indexed_at=datetime.now(UTC),
        is_deleted=False,
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_headers(test_user) -> dict[str, str]:
    """
    Bearer token headers for the test admin user.

    Generates a real JWT signed with the test secret.
    """
    import jose.jwt as jwt

    payload = {
        "sub": str(test_user.id),
        "email": test_user.email,
        "org_id": str(test_user.org_id),
        "role": test_user.role.value,
        "iss": "rag-knowledge-assistant",
        "aud": "rag-api",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(datetime.now(UTC).timestamp()) + 3600,
    }
    token = jwt.encode(payload, "test-jwt-secret-key-minimum-32-chars!", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def async_client(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    httpx.AsyncClient wired to the API Gateway FastAPI app.

    Overrides the get_db dependency to inject the test DB session.
    """
    from api_gateway.main import app
    from shared.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=30.0,
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Redis fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def redis_client():
    """
    Fake Redis client for testing.

    Uses fakeredis if available, otherwise returns an AsyncMock.
    """
    try:
        import fakeredis.aioredis as fakeredis

        return fakeredis.FakeRedis(decode_responses=True)
    except ImportError:
        # Fallback: mock with common Redis interface
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=0)
        mock.incr = AsyncMock(return_value=1)
        mock.expire = AsyncMock(return_value=True)
        mock.ttl = AsyncMock(return_value=-1)
        mock.lpush = AsyncMock(return_value=1)
        mock.lrange = AsyncMock(return_value=[])
        mock.hset = AsyncMock(return_value=1)
        mock.hget = AsyncMock(return_value=None)
        mock.hgetall = AsyncMock(return_value={})
        mock.ping = AsyncMock(return_value=True)
        return mock
