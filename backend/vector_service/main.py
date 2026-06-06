"""
Vector Service — FastAPI application entry point.

Startup sequence:
  1. Configure structlog + OpenTelemetry
  2. Connect asyncpg pool (pgvector)
  3. Load cross-encoder reranker into memory
  4. Mount routes

Shutdown:
  1. Close asyncpg pool gracefully
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from vector_service.config import get_settings
from vector_service.exceptions import VectorServiceError
from vector_service.routes.search import router as search_router
from vector_service.services.reranker import get_reranker

# ── Structlog configuration ────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

# ── Prometheus metrics ─────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "vector_service_requests_total",
    "Total search requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "vector_service_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
SEARCH_RESULTS = Histogram(
    "vector_service_search_results",
    "Number of results returned per search",
    ["search_type"],
    buckets=[1, 5, 10, 20, 50, 100],
)


# ── Lifespan ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown of shared resources."""
    settings = get_settings()

    # ── OpenTelemetry ──────────────────────────────────────────────────────
    if settings.otel_enabled:
        resource = Resource(attributes={"service.name": settings.service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("otel_configured", endpoint=settings.otel_endpoint)

    # ── asyncpg connection pool ────────────────────────────────────────────
    logger.info("db_pool_connecting", dsn_prefix=settings.asyncpg_dsn[:30])
    pool = await asyncpg.create_pool(
        dsn=settings.asyncpg_dsn,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        command_timeout=settings.db_command_timeout,
        server_settings={"application_name": settings.service_name},
    )
    app.state.db_pool = pool
    logger.info(
        "db_pool_connected",
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )

    # ── Reranker ───────────────────────────────────────────────────────────
    reranker = get_reranker()
    reranker.load()

    yield  # ── Application running ─────────────────────────────────────────

    # ── Shutdown ───────────────────────────────────────────────────────────
    logger.info("db_pool_closing")
    await pool.close()
    logger.info("db_pool_closed")


# ── Application factory ────────────────────────────────────────────────────


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Vector Search Service",
        description="Hybrid semantic + keyword search with pgvector and cross-encoder reranking",
        version=settings.service_version,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restricted by API gateway; internal-only service
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging + metrics middleware ──────────────────────────────
    @app.middleware("http")
    async def request_telemetry(request: Request, call_next) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        latency = time.perf_counter() - start

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(endpoint=request.url.path).observe(latency)

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=round(latency * 1000, 2),
        )
        return response

    # ── Exception handlers ────────────────────────────────────────────────
    @app.exception_handler(VectorServiceError)
    async def vector_error_handler(request: Request, exc: VectorServiceError) -> JSONResponse:
        logger.warning("vector_service_error", message=exc.message, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "type": type(exc).__name__},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "type": "InternalError"},
        )

    # ── Routes ────────────────────────────────────────────────────────────
    app.include_router(search_router, prefix="/api/v1")

    @app.get("/health", tags=["ops"])
    async def health(request: Request):
        pool: asyncpg.Pool = request.app.state.db_pool
        db_ok = False
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
        except Exception:
            logger.exception("health_check_db_failed")

        return {
            "status": "ok" if db_ok else "degraded",
            "version": settings.service_version,
            "db_connected": db_ok,
            "reranker_loaded": get_reranker().is_loaded,
        }

    @app.get("/metrics", tags=["ops"])
    async def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # ── OpenTelemetry auto-instrumentation ────────────────────────────────
    FastAPIInstrumentor.instrument_app(app)

    return app


app = create_app()
