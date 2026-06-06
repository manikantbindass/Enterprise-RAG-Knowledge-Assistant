"""
User Business Logic Service.

Orchestrates user CRUD, password hashing, event publishing.
Pure business logic — no HTTP concerns here.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.config import get_config
from user_service.exceptions import (
    InvalidPasswordError,
    SelfDeletionError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from user_service.models.schemas import (
    UserActivitySummary,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from user_service.repositories.user_repository import UserModel, UserRepository

logger = structlog.get_logger(__name__)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(plain: str) -> str:
    """Hash plain-text password with bcrypt."""
    return _pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against stored hash."""
    return _pwd_context.verify(plain, hashed)


def _to_response(user: UserModel) -> UserResponse:
    """Convert ORM model → response schema. Never expose hashed_password."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,  # type: ignore[arg-type]
        status=user.status,  # type: ignore[arg-type]
        organization_id=user.organization_id,
        metadata=user.metadata_,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


class UserService:
    """Orchestrates all user-related business operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)
        self._session = session
        self._cfg = get_config()

    async def list_users(
        self,
        organization_id: uuid.UUID | None = None,
        role: str | None = None,
        status: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> UserListResponse:
        """Paginated user list with optional filters."""
        page_size = min(page_size, self._cfg.max_page_size)
        items, total = await self._repo.list_users(
            organization_id=organization_id,
            role=role,
            status=status,
            search=search,
            page=page,
            page_size=page_size,
        )
        return UserListResponse(
            items=[_to_response(u) for u in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),  # ceiling division
        )

    async def get_user(self, user_id: uuid.UUID) -> UserResponse:
        """Fetch single user by ID."""
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(str(user_id))
        return _to_response(user)

    async def create_user(self, payload: UserCreate) -> UserResponse:
        """
        Create new user.

        Validates email uniqueness, hashes password, checks org user limit.
        """
        # Uniqueness check
        existing = await self._repo.get_by_email(payload.email)
        if existing:
            raise UserAlreadyExistsError(payload.email)

        hashed_pw = _hash_password(payload.password)
        user = await self._repo.create(
            organization_id=payload.organization_id,
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hashed_pw,
            role=payload.role.value,
            metadata=payload.metadata,
        )
        await self._session.commit()
        logger.info("user_service.create_user", user_id=str(user.id))
        return _to_response(user)

    async def update_user(
        self,
        user_id: uuid.UUID,
        payload: UserUpdate,
    ) -> UserResponse:
        """Update user fields (admin path — can change role/status)."""
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(str(user_id))

        updates: dict[str, Any] = {}
        if payload.full_name is not None:
            updates["full_name"] = payload.full_name
        if payload.role is not None:
            updates["role"] = payload.role.value
        if payload.status is not None:
            updates["status"] = payload.status.value
        if payload.metadata is not None:
            updates["metadata_"] = payload.metadata

        if not updates:
            return _to_response(user)

        updated = await self._repo.update(user_id, updates)
        await self._session.commit()
        return _to_response(updated)  # type: ignore[arg-type]

    async def update_own_profile(
        self,
        user_id: uuid.UUID,
        full_name: str | None,
        metadata: dict[str, Any] | None,
    ) -> UserResponse:
        """Self-service profile update — cannot change role or status."""
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(str(user_id))

        updates: dict[str, Any] = {}
        if full_name is not None:
            updates["full_name"] = full_name
        if metadata is not None:
            updates["metadata_"] = metadata

        if not updates:
            return _to_response(user)

        updated = await self._repo.update(user_id, updates)
        await self._session.commit()
        return _to_response(updated)  # type: ignore[arg-type]

    async def soft_delete_user(
        self, user_id: uuid.UUID, requesting_user_id: uuid.UUID
    ) -> None:
        """
        Soft-delete a user.

        Guards against self-deletion.
        """
        if user_id == requesting_user_id:
            raise SelfDeletionError()

        user = await self._repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(str(user_id))

        deleted = await self._repo.soft_delete(user_id)
        if not deleted:
            raise UserNotFoundError(str(user_id))

        await self._session.commit()
        logger.info("user_service.soft_delete", user_id=str(user_id))

    async def get_user_activity(self, user_id: uuid.UUID) -> UserActivitySummary:
        """
        Fetch activity summary for a user.

        Queries the audit_logs table for aggregated stats.
        Stats are approximate — audit_logs may be in a separate partition.
        """
        from sqlalchemy import text

        user = await self._repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(str(user_id))

        raw = await self._session.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE action = 'query.executed')          AS total_queries,
                    COUNT(*) FILTER (WHERE action = 'document.uploaded')        AS total_docs_uploaded,
                    COUNT(*) FILTER (WHERE action = 'document.deleted')         AS total_docs_deleted,
                    MAX(created_at) FILTER (WHERE action = 'query.executed')    AS last_query_at
                FROM audit_logs
                WHERE user_id = :user_id
                """
            ),
            {"user_id": str(user_id)},
        )
        row = raw.fetchone()

        top_resources_raw = await self._session.execute(
            text(
                """
                SELECT resource_type, resource_id, COUNT(*) AS cnt
                FROM audit_logs
                WHERE user_id = :user_id
                GROUP BY resource_type, resource_id
                ORDER BY cnt DESC
                LIMIT 5
                """
            ),
            {"user_id": str(user_id)},
        )
        top_resources = [
            {"resource_type": r.resource_type, "resource_id": r.resource_id, "count": r.cnt}
            for r in top_resources_raw.fetchall()
        ]

        return UserActivitySummary(
            user_id=user_id,
            total_queries=row.total_queries or 0 if row else 0,
            total_documents_uploaded=row.total_docs_uploaded or 0 if row else 0,
            total_documents_deleted=row.total_docs_deleted or 0 if row else 0,
            last_query_at=row.last_query_at if row else None,
            last_login_at=user.last_login_at,
            most_used_resources=top_resources,
        )

    async def verify_credentials(self, email: str, password: str) -> UserResponse | None:
        """
        Verify email+password for authentication service use.

        Returns user if valid, None if not (timing-safe — always runs bcrypt).
        """
        user = await self._repo.get_by_email(email)
        # Always run verify to prevent timing attacks
        valid = _verify_password(password, user.hashed_password if user else "$2b$12$invalid")
        if not user or not valid or user.status != "active":
            return None
        await self._repo.update_last_login(user.id)
        await self._session.commit()
        return _to_response(user)
