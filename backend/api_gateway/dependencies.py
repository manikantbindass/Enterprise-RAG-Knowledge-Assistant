"""
FastAPI dependencies for API Gateway.

Provides:
- Database session (async SQLAlchemy)
- Redis connection
- Shared httpx.AsyncClient
- JWT-validated current user
- Role-based access control
- Per-service proxy instances
"""

from __future__ import annotations

import time
from typing import Annotated, Any

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config import GatewayConfig, get_config
from exceptions import (
    ForbiddenException,
    InsufficientRoleException,
    InvalidTokenException,
    TokenExpiredException,
    UnauthorizedException,
)
from proxy import ServiceProxy

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Bearer scheme — auto_error=False so we can produce custom error messages
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Pydantic model for JWT payload
# ---------------------------------------------------------------------------


class TokenPayload(BaseModel):
    """Claims extracted from a valid JWT access token."""

    sub: str = Field(..., description="Subject — user UUID")
    email: str = Field(..., description="User email address")
    role: str = Field(..., description="User role: admin | manager | user")
    org_id: str | None = Field(None, description="Organization UUID (if any)")
    is_active: bool = Field(default=True)
    exp: int = Field(..., description="Expiry unix timestamp")
    iat: int = Field(..., description="Issued-at unix timestamp")
    jti: str | None = Field(None, description="JWT ID for token revocation")


class CurrentUser(BaseModel):
    """Resolved user available to route handlers via dependency injection."""

    user_id: str
    email: str
    role: str
    org_id: str | None
    is_active: bool
    token: str  # raw bearer token, forwarded to upstream services

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Infrastructure dependencies
# ---------------------------------------------------------------------------


def get_config_dep() -> GatewayConfig:
    """Inject singleton GatewayConfig."""
    return get_config()


ConfigDep = Annotated[GatewayConfig, Depends(get_config_dep)]


async def get_db(request: Request) -> AsyncSession:
    """
    Yield an async SQLAlchemy session.

    Session is committed on success, rolled back on exception, and always closed.
    """
    async_session_factory = request.app.state.async_session_factory
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_redis(request: Request) -> aioredis.Redis:
    """Inject Redis client from app state."""
    return request.app.state.redis  # type: ignore[return-value]


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Inject shared httpx.AsyncClient from app state."""
    return request.app.state.http_client  # type: ignore[return-value]


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


# ---------------------------------------------------------------------------
# Per-service proxy factories
# ---------------------------------------------------------------------------


def _make_proxy_dep(service_name: str, url_getter: str):
    """Factory: create a Depends()-compatible proxy dependency for a service."""

    async def _dep(
        request: Request,
        config: ConfigDep,
        client: HttpClientDep,
    ) -> ServiceProxy:
        base_url: str = getattr(config, url_getter)
        return ServiceProxy(service_name, base_url, client, config)

    return Depends(_dep)


AuthProxyDep = Annotated[
    ServiceProxy,
    _make_proxy_dep("auth", "auth_service_base"),
]
UserProxyDep = Annotated[
    ServiceProxy,
    _make_proxy_dep("user", "user_service_base"),
]
DocumentProxyDep = Annotated[
    ServiceProxy,
    _make_proxy_dep("document", "document_service_base"),
]
SearchProxyDep = Annotated[
    ServiceProxy,
    _make_proxy_dep("search", "search_service_base"),
]
ChatProxyDep = Annotated[
    ServiceProxy,
    _make_proxy_dep("chat", "chat_service_base"),
]
OrgProxyDep = Annotated[
    ServiceProxy,
    _make_proxy_dep("organization", "organization_service_base"),
]
AnalyticsProxyDep = Annotated[
    ServiceProxy,
    _make_proxy_dep("analytics", "analytics_service_base"),
]


# ---------------------------------------------------------------------------
# JWT / Auth dependencies
# ---------------------------------------------------------------------------


async def _decode_token(token: str, config: GatewayConfig) -> TokenPayload:
    """Decode and validate JWT. Raises typed gateway exceptions."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            config.secret_key,
            algorithms=[config.algorithm],
            options={"verify_aud": False},
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredException() from exc
    except JWTError as exc:
        raise InvalidTokenException(detail=str(exc)) from exc

    try:
        return TokenPayload(**payload)
    except Exception as exc:
        raise InvalidTokenException(
            message="Token payload malformed",
            detail=str(exc),
        ) from exc


async def get_current_user(
    request: Request,
    config: ConfigDep,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> CurrentUser:
    """
    Validate JWT from Authorization header and return the resolved user.

    Stores user in request.state.user for middleware access.
    """
    if credentials is None:
        raise UnauthorizedException("Authorization header missing")

    token = credentials.credentials
    payload = await _decode_token(token, config)

    if not payload.is_active:
        raise UnauthorizedException("User account is deactivated")

    user = CurrentUser(
        user_id=payload.sub,
        email=payload.email,
        role=payload.role,
        org_id=payload.org_id,
        is_active=payload.is_active,
        token=token,
    )

    # store on request state for logging middleware
    request.state.user = user

    logger.bind(user_id=user.user_id, role=user.role).debug("user_authenticated")
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_current_active_user(user: CurrentUserDep) -> CurrentUser:
    """Ensure the authenticated user is active."""
    if not user.is_active:
        raise ForbiddenException("User account is deactivated")
    return user


ActiveUserDep = Annotated[CurrentUser, Depends(get_current_active_user)]


def require_role(*roles: str):
    """
    Dependency factory: require that current user has one of the given roles.

    Usage::

        @router.get("/admin/thing")
        async def thing(user: Annotated[CurrentUser, Depends(require_role("admin"))]):
            ...
    """

    async def _check_role(user: CurrentUserDep) -> CurrentUser:
        if user.role not in roles:
            raise InsufficientRoleException(
                message=f"Role '{user.role}' is not in required roles: {list(roles)}",
                detail={"required": list(roles), "actual": user.role},
            )
        return user

    return Depends(_check_role)


# Convenience role aliases
AdminDep = Annotated[CurrentUser, Depends(require_role("admin"))]
AdminOrManagerDep = Annotated[CurrentUser, Depends(require_role("admin", "manager"))]


# ---------------------------------------------------------------------------
# Request-ID helper
# ---------------------------------------------------------------------------


def get_request_id(
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> str:
    """Extract or generate a request ID from incoming headers."""
    import uuid

    return x_request_id or str(uuid.uuid4())


RequestIdDep = Annotated[str, Depends(get_request_id)]
