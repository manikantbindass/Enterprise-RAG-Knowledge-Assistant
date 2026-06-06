"""
User management routes — proxied to user-service.

GET    /api/v1/users          (admin only — list all users)
POST   /api/v1/users          (admin only — create user)
GET    /api/v1/users/me       (current user's full profile)
PUT    /api/v1/users/me       (current user updates own profile)
GET    /api/v1/users/{id}     (admin or self)
PUT    /api/v1/users/{id}     (admin only)
DELETE /api/v1/users/{id}     (admin only)
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, EmailStr, Field

from dependencies import (
    ActiveUserDep,
    AdminDep,
    CurrentUser,
    RequestIdDep,
    UserProxyDep,
    require_role,
)
from exceptions import ForbiddenException, NotFoundException

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    """Admin-initiated user creation."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(default="user", pattern="^(admin|manager|user)$")
    org_id: str | None = None
    is_active: bool = Field(default=True)


class UpdateUserRequest(BaseModel):
    """Partial user update — all fields optional."""

    full_name: str | None = Field(None, min_length=1, max_length=200)
    role: str | None = Field(None, pattern="^(admin|manager|user)$")
    org_id: str | None = None
    is_active: bool | None = None
    avatar_url: str | None = None


class UpdateMeRequest(BaseModel):
    """Self-service profile update — cannot change role or active status."""

    full_name: str | None = Field(None, min_length=1, max_length=200)
    avatar_url: str | None = None
    preferences: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Full user record returned to clients."""

    user_id: str
    email: str
    full_name: str
    role: str
    org_id: str | None
    is_active: bool
    avatar_url: str | None
    created_at: str
    updated_at: str


class PaginatedUsersResponse(BaseModel):
    """Paginated list of users."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DeleteResponse(BaseModel):
    """Acknowledgement of deletion."""

    message: str
    user_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedUsersResponse,
    summary="List all users (admin only)",
)
async def list_users(
    proxy: UserProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(None, description="Search by name or email"),
    role: str | None = Query(None, pattern="^(admin|manager|user)$"),
    org_id: str | None = Query(None, description="Filter by organisation"),
    is_active: bool | None = Query(None),
) -> PaginatedUsersResponse:
    """
    List all users with pagination and filtering.
    Restricted to admin role.
    """
    params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
    }
    if search:
        params["search"] = search
    if role:
        params["role"] = role
    if org_id:
        params["org_id"] = org_id
    if is_active is not None:
        params["is_active"] = is_active

    response = await proxy.request(
        "GET",
        "/users",
        authorization=f"Bearer {admin.token}",
        params=params,
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return PaginatedUsersResponse(**response.json())


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
)
async def create_user(
    payload: CreateUserRequest,
    proxy: UserProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> UserResponse:
    """
    Admin creates a user directly (bypassing self-registration flow).
    """
    log = logger.bind(request_id=request_id, admin_id=admin.user_id)
    log.info("admin_create_user", email=payload.email)

    response = await proxy.request(
        "POST",
        "/users",
        json=payload.model_dump(),
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 409:
        from exceptions import ConflictException
        raise ConflictException("User with that email already exists")

    proxy.raise_for_upstream(response)
    data = response.json()
    log.info("admin_create_user_success", user_id=data.get("user_id"))
    return UserResponse(**data)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user's full profile",
)
async def get_me(
    proxy: UserProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> UserResponse:
    """Return the full profile of the authenticated user."""
    response = await proxy.request(
        "GET",
        "/users/me",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return UserResponse(**response.json())


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update current user's profile",
)
async def update_me(
    payload: UpdateMeRequest,
    proxy: UserProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> UserResponse:
    """Self-service profile update — cannot elevate own role."""
    response = await proxy.request(
        "PUT",
        "/users/me",
        json=payload.model_dump(exclude_none=True),
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return UserResponse(**response.json())


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
)
async def get_user(
    user_id: str,
    proxy: UserProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> UserResponse:
    """
    Get a user by ID.

    Admin can fetch any user; regular users can only fetch their own profile.
    """
    if current_user.role != "admin" and current_user.user_id != user_id:
        raise ForbiddenException("Cannot access another user's profile")

    response = await proxy.request(
        "GET",
        f"/users/{user_id}",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"User '{user_id}' not found")

    proxy.raise_for_upstream(response)
    return UserResponse(**response.json())


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user by ID (admin only)",
)
async def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    proxy: UserProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> UserResponse:
    """Admin updates any user's profile, role, or active status."""
    log = logger.bind(request_id=request_id, admin_id=admin.user_id, target=user_id)
    log.info("admin_update_user")

    response = await proxy.request(
        "PUT",
        f"/users/{user_id}",
        json=payload.model_dump(exclude_none=True),
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"User '{user_id}' not found")

    proxy.raise_for_upstream(response)
    return UserResponse(**response.json())


@router.delete(
    "/{user_id}",
    response_model=DeleteResponse,
    summary="Delete user by ID (admin only)",
)
async def delete_user(
    user_id: str,
    proxy: UserProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> DeleteResponse:
    """
    Soft-delete a user account.

    Admins cannot delete their own account via this endpoint.
    """
    if admin.user_id == user_id:
        raise ForbiddenException("Cannot delete your own account via admin endpoint")

    log = logger.bind(request_id=request_id, admin_id=admin.user_id, target=user_id)
    log.info("admin_delete_user")

    response = await proxy.request(
        "DELETE",
        f"/users/{user_id}",
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"User '{user_id}' not found")

    proxy.raise_for_upstream(response)
    log.info("admin_delete_user_success")
    return DeleteResponse(message="User deleted successfully", user_id=user_id)
