"""
Processing Service — FastAPI app + background RabbitMQ worker.

The FastAPI app exposes health/metrics endpoints.
The RabbitMQ worker runs as a background asyncio task.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from processing_service.config import get_config
from processing_service.worker import ProcessingWorker

# ── Logging ───────────────────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

# ── Metrics ───────────────────────────────────────────────────────────────────

DOCS_PROCESSED = Counter(
    "processing_service_documents_processed_total",
    "Total documents processed",
    ["status"],
)
PROCESSING_LATENCY = Histogram(
    "processing_service_document_duration_seconds",
    "Document processing time",
    ["content_type"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],
)
CHUNKS_CREATED = Counter(
    "processing_service_chunks_created_total",
    "Total chunks created",
    ["strategy"],
)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start background worker alongside FastAPI."""
    config = get_config()
    log = logger.bind(service=config.service_name, env=config.environment)
    log.info("service_starting")

    worker = ProcessingWorker(config)
    app.state.worker = worker

    # Start worker as background task
    worker_task = asyncio.create_task(worker.start(), name="processing-worker")
    app.state.worker_task = worker_task

    log.info("service_ready", host=config.host, port=config.port)

    yield  # ── running ──────────────────────────────────────────────────────

    log.info("service_shutting_down")
    worker_task.cancel()
    try:
        await asyncio.wait_for(worker.stop(), timeout=10.0)
    except asyncio.TimeoutError:
        log.warning("worker_shutdown_timeout")
    log.info("service_stopped")


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and configure FastAPI application."""
    config = get_config()

    app = FastAPI(
        title="Processing Service",
        description="Extracts, cleans, and chunks documents from the doc.uploaded queue",
        version="1.0.0",
        docs_url="/docs" if config.debug else None,
        redoc_url="/redoc" if config.debug else None,
        openapi_url="/openapi.json" if config.debug else None,
        lifespan=lifespan,
    )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "detail": str(exc)},
        )

    @app.get("/health", tags=["Ops"])
    async def health() -> dict:
        return {"status": "healthy", "service": "processing-service"}

    @app.get("/ready", tags=["Ops"])
    async def readiness(request: Request) -> dict:
        worker: ProcessingWorker = request.app.state.worker
        worker_task = request.app.state.worker_task

        is_running = not worker_task.done()
        return JSONResponse(
            status_code=200 if is_running else 503,
            content={
                "status": "ready" if is_running else "worker_stopped",
                "worker_running": is_running,
            },
        )

    @app.get("/metrics", tags=["Ops"])
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        workers=1,  # Single worker — RabbitMQ consumer manages own concurrency
        log_config=None,
    )
