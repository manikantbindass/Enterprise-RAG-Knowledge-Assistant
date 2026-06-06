"""Audit Service — Main FastAPI application + RabbitMQ consumer"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import AuditConfig
from routes.audit import router as audit_router

logger = structlog.get_logger(__name__)
config = AuditConfig()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Audit service starting")
    import asyncio
    from worker import AuditWorker
    worker = AuditWorker(config)
    task = asyncio.create_task(worker.start())
    app.state.worker_task = task
    yield
    task.cancel()
    logger.info("Audit service shutting down")


app = FastAPI(title="RAG Audit Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(audit_router, prefix="/audit", tags=["audit"])


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "audit_service"}
