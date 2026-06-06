"""
Pydantic v2 schemas for the Auth Service.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Request schemas ────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=1, max_length=256)
    org_id: UUID | None = None


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=150, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    org_id: UUID | None = None
    role: str = Field(default="viewer", pattern="^(admin|editor|viewer)$")

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class VerifyTokenRequest(BaseModel):
    token: str = Field(..., min_length=1)


class FeedbackRequest(BaseModel):
    token: str


# ── Response schemas ───────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    scope: str = "openid profile email"


class UserInfo(BaseModel):
    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    org_id: UUID | None = None
    roles: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime


class LoginResponse(BaseModel):
    user: UserInfo
    tokens: TokenResponse


class VerifyTokenResponse(BaseModel):
    valid: bool
    user_id: UUID | None = None
    username: str | None = None
    org_id: UUID | None = None
    roles: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class RegisterResponse(BaseModel):
    user: UserInfo
    message: str = "User registered successfully"
