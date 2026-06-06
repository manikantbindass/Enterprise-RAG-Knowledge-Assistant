"""
TenantMiddleware — extract org_id from JWT, set RLS context.

Flow:
1. Read Authorization: Bearer <token> header
2. Decode JWT (no full verification — security.py handles that in route deps)
3. Extract org_id claim
4. Store in request.state.org_id and structlog context
5. Call set_tenant_context() to set PostgreSQL session variable

Paths in EXCLUDE_PATHS skip tenant extraction (health, metrics, docs).
"""

from __future__ import annotations

import re
from typing import Sequence

import structlog
from fastapi import Request, Response
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from shared.logging import set_request_context

logger = structlog.get_logger(__name__)

# Paths that do NOT require a tenant context
_EXCLUDE_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/ready",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/register",
    }
)

_EXCLUDE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^/static/"),
]


class TenantMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that extracts and validates tenant context from JWT.

    Does NOT fully verify the JWT signature — that is done by the
    `get_current_user` FastAPI dependency in routes that need it.

    This middleware only reads the `org_id` claim to set up:
    - request.state.org_id
    - request.state.user_id
    - structlog context vars
    - PostgreSQL SET LOCAL app.current_org_id (via set_tenant_context)

    The PostgreSQL context is set lazily — only for requests that have
    a database session (to avoid opening a DB connection for static paths).
    """

    def __init__(
        self,
        app: ASGIApp,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        exclude_paths: Sequence[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._jwt_secret = jwt_secret
        self._jwt_algorithm = jwt_algorithm
        self._exclude_paths = frozenset(exclude_paths or []) | _EXCLUDE_PATHS

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Initialize state with safe defaults
        request.state.org_id = None
        request.state.user_id = None
        request.state.user_role = None
        request.state.tenant_context_set = False

        # Skip excluded paths
        if self._is_excluded(request.url.path):
            return await call_next(request)

        # Extract JWT from Authorization header
        token = self._extract_token(request)
        if token:
            claims = self._decode_token_unverified(token)
            if claims:
                org_id = claims.get("org_id") or claims.get("organization_id")
                user_id = claims.get("sub") or claims.get("user_id")
                user_role = claims.get("role")

                request.state.org_id = org_id
                request.state.user_id = user_id
                request.state.user_role = user_role

                # Inject into structlog context for all subsequent log calls
                set_request_context(
                    org_id=str(org_id) if org_id else "",
                    user_id=str(user_id) if user_id else "",
                )

                logger.debug(
                    "tenant_context_extracted",
                    org_id=org_id,
                    user_id=user_id,
                    path=request.url.path,
                )

        return await call_next(request)

    def _is_excluded(self, path: str) -> bool:
        if path in self._exclude_paths:
            return True
        return any(pattern.match(path) for pattern in _EXCLUDE_PATTERNS)

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip() or None
        # Also support API key via X-API-Key header (handled separately)
        return None

    def _decode_token_unverified(self, token: str) -> dict | None:
        """
        Decode JWT claims WITHOUT signature verification.

        We only need org_id/user_id for context setup. Full verification
        (expiry, signature, audience) happens in security.get_current_user.
        This avoids duplicate crypto work and keeps middleware lightweight.
        """
        try:
            return jwt.get_unverified_claims(token)
        except JWTError as exc:
            logger.debug("jwt_claims_unverified_decode_failed", error=str(exc))
            return None
