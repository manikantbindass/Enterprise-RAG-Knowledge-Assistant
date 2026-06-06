"""
Auth routes — proxied to auth-service.

POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me
POST   /api/v1/auth/forgot-password
POST   /api/v1/auth/reset-password
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator

from dependencies import (
    AuthProxyDep,
    ConfigDep,
    CurrentUserDep,
    RequestIdDep,
    get_current_user,
)
from exceptions import UnauthorizedException, UpstreamServiceException

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """New user registration payload."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=200)
    organization_id: str | None = Field(None, description="Org to join on registration")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    """Credential-based login payload."""

    email: EmailStr
    password: str = Field(..., min_length=1)
    remember_me: bool = Field(default=False)


class RefreshRequest(BaseModel):
    """Token refresh payload."""

    refresh_token: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    """Request password reset email."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Consume reset token and set new password."""

    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TokenPair(BaseModel):
    """Access + refresh token pair returned on login / refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class UserProfile(BaseModel):
    """Minimal user profile returned from /auth/me."""

    user_id: str
    email: str
    full_name: str
    role: str
    org_id: str | None
    is_active: bool
    created_at: str


class RegisterResponse(BaseModel):
    """Response after successful registration."""

    message: str
    user_id: str


class MessageResponse(BaseModel):
    """Generic success message."""

    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    payload: RegisterRequest,
    proxy: AuthProxyDep,
    request_id: RequestIdDep,
) -> RegisterResponse:
    """
    Create a new user account.

    Proxies to auth-service POST /auth/register.
    Returns 409 if email already exists.
    """
    log = logger.bind(request_id=request_id, email=payload.email)
    log.info("register_attempt")

    response = await proxy.request(
        "POST",
        "/auth/register",
        json=payload.model_dump(),
        request_id=request_id,
    )

    if response.status_code == 409:
        from exceptions import ConflictException
        raise ConflictException("Email address already registered")

    proxy.raise_for_upstream(response)
    data: dict[str, Any] = response.json()
    log.info("register_success", user_id=data.get("user_id"))
    return RegisterResponse(**data)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Authenticate with email and password",
)
async def login(
    payload: LoginRequest,
    proxy: AuthProxyDep,
    request_id: RequestIdDep,
) -> TokenPair:
    """
    Exchange credentials for an access + refresh token pair.

    Proxies to auth-service POST /auth/login.
    Returns 401 on bad credentials, 403 if account deactivated.
    """
    log = logger.bind(request_id=request_id, email=payload.email)
    log.info("login_attempt")

    response = await proxy.request(
        "POST",
        "/auth/login",
        json=payload.model_dump(),
        request_id=request_id,
    )

    if response.status_code == 401:
        raise UnauthorizedException("Invalid email or password")
    if response.status_code == 403:
        from exceptions import ForbiddenException
        raise ForbiddenException("Account deactivated")

    proxy.raise_for_upstream(response)
    data: dict[str, Any] = response.json()
    log.info("login_success")
    return TokenPair(**data)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Invalidate the current access token",
)
async def logout(
    proxy: AuthProxyDep,
    request_id: RequestIdDep,
    current_user: CurrentUserDep,
) -> MessageResponse:
    """
    Revoke the current JWT (adds jti to denylist in Redis).

    Requires a valid access token in Authorization header.
    """
    log = logger.bind(request_id=request_id, user_id=current_user.user_id)
    log.info("logout_attempt")

    response = await proxy.request(
        "POST",
        "/auth/logout",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    proxy.raise_for_upstream(response)
    log.info("logout_success")
    return MessageResponse(message="Logged out successfully")


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Refresh access token using refresh token",
)
async def refresh_token(
    payload: RefreshRequest,
    proxy: AuthProxyDep,
    request_id: RequestIdDep,
) -> TokenPair:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    Old refresh token is invalidated (rotation).
    """
    log = logger.bind(request_id=request_id)
    log.info("token_refresh_attempt")

    response = await proxy.request(
        "POST",
        "/auth/refresh",
        json=payload.model_dump(),
        request_id=request_id,
    )

    if response.status_code == 401:
        raise UnauthorizedException("Refresh token is invalid or expired")

    proxy.raise_for_upstream(response)
    data: dict[str, Any] = response.json()
    log.info("token_refresh_success")
    return TokenPair(**data)


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get current authenticated user profile",
)
async def get_me(
    proxy: AuthProxyDep,
    request_id: RequestIdDep,
    current_user: CurrentUserDep,
) -> UserProfile:
    """
    Return the profile of the currently authenticated user.

    Proxies to auth-service GET /auth/me with forwarded JWT.
    """
    response = await proxy.request(
        "GET",
        "/auth/me",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return UserProfile(**response.json())


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request a password reset email",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    proxy: AuthProxyDep,
    request_id: RequestIdDep,
) -> MessageResponse:
    """
    Trigger a password reset email for the given address.

    Always returns 200 to avoid email enumeration.
    """
    await proxy.request(
        "POST",
        "/auth/forgot-password",
        json=payload.model_dump(),
        request_id=request_id,
    )
    # Return generic message regardless of whether email exists
    return MessageResponse(
        message="If that email address is registered, a reset link has been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password using a reset token",
)
async def reset_password(
    payload: ResetPasswordRequest,
    proxy: AuthProxyDep,
    request_id: RequestIdDep,
) -> MessageResponse:
    """
    Consume a one-time password reset token and set the new password.

    Token is invalidated after use.
    """
    response = await proxy.request(
        "POST",
        "/auth/reset-password",
        json=payload.model_dump(),
        request_id=request_id,
    )

    if response.status_code == 400:
        from exceptions import BadRequestException
        raise BadRequestException("Invalid or expired reset token")

    proxy.raise_for_upstream(response)
    return MessageResponse(message="Password reset successfully")
