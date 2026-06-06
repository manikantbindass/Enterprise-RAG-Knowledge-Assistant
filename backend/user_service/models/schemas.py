"""
User & Organization Pydantic Schemas.

Request/response models with full validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    SUSPENDED = "suspended"


class OrgPlan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class OrgStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── User Schemas ──────────────────────────────────────────────────────────────

class UserCreate(BaseSchema):
    """Request body for creating a new user (admin only)."""

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    role: UserRole = UserRole.VIEWER
    organization_id: uuid.UUID
    password: str = Field(min_length=8, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Enforce password complexity rules."""
        errors: list[str] = []
        if not any(c.isupper() for c in v):
            errors.append("must contain uppercase letter")
        if not any(c.islower() for c in v):
            errors.append("must contain lowercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("must contain digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in v):
            errors.append("must contain special character")
        if errors:
            raise ValueError("; ".join(errors))
        return v

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class UserUpdate(BaseSchema):
    """Request body for updating a user (admin or self)."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    role: UserRole | None = None
    status: UserStatus | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v else None


class UserProfileUpdate(BaseSchema):
    """Request body for self-profile update (restricted fields)."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v else None


class UserResponse(BaseSchema):
    """User response — never exposes password hash."""

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    status: UserStatus
    organization_id: uuid.UUID
    metadata: dict[str, Any]
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseSchema):
    """Paginated list of users."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    pages: int


class UserActivitySummary(BaseSchema):
    """Summary of user activity — derived from audit logs."""

    user_id: uuid.UUID
    total_queries: int
    total_documents_uploaded: int
    total_documents_deleted: int
    last_query_at: datetime | None
    last_login_at: datetime | None
    most_used_resources: list[dict[str, Any]]


# ── Organization Schemas ──────────────────────────────────────────────────────

class OrgSettings(BaseSchema):
    """Organization-level configurable settings."""

    max_users: int = Field(default=50, ge=1, le=10_000)
    max_documents: int = Field(default=10_000, ge=1)
    max_storage_gb: float = Field(default=100.0, ge=0.1)
    max_queries_per_month: int = Field(default=100_000, ge=1)
    allowed_domains: list[str] = Field(default_factory=list)
    sso_enabled: bool = False
    mfa_required: bool = False
    departments: list[str] = Field(default_factory=list)
    custom_branding: dict[str, Any] = Field(default_factory=dict)


class OrganizationCreate(BaseSchema):
    """Request body for creating an organization."""

    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(
        min_length=2,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
        description="URL-safe identifier: lowercase alphanumeric + hyphens",
    )
    plan: OrgPlan = OrgPlan.STARTER
    settings: OrgSettings = Field(default_factory=OrgSettings)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class OrganizationUpdate(BaseSchema):
    """Request body for updating an organization."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    plan: OrgPlan | None = None
    status: OrgStatus | None = None
    settings: OrgSettings | None = None
    metadata: dict[str, Any] | None = None


class OrganizationStats(BaseSchema):
    """Live statistics for an organization."""

    total_users: int
    active_users: int
    total_documents: int
    total_storage_bytes: int
    total_queries_this_month: int


class OrganizationResponse(BaseSchema):
    """Full org response with stats."""

    id: uuid.UUID
    name: str
    slug: str
    plan: OrgPlan
    status: OrgStatus
    settings: dict[str, Any]
    metadata: dict[str, Any]
    stats: OrganizationStats | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationListResponse(BaseSchema):
    """Paginated list of organizations."""

    items: list[OrganizationResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ── Usage / Billing Schemas ───────────────────────────────────────────────────

class UsageMetrics(BaseSchema):
    """Usage metrics for an organization — used for billing and quota enforcement."""

    organization_id: uuid.UUID
    period_start: datetime
    period_end: datetime

    # Users
    current_users: int
    max_users: int
    users_utilization_pct: float

    # Documents
    current_documents: int
    max_documents: int
    documents_utilization_pct: float

    # Storage
    current_storage_bytes: int
    current_storage_gb: float
    max_storage_gb: float
    storage_utilization_pct: float

    # Queries
    queries_this_month: int
    max_queries_per_month: int
    queries_utilization_pct: float

    # Billing
    plan: OrgPlan
    overage_queries: int
    overage_storage_gb: float
    estimated_overage_cost_usd: float

    # Alerts
    near_limit_resources: list[str]  # resources at >80% usage


class OrgMemberResponse(BaseSchema):
    """Member entry in org member list."""

    user_id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    status: UserStatus
    joined_at: datetime
    last_login_at: datetime | None


class OrgMembersResponse(BaseSchema):
    """Paginated org member list."""

    items: list[OrgMemberResponse]
    total: int
    page: int
    page_size: int
    pages: int
