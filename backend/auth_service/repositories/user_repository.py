"""
User DB repository — async SQLAlchemy 2.0 ORM.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog
from sqlalchemy import Boolean, DateTime, String, Text, select, update
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from auth_service.exceptions import UserAlreadyExistsError, UserNotFoundError

logger = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    """Users table — mirrors Keycloak user data for local fast lookups."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    keycloak_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    org_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    roles: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        username: str,
        email: str,
        hashed_password: str | None,
        first_name: str,
        last_name: str,
        org_id: UUID | None = None,
        roles: list[str] | None = None,
        keycloak_id: str | None = None,
    ) -> UserModel:
        # Check uniqueness
        existing = await self._session.execute(
            select(UserModel).where(
                (UserModel.username == username) | (UserModel.email == email)
            )
        )
        if existing.scalar_one_or_none():
            raise UserAlreadyExistsError(username)

        user = UserModel(
            username=username,
            email=email,
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            org_id=org_id,
            roles=roles or ["viewer"],
            keycloak_id=keycloak_id,
        )
        self._session.add(user)
        await self._session.flush()
        logger.info("user_created", username=username, user_id=str(user.id))
        return user

    async def get_by_id(self, user_id: UUID) -> UserModel:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise UserNotFoundError(str(user_id))
        return user

    async def get_by_username(self, username: str) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_keycloak_id(self, keycloak_id: str) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.keycloak_id == keycloak_id)
        )
        return result.scalar_one_or_none()

    async def update_keycloak_id(self, user_id: UUID, keycloak_id: str) -> None:
        await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(keycloak_id=keycloak_id, updated_at=datetime.now(timezone.utc))
        )

    async def deactivate(self, user_id: UUID) -> None:
        await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(is_active=False, updated_at=datetime.now(timezone.utc))
        )
