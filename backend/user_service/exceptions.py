"""
User Service — Custom Exceptions.

Structured exception hierarchy for clean error handling and consistent API responses.
"""

from __future__ import annotations


class UserServiceError(Exception):
    """Base exception for user service."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── User Exceptions ───────────────────────────────────────────────────────────

class UserNotFoundError(UserServiceError):
    """Raised when user lookup returns no result."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' not found", status_code=404)
        self.user_id = user_id


class UserAlreadyExistsError(UserServiceError):
    """Raised when creating a user with duplicate email."""

    def __init__(self, email: str) -> None:
        super().__init__(f"User with email '{email}' already exists", status_code=409)
        self.email = email


class UserSoftDeletedException(UserServiceError):
    """Raised when operating on a soft-deleted user."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' has been deactivated", status_code=410)
        self.user_id = user_id


class InvalidPasswordError(UserServiceError):
    """Raised when password fails validation rules."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid password: {reason}", status_code=422)


# ── Organization Exceptions ───────────────────────────────────────────────────

class OrganizationNotFoundError(UserServiceError):
    """Raised when org lookup returns no result."""

    def __init__(self, org_id: str) -> None:
        super().__init__(f"Organization '{org_id}' not found", status_code=404)
        self.org_id = org_id


class OrganizationAlreadyExistsError(UserServiceError):
    """Raised when creating an org with a duplicate slug."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Organization with slug '{slug}' already exists", status_code=409)
        self.slug = slug


class OrgLimitExceededError(UserServiceError):
    """Raised when an org would exceed its configured limit."""

    def __init__(self, resource: str, limit: int) -> None:
        super().__init__(
            f"Organization limit exceeded for '{resource}': max={limit}",
            status_code=429,
        )
        self.resource = resource
        self.limit = limit


# ── Authorization Exceptions ──────────────────────────────────────────────────

class InsufficientPermissionsError(UserServiceError):
    """Raised when caller lacks required role/permission."""

    def __init__(self, required_role: str) -> None:
        super().__init__(
            f"Insufficient permissions. Required role: {required_role}",
            status_code=403,
        )
        self.required_role = required_role


class SelfDeletionError(UserServiceError):
    """Raised when an admin tries to delete their own account."""

    def __init__(self) -> None:
        super().__init__("Cannot delete your own account", status_code=400)
