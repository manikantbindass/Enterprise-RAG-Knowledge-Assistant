"""
User Service — FastAPI Application Entry Point.

Lifespan manages DB engine and RabbitMQ connection.
Middleware adds correlation IDs, structured logging, metrics.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import create_async_engine

import structlog

from user_service.config import get_config
from user_service.exceptions import UserServiceError
from user_service.routes.organizations import router as org_router
from user_service.routes.users import router as user_router

logger = structlog.get_logger(__name__)
cfg = get_config()

# ── Prometheus metrics ────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "user_service_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "user_service_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


# ── OpenTelemetry setup ───────────────────────────────────────────────────────

def _setup_tracing() -> None:
    """Configure OTLP exporter if endpoint is configured."""
    if not cfg.otlp_endpoint:
        return

    resource = Resource.create(
        {
            "service.name": cfg.service_name,
            "deployment.environment": cfg.environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=cfg.otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


# ── Structlog configuration ───────────────────────────────────────────────────

def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
            if cfg.environment == "development"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(cfg.log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup/shutdown for DB engine and instrumentation."""
    _configure_logging()
    _setup_tracing()

    engine = create_async_engine(
        cfg.database_url,
        pool_size=cfg.db_pool_size,
        max_overflow=cfg.db_max_overflow,
        pool_timeout=cfg.db_pool_timeout,
        echo=cfg.db_echo,
        pool_pre_ping=True,
    )
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    logger.info(
        "user_service.startup",
        service=cfg.service_name,
        environment=cfg.environment,
        port=cfg.port,
    )

    yield

    await engine.dispose()
    logger.info("user_service.shutdown")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="User Service",
        description="Enterprise RAG — User & Organization management",
        version="1.0.0",
        docs_url="/docs" if cfg.environment != "production" else None,
        redoc_url="/redoc" if cfg.environment != "production" else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if cfg.environment == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Correlation ID + logging middleware ───────────────────────────────────
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next) -> Response:  # type: ignore
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start

        endpoint = request.url.path
        REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, endpoint).observe(elapsed)

        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(
            "http.request",
            status_code=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
        )
        return response

    # ── Global exception handler ───────────────────────────────────────────────
    @app.exception_handler(UserServiceError)
    async def service_error_handler(request: Request, exc: UserServiceError) -> JSONResponse:
        logger.warning("user_service.error", error=exc.message, status=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "error_type": type(exc).__name__},
        )

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(user_router)
    app.include_router(org_router)

    # ── Health + Metrics ──────────────────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    async def health() -> dict:
        return {"status": "healthy", "service": cfg.service_name}

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # OpenTelemetry FastAPI instrumentation
    FastAPIInstrumentor.instrument_app(app)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "user_service.main:app",
        host=cfg.host,
        port=cfg.port,
        workers=cfg.workers,
        log_level=cfg.log_level.lower(),
    )
