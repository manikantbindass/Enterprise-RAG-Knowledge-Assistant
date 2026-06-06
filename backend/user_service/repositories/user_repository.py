"""
User Repository — Database operations for users.

All queries use SQLAlchemy 2.0 async ORM. No raw SQL except for
performance-critical bulk operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.shared.database import Base  # noqa: F401 — ensure model registered

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# ORM Model (inline — shared DB, each service owns its queries)
# ---------------------------------------------------------------------------

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    """ORM model for the users table."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="viewer")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_users_org_role", "organization_id", "role"),
        Index("ix_users_org_status", "organization_id", "status"),
    )


class UserRepository:
    """All database operations for users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> UserModel | None:
        """Fetch user by primary key, excluding soft-deleted."""
        stmt = select(UserModel).where(
            UserModel.id == user_id,
            UserModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserModel | None:
        """Fetch user by email (case-insensitive), excluding soft-deleted."""
        stmt = select(UserModel).where(
            func.lower(UserModel.email) == email.lower(),
            UserModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        organization_id: uuid.UUID | None = None,
        role: str | None = None,
        status: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[UserModel], int]:
        """
        Paginated, filterable user list.

        Returns (items, total_count).
        """
        conditions = [UserModel.deleted_at.is_(None)]

        if organization_id:
            conditions.append(UserModel.organization_id == organization_id)
        if role:
            conditions.append(UserModel.role == role)
        if status:
            conditions.append(UserModel.status == status)
        if search:
            like = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(UserModel.email).like(like),
                    func.lower(UserModel.full_name).like(like),
                )
            )

        where_clause = and_(*conditions)

        # Total count
        count_stmt = select(func.count(UserModel.id)).where(where_clause)
        total: int = (await self._session.execute(count_stmt)).scalar_one()

        # Paginated fetch
        offset = (page - 1) * page_size
        stmt = (
            select(UserModel)
            .where(where_clause)
            .order_by(UserModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all(), total  # type: ignore[return-value]

    async def create(
        self,
        organization_id: uuid.UUID,
        email: str,
        full_name: str,
        hashed_password: str,
        role: str,
        metadata: dict[str, Any],
    ) -> UserModel:
        """Insert new user row."""
        user = UserModel(
            organization_id=organization_id,
            email=email.lower(),
            full_name=full_name,
            hashed_password=hashed_password,
            role=role,
            status="active",
            metadata_=metadata,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        logger.info("user.created", user_id=str(user.id), email=email)
        return user

    async def update(
        self,
        user_id: uuid.UUID,
        updates: dict[str, Any],
    ) -> UserModel | None:
        """Partial update user. Returns updated model or None if not found."""
        updates["updated_at"] = datetime.now(timezone.utc)
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
            .values(**updates)
            .returning(UserModel)
        )
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            logger.info("user.updated", user_id=str(user_id), fields=list(updates.keys()))
        return user

    async def soft_delete(self, user_id: uuid.UUID) -> bool:
        """Mark user as deleted without removing row."""
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
            .values(
                deleted_at=datetime.now(timezone.utc),
                status="inactive",
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = await self._session.execute(stmt)
        deleted = result.rowcount > 0
        if deleted:
            logger.info("user.soft_deleted", user_id=str(user_id))
        return deleted

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        """Stamp last_login_at for the user."""
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )
        await self._session.execute(stmt)

    async def count_by_org(self, organization_id: uuid.UUID) -> int:
        """Count active users in an org."""
        stmt = select(func.count(UserModel.id)).where(
            UserModel.organization_id == organization_id,
            UserModel.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one()
