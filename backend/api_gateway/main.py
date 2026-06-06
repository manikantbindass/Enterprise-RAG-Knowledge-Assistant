"""
API Gateway — main FastAPI application entry point.

Responsibilities:
- App lifecycle: init/shutdown DB, Redis, RabbitMQ, HTTP client
- Middleware stack: CORS, TrustedHost, RateLimit, RequestLogging, GZip
- Router mounting at /api/v1
- Exception handlers for all custom gateway exceptions
- /health endpoint (standalone, no auth)
- /metrics endpoint (Prometheus)
- OpenTelemetry instrumentation
- OpenAPI docs customisation
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from config import GatewayConfig, get_config
from exceptions import (
    BadRequestException,
    CacheException,
    ConflictException,
    DatabaseException,
    ForbiddenException,
    GatewayBaseException,
    GatewayTimeoutException,
    InsufficientRoleException,
    InternalServerException,
    InvalidTokenException,
    NotFoundException,
    PayloadTooLargeException,
    RateLimitExceededException,
    ServiceUnavailableException,
    TokenExpiredException,
    UnauthorizedException,
    UnprocessableEntityException,
    UpstreamServiceException,
    ValidationException,
)
from proxy import build_http_client
from routes import (
    admin_router,
    auth_router,
    chat_router,
    documents_router,
    health_router,
    organizations_router,
    search_router,
    users_router,
)

# ---------------------------------------------------------------------------
# Structured logging setup
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger("api_gateway.main")


# ---------------------------------------------------------------------------
# OpenTelemetry initialisation
# ---------------------------------------------------------------------------


def _setup_otel(config: GatewayConfig) -> None:
    """Configure OpenTelemetry tracing with OTLP gRPC exporter."""
    if not config.otel_enabled:
        logger.info("otel_disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": config.otel_service_name,
                "service.version": config.app_version,
                "deployment.environment": config.environment,
            }
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=config.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Auto-instrument httpx and redis
        HTTPXClientInstrumentor().instrument()
        RedisInstrumentor().instrument()

        logger.info(
            "otel_initialised",
            endpoint=config.otel_exporter_otlp_endpoint,
            service=config.otel_service_name,
        )
    except ImportError as exc:
        logger.warning("otel_import_error", error=str(exc))


# ---------------------------------------------------------------------------
# Middleware: Request Logging
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log every request with duration, status code, user ID, and request ID.

    Injects X-Request-ID into the response.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        log = logger.bind(
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
            request_id=request_id,
        )
        log.info("request_started")

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            log.error(
                "request_unhandled_exception",
                error=str(exc),
                elapsed_ms=round(elapsed, 1),
            )
            raise

        elapsed = (time.perf_counter() - start) * 1000
        user_id: str | None = None
        if hasattr(request.state, "user"):
            user_id = request.state.user.user_id

        log.info(
            "request_completed",
            status_code=response.status_code,
            elapsed_ms=round(elapsed, 1),
            user_id=user_id,
        )

        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Middleware: Rate Limiting (Redis sliding-window)
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter backed by Redis.

    Key: client IP (or user ID if authenticated).
    Limits: config.rate_limit_requests per config.rate_limit_window_seconds.
    Skips /health and /metrics endpoints.
    """

    _SKIP_PATHS = frozenset({"/health", "/metrics", "/docs", "/openapi.json"})

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        config: GatewayConfig = get_config()

        if not config.rate_limit_enabled:
            return await call_next(request)

        if request.url.path in self._SKIP_PATHS:
            return await call_next(request)

        try:
            redis: aioredis.Redis = request.app.state.redis
            client_key = request.client.host if request.client else "unknown"
            window = config.rate_limit_window_seconds
            limit = config.rate_limit_requests

            redis_key = f"ratelimit:{client_key}"
            now_ms = int(time.time() * 1000)
            window_ms = window * 1000

            pipe = redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, now_ms - window_ms)
            pipe.zadd(redis_key, {str(uuid.uuid4()): now_ms})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window + 1)
            results = await pipe.execute()

            count: int = results[2]
            remaining = max(0, limit - count)

            if count > limit:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests — slow down",
                    },
                    headers={
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(window),
                        "Retry-After": str(window),
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(window)
            return response

        except aioredis.RedisError:
            # Fail open — don't block traffic if Redis is down
            logger.warning("rate_limit_redis_error_fail_open")
            return await call_next(request)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown.

    Startup:
    - Initialise PostgreSQL engine and session factory
    - Connect to Redis
    - Connect to RabbitMQ (optional)
    - Build shared httpx.AsyncClient

    Shutdown:
    - Close all connections gracefully
    """
    config = get_config()
    logger.info("gateway_starting", version=config.app_version, env=config.environment)

    # ---- Postgres ----
    engine: AsyncEngine = create_async_engine(
        config.database_url,
        pool_size=config.db_pool_size,
        max_overflow=config.db_max_overflow,
        pool_timeout=config.db_pool_timeout,
        pool_pre_ping=True,
        echo=config.db_echo,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    app.state.engine = engine
    app.state.async_session_factory = session_factory
    logger.info("database_connected")

    # ---- Redis ----
    redis_client = aioredis.from_url(
        config.redis_url,
        max_connections=config.redis_max_connections,
        socket_timeout=config.redis_socket_timeout,
        socket_connect_timeout=config.redis_connect_timeout,
        decode_responses=False,
    )
    try:
        await redis_client.ping()
        logger.info("redis_connected", url=config.redis_url)
    except Exception as exc:
        logger.warning("redis_connect_failed", error=str(exc))
    app.state.redis = redis_client

    # ---- RabbitMQ (optional) ----
    app.state.rabbitmq_channel = None
    try:
        import aio_pika  # type: ignore[import]

        rmq_connection = await aio_pika.connect_robust(config.rabbitmq_url)
        rmq_channel = await rmq_connection.channel()
        app.state.rabbitmq_connection = rmq_connection
        app.state.rabbitmq_channel = rmq_channel
        logger.info("rabbitmq_connected", url=config.rabbitmq_url)
    except ImportError:
        logger.warning("rabbitmq_aio_pika_not_installed")
    except Exception as exc:
        logger.warning("rabbitmq_connect_failed", error=str(exc))

    # ---- HTTP client ----
    http_client = build_http_client(config)
    app.state.http_client = http_client
    logger.info("http_client_ready")

    logger.info("gateway_started")

    # ---- Run app ----
    yield

    # ---- Shutdown ----
    logger.info("gateway_shutting_down")

    await http_client.aclose()
    logger.info("http_client_closed")

    await redis_client.aclose()
    logger.info("redis_closed")

    if app.state.rabbitmq_channel is not None:
        try:
            await app.state.rabbitmq_channel.close()
            await app.state.rabbitmq_connection.close()
            logger.info("rabbitmq_closed")
        except Exception as exc:
            logger.warning("rabbitmq_close_error", error=str(exc))

    await engine.dispose()
    logger.info("database_closed")

    logger.info("gateway_stopped")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    config = get_config()

    # OTel must be set up before app creation so auto-instrumentation works
    _setup_otel(config)

    app = FastAPI(
        title=config.app_name,
        description=(
            "Enterprise RAG Knowledge Assistant — API Gateway\n\n"
            "Central gateway for all microservices: auth, users, organisations, "
            "documents, semantic search, and AI chat with retrieval-augmented generation."
        ),
        version=config.app_version,
        docs_url="/docs" if not config.is_production else None,
        redoc_url="/redoc" if not config.is_production else None,
        openapi_url="/openapi.json" if not config.is_production else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        contact={
            "name": "Platform Engineering",
            "email": "platform@example.com",
        },
        license_info={
            "name": "Proprietary",
        },
        openapi_tags=[
            {"name": "Authentication", "description": "Login, logout, token management"},
            {"name": "Users", "description": "User profile management"},
            {"name": "Organizations", "description": "Multi-tenant org management"},
            {"name": "Documents", "description": "Document upload and ingestion"},
            {"name": "Search", "description": "Semantic and hybrid document search"},
            {"name": "Chat", "description": "AI-powered RAG conversations"},
            {"name": "Admin", "description": "System administration"},
            {"name": "health", "description": "Health and readiness probes"},
        ],
    )

    # ------------------------------------------------------------------
    # Middleware (order matters — outermost = first to process request)
    # ------------------------------------------------------------------

    # GZip — compress large responses
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Rate limiting
    app.add_middleware(RateLimitMiddleware)

    # Request logging + X-Request-ID injection
    app.add_middleware(RequestLoggingMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=config.cors_allow_credentials,
        allow_methods=config.cors_allow_methods,
        allow_headers=config.cors_allow_headers,
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # TrustedHost — rejects requests with unexpected Host headers
    if config.allowed_hosts != ["*"]:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=config.allowed_hosts,
        )

    # ------------------------------------------------------------------
    # OpenTelemetry FastAPI instrumentation
    # ------------------------------------------------------------------
    if config.otel_enabled:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # Prometheus metrics
    # ------------------------------------------------------------------
    if config.metrics_enabled:
        instrumentator = Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            should_respect_env_var=False,
            should_instrument_requests_inprogress=True,
            excluded_handlers=["/health", "/metrics"],
            inprogress_name="gateway_requests_inprogress",
            inprogress_labels=True,
        )
        instrumentator.instrument(app).expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,
            tags=["monitoring"],
        )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    API_V1_PREFIX = "/api/v1"

    # Health check — no prefix, no auth
    app.include_router(health_router)

    # Auth routes
    app.include_router(auth_router, prefix=API_V1_PREFIX)

    # Resource routes (all require auth via dependency injection)
    app.include_router(users_router, prefix=API_V1_PREFIX)
    app.include_router(organizations_router, prefix=API_V1_PREFIX)
    app.include_router(documents_router, prefix=API_V1_PREFIX)
    app.include_router(search_router, prefix=API_V1_PREFIX)
    app.include_router(chat_router, prefix=API_V1_PREFIX)

    # Admin routes
    app.include_router(admin_router, prefix=API_V1_PREFIX)

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    @app.exception_handler(GatewayBaseException)
    async def gateway_exception_handler(
        request: Request, exc: GatewayBaseException
    ) -> JSONResponse:
        log = logger.bind(
            path=request.url.path,
            error_code=exc.error_code,
            status_code=exc.status_code,
        )
        if exc.status_code >= 500:
            log.error("gateway_server_error", message=exc.message)
        else:
            log.warning("gateway_client_error", message=exc.message)

        headers: dict[str, str] = {}
        if isinstance(exc, RateLimitExceededException):
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            "request_validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "detail": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            },
        )

    # ------------------------------------------------------------------
    # Root redirect
    # ------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            content={
                "service": "Enterprise RAG Knowledge Assistant — API Gateway",
                "version": config.app_version,
                "docs": "/docs",
                "health": "/health",
            }
        )

    logger.info("app_created", version=config.app_version)
    return app


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    import uvicorn

    cfg = get_config()
    uvicorn.run(
        "main:app",
        host=cfg.host,
        port=cfg.port,
        workers=cfg.workers,
        log_level=cfg.log_level.lower(),
        access_log=False,  # handled by RequestLoggingMiddleware
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
