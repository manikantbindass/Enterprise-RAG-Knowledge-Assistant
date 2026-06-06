"""
SQLAlchemy 2.0 base models using mapped_column and Mapped type hints.

BaseModel   — UUID primary key, timestamps
TenantModel — BaseModel + org_id foreign key for multi-tenancy
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class BaseModel(Base):
    """
    Abstract base for all ORM models.

    Provides:
    - UUID primary key (generated server-side for correctness)
    - created_at / updated_at with automatic server defaults
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
        comment="Primary key — UUID v4",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Row creation timestamp (UTC)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp (UTC)",
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"

    def to_dict(self) -> dict:
        """Return a plain dict of all column values. Useful for logging."""
        return {
            col.key: getattr(self, col.key)
            for col in self.__table__.columns  # type: ignore[attr-defined]
        }


class TenantModel(BaseModel):
    """
    Abstract base for all tenant-scoped models.

    Adds org_id FK so PostgreSQL RLS policies can filter per organization.
    Every table that holds tenant data must inherit from this.
    """

    __abstract__ = True

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant organization — FK to organizations.id",
    )
