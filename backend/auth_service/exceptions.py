"""
Auth service exceptions.
"""

from __future__ import annotations


class AuthServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthenticationError(AuthServiceError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class TokenExpiredError(AuthenticationError):
    def __init__(self, message: str = "Token has expired") -> None:
        super().__init__(message)


class UserNotFoundError(AuthServiceError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"User {identifier!r} not found", status_code=404)


class UserAlreadyExistsError(AuthServiceError):
    def __init__(self, username: str) -> None:
        super().__init__(f"User {username!r} already exists", status_code=409)


class KeycloakUnavailableError(AuthServiceError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(f"Keycloak unavailable: {detail}", status_code=503)


class PermissionDeniedError(AuthServiceError):
    def __init__(self, action: str = "") -> None:
        super().__init__(f"Permission denied{': ' + action if action else ''}", status_code=403)


class InvalidCredentialsError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("Invalid username or password")
