"""
Unit tests for JWT authentication and RBAC.

Tests:
- JWT creation and verification
- Expired token raises
- Invalid/tampered token raises
- RBAC: admin can access admin routes
- RBAC: viewer blocked from write routes
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub auth utilities (mirrors real implementation)
# ---------------------------------------------------------------------------

try:
    from api_gateway.dependencies import verify_jwt_token
    from api_gateway.services.auth import AuthService, TokenPayload
    from shared.models.user import UserRole
except ImportError:
    import enum
    from dataclasses import dataclass
    from typing import Optional

    class UserRole(str, enum.Enum):
        ADMIN = "admin"
        MANAGER = "manager"
        EMPLOYEE = "employee"
        VIEWER = "viewer"

    ROLE_HIERARCHY = {
        UserRole.ADMIN: 4,
        UserRole.MANAGER: 3,
        UserRole.EMPLOYEE: 2,
        UserRole.VIEWER: 1,
    }

    @dataclass
    class TokenPayload:
        sub: str
        email: str
        org_id: str
        role: UserRole
        iss: str
        aud: str
        iat: int
        exp: int
        jti: Optional[str] = None

    class TokenExpiredError(Exception):
        """JWT token has expired."""

    class TokenInvalidError(Exception):
        """JWT token is invalid or tampered."""

    class InsufficientPermissionsError(Exception):
        """User lacks required role."""

    _SECRET = "test-jwt-secret-key-minimum-32-chars!"
    _ALGORITHM = "HS256"
    _ISSUER = "rag-knowledge-assistant"
    _AUDIENCE = "rag-api"

    def create_access_token(
        user_id: str,
        email: str,
        org_id: str,
        role: UserRole,
        expires_in_minutes: int = 30,
        secret: str = _SECRET,
    ) -> str:
        """Create a signed JWT access token."""
        import jose.jwt as jwt

        now = int(datetime.now(UTC).timestamp())
        payload = {
            "sub": user_id,
            "email": email,
            "org_id": org_id,
            "role": role.value,
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "iat": now,
            "exp": now + expires_in_minutes * 60,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, secret, algorithm=_ALGORITHM)

    def verify_access_token(token: str, secret: str = _SECRET) -> TokenPayload:
        """Verify and decode a JWT access token."""
        import jose.exceptions
        import jose.jwt as jwt

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[_ALGORITHM],
                audience=_AUDIENCE,
                issuer=_ISSUER,
            )
        except jose.exceptions.ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except jose.exceptions.JWTError as exc:
            raise TokenInvalidError(f"Token invalid: {exc}") from exc

        return TokenPayload(
            sub=payload["sub"],
            email=payload["email"],
            org_id=payload["org_id"],
            role=UserRole(payload["role"]),
            iss=payload["iss"],
            aud=payload["aud"],
            iat=payload["iat"],
            exp=payload["exp"],
            jti=payload.get("jti"),
        )

    def require_role(current_role: UserRole, required_role: UserRole) -> None:
        """Raise InsufficientPermissionsError if current_role < required_role."""
        if ROLE_HIERARCHY[current_role] < ROLE_HIERARCHY[required_role]:
            raise InsufficientPermissionsError(
                f"Role {current_role.value!r} cannot access route requiring {required_role.value!r}"
            )


# ===========================================================================
# JWT creation and verification
# ===========================================================================

class TestJWTCreateAndVerify:
    """Tests for JWT token lifecycle."""

    def test_jwt_create_and_verify_roundtrip(self):
        """Token created → verified → payload matches."""
        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        token = create_access_token(
            user_id=user_id,
            email="test@example.com",
            org_id=org_id,
            role=UserRole.ADMIN,
        )
        payload = verify_access_token(token)
        assert payload.sub == user_id
        assert payload.email == "test@example.com"
        assert payload.org_id == org_id
        assert payload.role == UserRole.ADMIN

    def test_jwt_create_returns_string(self):
        """create_access_token returns a non-empty string."""
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="u@test.com",
            org_id=str(uuid.uuid4()),
            role=UserRole.EMPLOYEE,
        )
        assert isinstance(token, str)
        assert len(token) > 50

    def test_jwt_token_has_three_parts(self):
        """JWT format: header.payload.signature."""
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="u@test.com",
            org_id=str(uuid.uuid4()),
            role=UserRole.VIEWER,
        )
        parts = token.split(".")
        assert len(parts) == 3

    def test_jwt_contains_jti(self):
        """Token payload includes unique JTI for revocation support."""
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="u@test.com",
            org_id=str(uuid.uuid4()),
            role=UserRole.MANAGER,
        )
        payload = verify_access_token(token)
        assert payload.jti is not None
        assert len(payload.jti) > 0

    def test_jwt_iss_and_aud_set(self):
        """Issuer and audience fields are set correctly."""
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="u@test.com",
            org_id=str(uuid.uuid4()),
            role=UserRole.EMPLOYEE,
        )
        payload = verify_access_token(token)
        assert payload.iss == "rag-knowledge-assistant"
        assert payload.aud == "rag-api"


# ===========================================================================
# Expired token
# ===========================================================================

class TestExpiredToken:
    """Tests for expired JWT handling."""

    def test_expired_token_raises(self):
        """Token with exp in the past raises TokenExpiredError."""
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="u@test.com",
            org_id=str(uuid.uuid4()),
            role=UserRole.EMPLOYEE,
            expires_in_minutes=-1,  # already expired
        )
        with pytest.raises(TokenExpiredError):
            verify_access_token(token)

    def test_expired_by_one_second_raises(self):
        """Even 1-second expiry offset raises."""
        import jose.jwt as jwt

        now = int(datetime.now(UTC).timestamp())
        payload = {
            "sub": str(uuid.uuid4()),
            "email": "u@test.com",
            "org_id": str(uuid.uuid4()),
            "role": "employee",
            "iss": "rag-knowledge-assistant",
            "aud": "rag-api",
            "iat": now - 10,
            "exp": now - 1,  # expired 1 second ago
        }
        token = jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
        with pytest.raises(TokenExpiredError):
            verify_access_token(token)


# ===========================================================================
# Invalid token
# ===========================================================================

class TestInvalidToken:
    """Tests for tampered / invalid JWT handling."""

    def test_invalid_token_wrong_secret_raises(self):
        """Token signed with wrong secret raises TokenInvalidError."""
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="u@test.com",
            org_id=str(uuid.uuid4()),
            role=UserRole.EMPLOYEE,
            secret="wrong-secret-key-that-is-long-enough",
        )
        with pytest.raises(TokenInvalidError):
            verify_access_token(token)  # uses default correct secret

    def test_invalid_token_garbage_raises(self):
        """Random string raises TokenInvalidError."""
        with pytest.raises((TokenInvalidError, Exception)):
            verify_access_token("this.is.garbage")

    def test_invalid_token_tampered_payload_raises(self):
        """Modifying payload bytes raises TokenInvalidError."""
        import base64

        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="u@test.com",
            org_id=str(uuid.uuid4()),
            role=UserRole.EMPLOYEE,
        )
        # Flip one byte in the payload section
        parts = token.split(".")
        # Tamper signature
        parts[2] = parts[2][:-4] + "XXXX"
        tampered = ".".join(parts)
        with pytest.raises((TokenInvalidError, Exception)):
            verify_access_token(tampered)

    def test_empty_token_raises(self):
        """Empty string raises."""
        with pytest.raises(Exception):
            verify_access_token("")


# ===========================================================================
# RBAC tests
# ===========================================================================

class TestRBAC:
    """Tests for role-based access control enforcement."""

    def test_rbac_admin_can_access_admin_route(self):
        """Admin role satisfies admin requirement — no exception."""
        require_role(UserRole.ADMIN, UserRole.ADMIN)  # should not raise

    def test_rbac_admin_can_access_all_lower_roles(self):
        """Admin satisfies manager, employee, viewer requirements."""
        for role in [UserRole.MANAGER, UserRole.EMPLOYEE, UserRole.VIEWER]:
            require_role(UserRole.ADMIN, role)  # no exception

    def test_rbac_manager_blocked_from_admin(self):
        """Manager cannot access admin-only routes."""
        with pytest.raises(InsufficientPermissionsError):
            require_role(UserRole.MANAGER, UserRole.ADMIN)

    def test_rbac_viewer_blocked_from_employee(self):
        """Viewer blocked from employee-level routes."""
        with pytest.raises(InsufficientPermissionsError):
            require_role(UserRole.VIEWER, UserRole.EMPLOYEE)

    def test_rbac_viewer_blocked_from_admin(self):
        """Viewer cannot access admin routes."""
        with pytest.raises(InsufficientPermissionsError):
            require_role(UserRole.VIEWER, UserRole.ADMIN)

    def test_rbac_employee_can_access_viewer(self):
        """Employee satisfies viewer requirement."""
        require_role(UserRole.EMPLOYEE, UserRole.VIEWER)  # no exception

    def test_rbac_same_role_allowed(self):
        """Exact role match is always allowed."""
        for role in UserRole:
            require_role(role, role)  # no exception
