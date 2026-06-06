"""
Organization Business Logic Service.

Manages org CRUD, usage calculation, and limit enforcement.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.config import get_config
from user_service.exceptions import (
    OrgLimitExceededError,
    OrganizationAlreadyExistsError,
    OrganizationNotFoundError,
)
from user_service.models.schemas import (
    OrgMemberResponse,
    OrgMembersResponse,
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationStats,
    OrganizationUpdate,
    UsageMetrics,
)
from user_service.repositories.organization_repository import (
    OrganizationModel,
    OrganizationRepository,
)
from user_service.repositories.user_repository import UserRepository

logger = structlog.get_logger(__name__)


def _to_response(
    org: OrganizationModel,
    stats: OrganizationStats | None = None,
) -> OrganizationResponse:
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        plan=org.plan,  # type: ignore[arg-type]
        status=org.status,  # type: ignore[arg-type]
        settings=org.settings,
        metadata=org.metadata_,
        stats=stats,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


class OrganizationService:
    """Orchestrates organization management and usage tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self._org_repo = OrganizationRepository(session)
        self._user_repo = UserRepository(session)
        self._session = session
        self._cfg = get_config()

    async def list_organizations(
        self,
        status: str | None = None,
        plan: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> OrganizationListResponse:
        """List all orgs — super-admin only."""
        page_size = min(page_size, self._cfg.max_page_size)
        items, total = await self._org_repo.list_organizations(
            status=status, plan=plan, page=page, page_size=page_size
        )
        return OrganizationListResponse(
            items=[_to_response(o) for o in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )

    async def get_organization(self, org_id: uuid.UUID) -> OrganizationResponse:
        """Fetch org with live stats."""
        org = await self._org_repo.get_by_id(org_id)
        if not org:
            raise OrganizationNotFoundError(str(org_id))

        raw_stats = await self._org_repo.get_live_stats(org_id)
        stats = OrganizationStats(
            total_users=raw_stats["total_users"],
            active_users=raw_stats["active_users"],
            total_documents=raw_stats["total_documents"],
            total_storage_bytes=raw_stats["total_storage_bytes"],
            total_queries_this_month=raw_stats["total_queries_this_month"],
        )
        return _to_response(org, stats=stats)

    async def create_organization(self, payload: OrganizationCreate) -> OrganizationResponse:
        """Create new organization. Slug must be globally unique."""
        existing = await self._org_repo.get_by_slug(payload.slug)
        if existing:
            raise OrganizationAlreadyExistsError(payload.slug)

        org = await self._org_repo.create(
            name=payload.name,
            slug=payload.slug,
            plan=payload.plan.value,
            settings=payload.settings.model_dump(),
            metadata=payload.metadata,
        )
        await self._session.commit()
        logger.info("org_service.create", org_id=str(org.id), slug=payload.slug)
        return _to_response(org)

    async def update_organization(
        self, org_id: uuid.UUID, payload: OrganizationUpdate
    ) -> OrganizationResponse:
        """Update org fields."""
        org = await self._org_repo.get_by_id(org_id)
        if not org:
            raise OrganizationNotFoundError(str(org_id))

        updates: dict = {}
        if payload.name is not None:
            updates["name"] = payload.name
        if payload.plan is not None:
            updates["plan"] = payload.plan.value
        if payload.status is not None:
            updates["status"] = payload.status.value
        if payload.settings is not None:
            updates["settings"] = payload.settings.model_dump()
        if payload.metadata is not None:
            updates["metadata_"] = payload.metadata

        if not updates:
            return _to_response(org)

        updated = await self._org_repo.update(org_id, updates)
        await self._session.commit()
        return _to_response(updated)  # type: ignore[arg-type]

    async def get_usage_metrics(self, org_id: uuid.UUID) -> UsageMetrics:
        """
        Calculate current usage vs org limits.

        Computes utilization percentages and flags near-limit resources.
        """
        org = await self._org_repo.get_by_id(org_id)
        if not org:
            raise OrganizationNotFoundError(str(org_id))

        settings = org.settings
        raw = await self._org_repo.get_live_stats(org_id)

        max_users = settings.get("max_users", self._cfg.default_max_users)
        max_docs = settings.get("max_documents", self._cfg.default_max_documents)
        max_storage_gb = settings.get("max_storage_gb", self._cfg.default_max_storage_gb)
        max_queries = settings.get(
            "max_queries_per_month", self._cfg.default_max_queries_per_month
        )

        cur_users = raw["total_users"]
        cur_docs = raw["total_documents"]
        cur_storage_bytes = raw["total_storage_bytes"]
        cur_storage_gb = cur_storage_bytes / (1024**3)
        cur_queries = raw["total_queries_this_month"]

        def pct(cur: float, mx: float) -> float:
            return round((cur / mx * 100) if mx > 0 else 0.0, 2)

        near_limit = [
            r
            for r, c, m in [
                ("users", cur_users, max_users),
                ("documents", cur_docs, max_docs),
                ("storage", cur_storage_gb, max_storage_gb),
                ("queries", cur_queries, max_queries),
            ]
            if m > 0 and (c / m) >= 0.80
        ]

        # Overage cost estimation (simplified — real billing via Stripe)
        overage_queries = max(0, cur_queries - max_queries)
        overage_storage = max(0.0, cur_storage_gb - max_storage_gb)
        overage_cost = (overage_queries / 1000) * 0.01 + overage_storage * 0.023  # $/GB/month

        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        return UsageMetrics(
            organization_id=org_id,
            period_start=period_start,
            period_end=now,
            current_users=cur_users,
            max_users=max_users,
            users_utilization_pct=pct(cur_users, max_users),
            current_documents=cur_docs,
            max_documents=max_docs,
            documents_utilization_pct=pct(cur_docs, max_docs),
            current_storage_bytes=cur_storage_bytes,
            current_storage_gb=round(cur_storage_gb, 4),
            max_storage_gb=max_storage_gb,
            storage_utilization_pct=pct(cur_storage_gb, max_storage_gb),
            queries_this_month=cur_queries,
            max_queries_per_month=max_queries,
            queries_utilization_pct=pct(cur_queries, max_queries),
            plan=org.plan,  # type: ignore[arg-type]
            overage_queries=overage_queries,
            overage_storage_gb=round(overage_storage, 4),
            estimated_overage_cost_usd=round(overage_cost, 4),
            near_limit_resources=near_limit,
        )

    async def check_user_limit(self, org_id: uuid.UUID) -> None:
        """Raise OrgLimitExceededError if org is at user capacity."""
        org = await self._org_repo.get_by_id(org_id)
        if not org:
            raise OrganizationNotFoundError(str(org_id))

        max_users = org.settings.get("max_users", self._cfg.default_max_users)
        cur_users = await self._user_repo.count_by_org(org_id)

        if cur_users >= max_users:
            raise OrgLimitExceededError("users", max_users)

    async def get_members(
        self,
        org_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> OrgMembersResponse:
        """List all members of an organization."""
        org = await self._org_repo.get_by_id(org_id)
        if not org:
            raise OrganizationNotFoundError(str(org_id))

        page_size = min(page_size, self._cfg.max_page_size)
        users, total = await self._user_repo.list_users(
            organization_id=org_id, page=page, page_size=page_size
        )

        members = [
            OrgMemberResponse(
                user_id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=u.role,  # type: ignore[arg-type]
                status=u.status,  # type: ignore[arg-type]
                joined_at=u.created_at,
                last_login_at=u.last_login_at,
            )
            for u in users
        ]

        return OrgMembersResponse(
            items=members,
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )
