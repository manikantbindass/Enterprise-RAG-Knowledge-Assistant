"""
Audit Business Logic Service.

Handles event ingestion, stats aggregation, and CSV export orchestration.
"""

from __future__ import annotations

import asyncio
import csv
import io
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from audit_service.config import get_config
from audit_service.models.schemas import (
    AuditEventPayload,
    AuditExportRequest,
    AuditExportResponse,
    AuditLogListResponse,
    AuditLogResponse,
    AuditStats,
    DailyActionCount,
    TopResource,
    TopUser,
)
from audit_service.repositories.audit_repository import AuditLogModel, AuditRepository

logger = structlog.get_logger(__name__)
cfg = get_config()

# In-memory export job store (replace with Redis in production)
_export_jobs: dict[str, dict[str, Any]] = {}


def _model_to_response(log: AuditLogModel) -> AuditLogResponse:
    return AuditLogResponse(
        id=log.id,
        organization_id=log.organization_id,
        user_id=log.user_id,
        action=log.action,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        before_state=log.before_state,
        after_state=log.after_state,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        success=log.success,
        error_message=log.error_message,
        metadata=log.metadata_,
        created_at=log.created_at,
    )


class AuditService:
    """Audit log business operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditRepository(session)
        self._session = session

    async def log_event(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        before_state: dict[str, Any] | None,
        after_state: dict[str, Any] | None,
        ip_address: str | None,
        user_agent: str | None,
        success: bool,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> uuid.UUID:
        """
        Insert a single audit event synchronously.

        For high-throughput use the bulk insert path via the worker.
        """
        event_id = uuid.uuid4()
        event = {
            "id": event_id,
            "organization_id": org_id,
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "before_state": before_state,
            "after_state": after_state,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "success": success,
            "error_message": error_message,
            "metadata_": metadata or {},
            "created_at": timestamp or datetime.now(timezone.utc),
        }
        await self._repo.bulk_insert([event])
        await self._session.commit()
        logger.info("audit.logged", event_id=str(event_id), action=action)
        return event_id

    async def get_log_entry(
        self, log_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AuditLogResponse:
        """Fetch single log entry, scoped to org."""
        log = await self._repo.get_by_id(log_id, organization_id)
        if not log:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Audit log '{log_id}' not found")
        return _model_to_response(log)

    async def list_logs(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        success: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditLogListResponse:
        """Paginated audit log query."""
        page_size = min(page_size, cfg.max_page_size)
        items, total = await self._repo.list_logs(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            date_from=date_from,
            date_to=date_to,
            success=success,
            page=page,
            page_size=page_size,
        )
        return AuditLogListResponse(
            items=[_model_to_response(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )

    async def get_stats(
        self,
        organization_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> AuditStats:
        """Compute aggregate stats for the given org + date range."""
        raw = await self._repo.get_stats(organization_id, date_from, date_to)
        s = raw["summary"]

        daily = [
            DailyActionCount(
                date=r.date,
                action=r.action,
                count=r.count,
                success_count=r.success_count,
                failure_count=r.failure_count,
            )
            for r in raw["daily"]
        ]
        top_users = [
            TopUser(
                user_id=uuid.UUID(str(r.user_id)),
                action_count=r.action_count,
                last_action_at=r.last_action_at,
            )
            for r in raw["top_users"]
        ]
        top_resources = [
            TopResource(
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                access_count=r.access_count,
            )
            for r in raw["top_resources"]
        ]
        common_actions = [
            {"action": r.action, "count": r.cnt} for r in raw["common_actions"]
        ]

        return AuditStats(
            organization_id=organization_id,
            period_start=date_from,
            period_end=date_to,
            total_events=s.total_events if s else 0,
            success_events=s.success_events if s else 0,
            failure_events=s.failure_events if s else 0,
            unique_users=s.unique_users if s else 0,
            actions_per_day=daily,
            top_users=top_users,
            top_resources=top_resources,
            most_common_actions=common_actions,
        )

    async def initiate_export(
        self,
        organization_id: uuid.UUID,
        request: AuditExportRequest,
    ) -> AuditExportResponse:
        """
        Start async CSV/JSONL export job.

        Returns job_id immediately; actual export happens in background.
        """
        job_id = uuid.uuid4()
        _export_jobs[str(job_id)] = {
            "status": "pending",
            "organization_id": organization_id,
            "request": request,
            "created_at": datetime.now(timezone.utc),
            "file_path": None,
        }

        # Fire-and-forget background task
        asyncio.create_task(
            self._run_export(job_id, organization_id, request),
            name=f"audit-export-{job_id}",
        )

        return AuditExportResponse(
            job_id=job_id,
            status="pending",
            message="Export job queued. Poll /audit/export/{job_id} for status.",
        )

    async def _run_export(
        self,
        job_id: uuid.UUID,
        organization_id: uuid.UUID,
        request: AuditExportRequest,
    ) -> None:
        """
        Background export: stream rows → write file → update job status.

        Memory-efficient: processes in batches of 1000.
        """
        job_key = str(job_id)
        _export_jobs[job_key]["status"] = "running"

        os.makedirs(cfg.export_temp_dir, exist_ok=True)
        file_path = os.path.join(cfg.export_temp_dir, f"{job_id}.{request.format}")

        try:
            row_count = 0
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                if request.format == "csv":
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "id", "organization_id", "user_id", "action",
                            "resource_type", "resource_id", "ip_address",
                            "user_agent", "success", "error_message", "created_at",
                        ]
                    )
                    async for batch in self._repo.stream_for_export(
                        organization_id=organization_id,
                        date_from=request.date_from,
                        date_to=request.date_to,
                        user_id=request.user_id,
                        action=request.action,
                        resource_type=request.resource_type,
                        success=request.success,
                    ):
                        for row in batch:
                            writer.writerow(
                                [
                                    row.id, row.organization_id, row.user_id,
                                    row.action, row.resource_type, row.resource_id,
                                    row.ip_address, row.user_agent, row.success,
                                    row.error_message, row.created_at.isoformat(),
                                ]
                            )
                            row_count += 1
                else:
                    # JSONL
                    import json
                    async for batch in self._repo.stream_for_export(
                        organization_id=organization_id,
                        date_from=request.date_from,
                        date_to=request.date_to,
                        user_id=request.user_id,
                        action=request.action,
                        resource_type=request.resource_type,
                        success=request.success,
                    ):
                        for row in batch:
                            f.write(
                                json.dumps(
                                    {
                                        "id": str(row.id),
                                        "action": row.action,
                                        "resource_type": row.resource_type,
                                        "success": row.success,
                                        "created_at": row.created_at.isoformat(),
                                    }
                                )
                                + "\n"
                            )
                            row_count += 1

            _export_jobs[job_key].update(
                {
                    "status": "completed",
                    "file_path": file_path,
                    "row_count": row_count,
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            logger.info("audit.export.completed", job_id=job_key, rows=row_count)

        except Exception as exc:
            logger.error("audit.export.failed", job_id=job_key, error=str(exc))
            _export_jobs[job_key].update(
                {"status": "failed", "error": str(exc)}
            )
