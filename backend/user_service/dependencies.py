"""
User Service — FastAPI Dependencies.

Injectable dependencies for DB sessions, current user, role checks.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from user_service.config import get_config
from user_service.models.schemas import UserRole

logger = structlog.get_logger(__name__)
_cfg = get_config()

# ── Database ──────────────────────────────────────────────────────────────────

_engine = create_async_engine(
    _cfg.database_url,
    pool_size=_cfg.db_pool_size,
    max_overflow=_cfg.db_max_overflow,
    pool_timeout=_cfg.db_pool_timeout,
    echo=_cfg.db_echo,
    pool_pre_ping=True,
)

_async_session_factory = async_sessionmaker(
    _engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """Yield async DB session, closed after request."""
    async with _async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ── Auth / Current User ───────────────────────────────────────────────────────

class CurrentUser:
    """Minimal user context extracted from JWT token."""

    def __init__(
        self,
        user_id: uuid.UUID,
        email: str,
        role: UserRole,
        organization_id: uuid.UUID,
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.role = role
        self.organization_id = organization_id

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """
    Extract and validate JWT from Authorization header.

    Raises 401 on missing/invalid token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token,
            _cfg.jwt_secret_key,
            algorithms=[_cfg.jwt_algorithm],
            audience=_cfg.jwt_audience,
            issuer=_cfg.jwt_issuer,
        )
    except JWTError as exc:
        logger.warning("jwt.invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        return CurrentUser(
            user_id=uuid.UUID(payload["sub"]),
            email=payload["email"],
            role=UserRole(payload["role"]),
            organization_id=uuid.UUID(payload["org_id"]),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload malformed",
        ) from exc


def require_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Dependency that enforces admin or super_admin role."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


def require_super_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Dependency that enforces super_admin role."""
    if not current_user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-admin role required",
        )
    return current_user
