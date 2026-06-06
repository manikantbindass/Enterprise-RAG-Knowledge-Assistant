"""
Audit Service Schemas.

Request/response models for audit log querying and export.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Inbound event (from RabbitMQ) ─────────────────────────────────────────────

class AuditEventPayload(BaseSchema):
    """Schema for audit events consumed from RabbitMQ."""

    organization_id: uuid.UUID
    user_id: uuid.UUID | None = None
    action: str = Field(min_length=1, max_length=128, description="dot.notation action name")
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: str | None = Field(default=None, max_length=255)
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    ip_address: str | None = Field(default=None, max_length=45)
    user_agent: str | None = Field(default=None, max_length=512)
    success: bool = True
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None  # falls back to server time if None


# ── API Response Schemas ──────────────────────────────────────────────────────

class AuditLogResponse(BaseSchema):
    """Single audit log entry response."""

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    success: bool
    error_message: str | None
    metadata: dict[str, Any]
    created_at: datetime


class AuditLogListResponse(BaseSchema):
    """Paginated audit log response."""

    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ── Stats ─────────────────────────────────────────────────────────────────────

class DailyActionCount(BaseSchema):
    """Actions per day bucket."""

    date: str  # ISO date string YYYY-MM-DD
    action: str
    count: int
    success_count: int
    failure_count: int


class TopUser(BaseSchema):
    """User with highest activity count."""

    user_id: uuid.UUID
    action_count: int
    last_action_at: datetime


class TopResource(BaseSchema):
    """Most accessed resource."""

    resource_type: str
    resource_id: str | None
    access_count: int


class AuditStats(BaseSchema):
    """Aggregate audit statistics."""

    organization_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    total_events: int
    success_events: int
    failure_events: int
    unique_users: int
    actions_per_day: list[DailyActionCount]
    top_users: list[TopUser]
    top_resources: list[TopResource]
    most_common_actions: list[dict[str, Any]]


# ── Export ────────────────────────────────────────────────────────────────────

class AuditExportRequest(BaseSchema):
    """Request to export audit logs as CSV."""

    date_from: datetime
    date_to: datetime
    user_id: uuid.UUID | None = None
    action: str | None = None
    resource_type: str | None = None
    success: bool | None = None
    format: str = Field(default="csv", pattern="^(csv|jsonl)$")


class AuditExportResponse(BaseSchema):
    """Response after initiating export."""

    job_id: uuid.UUID
    status: str
    message: str
    estimated_rows: int | None = None
