"""
Conversation and Message SQLAlchemy models.

Conversation — a chat session between a user and the RAG system.
Message      — individual turn in a conversation (user or assistant).

FeedbackType tracks thumbs-up/down on assistant responses.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import TenantModel

if TYPE_CHECKING:
    from shared.models.user import User


class MessageRole(str, enum.Enum):
    """
    Speaker role in a conversation turn.

    user      — human message
    assistant — LLM-generated response
    system    — system prompt (stored for audit, not shown to user)
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class FeedbackType(str, enum.Enum):
    """
    User feedback on an assistant message.

    thumbs_up   — helpful response
    thumbs_down — unhelpful / wrong response
    """

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class Conversation(TenantModel):
    """
    A conversation session between a user and the RAG knowledge assistant.

    Conversations group a sequence of messages under a shared context.
    Session metadata (title, active documents) is stored in session_context.
    """

    __tablename__ = "conversations"

    # ------------------------------------------------------------------ #
    # User                                                                  #
    # ------------------------------------------------------------------ #
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user",
    )

    # ------------------------------------------------------------------ #
    # Metadata                                                              #
    # ------------------------------------------------------------------ #
    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Auto-generated or user-set conversation title",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Soft-archive old conversations",
    )

    # ------------------------------------------------------------------ #
    # Session context                                                       #
    # ------------------------------------------------------------------ #
    session_context: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        server_default="{}",
        comment="Session-level context: pinned documents, filters, llm settings",
    )

    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Denormalized count for quick pagination info",
    )

    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent message — for sorting",
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #
    user: Mapped["User"] = relationship(
        "User",
        back_populates="conversations",
        lazy="noload",
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} user={self.user_id} title={self.title!r}>"


class Message(TenantModel):
    """
    A single message in a conversation.

    For assistant messages, sources contains retrieved document chunks
    used to generate the response (RAG citations).
    """

    __tablename__ = "messages"

    # ------------------------------------------------------------------ #
    # Parent conversation                                                   #
    # ------------------------------------------------------------------ #
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent conversation",
    )

    # ------------------------------------------------------------------ #
    # Content                                                               #
    # ------------------------------------------------------------------ #
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role_enum", create_type=True),
        nullable=False,
        comment="Speaker role",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message text (markdown for assistant messages)",
    )

    # ------------------------------------------------------------------ #
    # RAG sources                                                           #
    # ------------------------------------------------------------------ #
    sources: Mapped[Optional[list[dict]]] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Retrieved chunks used for this response. "
            "Array of {chunk_id, document_id, score, excerpt}"
        ),
    )

    # ------------------------------------------------------------------ #
    # LLM metadata                                                          #
    # ------------------------------------------------------------------ #
    model_used: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="LLM model identifier (e.g. gpt-4o)",
    )

    prompt_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Input tokens consumed",
    )

    completion_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Output tokens generated",
    )

    latency_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="End-to-end response latency in milliseconds",
    )

    # ------------------------------------------------------------------ #
    # User feedback                                                         #
    # ------------------------------------------------------------------ #
    feedback_type: Mapped[Optional[FeedbackType]] = mapped_column(
        Enum(FeedbackType, name="feedback_type_enum", create_type=True),
        nullable=True,
        comment="User thumbs up/down on this message",
    )

    feedback_comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Free-text feedback from user",
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<Message id={self.id} role={self.role.value!r} conv={self.conversation_id}>"
        )
