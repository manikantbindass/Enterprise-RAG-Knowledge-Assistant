"""
Document Service — FastAPI application entry point.

Lifecycle:
  startup  → DB engine, storage, virus scanner, RabbitMQ
  shutdown → close all connections gracefully
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from aio_pika import connect_robust
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from document_service.config import get_config
from document_service.exceptions import DocumentServiceError
from document_service.models.schemas import ErrorResponse
from document_service.repositories.document_repository import Base
from document_service.routes import documents
from document_service.services.document_service import StorageClient
from document_service.services.virus_scanner import VirusScannerService

# ── Logging setup ─────────────────────────────────────────────────────────────

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

# ── Prometheus metrics ────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "document_service_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "document_service_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)
UPLOAD_COUNT = Counter(
    "document_service_uploads_total",
    "Total document uploads",
    ["status"],
)
UPLOAD_SIZE = Histogram(
    "document_service_upload_size_bytes",
    "Upload file size distribution",
    buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600],
)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize and teardown all service dependencies."""
    config = get_config()
    log = logger.bind(service=config.service_name, env=config.environment)
    log.info("service_starting")

    # 1. Database
    engine = create_async_engine(
        config.database_url,
        pool_size=config.db_pool_size,
        max_overflow=config.db_max_overflow,
        pool_timeout=config.db_pool_timeout,
        echo=config.db_echo,
        pool_pre_ping=True,
    )
    # Create tables (idempotent; use Alembic for production migrations)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False
    )
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    log.info("database_ready", url=config.database_url.split("@")[-1])

    # 2. Storage (S3 / MinIO)
    storage = StorageClient(config)
    try:
        await storage.initialize()
        app.state.storage_client = storage
        log.info("storage_ready", backend=config.storage_backend)
    except Exception as exc:
        log.error("storage_init_failed", error=str(exc))
        raise

    # 3. Virus scanner (ClamAV)
    scanner = VirusScannerService(
        host=config.clamav_host,
        port=config.clamav_port,
        timeout=config.clamav_timeout,
    )
    await scanner.initialize()  # logs warning if unavailable — does not raise
    app.state.virus_scanner = scanner

    # 4. RabbitMQ
    try:
        rmq = await connect_robust(config.rabbitmq_url)
        app.state.rabbitmq_connection = rmq
        log.info("rabbitmq_connected", url=config.rabbitmq_url.split("@")[-1])
    except Exception as exc:
        log.warning("rabbitmq_init_failed", error=str(exc), fallback="events_disabled")
        app.state.rabbitmq_connection = None

    log.info("service_ready", host=config.host, port=config.port)

    yield  # ── service is running ──────────────────────────────────────────

    # Teardown
    log.info("service_shutting_down")

    rmq = getattr(app.state, "rabbitmq_connection", None)
    if rmq:
        await rmq.close()

    await engine.dispose()
    log.info("service_stopped")


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    config = get_config()

    app = FastAPI(
        title="Document Service",
        description="Upload, manage, and track RAG document lifecycle",
        version="1.0.0",
        docs_url="/docs" if config.debug else None,
        redoc_url="/redoc" if config.debug else None,
        openapi_url="/openapi.json" if config.debug else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if config.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request ID + logging middleware ───────────────────────────────────────
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method, endpoint=request.url.path
        ).observe(duration)

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Exception handlers ────────────────────────────────────────────────────

    @app.exception_handler(DocumentServiceError)
    async def document_service_error_handler(
        request: Request, exc: DocumentServiceError
    ) -> JSONResponse:
        logger.warning(
            "domain_error",
            error_code=exc.error_code,
            message=exc.message,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.error_code,
                detail=exc.detail or exc.message,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="VALIDATION_ERROR",
                detail=str(exc.errors()),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error="INTERNAL_ERROR", detail="An unexpected error occurred").model_dump(),
        )

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(documents.router, prefix="/api/v1")

    @app.get("/health", tags=["Ops"])
    async def health() -> dict:
        return {"status": "healthy", "service": "document-service"}

    @app.get("/ready", tags=["Ops"])
    async def readiness(request: Request) -> dict:
        """Check all critical dependencies."""
        checks: dict[str, str] = {}

        # DB check
        try:
            session_factory = request.app.state.db_session_factory
            async with session_factory() as session:
                await session.execute(__import__("sqlalchemy").text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"

        # Storage check
        storage: StorageClient = request.app.state.storage_client
        checks["storage"] = "ok" if storage else "unavailable"

        # Scanner check
        scanner: VirusScannerService = request.app.state.virus_scanner
        checks["virus_scanner"] = "ok" if scanner.is_available else "degraded"

        all_ok = all(v == "ok" or v == "degraded" for v in checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"status": "ready" if all_ok else "not_ready", "checks": checks},
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
        workers=config.workers,
        log_config=None,  # structlog handles logging
    )
