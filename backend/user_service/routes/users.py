"""
Users Router — CRUD endpoints for user management.

Route handlers are thin: validate input → call service → return response.
No business logic here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.dependencies import (
    CurrentUser,
    get_current_user,
    get_db,
    require_admin,
)
from user_service.exceptions import (
    InsufficientPermissionsError,
    SelfDeletionError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from user_service.models.schemas import (
    UserActivitySummary,
    UserCreate,
    UserListResponse,
    UserProfileUpdate,
    UserResponse,
    UserUpdate,
)
from user_service.services.user_service import UserService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


def _get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> UserService:
    return UserService(session)


# ── GET /users/me — must be defined BEFORE /users/{id} ───────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_my_profile(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[UserService, Depends(_get_service)],
) -> UserResponse:
    """Return the authenticated user's own profile."""
    try:
        return await svc.get_user(current_user.user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update own profile",
)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[UserService, Depends(_get_service)],
) -> UserResponse:
    """Update authenticated user's own full_name or metadata."""
    try:
        return await svc.update_own_profile(
            user_id=current_user.user_id,
            full_name=payload.full_name,
            metadata=payload.metadata,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ── GET /users — Admin only ───────────────────────────────────────────────────

@router.get(
    "",
    response_model=UserListResponse,
    summary="List users (admin only)",
)
async def list_users(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    svc: Annotated[UserService, Depends(_get_service)],
    role: str | None = Query(default=None, description="Filter by role"),
    status: str | None = Query(default=None, description="Filter by status"),
    search: str | None = Query(default=None, description="Search by name/email"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> UserListResponse:
    """
    Paginated user list.

    Super-admins see all orgs. Admins only see their own org.
    """
    org_filter = None if current_user.is_super_admin else current_user.organization_id
    return await svc.list_users(
        organization_id=org_filter,
        role=role,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )


# ── POST /users — Admin only ──────────────────────────────────────────────────

@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create user (admin only)",
)
async def create_user(
    payload: UserCreate,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    svc: Annotated[UserService, Depends(_get_service)],
) -> UserResponse:
    """
    Create a new user in an organization.

    Non-super-admins can only create users in their own org.
    """
    if not current_user.is_super_admin:
        payload = payload.model_copy(
            update={"organization_id": current_user.organization_id}
        )
    try:
        return await svc.create_user(payload)
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ── GET /users/{id} ───────────────────────────────────────────────────────────

@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
)
async def get_user(
    user_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[UserService, Depends(_get_service)],
) -> UserResponse:
    """
    Fetch user by ID.

    Users can only fetch their own profile or users in their org (admins).
    """
    try:
        user = await svc.get_user(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    # Non-admin can only see themselves
    if not current_user.is_admin and user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    # Admin can only see their org (unless super_admin)
    if current_user.is_admin and not current_user.is_super_admin:
        if user.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return user


# ── PUT /users/{id} ───────────────────────────────────────────────────────────

@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user (admin only)",
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    svc: Annotated[UserService, Depends(_get_service)],
) -> UserResponse:
    """Update user fields. Admins can change role/status. Super-admins unrestricted."""
    try:
        return await svc.update_user(user_id, payload)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ── DELETE /users/{id} ────────────────────────────────────────────────────────

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete user (admin only)",
)
async def delete_user(
    user_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    svc: Annotated[UserService, Depends(_get_service)],
) -> None:
    """Soft-delete a user. The row is retained for audit compliance."""
    try:
        await svc.soft_delete_user(user_id, current_user.user_id)
    except (UserNotFoundError, SelfDeletionError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ── GET /users/{id}/activity ──────────────────────────────────────────────────

@router.get(
    "/{user_id}/activity",
    response_model=UserActivitySummary,
    summary="Get user activity summary",
)
async def get_user_activity(
    user_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[UserService, Depends(_get_service)],
) -> UserActivitySummary:
    """
    Aggregated activity stats for a user from audit_logs.

    Users can only view their own. Admins see their org's users.
    """
    if not current_user.is_admin and user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        return await svc.get_user_activity(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
