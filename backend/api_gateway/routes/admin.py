"""
Admin routes — internal operations, metrics, and oversight.

GET    /api/v1/admin/metrics           system-wide metrics snapshot
GET    /api/v1/admin/audit-logs        paginated audit log entries
GET    /api/v1/admin/users             all users with extended info
GET    /api/v1/admin/processing-jobs   document processing job queue
POST   /api/v1/admin/processing-jobs/{job_id}/retry   retry failed job
"""

from __future__ import annotations

from typing import Any, Literal

import structlog
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from dependencies import (
    AdminDep,
    AnalyticsProxyDep,
    DocumentProxyDep,
    RequestIdDep,
    UserProxyDep,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class MetricsSnapshot(BaseModel):
    """System-wide operational metrics."""

    total_users: int
    active_users_24h: int
    total_organizations: int
    total_documents: int
    documents_processing: int
    documents_failed: int
    total_conversations: int
    conversations_24h: int
    total_messages: int
    messages_24h: int
    avg_response_time_ms: float | None
    search_requests_24h: int
    storage_bytes_used: int
    vector_count: int
    collected_at: str


class AuditLogEntry(BaseModel):
    """Single audit log record."""

    log_id: str
    timestamp: str
    user_id: str | None
    user_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    user_agent: str | None
    status_code: int | None
    details: dict[str, Any] | None


class PaginatedAuditLogsResponse(BaseModel):
    """Paginated audit log response."""

    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    pages: int


class ProcessingJob(BaseModel):
    """Document processing pipeline job."""

    job_id: str
    doc_id: str
    filename: str
    status: Literal["pending", "processing", "ready", "failed", "cancelled"]
    stage: str | None
    progress_percent: float | None
    error_message: str | None
    retries: int
    enqueued_at: str
    started_at: str | None
    completed_at: str | None
    org_id: str | None


class PaginatedJobsResponse(BaseModel):
    """Paginated processing jobs response."""

    items: list[ProcessingJob]
    total: int
    page: int
    page_size: int
    pages: int


class AdminUserEntry(BaseModel):
    """Extended user record for admin dashboard."""

    user_id: str
    email: str
    full_name: str
    role: str
    org_id: str | None
    org_name: str | None
    is_active: bool
    last_login_at: str | None
    login_count: int
    created_at: str


class PaginatedAdminUsersResponse(BaseModel):
    """Paginated admin user list."""

    items: list[AdminUserEntry]
    total: int
    page: int
    page_size: int
    pages: int


class RetryJobResponse(BaseModel):
    """Job retry acknowledgement."""

    job_id: str
    message: str
    new_status: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/metrics",
    response_model=MetricsSnapshot,
    summary="Get system-wide metrics snapshot (admin only)",
)
async def get_metrics(
    proxy: AnalyticsProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> MetricsSnapshot:
    """
    Return a consolidated metrics snapshot across all services.

    Aggregated by the analytics-service. Used for the admin dashboard.
    """
    log = logger.bind(request_id=request_id, admin_id=admin.user_id)
    log.info("admin_metrics_fetch")

    response = await proxy.request(
        "GET",
        "/analytics/metrics/snapshot",
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return MetricsSnapshot(**response.json())


@router.get(
    "/audit-logs",
    response_model=PaginatedAuditLogsResponse,
    summary="List audit log entries (admin only)",
)
async def list_audit_logs(
    proxy: AnalyticsProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: str | None = Query(None, description="Filter by user"),
    action: str | None = Query(None, description="Filter by action type"),
    resource_type: str | None = Query(None),
    date_from: str | None = Query(None, description="ISO-8601"),
    date_to: str | None = Query(None, description="ISO-8601"),
) -> PaginatedAuditLogsResponse:
    """
    Retrieve paginated audit log entries.

    Supports filtering by user, action type, resource type, and date range.
    """
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if user_id:
        params["user_id"] = user_id
    if action:
        params["action"] = action
    if resource_type:
        params["resource_type"] = resource_type
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    response = await proxy.request(
        "GET",
        "/analytics/audit-logs",
        authorization=f"Bearer {admin.token}",
        params=params,
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return PaginatedAuditLogsResponse(**response.json())


@router.get(
    "/users",
    response_model=PaginatedAdminUsersResponse,
    summary="List all users with extended admin info (admin only)",
)
async def admin_list_users(
    proxy: UserProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(None),
    role: str | None = Query(None, pattern="^(admin|manager|user)$"),
    org_id: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> PaginatedAdminUsersResponse:
    """
    Extended user list for admin dashboard.

    Includes org name, last login, and login count (enriched by user-service).
    """
    params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "extended": True,
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
        "/users/admin/extended",
        authorization=f"Bearer {admin.token}",
        params=params,
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return PaginatedAdminUsersResponse(**response.json())


@router.get(
    "/processing-jobs",
    response_model=PaginatedJobsResponse,
    summary="List document processing jobs (admin only)",
)
async def list_processing_jobs(
    proxy: DocumentProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(
        None,
        alias="status",
        pattern="^(pending|processing|ready|failed|cancelled)$",
    ),
    org_id: str | None = Query(None),
) -> PaginatedJobsResponse:
    """
    View the document ingestion job queue.

    Filter by status to see failed/stuck jobs that need intervention.
    """
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if status_filter:
        params["status"] = status_filter
    if org_id:
        params["org_id"] = org_id

    response = await proxy.request(
        "GET",
        "/documents/admin/jobs",
        authorization=f"Bearer {admin.token}",
        params=params,
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return PaginatedJobsResponse(**response.json())


@router.post(
    "/processing-jobs/{job_id}/retry",
    response_model=RetryJobResponse,
    summary="Retry a failed processing job (admin only)",
)
async def retry_processing_job(
    job_id: str,
    proxy: DocumentProxyDep,
    request_id: RequestIdDep,
    admin: AdminDep,
) -> RetryJobResponse:
    """
    Re-enqueue a failed document processing job.

    Resets retry counter and re-submits to the processing queue.
    """
    log = logger.bind(
        request_id=request_id,
        admin_id=admin.user_id,
        job_id=job_id,
    )
    log.info("retry_processing_job")

    response = await proxy.request(
        "POST",
        f"/documents/admin/jobs/{job_id}/retry",
        authorization=f"Bearer {admin.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        from exceptions import NotFoundException
        raise NotFoundException(f"Processing job '{job_id}' not found")

    proxy.raise_for_upstream(response)
    data = response.json()
    log.info("retry_processing_job_success", new_status=data.get("new_status"))
    return RetryJobResponse(**data)
