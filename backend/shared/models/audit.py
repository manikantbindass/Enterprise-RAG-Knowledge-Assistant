"""
AuditLog SQLAlchemy model.

Immutable append-only record of all significant actions.
Used for compliance, security investigation, and analytics.

Never UPDATE or DELETE audit rows — only INSERT.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import TenantModel


class AuditLog(TenantModel):
    """
    Immutable audit trail entry.

    Records who did what, when, from where, and what changed.
    Partitioned by created_at in production (monthly partitions).

    Table is append-only — no updates, no deletes, no soft-delete.
    """

    __tablename__ = "audit_logs"

    __table_args__ = (
        # Fast lookup by actor
        Index("ix_audit_logs_actor_id", "actor_id"),
        # Fast lookup by resource
        Index("ix_audit_logs_resource_type_resource_id", "resource_type", "resource_id"),
        # Time-range queries
        Index("ix_audit_logs_created_at", "created_at"),
        # Org + time for compliance exports
        Index("ix_audit_logs_org_id_created_at", "org_id", "created_at"),
    )

    # ------------------------------------------------------------------ #
    # Actor                                                                 #
    # ------------------------------------------------------------------ #
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who performed the action (null for system actions)",
    )

    actor_email: Mapped[Optional[str]] = mapped_column(
        String(320),
        nullable=True,
        comment="Denormalized email — preserved after user deletion",
    )

    # ------------------------------------------------------------------ #
    # Action                                                                #
    # ------------------------------------------------------------------ #
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment=(
            "Action verb in dot notation: "
            "user.login, document.upload, conversation.create, org.settings.update"
        ),
    )

    # ------------------------------------------------------------------ #
    # Resource                                                              #
    # ------------------------------------------------------------------ #
    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of resource affected (e.g. 'document', 'user', 'conversation')",
    )

    resource_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="ID of the affected resource",
    )

    # ------------------------------------------------------------------ #
    # Change data                                                           #
    # ------------------------------------------------------------------ #
    before_state: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot of resource state BEFORE the action",
    )

    after_state: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot of resource state AFTER the action",
    )

    # ------------------------------------------------------------------ #
    # Request context                                                       #
    # ------------------------------------------------------------------ #
    request_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        comment="Correlation ID from X-Request-ID header",
    )

    ip_address: Mapped[Optional[str]] = mapped_column(
        INET,
        nullable=True,
        comment="Client IP address",
    )

    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="HTTP User-Agent string",
    )

    # ------------------------------------------------------------------ #
    # Outcome                                                               #
    # ------------------------------------------------------------------ #
    status_code: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        comment="HTTP response status code (if applicable)",
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error detail if the action failed",
    )

    # ------------------------------------------------------------------ #
    # Extra                                                                 #
    # ------------------------------------------------------------------ #
    extra: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional context — service-specific data",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"actor={self.actor_email!r} resource={self.resource_type}/{self.resource_id}>"
        )
