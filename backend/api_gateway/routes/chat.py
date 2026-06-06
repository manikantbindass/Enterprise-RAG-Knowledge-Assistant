"""
Chat routes — proxied to chat-service.

POST   /api/v1/chat/conversations                          create conversation
GET    /api/v1/chat/conversations                          list conversations (paginated)
GET    /api/v1/chat/conversations/{conv_id}                get conversation
DELETE /api/v1/chat/conversations/{conv_id}                delete conversation
POST   /api/v1/chat/conversations/{conv_id}/messages       send message (SSE streaming)
GET    /api/v1/chat/conversations/{conv_id}/messages       list messages
POST   /api/v1/chat/messages/{msg_id}/feedback             submit message feedback
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

import structlog
from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dependencies import (
    ActiveUserDep,
    ChatProxyDep,
    ConfigDep,
    RequestIdDep,
)
from exceptions import NotFoundException

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    """Create a new conversation session."""

    title: str | None = Field(
        None,
        max_length=300,
        description="Optional title; auto-generated from first message if omitted",
    )
    system_prompt: str | None = Field(
        None,
        max_length=4000,
        description="Custom system prompt override",
    )
    context_doc_ids: list[str] | None = Field(
        None,
        description="Pre-load specific documents as context",
    )
    metadata: dict[str, Any] | None = None


class SendMessageRequest(BaseModel):
    """Send a user message to a conversation and get a streamed response."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="The user's message text",
    )
    search_filters: dict[str, Any] | None = Field(
        None,
        description="Optional search filters applied during RAG retrieval",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of retrieved chunks to include in context",
    )
    stream: bool = Field(
        default=True,
        description="If true, response is streamed via SSE",
    )
    temperature: float | None = Field(
        None,
        ge=0.0,
        le=2.0,
        description="LLM temperature override",
    )


class MessageFeedbackRequest(BaseModel):
    """User feedback on a message."""

    rating: Literal["thumbs_up", "thumbs_down", "neutral"]
    comment: str | None = Field(None, max_length=1000)
    correction: str | None = Field(
        None,
        max_length=4000,
        description="Corrected answer provided by user",
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ConversationResponse(BaseModel):
    """Conversation metadata."""

    conv_id: str
    title: str | None
    user_id: str
    org_id: str | None
    message_count: int
    created_at: str
    updated_at: str
    metadata: dict[str, Any] | None


class PaginatedConversationsResponse(BaseModel):
    """Paginated conversation list."""

    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int
    pages: int


class MessageSource(BaseModel):
    """Source document chunk cited in a response."""

    chunk_id: str
    doc_id: str
    filename: str
    excerpt: str
    score: float
    page_number: int | None


class MessageResponse(BaseModel):
    """A single message in a conversation."""

    msg_id: str
    conv_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    sources: list[MessageSource] | None
    tokens_used: int | None
    created_at: str
    feedback: dict[str, Any] | None


class PaginatedMessagesResponse(BaseModel):
    """Paginated message list."""

    items: list[MessageResponse]
    total: int
    conv_id: str


class FeedbackResponse(BaseModel):
    """Feedback submission acknowledgement."""

    msg_id: str
    message: str


class DeleteResponse(BaseModel):
    """Deletion acknowledgement."""

    message: str
    conv_id: str


# ---------------------------------------------------------------------------
# SSE streaming helper
# ---------------------------------------------------------------------------


async def _sse_stream_from_proxy(
    proxy: "ChatProxyDep",
    conv_id: str,
    payload: dict[str, Any],
    authorization: str,
    request_id: str,
) -> AsyncIterator[str]:
    """
    Relay SSE events from chat-service to the client.

    Each upstream SSE event is forwarded as-is. A terminal [DONE] event
    is injected if the upstream doesn't send one before the stream closes.
    """
    sent_done = False
    try:
        async for chunk in proxy.stream(
            "POST",
            f"/chat/conversations/{conv_id}/messages/stream",
            authorization=authorization,
            request_id=request_id,
            json=payload,
        ):
            decoded = chunk.decode("utf-8", errors="replace")
            yield decoded
            if "[DONE]" in decoded:
                sent_done = True
    except Exception as exc:
        error_event = json.dumps({"error": str(exc), "type": "stream_error"})
        yield f"data: {error_event}\n\n"
        raise
    finally:
        if not sent_done:
            yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
async def create_conversation(
    payload: CreateConversationRequest,
    proxy: ChatProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> ConversationResponse:
    """
    Start a new conversation session.

    Optionally pre-load specific documents as context or set a custom system prompt.
    """
    log = logger.bind(request_id=request_id, user_id=current_user.user_id)
    log.info("create_conversation")

    body = payload.model_dump(exclude_none=True)
    body["user_id"] = current_user.user_id
    body["org_id"] = current_user.org_id

    response = await proxy.request(
        "POST",
        "/chat/conversations",
        json=body,
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    data = response.json()
    log.info("create_conversation_success", conv_id=data.get("conv_id"))
    return ConversationResponse(**data)


@router.get(
    "/conversations",
    response_model=PaginatedConversationsResponse,
    summary="List user's conversations",
)
async def list_conversations(
    proxy: ChatProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(None, description="Filter by title"),
) -> PaginatedConversationsResponse:
    """
    List conversations belonging to the current user.

    Admin can see all conversations; regular users only see their own.
    """
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if current_user.role != "admin":
        params["user_id"] = current_user.user_id
    if search:
        params["search"] = search

    response = await proxy.request(
        "GET",
        "/chat/conversations",
        authorization=f"Bearer {current_user.token}",
        params=params,
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return PaginatedConversationsResponse(**response.json())


@router.get(
    "/conversations/{conv_id}",
    response_model=ConversationResponse,
    summary="Get conversation by ID",
)
async def get_conversation(
    conv_id: str,
    proxy: ChatProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> ConversationResponse:
    """Get conversation metadata. User must own the conversation (admin can access any)."""
    response = await proxy.request(
        "GET",
        f"/chat/conversations/{conv_id}",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Conversation '{conv_id}' not found")
    if response.status_code == 403:
        from exceptions import ForbiddenException
        raise ForbiddenException("Access to this conversation is not permitted")

    proxy.raise_for_upstream(response)
    return ConversationResponse(**response.json())


@router.delete(
    "/conversations/{conv_id}",
    response_model=DeleteResponse,
    summary="Delete a conversation",
)
async def delete_conversation(
    conv_id: str,
    proxy: ChatProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> DeleteResponse:
    """Delete a conversation and all its messages."""
    log = logger.bind(
        request_id=request_id,
        user_id=current_user.user_id,
        conv_id=conv_id,
    )
    log.info("delete_conversation")

    response = await proxy.request(
        "DELETE",
        f"/chat/conversations/{conv_id}",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Conversation '{conv_id}' not found")

    proxy.raise_for_upstream(response)
    log.info("delete_conversation_success")
    return DeleteResponse(
        message="Conversation deleted successfully",
        conv_id=conv_id,
    )


@router.post(
    "/conversations/{conv_id}/messages",
    summary="Send a message — returns streaming SSE or JSON response",
    responses={
        200: {
            "description": "Streaming SSE response (text/event-stream) or JSON",
            "content": {
                "text/event-stream": {},
                "application/json": {"model": MessageResponse},
            },
        }
    },
)
async def send_message(
    conv_id: str,
    payload: SendMessageRequest,
    proxy: ChatProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
    config: ConfigDep,
) -> Any:
    """
    Send a user message to a conversation and receive the assistant's response.

    **Streaming mode** (default, `stream=true`):
    Returns a `text/event-stream` SSE response. Each event contains a JSON
    chunk of the assistant's reply. Final event is `data: [DONE]`.

    **Non-streaming mode** (`stream=false`):
    Returns a complete `MessageResponse` JSON once the LLM finishes.

    The chat-service performs:
    1. Conversation history retrieval
    2. RAG retrieval from vector store
    3. Context assembly
    4. LLM generation
    5. Source citation attachment
    """
    log = logger.bind(
        request_id=request_id,
        user_id=current_user.user_id,
        conv_id=conv_id,
    )

    auth_header = f"Bearer {current_user.token}"
    body = payload.model_dump(exclude_none=True)

    # Streaming path
    if payload.stream and config.streaming_enabled:
        log.info("chat_stream_start")
        return StreamingResponse(
            _sse_stream_from_proxy(
                proxy,
                conv_id,
                body,
                auth_header,
                request_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable nginx buffering
                "Connection": "keep-alive",
            },
        )

    # Non-streaming path
    log.info("chat_message_send")
    response = await proxy.request(
        "POST",
        f"/chat/conversations/{conv_id}/messages",
        json=body,
        authorization=auth_header,
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Conversation '{conv_id}' not found")

    proxy.raise_for_upstream(response)
    log.info("chat_message_success")
    return MessageResponse(**response.json())


@router.get(
    "/conversations/{conv_id}/messages",
    response_model=PaginatedMessagesResponse,
    summary="List messages in a conversation",
)
async def list_messages(
    conv_id: str,
    proxy: ChatProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
    limit: int = Query(default=50, ge=1, le=200),
    before_msg_id: str | None = Query(
        None,
        description="Cursor: return messages before this message ID",
    ),
) -> PaginatedMessagesResponse:
    """
    Retrieve the message history for a conversation.

    Uses cursor-based pagination via `before_msg_id`.
    """
    params: dict[str, Any] = {"limit": limit}
    if before_msg_id:
        params["before_msg_id"] = before_msg_id

    response = await proxy.request(
        "GET",
        f"/chat/conversations/{conv_id}/messages",
        authorization=f"Bearer {current_user.token}",
        params=params,
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Conversation '{conv_id}' not found")

    proxy.raise_for_upstream(response)
    return PaginatedMessagesResponse(**response.json())


@router.post(
    "/messages/{msg_id}/feedback",
    response_model=FeedbackResponse,
    summary="Submit feedback on an assistant message",
)
async def submit_feedback(
    msg_id: str,
    payload: MessageFeedbackRequest,
    proxy: ChatProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> FeedbackResponse:
    """
    Submit a thumbs up/down rating and optional correction for an assistant message.

    Feedback is used to track answer quality and fine-tune retrieval.
    """
    log = logger.bind(
        request_id=request_id,
        user_id=current_user.user_id,
        msg_id=msg_id,
        rating=payload.rating,
    )
    log.info("message_feedback")

    response = await proxy.request(
        "POST",
        f"/chat/messages/{msg_id}/feedback",
        json=payload.model_dump(exclude_none=True),
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Message '{msg_id}' not found")

    proxy.raise_for_upstream(response)
    log.info("message_feedback_success")
    return FeedbackResponse(
        msg_id=msg_id,
        message="Feedback recorded successfully",
    )
