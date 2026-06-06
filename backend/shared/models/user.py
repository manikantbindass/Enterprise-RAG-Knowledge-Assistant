"""
User SQLAlchemy model with role-based access control.

UserRole enum maps to PostgreSQL native enum type.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import BaseModel

if TYPE_CHECKING:
    from shared.models.conversation import Conversation
    from shared.models.organization import Organization


class UserRole(str, enum.Enum):
    """
    RBAC roles — ordered from highest to lowest privilege.

    admin    — full org control (manage users, billing, settings)
    manager  — manage documents and view all conversations
    employee — upload docs, query knowledge base
    viewer   — read-only query access
    """

    ADMIN = "admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"
    VIEWER = "viewer"


class User(BaseModel):
    """
    Platform user belonging to one organization.

    Authentication is JWT-based. Passwords are bcrypt-hashed.
    API keys are stored as sha256(key) for zero-knowledge storage.
    """

    __tablename__ = "users"

    # ------------------------------------------------------------------ #
    # Tenant FK                                                             #
    # ------------------------------------------------------------------ #
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning organization",
    )

    # ------------------------------------------------------------------ #
    # Identity                                                              #
    # ------------------------------------------------------------------ #
    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique email address — login identifier",
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name",
    )

    # ------------------------------------------------------------------ #
    # Auth                                                                  #
    # ------------------------------------------------------------------ #
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt hash of user password",
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", create_type=True),
        nullable=False,
        default=UserRole.EMPLOYEE,
        server_default=UserRole.EMPLOYEE.value,
        comment="RBAC role",
    )

    # ------------------------------------------------------------------ #
    # Status                                                                #
    # ------------------------------------------------------------------ #
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Disabled users cannot log in",
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Email verification status",
    )

    # ------------------------------------------------------------------ #
    # API Key (optional — for service-to-service)                          #
    # ------------------------------------------------------------------ #
    api_key_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
        comment="SHA-256 of API key — zero-knowledge storage",
    )

    # ------------------------------------------------------------------ #
    # Activity tracking                                                     #
    # ------------------------------------------------------------------ #
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent successful login",
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="users",
        lazy="selectin",
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role.value!r}>"
