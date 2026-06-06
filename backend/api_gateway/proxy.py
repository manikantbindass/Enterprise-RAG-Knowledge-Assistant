"""
ServiceProxy — thin HTTP proxy layer sitting between gateway routes and microservices.

Responsibilities:
- Forward Authorization header + X-Request-ID to upstream
- Apply configurable timeouts per upstream service
- Retry on 503 / connection errors with exponential backoff
- Stream SSE responses without buffering
- Translate upstream errors to gateway exceptions
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config import GatewayConfig
from exceptions import (
    GatewayTimeoutException,
    ServiceUnavailableException,
    UpstreamServiceException,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on network errors and 503 responses."""
    if isinstance(exc, httpx.ConnectError | httpx.RemoteProtocolError):
        return True
    if isinstance(exc, UpstreamServiceException) and exc.upstream_status == 503:
        return True
    return False


class ServiceProxy:
    """
    Proxy requests from the gateway to a named downstream microservice.

    Usage::

        proxy = ServiceProxy("auth", config.auth_service_base, http_client, config)
        response = await proxy.request("POST", "/auth/login", json=payload)
    """

    def __init__(
        self,
        service_name: str,
        base_url: str,
        client: httpx.AsyncClient,
        config: GatewayConfig,
    ) -> None:
        self.service_name = service_name
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.config = config
        self._timeout = httpx.Timeout(
            connect=config.proxy_timeout_connect,
            read=config.proxy_timeout_read,
            write=config.proxy_timeout_write,
            pool=config.proxy_timeout_pool,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        authorization: str | None = None,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        content: bytes | None = None,
        files: Any | None = None,
        data: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> httpx.Response:
        """
        Forward a single request to the microservice.

        Retries on network errors / 503 up to config.proxy_max_retries times.
        Raises gateway exceptions on terminal failures.
        """
        upstream_headers = self._build_headers(
            authorization=authorization,
            request_id=request_id,
            extra=headers,
        )
        url = f"{self.base_url}{path}"

        start = time.perf_counter()
        log = logger.bind(service=self.service_name, method=method, path=path)

        async def _attempt() -> httpx.Response:
            try:
                response = await self.client.request(
                    method=method,
                    url=url,
                    headers=upstream_headers,
                    params=params,
                    json=json,
                    content=content,
                    files=files,
                    data=data,
                    timeout=self._timeout,
                )
            except httpx.TimeoutException as exc:
                log.warning("upstream_timeout", error=str(exc))
                raise GatewayTimeoutException(
                    f"Service '{self.service_name}' timed out"
                ) from exc
            except httpx.ConnectError as exc:
                log.warning("upstream_connect_error", error=str(exc))
                raise ServiceUnavailableException(
                    f"Cannot reach service '{self.service_name}'"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise exc  # re-raise for status handling below

            elapsed = time.perf_counter() - start
            log.info(
                "upstream_response",
                status=response.status_code,
                elapsed_ms=round(elapsed * 1000, 1),
            )

            if response.status_code == 503:
                raise UpstreamServiceException(
                    self.service_name,
                    upstream_status=503,
                    message=f"Service '{self.service_name}' unavailable",
                )

            return response

        retry_cfg = AsyncRetrying(
            stop=stop_after_attempt(self.config.proxy_max_retries),
            wait=wait_exponential(
                multiplier=self.config.proxy_retry_backoff_factor,
                min=0.5,
                max=10,
            ),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )

        try:
            async for attempt in retry_cfg:
                with attempt:
                    return await _attempt()
        except (GatewayTimeoutException, ServiceUnavailableException):
            raise
        except Exception as exc:
            log.error("upstream_unexpected_error", error=str(exc))
            raise UpstreamServiceException(
                self.service_name,
                message=f"Unexpected error from '{self.service_name}'",
                detail=str(exc),
            ) from exc

        # mypy: all paths return or raise above
        raise ServiceUnavailableException()  # pragma: no cover

    async def stream(
        self,
        method: str,
        path: str,
        *,
        authorization: str | None = None,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> AsyncIterator[bytes]:
        """
        Stream a response from the microservice (for SSE / chunked transfers).

        Yields raw bytes chunks. Caller is responsible for SSE framing.
        """
        upstream_headers = self._build_headers(
            authorization=authorization,
            request_id=request_id,
            extra=headers,
        )
        url = f"{self.base_url}{path}"
        log = logger.bind(service=self.service_name, method=method, path=path)

        # Streaming timeout: long read, normal connect/write
        stream_timeout = httpx.Timeout(
            connect=self.config.proxy_timeout_connect,
            read=None,  # no read timeout — stream can be long
            write=self.config.proxy_timeout_write,
            pool=self.config.proxy_timeout_pool,
        )

        try:
            async with self.client.stream(
                method=method,
                url=url,
                headers=upstream_headers,
                params=params,
                json=json,
                timeout=stream_timeout,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    log.warning(
                        "stream_upstream_error",
                        status=response.status_code,
                        body=body[:500],
                    )
                    raise UpstreamServiceException(
                        self.service_name,
                        upstream_status=response.status_code,
                        message=f"Service '{self.service_name}' returned {response.status_code}",
                    )

                log.info("stream_started", status=response.status_code)
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    if chunk:
                        yield chunk

        except (UpstreamServiceException, GatewayTimeoutException):
            raise
        except httpx.TimeoutException as exc:
            log.warning("stream_timeout", error=str(exc))
            raise GatewayTimeoutException(
                f"Stream from '{self.service_name}' timed out"
            ) from exc
        except httpx.ConnectError as exc:
            log.warning("stream_connect_error", error=str(exc))
            raise ServiceUnavailableException(
                f"Cannot reach service '{self.service_name}' for streaming"
            ) from exc
        except Exception as exc:
            log.error("stream_unexpected_error", error=str(exc))
            raise UpstreamServiceException(
                self.service_name,
                message=f"Stream error from '{self.service_name}'",
                detail=str(exc),
            ) from exc

    def raise_for_upstream(self, response: httpx.Response) -> None:
        """
        Raise a typed gateway exception for non-2xx upstream responses.

        Call this after request() when you want to surface upstream 4xx as
        gateway errors instead of forwarding the raw upstream body.
        """
        if response.is_success:
            return

        try:
            body: dict[str, Any] = response.json()
        except Exception:
            body = {"raw": response.text[:200]}

        raise UpstreamServiceException(
            self.service_name,
            upstream_status=response.status_code,
            message=body.get("message", f"Service '{self.service_name}' error"),
            detail=body,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_headers(
        self,
        authorization: str | None,
        request_id: str | None,
        extra: dict[str, str] | None,
    ) -> dict[str, str]:
        """Build forwarded headers for upstream request."""
        headers: dict[str, str] = {
            "X-Request-ID": request_id or str(uuid.uuid4()),
            "X-Gateway-Service": "api-gateway",
            "Accept": "application/json",
        }
        if authorization:
            headers["Authorization"] = authorization
        if extra:
            # extra headers override defaults (except request-id)
            for k, v in extra.items():
                headers[k] = v
        return headers


def build_http_client(config: GatewayConfig) -> httpx.AsyncClient:
    """
    Create a shared httpx.AsyncClient configured from GatewayConfig.

    Call once at startup and store in app.state.
    """
    limits = httpx.Limits(
        max_connections=config.proxy_max_connections,
        max_keepalive_connections=config.proxy_max_keepalive_connections,
        keepalive_expiry=30,
    )
    timeout = httpx.Timeout(
        connect=config.proxy_timeout_connect,
        read=config.proxy_timeout_read,
        write=config.proxy_timeout_write,
        pool=config.proxy_timeout_pool,
    )
    return httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        follow_redirects=False,
        http2=True,
    )
