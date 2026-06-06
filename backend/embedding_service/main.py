"""
Embedding Service — Main Application + RabbitMQ Consumer
Consumes doc.processed events, generates embeddings, stores in pgvector
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI

from config import EmbeddingConfig
from worker import EmbeddingWorker

logger = structlog.get_logger(__name__)
config = EmbeddingConfig()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Embedding service starting")
    worker = EmbeddingWorker(config)
    app.state.worker = worker
    import asyncio
    task = asyncio.create_task(worker.start())
    app.state.worker_task = task
    yield
    task.cancel()
    logger.info("Embedding service shutting down")


app = FastAPI(title="RAG Embedding Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "embedding_service"}
