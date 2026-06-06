"""
Audit Service Worker — RabbitMQ consumer.

Consumes audit.event messages from RabbitMQ and bulk-inserts into PostgreSQL.
Uses asyncio batching: accumulate events for up to FLUSH_INTERVAL seconds
or BATCH_SIZE events, whichever comes first. This gives ~10-50x insert
throughput vs single-row inserts.
"""

from __future__ import annotations

import asyncio
import json
import signal
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from aio_pika import IncomingMessage, connect_robust
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from audit_service.config import get_config
from audit_service.models.schemas import AuditEventPayload
from audit_service.repositories.audit_repository import AuditRepository

logger = structlog.get_logger(__name__)
cfg = get_config()


class AuditWorker:
    """
    RabbitMQ consumer with async batch processing.

    Architecture:
      - Consumer coroutine reads messages → puts into asyncio.Queue
      - Flusher coroutine drains queue every FLUSH_INTERVAL or BATCH_SIZE
      - DB write uses bulk INSERT with ON CONFLICT DO NOTHING (idempotent)
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10_000)
        self._engine = create_async_engine(
            cfg.database_url,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._running = True
        self._total_processed = 0
        self._total_failed = 0

    async def _parse_message(self, raw: bytes) -> dict[str, Any] | None:
        """Parse and validate incoming RabbitMQ message."""
        try:
            data = json.loads(raw.decode("utf-8"))
            payload = AuditEventPayload.model_validate(data)
            return {
                "id": uuid.uuid4(),
                "organization_id": payload.organization_id,
                "user_id": payload.user_id,
                "action": payload.action,
                "resource_type": payload.resource_type,
                "resource_id": payload.resource_id,
                "before_state": payload.before_state,
                "after_state": payload.after_state,
                "ip_address": payload.ip_address,
                "user_agent": payload.user_agent,
                "success": payload.success,
                "error_message": payload.error_message,
                "metadata_": payload.metadata,
                "created_at": payload.timestamp or datetime.now(timezone.utc),
            }
        except Exception as exc:
            logger.error("audit_worker.parse_error", error=str(exc), raw=raw[:200])
            self._total_failed += 1
            return None

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        """RabbitMQ message callback — parse and enqueue."""
        async with message.process(requeue=False):
            parsed = await self._parse_message(message.body)
            if parsed:
                await self._queue.put(parsed)

    async def _flush_batch(self, batch: list[dict[str, Any]]) -> None:
        """Bulk insert a batch into the database."""
        if not batch:
            return
        try:
            async with self._session_factory() as session:
                repo = AuditRepository(session)
                inserted = await repo.bulk_insert(batch)
                await session.commit()
                self._total_processed += inserted
                logger.info(
                    "audit_worker.flushed",
                    batch_size=len(batch),
                    inserted=inserted,
                    total=self._total_processed,
                )
        except Exception as exc:
            logger.error("audit_worker.flush_error", error=str(exc), batch_size=len(batch))

    async def _flusher_loop(self) -> None:
        """
        Continuously drain queue into DB.

        Flushes when batch is full OR flush interval elapses.
        """
        batch: list[dict[str, Any]] = []
        last_flush = asyncio.get_event_loop().time()

        while self._running or not self._queue.empty():
            now = asyncio.get_event_loop().time()
            elapsed = now - last_flush

            # Drain available items up to batch size
            try:
                while len(batch) < cfg.bulk_insert_batch_size:
                    item = self._queue.get_nowait()
                    batch.append(item)
                    self._queue.task_done()
            except asyncio.QueueEmpty:
                pass

            should_flush = (
                len(batch) >= cfg.bulk_insert_batch_size
                or (batch and elapsed >= cfg.bulk_insert_flush_interval_seconds)
            )

            if should_flush:
                await self._flush_batch(batch)
                batch = []
                last_flush = asyncio.get_event_loop().time()
            else:
                await asyncio.sleep(0.1)

        # Final flush on shutdown
        if batch:
            await self._flush_batch(batch)

    async def run(self) -> None:
        """Start the worker: connect to RabbitMQ, consume messages."""
        logger.info("audit_worker.starting", queue=cfg.audit_queue)

        connection = await connect_robust(cfg.rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=cfg.worker_prefetch_count)

            exchange = await channel.declare_exchange(
                cfg.rabbitmq_exchange,
                durable=True,
                type="topic",
            )
            queue = await channel.declare_queue(
                cfg.audit_queue,
                durable=True,
                arguments={"x-queue-type": "quorum"},
            )
            await queue.bind(exchange, routing_key=cfg.audit_routing_key)

            logger.info("audit_worker.ready", queue=cfg.audit_queue)

            # Start flusher loop as concurrent task
            flusher_task = asyncio.create_task(self._flusher_loop())

            # Consume messages
            await queue.consume(self._on_message)

            # Wait until signal
            stop_event = asyncio.Event()

            def _shutdown(sig: int, _: Any) -> None:
                logger.info("audit_worker.shutdown_signal", signal=sig)
                self._running = False
                stop_event.set()

            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, _shutdown, sig, None)

            await stop_event.wait()
            await flusher_task

        await self._engine.dispose()
        logger.info(
            "audit_worker.stopped",
            total_processed=self._total_processed,
            total_failed=self._total_failed,
        )


async def main() -> None:
    """Entry point for standalone worker process."""
    import structlog

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )
    worker = AuditWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
