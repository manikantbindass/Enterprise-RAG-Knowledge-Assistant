"""
Custom exception hierarchy for API Gateway.

Every exception maps to a specific HTTP status code and structured JSON body.
FastAPI exception handlers registered in main.py convert these to responses.
"""

from __future__ import annotations

from typing import Any


class GatewayBaseException(Exception):
    """Root exception for all API Gateway errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: Any = None,
        error_code: str | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.detail = detail
        if error_code:
            self.error_code = error_code
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-safe dict for response body."""
        payload: dict[str, Any] = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


# ---------------------------------------------------------------------------
# 400 Bad Request
# ---------------------------------------------------------------------------


class ValidationException(GatewayBaseException):
    """Request payload failed validation."""

    status_code = 400
    error_code = "VALIDATION_ERROR"
    message = "Request validation failed"


class BadRequestException(GatewayBaseException):
    """Generic malformed request."""

    status_code = 400
    error_code = "BAD_REQUEST"
    message = "Bad request"


# ---------------------------------------------------------------------------
# 401 Unauthorized
# ---------------------------------------------------------------------------


class UnauthorizedException(GatewayBaseException):
    """Missing or invalid authentication credentials."""

    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "Authentication required"


class TokenExpiredException(GatewayBaseException):
    """JWT access token has expired."""

    status_code = 401
    error_code = "TOKEN_EXPIRED"
    message = "Access token has expired"


class InvalidTokenException(GatewayBaseException):
    """JWT signature or structure is invalid."""

    status_code = 401
    error_code = "INVALID_TOKEN"
    message = "Invalid authentication token"


# ---------------------------------------------------------------------------
# 403 Forbidden
# ---------------------------------------------------------------------------


class ForbiddenException(GatewayBaseException):
    """Authenticated user lacks required permissions."""

    status_code = 403
    error_code = "FORBIDDEN"
    message = "Insufficient permissions"


class InsufficientRoleException(ForbiddenException):
    """User role does not match required roles."""

    error_code = "INSUFFICIENT_ROLE"
    message = "Required role not granted"


# ---------------------------------------------------------------------------
# 404 Not Found
# ---------------------------------------------------------------------------


class NotFoundException(GatewayBaseException):
    """Requested resource does not exist."""

    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"


# ---------------------------------------------------------------------------
# 409 Conflict
# ---------------------------------------------------------------------------


class ConflictException(GatewayBaseException):
    """Resource already exists or state conflict."""

    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict"


# ---------------------------------------------------------------------------
# 413 Payload Too Large
# ---------------------------------------------------------------------------


class PayloadTooLargeException(GatewayBaseException):
    """Uploaded file or request body exceeds size limit."""

    status_code = 413
    error_code = "PAYLOAD_TOO_LARGE"
    message = "Request payload too large"


# ---------------------------------------------------------------------------
# 422 Unprocessable Entity
# ---------------------------------------------------------------------------


class UnprocessableEntityException(GatewayBaseException):
    """Request is well-formed but semantically invalid."""

    status_code = 422
    error_code = "UNPROCESSABLE_ENTITY"
    message = "Unprocessable entity"


# ---------------------------------------------------------------------------
# 429 Too Many Requests
# ---------------------------------------------------------------------------


class RateLimitExceededException(GatewayBaseException):
    """Client exceeded the rate limit."""

    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Too many requests — slow down"

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after: int = 60,
        detail: Any = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# 502 / 503 / 504 Upstream errors
# ---------------------------------------------------------------------------


class UpstreamServiceException(GatewayBaseException):
    """Upstream microservice returned an error."""

    status_code = 502
    error_code = "UPSTREAM_ERROR"
    message = "Upstream service error"

    def __init__(
        self,
        service: str,
        upstream_status: int | None = None,
        message: str | None = None,
        *,
        detail: Any = None,
    ) -> None:
        self.service = service
        self.upstream_status = upstream_status
        super().__init__(
            message or f"Service '{service}' returned an error",
            detail=detail,
        )


class ServiceUnavailableException(GatewayBaseException):
    """Upstream microservice is unavailable."""

    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"


class GatewayTimeoutException(GatewayBaseException):
    """Upstream microservice timed out."""

    status_code = 504
    error_code = "GATEWAY_TIMEOUT"
    message = "Upstream service timed out"


# ---------------------------------------------------------------------------
# 500 Internal Server Error
# ---------------------------------------------------------------------------


class InternalServerException(GatewayBaseException):
    """Unhandled internal error."""

    status_code = 500
    error_code = "INTERNAL_ERROR"
    message = "Internal server error"


class DatabaseException(GatewayBaseException):
    """Database operation failed."""

    status_code = 500
    error_code = "DATABASE_ERROR"
    message = "Database error"


class CacheException(GatewayBaseException):
    """Redis / cache operation failed."""

    status_code = 500
    error_code = "CACHE_ERROR"
    message = "Cache error"
