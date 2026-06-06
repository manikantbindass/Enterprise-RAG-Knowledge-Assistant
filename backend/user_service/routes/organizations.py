"""
Organizations Router — CRUD and usage endpoints.
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
    require_super_admin,
)
from user_service.exceptions import (
    OrgLimitExceededError,
    OrganizationAlreadyExistsError,
    OrganizationNotFoundError,
)
from user_service.models.schemas import (
    OrgMembersResponse,
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdate,
    UsageMetrics,
)
from user_service.services.organization_service import OrganizationService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> OrganizationService:
    return OrganizationService(session)


# ── GET /organizations — Super-admin only ─────────────────────────────────────

@router.get(
    "",
    response_model=OrganizationListResponse,
    summary="List all organizations (super-admin)",
)
async def list_organizations(
    _: Annotated[CurrentUser, Depends(require_super_admin)],
    svc: Annotated[OrganizationService, Depends(_get_service)],
    status: str | None = Query(default=None),
    plan: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> OrganizationListResponse:
    """List all organizations. Restricted to super-admins."""
    return await svc.list_organizations(status=status, plan=plan, page=page, page_size=page_size)


# ── POST /organizations ───────────────────────────────────────────────────────

@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization",
)
async def create_organization(
    payload: OrganizationCreate,
    _: Annotated[CurrentUser, Depends(require_super_admin)],
    svc: Annotated[OrganizationService, Depends(_get_service)],
) -> OrganizationResponse:
    """Create a new organization. Super-admin only."""
    try:
        return await svc.create_organization(payload)
    except OrganizationAlreadyExistsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ── GET /organizations/{id} ───────────────────────────────────────────────────

@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Get organization with stats",
)
async def get_organization(
    org_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[OrganizationService, Depends(_get_service)],
) -> OrganizationResponse:
    """
    Fetch org details with live stats.

    Users can only view their own org. Super-admins unrestricted.
    """
    if not current_user.is_super_admin and org_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        return await svc.get_organization(org_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ── PUT /organizations/{id} ───────────────────────────────────────────────────

@router.put(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Update organization",
)
async def update_organization(
    org_id: uuid.UUID,
    payload: OrganizationUpdate,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    svc: Annotated[OrganizationService, Depends(_get_service)],
) -> OrganizationResponse:
    """Update organization settings. Admins can only update their own org."""
    if not current_user.is_super_admin and org_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        return await svc.update_organization(org_id, payload)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ── GET /organizations/{id}/usage ─────────────────────────────────────────────

@router.get(
    "/{org_id}/usage",
    response_model=UsageMetrics,
    summary="Get usage metrics and billing info",
)
async def get_usage(
    org_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    svc: Annotated[OrganizationService, Depends(_get_service)],
) -> UsageMetrics:
    """
    Current usage vs limits with overage cost estimation.

    Admins can see their own org. Super-admins can see any org.
    """
    if not current_user.is_super_admin and org_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        return await svc.get_usage_metrics(org_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ── GET /organizations/{id}/members ──────────────────────────────────────────

@router.get(
    "/{org_id}/members",
    response_model=OrgMembersResponse,
    summary="List all org members",
)
async def get_members(
    org_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
    svc: Annotated[OrganizationService, Depends(_get_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> OrgMembersResponse:
    """List all members (active users) in an organization."""
    if not current_user.is_super_admin and org_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        return await svc.get_members(org_id, page=page, page_size=page_size)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
