"""
Embedding Service Worker — RabbitMQ consumer
Consumes doc.processed events → embeds chunks → stores in pgvector
"""
from __future__ import annotations

import json
import uuid

import aio_pika
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import EmbeddingConfig
from services.embedding_service import EmbeddingService

logger = structlog.get_logger(__name__)


class EmbeddingWorker:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config
        self.embedding_svc = EmbeddingService(config)
        self.engine = create_async_engine(config.database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def start(self) -> None:
        logger.info("Embedding worker connecting to RabbitMQ")
        connection = await aio_pika.connect_robust(self.config.rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue("doc.processed", durable=True)
            logger.info("Embedding worker listening", queue="doc.processed")
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process(requeue_on_fail=True):
                        await self._handle_message(message.body)

    async def _handle_message(self, body: bytes) -> None:
        try:
            payload = json.loads(body)
            document_id = uuid.UUID(payload["document_id"])
            org_id = uuid.UUID(payload["org_id"])
            provider = payload.get("embedding_provider", self.config.default_embedding_provider)
            logger.info("Processing embedding job", document_id=str(document_id))
            await self._embed_document(document_id, org_id, provider)
        except Exception as e:
            logger.error("Embedding job failed", error=str(e), exc_info=True)
            raise

    async def _embed_document(self, document_id: uuid.UUID, org_id: uuid.UUID, provider: str) -> None:
        async with self.session_factory() as session:
            # Set tenant context
            await session.execute(
                f"SET LOCAL app.current_org_id = '{org_id}'"  # noqa: S608
            )

            # Load un-embedded chunks
            from sqlalchemy import select, text
            from shared.models.document import DocumentChunk, Document

            result = await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.embedding.is_(None),
                )
            )
            chunks = result.scalars().all()
            if not chunks:
                logger.info("No chunks to embed", document_id=str(document_id))
                return

            texts = [c.content for c in chunks]
            embeddings, total_cost = await self.embedding_svc.embed_texts(texts, provider=provider)

            # Store embeddings
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding  # pgvector accepts list[float]

            # Update document status
            doc_result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                doc.status = "indexed"
                doc.chunk_count = len(chunks)

            await session.commit()
            logger.info(
                "Embeddings stored",
                document_id=str(document_id),
                chunk_count=len(chunks),
                cost_usd=total_cost,
                provider=provider,
            )
