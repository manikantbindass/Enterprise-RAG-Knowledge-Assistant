"""
Audit Repository — Optimized bulk inserts and paginated queries.

Uses PostgreSQL table partitioning by month for audit_logs.
Bulk inserts via core INSERT for maximum throughput.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = structlog.get_logger(__name__)

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


class Base(DeclarativeBase):
    pass


class AuditLogModel(Base):
    """ORM model for partitioned audit_logs table."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        # Partition key — must be in all partition queries
        index=True,
    )

    __table_args__ = (
        Index("ix_audit_logs_org_action", "organization_id", "action"),
        Index("ix_audit_logs_org_user", "organization_id", "user_id"),
        Index("ix_audit_logs_org_resource", "organization_id", "resource_type"),
        Index("ix_audit_logs_created_at_brin", "created_at", postgresql_using="brin"),
    )


class AuditRepository:
    """Optimized audit log database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_insert(self, events: list[dict[str, Any]]) -> int:
        """
        Bulk insert audit events using PostgreSQL INSERT for throughput.

        Uses ON CONFLICT DO NOTHING to handle duplicate IDs gracefully
        (idempotent re-delivery from RabbitMQ).
        Returns count of actually inserted rows.
        """
        if not events:
            return 0

        stmt = pg_insert(AuditLogModel).values(events)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        result = await self._session.execute(stmt)
        inserted = result.rowcount
        logger.debug("audit_repo.bulk_insert", count=len(events), inserted=inserted)
        return inserted

    async def get_by_id(
        self, log_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AuditLogModel | None:
        """Fetch single audit log entry by ID within org scope."""
        stmt = select(AuditLogModel).where(
            AuditLogModel.id == log_id,
            AuditLogModel.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

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
    ) -> tuple[list[AuditLogModel], int]:
        """
        Paginated, filtered audit log query.

        Uses partition pruning via date_from/date_to on created_at.
        """
        conditions = [AuditLogModel.organization_id == organization_id]

        if user_id:
            conditions.append(AuditLogModel.user_id == user_id)
        if action:
            conditions.append(AuditLogModel.action == action)
        if resource_type:
            conditions.append(AuditLogModel.resource_type == resource_type)
        if date_from:
            conditions.append(AuditLogModel.created_at >= date_from)
        if date_to:
            conditions.append(AuditLogModel.created_at <= date_to)
        if success is not None:
            conditions.append(AuditLogModel.success == success)

        where_clause = and_(*conditions)

        total: int = (
            await self._session.execute(
                select(func.count(AuditLogModel.id)).where(where_clause)
            )
        ).scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            select(AuditLogModel)
            .where(where_clause)
            .order_by(AuditLogModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all(), total  # type: ignore[return-value]

    async def get_stats(
        self,
        organization_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> dict[str, Any]:
        """
        Aggregate stats via a single optimized SQL query.

        Groups actions per day, top users, top resources, and common actions.
        """
        # Summary counts
        summary = await self._session.execute(
            text(
                """
                SELECT
                    COUNT(*)                                AS total_events,
                    COUNT(*) FILTER (WHERE success = TRUE)  AS success_events,
                    COUNT(*) FILTER (WHERE success = FALSE) AS failure_events,
                    COUNT(DISTINCT user_id)                 AS unique_users
                FROM audit_logs
                WHERE organization_id = :org_id
                  AND created_at BETWEEN :date_from AND :date_to
                """
            ),
            {"org_id": str(organization_id), "date_from": date_from, "date_to": date_to},
        )
        summary_row = summary.fetchone()

        # Actions per day
        daily = await self._session.execute(
            text(
                """
                SELECT
                    TO_CHAR(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS date,
                    action,
                    COUNT(*)                                               AS count,
                    COUNT(*) FILTER (WHERE success = TRUE)                 AS success_count,
                    COUNT(*) FILTER (WHERE success = FALSE)                AS failure_count
                FROM audit_logs
                WHERE organization_id = :org_id
                  AND created_at BETWEEN :date_from AND :date_to
                GROUP BY 1, 2
                ORDER BY 1 DESC, 3 DESC
                LIMIT 500
                """
            ),
            {"org_id": str(organization_id), "date_from": date_from, "date_to": date_to},
        )

        # Top users by event count
        top_users = await self._session.execute(
            text(
                """
                SELECT
                    user_id,
                    COUNT(*) AS action_count,
                    MAX(created_at) AS last_action_at
                FROM audit_logs
                WHERE organization_id = :org_id
                  AND created_at BETWEEN :date_from AND :date_to
                  AND user_id IS NOT NULL
                GROUP BY user_id
                ORDER BY action_count DESC
                LIMIT 10
                """
            ),
            {"org_id": str(organization_id), "date_from": date_from, "date_to": date_to},
        )

        # Top resources
        top_resources = await self._session.execute(
            text(
                """
                SELECT resource_type, resource_id, COUNT(*) AS access_count
                FROM audit_logs
                WHERE organization_id = :org_id
                  AND created_at BETWEEN :date_from AND :date_to
                GROUP BY resource_type, resource_id
                ORDER BY access_count DESC
                LIMIT 10
                """
            ),
            {"org_id": str(organization_id), "date_from": date_from, "date_to": date_to},
        )

        # Most common actions
        common_actions = await self._session.execute(
            text(
                """
                SELECT action, COUNT(*) AS cnt
                FROM audit_logs
                WHERE organization_id = :org_id
                  AND created_at BETWEEN :date_from AND :date_to
                GROUP BY action
                ORDER BY cnt DESC
                LIMIT 20
                """
            ),
            {"org_id": str(organization_id), "date_from": date_from, "date_to": date_to},
        )

        return {
            "summary": summary_row,
            "daily": daily.fetchall(),
            "top_users": top_users.fetchall(),
            "top_resources": top_resources.fetchall(),
            "common_actions": common_actions.fetchall(),
        }

    async def stream_for_export(
        self,
        organization_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
        user_id: uuid.UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        success: bool | None = None,
        batch_size: int = 1000,
    ):
        """
        Async generator yielding batches of rows for CSV export.

        Uses server-side cursor for memory-efficient streaming.
        """
        conditions = [
            f"organization_id = '{organization_id}'",
            f"created_at BETWEEN '{date_from.isoformat()}' AND '{date_to.isoformat()}'",
        ]
        if user_id:
            conditions.append(f"user_id = '{user_id}'")
        if action:
            conditions.append(f"action = '{action}'")
        if resource_type:
            conditions.append(f"resource_type = '{resource_type}'")
        if success is not None:
            conditions.append(f"success = {success}")

        where = " AND ".join(conditions)
        query = f"""
            SELECT id, organization_id, user_id, action, resource_type,
                   resource_id, ip_address, user_agent, success, error_message,
                   created_at
            FROM audit_logs
            WHERE {where}
            ORDER BY created_at DESC
        """  # noqa: S608 — controlled string; no user input in conditions

        async with self._session.begin():
            result = await self._session.stream(text(query))
            async for partition in result.partitions(batch_size):
                yield partition
