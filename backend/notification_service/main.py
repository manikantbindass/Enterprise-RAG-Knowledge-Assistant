"""Notification Service — Main app + RabbitMQ consumer"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Notification service starting")
    import asyncio
    from worker import NotificationWorker
    from config import NotificationConfig
    worker = NotificationWorker(NotificationConfig())
    task = asyncio.create_task(worker.start())
    yield
    task.cancel()


app = FastAPI(title="RAG Notification Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "notification_service"}
