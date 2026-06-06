"""
Chat Service — Routes
Conversation management + SSE streaming message endpoint
"""
import json
import uuid
from typing import Annotated, AsyncIterator

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db
from models.schemas import (
    ConversationCreate,
    ConversationResponse,
    FeedbackRequest,
    MessageCreate,
    MessageResponse,
    PaginatedConversations,
)
from services.rag_pipeline import RAGPipeline
from services.conversation_service import ConversationService

logger = structlog.get_logger(__name__)
router = APIRouter()


def get_rag_pipeline(request: Request) -> RAGPipeline:
    return RAGPipeline(reranker=request.app.state.reranker)


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    svc = ConversationService(db)
    conv = await svc.create(
        org_id=current_user["org_id"],
        user_id=current_user["id"],
        title=body.title,
    )
    return ConversationResponse.model_validate(conv)


@router.get("", response_model=PaginatedConversations)
async def list_conversations(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedConversations:
    svc = ConversationService(db)
    result = await svc.list(
        org_id=current_user["org_id"],
        user_id=current_user["id"],
        page=page,
        page_size=page_size,
    )
    return result


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    svc = ConversationService(db)
    conv = await svc.get(conversation_id, org_id=current_user["org_id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse.model_validate(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = ConversationService(db)
    deleted = await svc.delete(conversation_id, org_id=current_user["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rag: RAGPipeline = Depends(get_rag_pipeline),
) -> StreamingResponse:
    """
    Send a message and stream the RAG response via SSE.
    Each SSE event is: data: {"type": "token"|"sources"|"done"|"error", "content": ...}
    """
    svc = ConversationService(db)

    # Validate conversation belongs to this user/org
    conv = await svc.get(conversation_id, org_id=current_user["org_id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save user message
    user_msg = await svc.add_message(
        conversation_id=conversation_id,
        org_id=current_user["org_id"],
        role="user",
        content=body.content,
    )

    # Get conversation history for context
    history = await svc.get_messages(conversation_id, org_id=current_user["org_id"])

    async def event_stream() -> AsyncIterator[str]:
        full_response = ""
        sources = []
        tokens_used = 0
        cost = 0.0
        latency_ms = 0

        import time
        start_time = time.monotonic()

        try:
            async for event in rag.stream(
                query=body.content,
                conversation_history=history,
                org_id=str(current_user["org_id"]),
                user_id=str(current_user["id"]),
                llm_provider=body.llm_provider or "openai",
                filters=body.filters or {},
            ):
                if event["type"] == "token":
                    full_response += event["content"]
                    yield f"data: {json.dumps(event)}\n\n"
                elif event["type"] == "sources":
                    sources = event["content"]
                    yield f"data: {json.dumps(event)}\n\n"
                elif event["type"] == "metadata":
                    tokens_used = event.get("tokens_used", 0)
                    cost = event.get("cost", 0.0)
                elif event["type"] == "error":
                    yield f"data: {json.dumps(event)}\n\n"
                    return

            latency_ms = int((time.monotonic() - start_time) * 1000)

            # Persist assistant message
            await svc.add_message(
                conversation_id=conversation_id,
                org_id=current_user["org_id"],
                role="assistant",
                content=full_response,
                sources=sources,
                tokens_used=tokens_used,
                cost=cost,
                latency_ms=latency_ms,
            )

            yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

        except Exception as e:
            logger.error("Stream error", error=str(e), exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    svc = ConversationService(db)
    conv = await svc.get(conversation_id, org_id=current_user["org_id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await svc.get_messages(conversation_id, org_id=current_user["org_id"])
    return [MessageResponse.model_validate(m) for m in messages]


@router.post("/messages/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def submit_feedback(
    message_id: uuid.UUID,
    body: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = ConversationService(db)
    updated = await svc.set_feedback(
        message_id=message_id,
        org_id=current_user["org_id"],
        feedback=body.feedback,
        comment=body.comment,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Message not found")
