"""
Custom exception hierarchy for Enterprise RAG Knowledge Assistant.

Every exception maps to an HTTP status code and machine-readable error_code.
Services raise these; the global exception handler converts them to JSON.

Usage:
    raise NotFoundError(resource="document", resource_id=str(doc_id))
    raise ForbiddenError(message="Insufficient role: requires admin")
"""

from __future__ import annotations

from typing import Any, Optional


class RAGBaseException(Exception):
    """
    Root of the exception hierarchy.

    All custom exceptions inherit from here so callers can catch
    `RAGBaseException` to handle any service error uniformly.
    """

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        if error_code:
            self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict for HTTP responses."""
        payload: dict[str, Any] = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"status={self.status_code}, "
            f"code={self.error_code!r}, "
            f"message={self.message!r})"
        )


# ---------------------------------------------------------------------------
# 4xx Client Errors
# ---------------------------------------------------------------------------


class NotFoundError(RAGBaseException):
    """Resource not found — 404."""

    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"

    def __init__(
        self,
        message: str | None = None,
        *,
        resource: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if resource:
            details["resource"] = resource
        if resource_id:
            details["resource_id"] = resource_id
        if resource and not message:
            message = f"{resource} not found"
            if resource_id:
                message += f": {resource_id}"
        super().__init__(message, details=details)


class UnauthorizedError(RAGBaseException):
    """Missing or invalid credentials — 401."""

    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "Authentication required"

    def __init__(
        self,
        message: str | None = None,
        *,
        www_authenticate: str = "Bearer",
    ) -> None:
        self.www_authenticate = www_authenticate
        super().__init__(message)


class ForbiddenError(RAGBaseException):
    """Authenticated but insufficient permissions — 403."""

    status_code = 403
    error_code = "FORBIDDEN"
    message = "You do not have permission to perform this action"

    def __init__(
        self,
        message: str | None = None,
        *,
        required_role: str | None = None,
        action: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if required_role:
            details["required_role"] = required_role
        if action:
            details["action"] = action
        super().__init__(message, details=details)


class ValidationError(RAGBaseException):
    """Invalid request payload — 422."""

    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "Request validation failed"

    def __init__(
        self,
        message: str | None = None,
        *,
        field_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if field_errors:
            details["field_errors"] = field_errors
        super().__init__(message, details=details)


class ConflictError(RAGBaseException):
    """Resource conflict (duplicate, version mismatch) — 409."""

    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict"

    def __init__(
        self,
        message: str | None = None,
        *,
        resource: str | None = None,
        conflicting_field: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if resource:
            details["resource"] = resource
        if conflicting_field:
            details["conflicting_field"] = conflicting_field
        super().__init__(message, details=details)


class RateLimitError(RAGBaseException):
    """Too many requests — 429."""

    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Rate limit exceeded. Please slow down."

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after: int = 60,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        details: dict[str, Any] = {"retry_after_seconds": retry_after}
        if limit:
            details["limit"] = limit
        if window_seconds:
            details["window_seconds"] = window_seconds
        super().__init__(message, details=details)


class BadRequestError(RAGBaseException):
    """Malformed request — 400."""

    status_code = 400
    error_code = "BAD_REQUEST"
    message = "Bad request"


# ---------------------------------------------------------------------------
# 5xx Server Errors
# ---------------------------------------------------------------------------


class ServiceUnavailableError(RAGBaseException):
    """Downstream service unavailable — 503."""

    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    message = "A required service is temporarily unavailable"

    def __init__(
        self,
        message: str | None = None,
        *,
        service: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        details: dict[str, Any] = {}
        if service:
            details["service"] = service
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(message, details=details)


class InternalError(RAGBaseException):
    """Unexpected server error — 500."""

    status_code = 500
    error_code = "INTERNAL_ERROR"
    message = "An internal error occurred"


class StorageError(RAGBaseException):
    """Object storage operation failure — 500."""

    status_code = 500
    error_code = "STORAGE_ERROR"
    message = "Storage operation failed"

    def __init__(
        self,
        message: str | None = None,
        *,
        operation: str | None = None,
        path: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if operation:
            details["operation"] = operation
        if path:
            details["path"] = path
        super().__init__(message, details=details)


class MessagingError(RAGBaseException):
    """Message broker operation failure — 503."""

    status_code = 503
    error_code = "MESSAGING_ERROR"
    message = "Message broker operation failed"
