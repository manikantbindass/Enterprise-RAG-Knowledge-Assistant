"""
Chat Service — Conversation repository and service
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class ConversationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, org_id: uuid.UUID, user_id: uuid.UUID, title: str | None = None) -> Any:
        from shared.models.conversation import Conversation
        conv = Conversation(org_id=org_id, user_id=user_id, title=title or "New Conversation")
        self.db.add(conv)
        await self.db.commit()
        await self.db.refresh(conv)
        return conv

    async def get(self, conversation_id: uuid.UUID, org_id: uuid.UUID) -> Any | None:
        from shared.models.conversation import Conversation
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(self, org_id: uuid.UUID, user_id: uuid.UUID, page: int = 1, page_size: int = 20) -> dict:
        from shared.models.conversation import Conversation
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.org_id == org_id, Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .offset(offset)
            .limit(page_size)
        )
        items = result.scalars().all()
        return {"items": items, "page": page, "page_size": page_size, "total": len(items)}

    async def delete(self, conversation_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        from shared.models.conversation import Conversation
        conv = await self.get(conversation_id, org_id)
        if not conv:
            return False
        await self.db.delete(conv)
        await self.db.commit()
        return True

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        org_id: uuid.UUID,
        role: str,
        content: str,
        sources: list | None = None,
        tokens_used: int = 0,
        cost: float = 0.0,
        latency_ms: int = 0,
    ) -> Any:
        from shared.models.conversation import Message
        msg = Message(
            conversation_id=conversation_id,
            org_id=org_id,
            role=role,
            content=content,
            sources=sources or [],
            tokens_used=tokens_used,
            cost=cost,
            latency_ms=latency_ms,
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def get_messages(self, conversation_id: uuid.UUID, org_id: uuid.UUID) -> list:
        from shared.models.conversation import Message
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.org_id == org_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def set_feedback(
        self, message_id: uuid.UUID, org_id: uuid.UUID, feedback: str, comment: str | None = None
    ) -> bool:
        from shared.models.conversation import Message
        result = await self.db.execute(
            select(Message).where(Message.id == message_id, Message.org_id == org_id)
        )
        msg = result.scalar_one_or_none()
        if not msg:
            return False
        msg.feedback = feedback
        msg.feedback_comment = comment
        await self.db.commit()
        return True
