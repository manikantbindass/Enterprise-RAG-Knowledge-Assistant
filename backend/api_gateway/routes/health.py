"""
Health check route.

GET /health — returns overall gateway + dependency health status.
"""

from __future__ import annotations

import time
from typing import Any, Literal

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import GatewayConfig, get_config

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])

_start_time = time.time()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ServiceHealthStatus(BaseModel):
    """Health status of a single dependency."""

    status: Literal["healthy", "degraded", "unhealthy"]
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Full health check response."""

    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    uptime_seconds: float
    services: dict[str, ServiceHealthStatus] = Field(default_factory=dict)
    environment: str


# ---------------------------------------------------------------------------
# Health probe helpers
# ---------------------------------------------------------------------------


async def _check_database(request: Request) -> ServiceHealthStatus:
    """Ping PostgreSQL via a lightweight SELECT 1."""
    t0 = time.perf_counter()
    try:
        async_session_factory = request.app.state.async_session_factory
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        latency = (time.perf_counter() - t0) * 1000
        return ServiceHealthStatus(status="healthy", latency_ms=round(latency, 2))
    except Exception as exc:
        logger.warning("health_db_fail", error=str(exc))
        return ServiceHealthStatus(status="unhealthy", error=str(exc))


async def _check_redis(request: Request) -> ServiceHealthStatus:
    """Ping Redis."""
    t0 = time.perf_counter()
    try:
        redis: aioredis.Redis = request.app.state.redis
        await redis.ping()
        latency = (time.perf_counter() - t0) * 1000
        return ServiceHealthStatus(status="healthy", latency_ms=round(latency, 2))
    except Exception as exc:
        logger.warning("health_redis_fail", error=str(exc))
        return ServiceHealthStatus(status="unhealthy", error=str(exc))


async def _check_rabbitmq(request: Request) -> ServiceHealthStatus:
    """Check RabbitMQ reachability (TCP connect via app state connection)."""
    t0 = time.perf_counter()
    try:
        # RabbitMQ channel is optional — may not be initialised in all envs
        rmq = getattr(request.app.state, "rabbitmq_channel", None)
        if rmq is None:
            return ServiceHealthStatus(status="degraded", error="not_connected")
        # Check if channel is open
        is_open: bool = getattr(rmq, "is_open", False)
        if not is_open:
            return ServiceHealthStatus(status="degraded", error="channel_closed")
        latency = (time.perf_counter() - t0) * 1000
        return ServiceHealthStatus(status="healthy", latency_ms=round(latency, 2))
    except Exception as exc:
        logger.warning("health_rabbitmq_fail", error=str(exc))
        return ServiceHealthStatus(status="unhealthy", error=str(exc))


def _aggregate_status(
    services: dict[str, ServiceHealthStatus],
) -> Literal["healthy", "degraded", "unhealthy"]:
    """
    Derive overall status from individual service statuses.

    - Any 'unhealthy' → overall 'unhealthy'
    - Any 'degraded' → overall 'degraded'
    - All 'healthy' → 'healthy'
    """
    statuses = {s.status for s in services.values()}
    if "unhealthy" in statuses:
        return "unhealthy"
    if "degraded" in statuses:
        return "degraded"
    return "healthy"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Gateway health check",
    description=(
        "Returns the health status of the API Gateway and its critical dependencies "
        "(PostgreSQL, Redis, RabbitMQ). Used by load balancers and monitoring systems."
    ),
)
async def health_check(request: Request) -> HealthResponse:
    """
    Probe all infrastructure dependencies concurrently and return aggregated health.

    Status values:
    - **healthy** — all dependencies responding normally
    - **degraded** — some non-critical dependencies are slow or unreachable
    - **unhealthy** — critical dependencies (DB / Redis) are down
    """
    import asyncio

    config: GatewayConfig = get_config()

    db_status, redis_status, rmq_status = await asyncio.gather(
        _check_database(request),
        _check_redis(request),
        _check_rabbitmq(request),
    )

    services: dict[str, ServiceHealthStatus] = {
        "database": db_status,
        "redis": redis_status,
        "rabbitmq": rmq_status,
    }

    overall = _aggregate_status(services)
    uptime = round(time.time() - _start_time, 1)

    logger.info(
        "health_check",
        status=overall,
        db=db_status.status,
        redis=redis_status.status,
        rabbitmq=rmq_status.status,
    )

    return HealthResponse(
        status=overall,
        version=config.app_version,
        uptime_seconds=uptime,
        services=services,
        environment=config.environment,
    )
