"""
Audit Logs Router.

Read-only API for querying audit logs, stats, and export jobs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from audit_service.config import get_config
from audit_service.models.schemas import (
    AuditExportRequest,
    AuditExportResponse,
    AuditLogListResponse,
    AuditLogResponse,
    AuditStats,
)
from audit_service.services.audit_service import AuditService, _export_jobs

logger = structlog.get_logger(__name__)
cfg = get_config()

router = APIRouter(prefix="/audit", tags=["audit"])


# ── Shared dependencies ───────────────────────────────────────────────────────

from jose import JWTError, jwt
from fastapi import Header


class CurrentUser:
    def __init__(self, user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> None:
        self.user_id = user_id
        self.org_id = org_id
        self.role = role

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "super_admin")


async def get_db() -> AsyncSession:  # type: ignore[misc]
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    engine = create_async_engine(cfg.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token,
            cfg.jwt_secret_key,
            algorithms=[cfg.jwt_algorithm],
            audience=cfg.jwt_audience,
            issuer=cfg.jwt_issuer,
        )
        return CurrentUser(
            user_id=uuid.UUID(payload["sub"]),
            org_id=uuid.UUID(payload["org_id"]),
            role=payload["role"],
        )
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def _get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> AuditService:
    return AuditService(session)


# ── GET /audit/logs ───────────────────────────────────────────────────────────

@router.get(
    "/logs",
    response_model=AuditLogListResponse,
    summary="Paginated audit logs with filters",
)
async def list_audit_logs(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[AuditService, Depends(_get_service)],
    user_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    success: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> AuditLogListResponse:
    """
    Query audit logs for the caller's organization.

    Supports partition pruning when date_from/date_to are provided.
    """
    return await svc.list_logs(
        organization_id=current_user.org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        date_from=date_from,
        date_to=date_to,
        success=success,
        page=page,
        page_size=page_size,
    )


# ── GET /audit/logs/{id} ──────────────────────────────────────────────────────

@router.get(
    "/logs/{log_id}",
    response_model=AuditLogResponse,
    summary="Single audit log entry",
)
async def get_audit_log(
    log_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[AuditService, Depends(_get_service)],
) -> AuditLogResponse:
    """Fetch a single audit log entry by ID (org-scoped)."""
    return await svc.get_log_entry(log_id, current_user.org_id)


# ── GET /audit/stats ──────────────────────────────────────────────────────────

@router.get(
    "/stats",
    response_model=AuditStats,
    summary="Aggregate audit statistics",
)
async def get_audit_stats(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[AuditService, Depends(_get_service)],
    date_from: datetime = Query(
        default=None,
        description="Default: 30 days ago",
    ),
    date_to: datetime = Query(
        default=None,
        description="Default: now",
    ),
) -> AuditStats:
    """Aggregate stats: events per day, top users, top resources, common actions."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    if date_to is None:
        date_to = now
    if date_from is None:
        date_from = now - timedelta(days=30)

    return await svc.get_stats(
        organization_id=current_user.org_id,
        date_from=date_from,
        date_to=date_to,
    )


# ── POST /audit/export ────────────────────────────────────────────────────────

@router.post(
    "/export",
    response_model=AuditExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Export audit logs to CSV/JSONL (async)",
)
async def export_audit_logs(
    request: AuditExportRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[AuditService, Depends(_get_service)],
) -> AuditExportResponse:
    """
    Initiate async export. Returns job_id immediately.

    Poll GET /audit/export/{job_id} for status and download link.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required for export")

    return await svc.initiate_export(current_user.org_id, request)


# ── GET /audit/export/{job_id} ────────────────────────────────────────────────

@router.get(
    "/export/{job_id}",
    summary="Check export job status / download file",
)
async def get_export_status(
    job_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """Poll export job status. Returns download URL when completed."""
    job = _export_jobs.get(str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    if job.get("status") == "completed" and job.get("file_path"):
        return {
            "job_id": str(job_id),
            "status": "completed",
            "download_url": f"/audit/export/{job_id}/download",
            "row_count": job.get("row_count"),
        }
    return {"job_id": str(job_id), "status": job.get("status"), "error": job.get("error")}


@router.get(
    "/export/{job_id}/download",
    summary="Download completed export file",
)
async def download_export(
    job_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FileResponse:
    """Stream the export file to client."""
    job = _export_jobs.get(str(job_id))
    if not job or job.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Export not ready")

    file_path = job["file_path"]
    fmt = job["request"].format
    return FileResponse(
        path=file_path,
        media_type="text/csv" if fmt == "csv" else "application/x-ndjson",
        filename=f"audit_export_{job_id}.{fmt}",
    )
