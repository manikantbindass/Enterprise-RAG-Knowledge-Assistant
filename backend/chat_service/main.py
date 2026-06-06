"""
Chat Service — Main FastAPI Application
LangGraph RAG pipeline with streaming SSE, multi-provider LLM support
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from config import ChatConfig
from routes.chat import router as chat_router

logger = structlog.get_logger(__name__)
config = ChatConfig()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Chat service starting", version="1.0.0")
    # Pre-warm reranker model
    try:
        from services.reranker import CrossEncoderReranker
        app.state.reranker = CrossEncoderReranker()
        logger.info("Reranker model loaded")
    except Exception as e:
        logger.warning("Reranker not available", error=str(e))
        app.state.reranker = None
    yield
    logger.info("Chat service shutting down")


app = FastAPI(
    title="RAG Chat Service",
    description="LangGraph RAG pipeline with streaming SSE and multi-provider LLM",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/conversations", tags=["chat"])

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "chat_service"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
