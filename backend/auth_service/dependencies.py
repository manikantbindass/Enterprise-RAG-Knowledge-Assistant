"""
FastAPI dependencies for the Auth Service.
"""

from __future__ import annotations

from typing import AsyncGenerator

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.services.auth_service import AuthService
from auth_service.services.jwt_service import JWTService
from auth_service.services.keycloak_service import KeycloakService

logger = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Extract bearer token from Authorization header."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_db_session(request: Request) -> AsyncSession:
    """Pull async DB session from request state (set per-request in middleware)."""
    session: AsyncSession | None = getattr(request.state, "db_session", None)
    if session is None:
        raise RuntimeError("DB session not attached to request")
    return session


def get_redis(request: Request) -> Redis:
    """Pull Redis client from app state."""
    return request.app.state.redis


def get_jwt_service(redis: Redis = Depends(get_redis)) -> JWTService:
    return JWTService(redis)


def get_keycloak_service() -> KeycloakService:
    return KeycloakService()


def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    jwt_svc: JWTService = Depends(get_jwt_service),
    kc_svc: KeycloakService = Depends(get_keycloak_service),
) -> AuthService:
    return AuthService(session, jwt_svc, kc_svc)
