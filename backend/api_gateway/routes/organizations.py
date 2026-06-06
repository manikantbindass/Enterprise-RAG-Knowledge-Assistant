"""
Organization management routes — proxied to organization-service.

GET    /api/v1/organizations              (admin only — list all orgs)
POST   /api/v1/organizations              (admin only — create org)
GET    /api/v1/organizations/{org_id}     (admin or org member)
PUT    /api/v1/organizations/{org_id}     (admin only)
DELETE /api/v1/organizations/{org_id}     (admin only)
GET    /api/v1/organizations/{org_id}/members
POST   /api/v1/organizations/{org_id}/members
DELETE /api/v1/organizations/{org_id}/members/{user_id}
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from dependencies import (
    ActiveUserDep,
    AdminDep,
    OrgProxyDep,
    RequestIdDep,
)
from exceptions import ForbiddenException, NotFoundException

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateOrganizationRequest(BaseModel):
    """Payload for creating a new organization."""

    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(
        ...,
        min_length=2,
        max_length=60,
        pattern=r"^[a-z0-9\-]+$",
        description="URL-safe slug (lowercase, hyphens only)",
    )
    description: str | None = Field(None, max_length=1000)
    max_users: int = Field(default=100, ge=1, le=10_000)
    settings: dict[str, Any] | None = None


class UpdateOrganizationRequest(BaseModel):
    """Partial org update."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    max_users: int | None = Field(None, ge=1, le=10_000)
    is_active: bool | None = None
    settings: dict[str, Any] | None = None


class AddMemberRequest(BaseModel):
    """Add a user to an organization."""

    user_id: str
    role: str = Field(default="user", pattern="^(admin|manager|user)$")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OrganizationResponse(BaseModel):
    """Full organization record."""

    org_id: str
    name: str
    slug: str
    description: str | None
    max_users: int
    member_count: int
    is_active: bool
    created_at: str
    updated_at: str
    settings: dict[str, Any] | None


class PaginatedOrgsResponse(BaseModel):
    """Paginated list of organizations."""

    items: list[OrganizationResponse]
    total: int
    page: int
    page_size: int
    pages: int


class MemberResponse(BaseModel):
    """Organization member record."""

    user_id: str
    email: str
    full_name: str
    role: str
    joined_at: str


class PaginatedMembersResponse(BaseModel):
    """Paginated list of org members."""

    items: list[MemberResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DeleteResponse(BaseModel):
    """Generic deletion acknowledgement."""

    message: str


# ---------------------------------------------------------------------------
# Helper: verify caller can access org
# ---------------------------------------------------------------------------


def _assert_org_access(user: "CurrentUser", org_id: str) -> None:
    """Admin can access any org; member can only access their own org."""
    from dependencies import CurrentUser

    if user.role == "admin":
        return
    if user.org_id != org_id:
        raise ForbiddenException("Access to this organization is not permitted")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedOrgsResponse,
    summary="List all organizations (admin only)",
)
async def list_organizations(
    proxy: OrgProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> PaginatedOrgsResponse:
    """Paginated list of all organizations. Admin only."""
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if search:
        params["search"] = search
    if is_active is not None:
        params["is_active"] = is_active

    response = await proxy.request(
        "GET",
        "/organizations",
        authorization=f"Bearer {admin.token}",
        params=params,
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return PaginatedOrgsResponse(**response.json())


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization (admin only)",
)
async def create_organization(
    payload: CreateOrganizationRequest,
    proxy: OrgProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> OrganizationResponse:
    """Create a new tenant organization."""
    log = logger.bind(request_id=request_id, admin_id=admin.user_id)
    log.info("create_org", slug=payload.slug)

    response = await proxy.request(
        "POST",
        "/organizations",
        json=payload.model_dump(exclude_none=True),
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 409:
        from exceptions import ConflictException
        raise ConflictException(f"Organization slug '{payload.slug}' already taken")

    proxy.raise_for_upstream(response)
    data = response.json()
    log.info("create_org_success", org_id=data.get("org_id"))
    return OrganizationResponse(**data)


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Get organization details",
)
async def get_organization(
    org_id: str,
    proxy: OrgProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> OrganizationResponse:
    """Get organization by ID. Admin or org member only."""
    _assert_org_access(current_user, org_id)

    response = await proxy.request(
        "GET",
        f"/organizations/{org_id}",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Organization '{org_id}' not found")

    proxy.raise_for_upstream(response)
    return OrganizationResponse(**response.json())


@router.put(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Update organization (admin only)",
)
async def update_organization(
    org_id: str,
    payload: UpdateOrganizationRequest,
    proxy: OrgProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> OrganizationResponse:
    """Update organization settings. Admin only."""
    log = logger.bind(request_id=request_id, admin_id=admin.user_id, org_id=org_id)
    log.info("update_org")

    response = await proxy.request(
        "PUT",
        f"/organizations/{org_id}",
        json=payload.model_dump(exclude_none=True),
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Organization '{org_id}' not found")

    proxy.raise_for_upstream(response)
    return OrganizationResponse(**response.json())


@router.delete(
    "/{org_id}",
    response_model=DeleteResponse,
    summary="Delete organization (admin only)",
)
async def delete_organization(
    org_id: str,
    proxy: OrgProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> DeleteResponse:
    """Soft-delete an organization and cascade-deactivate its members."""
    log = logger.bind(request_id=request_id, admin_id=admin.user_id, org_id=org_id)
    log.info("delete_org")

    response = await proxy.request(
        "DELETE",
        f"/organizations/{org_id}",
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Organization '{org_id}' not found")

    proxy.raise_for_upstream(response)
    log.info("delete_org_success")
    return DeleteResponse(message=f"Organization '{org_id}' deleted successfully")


@router.get(
    "/{org_id}/members",
    response_model=PaginatedMembersResponse,
    summary="List organization members",
)
async def list_members(
    org_id: str,
    proxy: OrgProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedMembersResponse:
    """List members of an organization. Admin or org member."""
    _assert_org_access(current_user, org_id)

    response = await proxy.request(
        "GET",
        f"/organizations/{org_id}/members",
        authorization=f"Bearer {current_user.token}",
        params={"page": page, "page_size": page_size},
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Organization '{org_id}' not found")

    proxy.raise_for_upstream(response)
    return PaginatedMembersResponse(**response.json())


@router.post(
    "/{org_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add member to organization (admin only)",
)
async def add_member(
    org_id: str,
    payload: AddMemberRequest,
    proxy: OrgProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> MemberResponse:
    """Add an existing user to an organization."""
    response = await proxy.request(
        "POST",
        f"/organizations/{org_id}/members",
        json=payload.model_dump(),
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException("Organization or user not found")
    if response.status_code == 409:
        from exceptions import ConflictException
        raise ConflictException("User is already a member of this organization")

    proxy.raise_for_upstream(response)
    return MemberResponse(**response.json())


@router.delete(
    "/{org_id}/members/{user_id}",
    response_model=DeleteResponse,
    summary="Remove member from organization (admin only)",
)
async def remove_member(
    org_id: str,
    user_id: str,
    proxy: OrgProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> DeleteResponse:
    """Remove a user from an organization."""
    response = await proxy.request(
        "DELETE",
        f"/organizations/{org_id}/members/{user_id}",
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException("Organization or member not found")

    proxy.raise_for_upstream(response)
    return DeleteResponse(message=f"Member '{user_id}' removed from organization")
