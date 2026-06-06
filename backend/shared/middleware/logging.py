"""
RequestLoggingMiddleware — structured log for every HTTP request.

Logs on response (not on request) to capture status_code and latency.
Each request gets a unique request_id (UUID4) stamped in:
- X-Request-ID response header
- structlog context
- request.state.request_id
"""

from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from shared.logging import set_request_context, clear_request_context

logger = structlog.get_logger(__name__)

# Paths to skip logging (too noisy)
_SILENT_PATHS: frozenset[str] = frozenset({"/health", "/healthz", "/ready", "/metrics"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that emits one structured log line per HTTP request.

    Log fields:
    - method         — HTTP verb
    - path           — URL path (no query string in main field)
    - query          — query string if present
    - status_code    — response status
    - latency_ms     — float milliseconds
    - request_id     — UUID4 correlation ID
    - user_id        — from request.state (set by TenantMiddleware)
    - org_id         — from request.state (set by TenantMiddleware)
    - user_agent     — client User-Agent
    - content_length — response Content-Length if known
    - ip             — client IP

    Install AFTER TenantMiddleware so user_id/org_id are already in state.
    """

    def __init__(
        self,
        app: ASGIApp,
        service_name: str = "rag-service",
        silent_paths: frozenset[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._service_name = service_name
        self._silent_paths = silent_paths or _SILENT_PATHS

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Honour existing X-Request-ID (from upstream gateway) or generate one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Inject into structlog context (shared.logging contextvars)
        set_request_context(
            request_id=request_id,
            service_name=self._service_name,
        )

        # Skip logging for health/metrics endpoints
        path = request.url.path
        if path in self._silent_paths:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        start = time.perf_counter()
        status_code = 500  # default if exception leaks

        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            latency_ms = (time.perf_counter() - start) * 1000

            # Grab context set by TenantMiddleware (may be None for anon requests)
            user_id = getattr(request.state, "user_id", None)
            org_id = getattr(request.state, "org_id", None)

            log_method = logger.info if status_code < 400 else logger.warning
            if status_code >= 500:
                log_method = logger.error

            log_method(
                "http_request",
                method=request.method,
                path=path,
                query=str(request.url.query) or None,
                status_code=status_code,
                latency_ms=round(latency_ms, 3),
                request_id=request_id,
                user_id=str(user_id) if user_id else None,
                org_id=str(org_id) if org_id else None,
                user_agent=request.headers.get("User-Agent"),
                ip=self._get_client_ip(request),
                content_type=request.headers.get("Content-Type"),
            )

        response.headers["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str | None:
        """Respect X-Forwarded-For (reverse proxy) before falling back to direct IP."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None
