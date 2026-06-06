"""
Auth Service — FastAPI application entry point.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

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
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from auth_service.config import get_settings
from auth_service.exceptions import AuthServiceError
from auth_service.routes.auth import router as auth_router

# ── Structlog ─────────────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

# ── Prometheus ────────────────────────────────────────────────────────────
AUTH_REQUESTS = Counter(
    "auth_service_requests_total",
    "Total auth requests",
    ["method", "endpoint", "status_code"],
)
AUTH_LATENCY = Histogram(
    "auth_service_request_duration_seconds",
    "Request latency",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)


# ── Lifespan ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # OTel
    if settings.otel_enabled:
        resource = Resource(attributes={"service.name": settings.service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    # SQLAlchemy async engine
    engine = create_async_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.engine = engine
    logger.info("db_engine_created")

    # Redis
    redis_pool = ConnectionPool.from_url(
        str(settings.redis_url),
        max_connections=settings.redis_max_connections,
        decode_responses=False,
    )
    app.state.redis = Redis(connection_pool=redis_pool)
    logger.info("redis_connected")

    yield

    # Shutdown
    await app.state.redis.aclose()
    await engine.dispose()
    logger.info("auth_service_shutdown_complete")


# ── App factory ────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Auth Service",
        description="Authentication and authorization for Enterprise RAG",
        version=settings.service_version,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Per-request DB session middleware
    @app.middleware("http")
    async def db_session_middleware(request: Request, call_next) -> Response:
        session_factory: async_sessionmaker = request.app.state.session_factory
        async with session_factory() as session:
            async with session.begin():
                request.state.db_session = session
                response = await call_next(request)
        return response

    @app.middleware("http")
    async def telemetry_middleware(request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        latency = time.perf_counter() - start
        AUTH_REQUESTS.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
        ).inc()
        AUTH_LATENCY.labels(endpoint=request.url.path).observe(latency)
        return response

    @app.exception_handler(AuthServiceError)
    async def auth_error_handler(request: Request, exc: AuthServiceError) -> JSONResponse:
        logger.warning("auth_error", message=exc.message, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "type": type(exc).__name__},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", path=request.url.path)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    app.include_router(auth_router, prefix="/api/v1")

    @app.get("/health", tags=["ops"])
    async def health(request: Request):
        try:
            await request.app.state.redis.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

        return {
            "status": "ok" if redis_ok else "degraded",
            "version": settings.service_version,
            "redis": redis_ok,
        }

    @app.get("/metrics", tags=["ops"])
    async def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
