"""
Chat Service — Pydantic schemas
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str | None = Field(None, max_length=500)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    llm_provider: str | None
    total_tokens: int
    total_cost: float
    is_shared: bool
    created_at: datetime
    updated_at: datetime


class PaginatedConversations(BaseModel):
    items: list[ConversationResponse]
    page: int
    page_size: int
    total: int


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    llm_provider: Literal["openai", "anthropic", "azure", "ollama"] | None = "openai"
    filters: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    sources: list[dict] | None = []
    tokens_used: int | None = 0
    cost: float | None = 0.0
    latency_ms: int | None = None
    feedback: str | None = None
    feedback_comment: str | None = None
    created_at: datetime


class FeedbackRequest(BaseModel):
    feedback: Literal["positive", "negative", "neutral"]
    comment: str | None = Field(None, max_length=2000)
