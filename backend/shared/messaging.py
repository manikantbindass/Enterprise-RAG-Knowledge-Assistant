"""
RabbitMQ async client using aio-pika.

Provides:
- RabbitMQClient: connection pool, publisher, graceful reconnect
- AsyncPublisher: publish messages to exchange with routing key
- BaseConsumer: abstract consumer — subclass and implement process_message()

Message serialization: JSON (msgpack optional, falls back to JSON).

Connection pooling via aio_pika.pool.Pool — reuse connections and channels
across concurrent coroutines without creating a connection per request.

Usage (publisher):
    client = RabbitMQClient(url=settings.RABBITMQ_URL)
    await client.connect()
    await client.publish(
        exchange="documents",
        routing_key="document.uploaded",
        payload={"document_id": str(doc_id)},
    )

Usage (consumer):
    class DocumentConsumer(BaseConsumer):
        async def process_message(self, payload: dict, message: IncomingMessage):
            doc_id = payload["document_id"]
            await process_document(doc_id)

    consumer = DocumentConsumer(client, queue_name="document_processing")
    await consumer.start_consuming()
"""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import structlog
from aio_pika import (
    DeliveryMode,
    ExchangeType,
    Message,
    connect_robust,
)
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
)
from aio_pika.pool import Pool
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


def _serialize(payload: dict[str, Any]) -> bytes:
    """Serialize payload to JSON bytes. Extend to msgpack if needed."""
    return json.dumps(payload, default=_json_default).encode("utf-8")


def _deserialize(data: bytes) -> dict[str, Any]:
    """Deserialize message bytes to dict."""
    return json.loads(data.decode("utf-8"))


def _json_default(obj: Any) -> Any:
    """Handle non-serializable types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class RabbitMQClient:
    """
    Async RabbitMQ client with connection and channel pooling.

    Uses aio_pika.pool.Pool for efficient connection reuse.
    Connections auto-reconnect on failure (connect_robust).
    """

    def __init__(
        self,
        url: str,
        *,
        prefetch_count: int = 10,
        connection_pool_size: int = 2,
        channel_pool_size: int = 10,
        reconnect_interval: float = 5.0,
    ) -> None:
        self._url = url
        self._prefetch_count = prefetch_count
        self._connection_pool_size = connection_pool_size
        self._channel_pool_size = channel_pool_size
        self._reconnect_interval = reconnect_interval

        self._connection_pool: Pool[AbstractConnection] | None = None
        self._channel_pool: Pool[AbstractChannel] | None = None

    async def connect(self) -> None:
        """Initialize connection and channel pools."""

        async def get_connection() -> AbstractConnection:
            return await connect_robust(
                self._url,
                reconnect_interval=self._reconnect_interval,
            )

        async def get_channel() -> AbstractChannel:
            async with self._connection_pool.acquire() as connection:  # type: ignore[union-attr]
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=self._prefetch_count)
                return channel

        self._connection_pool = Pool(
            get_connection,
            max_size=self._connection_pool_size,
        )
        self._channel_pool = Pool(
            get_channel,
            max_size=self._channel_pool_size,
        )

        logger.info(
            "rabbitmq_connected",
            url=self._redact_url(self._url),
            connection_pool_size=self._connection_pool_size,
            channel_pool_size=self._channel_pool_size,
        )

    async def close(self) -> None:
        """Gracefully close all pooled connections."""
        if self._channel_pool:
            await self._channel_pool.close()
        if self._connection_pool:
            await self._connection_pool.close()
        logger.info("rabbitmq_disconnected")

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        *,
        exchange_type: ExchangeType = ExchangeType.TOPIC,
        persistent: bool = True,
        priority: int = 0,
        correlation_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Publish a message to an exchange.

        Args:
            exchange: Exchange name. Empty string = default exchange.
            routing_key: Message routing key.
            payload: Python dict — will be JSON-serialized.
            exchange_type: Exchange type (TOPIC by default).
            persistent: If True, message survives broker restart.
            priority: Message priority (0-9).
            correlation_id: Optional correlation ID for RPC patterns.
            headers: Optional AMQP message headers.
        """
        if not self._channel_pool:
            raise RuntimeError("RabbitMQClient not connected. Call connect() first.")

        body = _serialize(payload)
        message = Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT if persistent else DeliveryMode.NOT_PERSISTENT,
            content_type="application/json",
            content_encoding="utf-8",
            priority=priority,
            correlation_id=correlation_id or str(uuid.uuid4()),
            message_id=str(uuid.uuid4()),
            headers=headers or {},
        )

        async with self._channel_pool.acquire() as channel:
            amqp_exchange: AbstractExchange = await channel.declare_exchange(
                exchange,
                type=exchange_type,
                durable=True,
            )
            await amqp_exchange.publish(message, routing_key=routing_key)

        logger.debug(
            "message_published",
            exchange=exchange,
            routing_key=routing_key,
            size_bytes=len(body),
        )

    @staticmethod
    def _redact_url(url: str) -> str:
        try:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)
            if parsed.password:
                netloc = f"{parsed.username}:***@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return urlunparse(parsed._replace(netloc=netloc))
        except Exception:
            pass
        return url


class BaseConsumer(ABC):
    """
    Abstract base class for RabbitMQ consumers.

    Subclass and implement process_message(). Handles:
    - Queue declaration and binding
    - Message deserialization
    - Ack on success, Nack on failure (with dead-letter routing)
    - Graceful shutdown

    Usage:
        class MyConsumer(BaseConsumer):
            async def process_message(self, payload: dict, message: AbstractIncomingMessage):
                await do_work(payload)

        consumer = MyConsumer(
            client=rabbitmq_client,
            queue_name="my_queue",
            exchange="my_exchange",
            routing_keys=["task.created"],
        )
        await consumer.start_consuming()
    """

    def __init__(
        self,
        client: RabbitMQClient,
        *,
        queue_name: str,
        exchange: str,
        routing_keys: list[str],
        exchange_type: ExchangeType = ExchangeType.TOPIC,
        dead_letter_exchange: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self._client = client
        self._queue_name = queue_name
        self._exchange = exchange
        self._routing_keys = routing_keys
        self._exchange_type = exchange_type
        self._dead_letter_exchange = dead_letter_exchange
        self._max_retries = max_retries
        self._consuming = False

    @abstractmethod
    async def process_message(
        self,
        payload: dict[str, Any],
        message: AbstractIncomingMessage,
    ) -> None:
        """
        Process a deserialized message payload.

        Raise any exception to NACK the message.
        Return normally to ACK.
        """

    async def start_consuming(self) -> None:
        """Start consuming messages. Blocks until stop_consuming() is called."""
        if not self._client._channel_pool:
            raise RuntimeError("RabbitMQClient not connected.")

        self._consuming = True

        async with self._client._channel_pool.acquire() as channel:
            exchange = await channel.declare_exchange(
                self._exchange,
                type=self._exchange_type,
                durable=True,
            )

            queue_args: dict[str, Any] = {}
            if self._dead_letter_exchange:
                queue_args["x-dead-letter-exchange"] = self._dead_letter_exchange

            queue: AbstractQueue = await channel.declare_queue(
                self._queue_name,
                durable=True,
                arguments=queue_args,
            )

            for routing_key in self._routing_keys:
                await queue.bind(exchange, routing_key=routing_key)

            logger.info(
                "consumer_started",
                queue=self._queue_name,
                exchange=self._exchange,
                routing_keys=self._routing_keys,
            )

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if not self._consuming:
                        break
                    await self._handle_message(message)

    async def stop_consuming(self) -> None:
        """Signal the consumer to stop after the current message."""
        self._consuming = False
        logger.info("consumer_stopping", queue=self._queue_name)

    async def _handle_message(self, message: AbstractIncomingMessage) -> None:
        """Deserialize, process, ack/nack."""
        try:
            payload = _deserialize(message.body)
            await self.process_message(payload, message)
            await message.ack()
            logger.debug(
                "message_processed",
                queue=self._queue_name,
                message_id=message.message_id,
            )
        except Exception as exc:
            delivery_count = (message.headers or {}).get("x-delivery-count", 0)
            should_requeue = int(delivery_count) < self._max_retries

            logger.error(
                "message_processing_failed",
                queue=self._queue_name,
                message_id=message.message_id,
                error=str(exc),
                delivery_count=delivery_count,
                requeue=should_requeue,
                exc_info=True,
            )

            await message.nack(requeue=should_requeue)
