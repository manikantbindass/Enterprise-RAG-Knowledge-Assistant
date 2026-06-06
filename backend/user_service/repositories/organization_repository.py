"""
Organization Repository — Database operations for organizations.

Uses SQLAlchemy 2.0 async ORM. Org-level aggregations done via
window functions to avoid N+1 queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = structlog.get_logger(__name__)

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


class Base(DeclarativeBase):
    pass


class OrganizationModel(Base):
    """ORM model for the organizations table."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="starter")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_orgs_status", "status"),)


class OrganizationRepository:
    """All database operations for organizations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, org_id: uuid.UUID) -> OrganizationModel | None:
        """Fetch org by PK, excluding soft-deleted."""
        stmt = select(OrganizationModel).where(
            OrganizationModel.id == org_id,
            OrganizationModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> OrganizationModel | None:
        """Fetch org by unique slug."""
        stmt = select(OrganizationModel).where(
            OrganizationModel.slug == slug,
            OrganizationModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_organizations(
        self,
        status: str | None = None,
        plan: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[OrganizationModel], int]:
        """Paginated org list for super-admin."""
        conditions = [OrganizationModel.deleted_at.is_(None)]
        if status:
            conditions.append(OrganizationModel.status == status)
        if plan:
            conditions.append(OrganizationModel.plan == plan)

        where_clause = and_(*conditions)

        total: int = (
            await self._session.execute(
                select(func.count(OrganizationModel.id)).where(where_clause)
            )
        ).scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            select(OrganizationModel)
            .where(where_clause)
            .order_by(OrganizationModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all(), total  # type: ignore[return-value]

    async def create(
        self,
        name: str,
        slug: str,
        plan: str,
        settings: dict[str, Any],
        metadata: dict[str, Any],
    ) -> OrganizationModel:
        """Insert new organization row."""
        org = OrganizationModel(
            name=name,
            slug=slug,
            plan=plan,
            status="active",
            settings=settings,
            metadata_=metadata,
        )
        self._session.add(org)
        await self._session.flush()
        await self._session.refresh(org)
        logger.info("org.created", org_id=str(org.id), slug=slug)
        return org

    async def update(
        self,
        org_id: uuid.UUID,
        updates: dict[str, Any],
    ) -> OrganizationModel | None:
        """Partial update organization."""
        updates["updated_at"] = datetime.now(timezone.utc)
        stmt = (
            update(OrganizationModel)
            .where(
                OrganizationModel.id == org_id,
                OrganizationModel.deleted_at.is_(None),
            )
            .values(**updates)
            .returning(OrganizationModel)
        )
        result = await self._session.execute(stmt)
        org = result.scalar_one_or_none()
        if org:
            logger.info("org.updated", org_id=str(org_id))
        return org

    async def get_live_stats(self, org_id: uuid.UUID) -> dict[str, Any]:
        """
        Aggregate live stats from related tables.

        Uses a single CTE-based query to avoid multiple round-trips.
        Falls back to zeros for missing tables (documents, usage_metrics).
        """
        # User counts from users table
        from sqlalchemy import text

        raw = await self._session.execute(
            text(
                """
                SELECT
                    COUNT(u.id) FILTER (WHERE u.deleted_at IS NULL)                AS total_users,
                    COUNT(u.id) FILTER (WHERE u.deleted_at IS NULL
                                         AND u.status = 'active')                  AS active_users,
                    COALESCE(d.total_documents, 0)                                 AS total_documents,
                    COALESCE(d.total_storage_bytes, 0)                             AS total_storage_bytes,
                    COALESCE(um.queries_this_month, 0)                             AS total_queries_this_month
                FROM organizations o
                LEFT JOIN users u ON u.organization_id = o.id
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS total_documents,
                        COALESCE(SUM(file_size), 0) AS total_storage_bytes
                    FROM documents
                    WHERE organization_id = :org_id
                      AND deleted_at IS NULL
                ) d ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COALESCE(SUM(query_count), 0) AS queries_this_month
                    FROM usage_metrics
                    WHERE organization_id = :org_id
                      AND period_start >= date_trunc('month', NOW())
                ) um ON TRUE
                WHERE o.id = :org_id
                  AND o.deleted_at IS NULL
                GROUP BY d.total_documents, d.total_storage_bytes, um.queries_this_month
                """
            ),
            {"org_id": str(org_id)},
        )
        row = raw.fetchone()
        if not row:
            return {
                "total_users": 0,
                "active_users": 0,
                "total_documents": 0,
                "total_storage_bytes": 0,
                "total_queries_this_month": 0,
            }
        return {
            "total_users": row.total_users,
            "active_users": row.active_users,
            "total_documents": row.total_documents,
            "total_storage_bytes": row.total_storage_bytes,
            "total_queries_this_month": row.total_queries_this_month,
        }
