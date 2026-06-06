"""
Local JWT service — fallback when Keycloak is unavailable (development mode)
or as complementary token store for internal service-to-service auth.

Access tokens: short-lived HS256 JWTs.
Refresh tokens: opaque random strings stored in Redis with TTL.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from jose import JWTError, jwt
from redis.asyncio import Redis

from auth_service.config import get_settings
from auth_service.exceptions import AuthenticationError, TokenExpiredError

logger = structlog.get_logger(__name__)

_REFRESH_TOKEN_PREFIX = "refresh_token:"


class JWTService:
    """
    Manages JWT creation and validation plus Redis-backed refresh tokens.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._settings = get_settings()

    # ── Access token ───────────────────────────────────────────────────────

    def create_access_token(
        self,
        user_id: UUID,
        username: str,
        org_id: UUID | None,
        roles: list[str],
        extra_claims: dict[str, Any] | None = None,
    ) -> tuple[str, datetime]:
        """
        Create signed JWT access token.
        Returns (token_string, expiry_datetime).
        """
        settings = self._settings
        now = datetime.now(tz=timezone.utc)
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

        payload: dict[str, Any] = {
            "sub": str(user_id),
            "username": username,
            "org_id": str(org_id) if org_id else None,
            "roles": roles,
            "iat": now,
            "exp": expire,
            "jti": str(uuid.uuid4()),
            "iss": settings.service_name,
            **(extra_claims or {}),
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        return token, expire

    def verify_access_token(self, token: str) -> dict[str, Any]:
        """
        Decode and validate JWT. Raises AuthenticationError on failure.
        """
        settings = self._settings
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            return payload
        except JWTError as exc:
            error_str = str(exc).lower()
            if "expired" in error_str:
                raise TokenExpiredError("Access token has expired") from exc
            raise AuthenticationError(f"Invalid token: {exc}") from exc

    # ── Refresh token ──────────────────────────────────────────────────────

    async def create_refresh_token(self, user_id: UUID) -> str:
        """
        Generate opaque refresh token, store in Redis with TTL.
        Returns the token string.
        """
        settings = self._settings
        token = secrets.token_urlsafe(64)
        key = f"{_REFRESH_TOKEN_PREFIX}{token}"
        ttl = int(timedelta(days=settings.refresh_token_expire_days).total_seconds())

        await self._redis.setex(key, ttl, str(user_id))
        logger.debug("refresh_token_created", user_id=str(user_id))
        return token

    async def verify_refresh_token(self, token: str) -> UUID:
        """
        Validate refresh token against Redis. Returns user_id if valid.
        Raises AuthenticationError if invalid or expired.
        """
        key = f"{_REFRESH_TOKEN_PREFIX}{token}"
        raw = await self._redis.get(key)
        if raw is None:
            raise AuthenticationError("Refresh token invalid or expired")
        return UUID(raw.decode() if isinstance(raw, bytes) else raw)

    async def revoke_refresh_token(self, token: str) -> None:
        """Delete refresh token from Redis (logout)."""
        key = f"{_REFRESH_TOKEN_PREFIX}{token}"
        await self._redis.delete(key)
        logger.debug("refresh_token_revoked")

    async def revoke_all_user_tokens(self, user_id: UUID) -> int:
        """
        Scan Redis for all refresh tokens belonging to a user and delete them.
        Returns number of tokens revoked.
        Expensive — use only on security events (password change, account compromise).
        """
        revoked = 0
        async for key in self._redis.scan_iter(f"{_REFRESH_TOKEN_PREFIX}*"):
            value = await self._redis.get(key)
            if value and (value.decode() if isinstance(value, bytes) else value) == str(user_id):
                await self._redis.delete(key)
                revoked += 1
        logger.info("all_user_tokens_revoked", user_id=str(user_id), count=revoked)
        return revoked
