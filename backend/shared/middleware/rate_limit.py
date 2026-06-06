"""
RateLimitMiddleware — sliding window rate limiter backed by Redis.

Two independent limits per request:
1. Per-user  (identified by JWT sub claim / user_id)
2. Per-IP    (client IP as fallback / additional layer)

Algorithm: sliding window log using Redis sorted sets.
- Key: ratelimit:{scope}:{identifier}
- Members: request timestamps (float epoch)
- Window: ZREMRANGEBYSCORE clears timestamps older than window

Returns 429 with:
- X-RateLimit-Limit header
- X-RateLimit-Remaining header
- X-RateLimit-Reset header (Unix timestamp when window resets)
- Retry-After header (seconds until next slot available)
- JSON body {"error_code": "RATE_LIMIT_EXCEEDED", "message": "..."}
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog
from fastapi import Request, Response
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# Paths exempt from rate limiting
_EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/health", "/healthz", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"}
)

_RATE_LIMIT_LUA = """
-- Sliding window rate limiter
-- KEYS[1] = redis key
-- ARGV[1] = current timestamp (float)
-- ARGV[2] = window size in seconds
-- ARGV[3] = max requests per window

local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local cutoff = now - window

-- Remove entries outside the window
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

-- Count remaining entries in window
local count = redis.call('ZCARD', key)

if count >= limit then
    -- Get oldest entry to compute retry-after
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local oldest_ts = oldest[2] and tonumber(oldest[2]) or now
    local retry_after = math.ceil(oldest_ts + window - now)
    return {0, count, retry_after}
end

-- Add this request
redis.call('ZADD', key, now, now .. math.random())
redis.call('EXPIRE', key, math.ceil(window))

return {1, count + 1, 0}
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter middleware.

    Configure per-user and per-IP limits independently.
    Per-user limit is checked first (more specific), per-IP is a secondary defense.

    If Redis is unavailable, requests are ALLOWED (fail open) but the error is logged.
    Change fail-open to fail-closed by setting fail_open=False.
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_client: Redis,
        *,
        per_user_limit: int = 100,
        per_ip_limit: int = 200,
        window_seconds: int = 60,
        exempt_paths: frozenset[str] | None = None,
        fail_open: bool = True,
    ) -> None:
        super().__init__(app)
        self._redis = redis_client
        self._per_user_limit = per_user_limit
        self._per_ip_limit = per_ip_limit
        self._window_seconds = window_seconds
        self._exempt_paths = exempt_paths or _EXEMPT_PATHS
        self._fail_open = fail_open
        self._lua_script: Any = None  # loaded lazily

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip exempt paths
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        now = time.time()
        client_ip = self._get_client_ip(request)
        user_id = getattr(request.state, "user_id", None)

        try:
            # Check per-user limit first (if authenticated)
            if user_id:
                allowed, remaining, retry_after = await self._check_limit(
                    scope="user",
                    identifier=str(user_id),
                    limit=self._per_user_limit,
                    now=now,
                )
                if not allowed:
                    return self._rate_limit_response(
                        limit=self._per_user_limit,
                        remaining=0,
                        retry_after=retry_after,
                        window=self._window_seconds,
                        now=now,
                        scope="user",
                    )

            # Always check per-IP limit
            if client_ip:
                allowed, remaining, retry_after = await self._check_limit(
                    scope="ip",
                    identifier=client_ip,
                    limit=self._per_ip_limit,
                    now=now,
                )
                if not allowed:
                    return self._rate_limit_response(
                        limit=self._per_ip_limit,
                        remaining=0,
                        retry_after=retry_after,
                        window=self._window_seconds,
                        now=now,
                        scope="ip",
                    )

        except Exception as exc:
            logger.error(
                "rate_limit_check_failed",
                error=str(exc),
                path=request.url.path,
                fail_open=self._fail_open,
            )
            if not self._fail_open:
                return JSONResponse(
                    status_code=503,
                    content={"error_code": "SERVICE_UNAVAILABLE", "message": "Rate limiter unavailable"},
                )

        response = await call_next(request)
        return response

    async def _check_limit(
        self,
        scope: str,
        identifier: str,
        limit: int,
        now: float,
    ) -> tuple[bool, int, int]:
        """
        Execute sliding window check via Lua script.

        Returns (allowed, current_count, retry_after_seconds).
        """
        key = f"ratelimit:{scope}:{identifier}"

        if self._lua_script is None:
            self._lua_script = self._redis.register_script(_RATE_LIMIT_LUA)

        result = await self._lua_script(
            keys=[key],
            args=[str(now), str(self._window_seconds), str(limit)],
        )

        allowed = bool(result[0])
        count = int(result[1])
        retry_after = int(result[2])
        return allowed, count, retry_after

    def _rate_limit_response(
        self,
        *,
        limit: int,
        remaining: int,
        retry_after: int,
        window: int,
        now: float,
        scope: str,
    ) -> JSONResponse:
        reset_ts = int(now) + retry_after

        logger.warning(
            "rate_limit_exceeded",
            scope=scope,
            limit=limit,
            retry_after=retry_after,
        )

        return JSONResponse(
            status_code=429,
            content={
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                "details": {
                    "limit": limit,
                    "window_seconds": window,
                    "retry_after_seconds": retry_after,
                    "scope": scope,
                },
            },
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_ts),
                "Retry-After": str(retry_after),
            },
        )

    @staticmethod
    def _get_client_ip(request: Request) -> str | None:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None
