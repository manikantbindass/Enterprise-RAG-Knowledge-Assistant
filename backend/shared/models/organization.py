"""
Organization SQLAlchemy model.

Represents a tenant organization in the multi-tenant system.
All tenant-scoped data references this table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import BaseModel

if TYPE_CHECKING:
    from shared.models.document import Document
    from shared.models.user import User


class Organization(BaseModel):
    """
    Tenant organization.

    Each organization is an isolated tenant. Users, documents, conversations,
    and all other resources belong to exactly one organization.

    Plans control resource quotas (max_documents, max_users, max_storage_gb).
    """

    __tablename__ = "organizations"

    # ------------------------------------------------------------------ #
    # Identity                                                              #
    # ------------------------------------------------------------------ #
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable organization name",
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-safe unique identifier for the org (e.g. 'acme-corp')",
    )

    # ------------------------------------------------------------------ #
    # Plan / subscription                                                   #
    # ------------------------------------------------------------------ #
    plan: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="starter",
        server_default="starter",
        comment="Subscription plan: starter | professional | enterprise",
    )

    # ------------------------------------------------------------------ #
    # Configuration                                                         #
    # ------------------------------------------------------------------ #
    settings: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        server_default="{}",
        comment="Org-level feature flags and configuration",
    )

    # ------------------------------------------------------------------ #
    # Status                                                                #
    # ------------------------------------------------------------------ #
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Soft-disable an org without deleting data",
    )

    # ------------------------------------------------------------------ #
    # Quotas                                                                #
    # ------------------------------------------------------------------ #
    max_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1000,
        server_default="1000",
        comment="Maximum number of documents the org can upload",
    )

    max_users: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=25,
        server_default="25",
        comment="Maximum number of user accounts in this org",
    )

    max_storage_gb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Maximum storage quota in gigabytes",
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} slug={self.slug!r} plan={self.plan!r}>"
