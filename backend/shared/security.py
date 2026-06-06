"""
JWT security, password hashing, and API key management.

Functions:
- create_access_token()   — short-lived JWT
- create_refresh_token()  — long-lived JWT stored in HttpOnly cookie
- verify_token()          — validate and decode JWT
- get_current_user()      — FastAPI dependency (route-level auth)
- hash_password()         — bcrypt hash
- verify_password()       — bcrypt verify
- generate_api_key()      — random 40-char API key
- hash_api_key()          — sha256 for zero-knowledge storage
- verify_api_key()        — compare provided key against stored hash
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from shared.exceptions import ForbiddenError, UnauthorizedError

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password with bcrypt (12 rounds).

    Args:
        plain_password: User's raw password.

    Returns:
        bcrypt hash string suitable for database storage.
    """
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a bcrypt hash.

    Args:
        plain_password: User-supplied raw password.
        hashed_password: bcrypt hash from database.

    Returns:
        True if password matches.
    """
    return _pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# API key generation and verification
# ---------------------------------------------------------------------------

_API_KEY_PREFIX = "rag_"
_API_KEY_LENGTH = 40


def generate_api_key() -> tuple[str, str]:
    """
    Generate a cryptographically random API key.

    Returns:
        Tuple of (raw_key, hashed_key).
        Store hashed_key in the database, return raw_key to the user ONCE.

    Format: rag_<40 random chars>
    """
    raw_key = _API_KEY_PREFIX + secrets.token_urlsafe(_API_KEY_LENGTH)
    hashed = hash_api_key(raw_key)
    return raw_key, hashed


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of API key for zero-knowledge storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """
    Verify API key against stored SHA-256 hash.

    Uses secrets.compare_digest to prevent timing attacks.
    """
    candidate_hash = hash_api_key(raw_key)
    return secrets.compare_digest(candidate_hash, stored_hash)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------


def _build_token(
    *,
    subject: str,
    token_type: str,
    extra_claims: dict[str, Any],
    secret_key: str,
    algorithm: str,
    expire_delta: timedelta,
    issuer: str,
    audience: str,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + expire_delta

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iss": issuer,
        "aud": audience,
        "type": token_type,
        **extra_claims,
    }

    return jwt.encode(payload, secret_key, algorithm=algorithm)


def create_access_token(
    *,
    user_id: str,
    org_id: str,
    email: str,
    role: str,
    jwt_secret: str,
    jwt_algorithm: str = "HS256",
    expire_minutes: int = 30,
    issuer: str = "rag-knowledge-assistant",
    audience: str = "rag-api",
) -> str:
    """
    Create a short-lived JWT access token.

    Claims include user_id (sub), org_id, email, role for use
    in middleware and route dependencies without a DB lookup.

    Args:
        user_id: User UUID string.
        org_id: Organization UUID string.
        email: User email (for logging, not auth).
        role: User role string.
        jwt_secret: HMAC signing secret.
        jwt_algorithm: Signing algorithm (default HS256).
        expire_minutes: Token lifetime in minutes.
        issuer: JWT iss claim.
        audience: JWT aud claim.

    Returns:
        Signed JWT string.
    """
    return _build_token(
        subject=user_id,
        token_type="access",
        extra_claims={
            "org_id": org_id,
            "email": email,
            "role": role,
        },
        secret_key=jwt_secret,
        algorithm=jwt_algorithm,
        expire_delta=timedelta(minutes=expire_minutes),
        issuer=issuer,
        audience=audience,
    )


def create_refresh_token(
    *,
    user_id: str,
    org_id: str,
    jwt_secret: str,
    jwt_algorithm: str = "HS256",
    expire_days: int = 7,
    issuer: str = "rag-knowledge-assistant",
    audience: str = "rag-api",
) -> str:
    """
    Create a long-lived JWT refresh token.

    Refresh tokens carry minimal claims — only sub and org_id.
    Store these in HttpOnly cookies, not localStorage.

    Args:
        user_id: User UUID string.
        org_id: Organization UUID string.
        jwt_secret: HMAC signing secret.
        jwt_algorithm: Signing algorithm.
        expire_days: Token lifetime in days.
        issuer: JWT iss claim.
        audience: JWT aud claim.

    Returns:
        Signed JWT string.
    """
    return _build_token(
        subject=user_id,
        token_type="refresh",
        extra_claims={"org_id": org_id},
        secret_key=jwt_secret,
        algorithm=jwt_algorithm,
        expire_delta=timedelta(days=expire_days),
        issuer=issuer,
        audience=audience,
    )


def verify_token(
    token: str,
    *,
    jwt_secret: str,
    jwt_algorithm: str = "HS256",
    expected_type: str = "access",
    audience: str = "rag-api",
    issuer: str = "rag-knowledge-assistant",
) -> dict[str, Any]:
    """
    Verify JWT signature, expiry, type, issuer, and audience.

    Args:
        token: Raw JWT string.
        jwt_secret: Signing secret.
        jwt_algorithm: Algorithm to verify with.
        expected_type: 'access' or 'refresh'.
        audience: Expected aud claim.
        issuer: Expected iss claim.

    Returns:
        Decoded payload dict.

    Raises:
        UnauthorizedError: Token invalid, expired, wrong type, or tampered.
    """
    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=[jwt_algorithm],
            audience=audience,
            issuer=issuer,
        )
    except JWTError as exc:
        logger.warning("jwt_verification_failed", error=str(exc))
        raise UnauthorizedError("Invalid or expired token") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedError(
            f"Wrong token type: expected '{expected_type}', got '{payload.get('type')}'"
        )

    return payload


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

_http_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """
    Parsed JWT claims attached to each authenticated request.

    Injected by get_current_user() dependency.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        self.user_id: str = payload["sub"]
        self.org_id: str = payload["org_id"]
        self.email: str = payload.get("email", "")
        self.role: str = payload.get("role", "viewer")
        self.jti: str = payload.get("jti", "")

    def has_role(self, *roles: str) -> bool:
        """Return True if user's role is in the allowed roles list."""
        return self.role in roles

    def require_role(self, *roles: str) -> None:
        """Raise ForbiddenError if user lacks required role."""
        if not self.has_role(*roles):
            raise ForbiddenError(
                f"Action requires one of: {', '.join(roles)}",
                required_role=", ".join(roles),
            )

    def __repr__(self) -> str:
        return f"<CurrentUser user_id={self.user_id!r} role={self.role!r}>"


def make_get_current_user(
    jwt_secret: str,
    jwt_algorithm: str = "HS256",
    audience: str = "rag-api",
    issuer: str = "rag-knowledge-assistant",
):
    """
    Factory that creates a FastAPI dependency for JWT authentication.

    Usage in service main.py:
        from shared.security import make_get_current_user
        from shared.config import get_settings

        settings = get_settings()
        get_current_user = make_get_current_user(
            jwt_secret=settings.JWT_SECRET_KEY,
            jwt_algorithm=settings.JWT_ALGORITHM,
        )

    Then in routes:
        @router.get("/me")
        async def get_me(user: CurrentUser = Depends(get_current_user)):
            return {"user_id": user.user_id}
    """

    async def get_current_user(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
        request: Request = None,  # type: ignore[assignment]
    ) -> CurrentUser:
        if not credentials:
            raise UnauthorizedError("Missing Authorization header")

        payload = verify_token(
            credentials.credentials,
            jwt_secret=jwt_secret,
            jwt_algorithm=jwt_algorithm,
            expected_type="access",
            audience=audience,
            issuer=issuer,
        )

        user = CurrentUser(payload)

        # Also update request.state for middleware / logging
        if request is not None:
            request.state.user_id = user.user_id
            request.state.org_id = user.org_id

        logger.debug(
            "user_authenticated",
            user_id=user.user_id,
            org_id=user.org_id,
            role=user.role,
        )

        return user

    return get_current_user
