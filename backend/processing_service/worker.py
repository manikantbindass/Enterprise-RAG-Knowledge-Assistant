"""
RabbitMQ worker — consumes doc.uploaded events and runs full processing pipeline.

Pipeline per message:
  1. Fetch file from storage (S3/MinIO)
  2. Update DB status → processing
  3. Extract text (TextExtractor)
  4. OCR scanned pages (OCRService)
  5. Clean text (TextCleaner)
  6. Chunk text (ChunkingService)
  7. Persist chunks to DB
  8. Update DB status → chunking done
  9. Publish doc.processed event
  10. Update DB status → embedding (embedding service takes over)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from aio_pika import IncomingMessage, connect_robust
from aio_pika.abc import AbstractRobustConnection
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from processing_service.config import ProcessingServiceConfig
from processing_service.models.schemas import (
    Chunk,
    DocProcessedEvent,
    DocUploadedEvent,
    PageContent,
)
from processing_service.services.chunker import ChunkingService
from processing_service.services.cleaner import TextCleaner
from processing_service.services.extractor import ExtractionError, TextExtractor
from processing_service.services.ocr_service import OCRService

logger = structlog.get_logger(__name__)


class ProcessingWorker:
    """
    RabbitMQ consumer that processes document upload events.

    One instance per process. Multiple parallel prefetch slots handle
    concurrent documents (prefetch_count configurable).
    """

    def __init__(self, config: ProcessingServiceConfig) -> None:
        self._config = config
        self._rmq: AbstractRobustConnection | None = None
        self._session_factory: async_sessionmaker | None = None
        self._ocr = OCRService(
            engine=config.ocr_engine,
            tesseract_lang=config.tesseract_lang,
            tesseract_path=config.tesseract_path,
            azure_endpoint=config.azure_form_recognizer_endpoint,
            azure_key=config.azure_form_recognizer_key,
        )
        self._extractor = TextExtractor(
            ocr_service=self._ocr,
            max_pages=config.max_pages_per_document,
            pdf_fallback=config.pdf_fallback_to_pdfplumber,
        )
        self._cleaner = TextCleaner()
        self._chunker = ChunkingService(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            parent_chunk_size=config.parent_chunk_size,
            child_chunk_size=config.child_chunk_size,
            semantic_model=config.semantic_model,
            semantic_threshold=config.semantic_threshold,
        )
        self._log = logger.bind(worker="ProcessingWorker")

    async def start(self) -> None:
        """Initialize DB and RabbitMQ connections, then start consuming."""
        # DB
        engine = create_async_engine(
            self._config.database_url,
            pool_size=self._config.db_pool_size,
            max_overflow=self._config.db_max_overflow,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            engine, expire_on_commit=False, autoflush=False
        )

        # RabbitMQ
        self._rmq = await connect_robust(self._config.rabbitmq_url)
        self._log.info("worker_connected", url=self._config.rabbitmq_url.split("@")[-1])

        async with self._rmq.channel() as channel:
            await channel.set_qos(prefetch_count=self._config.rabbitmq_prefetch_count)

            # Declare exchange + queue
            exchange = await channel.declare_exchange(
                self._config.rabbitmq_exchange,
                durable=True,
            )
            queue = await channel.declare_queue(
                self._config.rabbitmq_doc_uploaded_queue,
                durable=True,
                arguments={"x-dead-letter-exchange": f"{self._config.rabbitmq_exchange}.dlx"},
            )
            await queue.bind(
                exchange,
                routing_key=self._config.rabbitmq_doc_uploaded_queue,
            )

            self._log.info(
                "consuming",
                queue=self._config.rabbitmq_doc_uploaded_queue,
                prefetch=self._config.rabbitmq_prefetch_count,
            )
            await queue.consume(self._handle_message)

            # Keep running until cancelled
            await asyncio.Future()

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._rmq:
            await self._rmq.close()
        self._log.info("worker_stopped")

    async def _handle_message(self, message: IncomingMessage) -> None:
        """
        Process a single doc.uploaded message.

        Acks on success, nacks (dead-letters) on permanent failure.
        """
        async with message.process(requeue=False):
            try:
                payload = json.loads(message.body)
                event = DocUploadedEvent(**payload)
            except (json.JSONDecodeError, Exception) as exc:
                self._log.error("invalid_message_payload", error=str(exc))
                return  # message already acked by context manager

            doc_id = uuid.UUID(event.document_id)
            log = self._log.bind(document_id=str(doc_id))
            log.info("processing_start", filename=event.filename)

            try:
                await self._process_document(event, doc_id)
                log.info("processing_complete")
            except Exception as exc:
                log.error("processing_failed", error=str(exc), exc_info=True)
                await self._update_status(doc_id, "failed", error_message=str(exc))

    async def _process_document(
        self, event: DocUploadedEvent, doc_id: uuid.UUID
    ) -> None:
        """Full processing pipeline for one document."""
        log = self._log.bind(document_id=str(doc_id))

        # 1. Update status → processing
        await self._update_status(doc_id, "processing")

        # 2. Fetch file from storage
        log.info("fetching_from_storage", storage_key=event.storage_key)
        content = await self._fetch_from_storage(event.storage_key, event.storage_backend)

        # 3. Extract text
        log.info("extracting_text", content_type=event.content_type)
        pages = await self._extractor.extract(
            content=content,
            content_type=event.content_type,
            filename=event.filename,
        )

        # 4. OCR any scanned pages
        scanned_pages = [p for p in pages if p.metadata.get("needs_ocr")]
        if scanned_pages:
            log.info("ocr_scanned_pages", count=len(scanned_pages))
            # Fetch original images for those pages (for PDFs, use PyMuPDF)
            ocr_results = await self._ocr_pdf_pages(content, scanned_pages)
            # Replace scanned placeholders with OCR results
            page_map = {r.page_num: r for r in ocr_results}
            pages = [page_map.get(p.page_num, p) for p in pages]

        # 5. Clean text
        log.info("cleaning_text")
        cleaned_pages = [
            PageContent(
                page_num=p.page_num,
                text=self._cleaner.clean(p.text),
                metadata=p.metadata,
                extraction_method=p.extraction_method,
            )
            for p in pages
        ]

        # Compute stats
        full_text = " ".join(p.text for p in cleaned_pages)
        word_count = self._cleaner.estimate_word_count(full_text)
        page_count = len(cleaned_pages)

        # 6. Chunk
        log.info("chunking", strategy=self._config.default_chunking_strategy)
        await self._update_status(doc_id, "chunking")
        chunks = self._chunker.chunk(
            pages=cleaned_pages,
            strategy=self._config.default_chunking_strategy,
            document_id=doc_id,
        )

        # 7. Persist chunks
        log.info("persisting_chunks", chunk_count=len(chunks))
        async with self._session_factory() as session:  # type: ignore[misc]
            await self._save_chunks(session, doc_id, chunks)
            await self._update_document_stats(
                session, doc_id, chunk_count=len(chunks),
                page_count=page_count, word_count=word_count,
                status="chunking",
            )
            await session.commit()

        # 8. Publish doc.processed
        await self._publish_processed_event(
            DocProcessedEvent(
                document_id=str(doc_id),
                chunk_count=len(chunks),
                page_count=page_count,
                word_count=word_count,
                storage_key=event.storage_key,
            )
        )

        # 9. Update status → embedding (embedding service takes over)
        await self._update_status(doc_id, "embedding")
        log.info("processing_pipeline_complete", chunks=len(chunks))

    async def _fetch_from_storage(
        self, storage_key: str, storage_backend: str
    ) -> bytes:
        """Download file bytes from S3/MinIO."""
        import boto3  # type: ignore[import-untyped]

        config = self._config
        loop = asyncio.get_event_loop()

        def _download_sync() -> bytes:
            kwargs: dict[str, Any] = {
                "aws_access_key_id": config.aws_access_key_id,
                "aws_secret_access_key": config.aws_secret_access_key,
                "region_name": config.aws_region,
            }
            if config.storage_backend == "minio":
                scheme = "https" if config.minio_secure else "http"
                kwargs["endpoint_url"] = f"{scheme}://{config.minio_endpoint}"
            elif config.s3_endpoint_url:
                kwargs["endpoint_url"] = config.s3_endpoint_url

            client = boto3.client("s3", **kwargs)
            response = client.get_object(Bucket=config.storage_bucket, Key=storage_key)
            return response["Body"].read()

        return await loop.run_in_executor(None, _download_sync)

    async def _ocr_pdf_pages(
        self, pdf_content: bytes, scanned_pages: list[PageContent]
    ) -> list[PageContent]:
        """Extract images from PDF pages and OCR them."""
        loop = asyncio.get_event_loop()
        results: list[PageContent] = []

        for page in scanned_pages:
            try:
                # Extract page as image using PyMuPDF
                img_bytes = await loop.run_in_executor(
                    None,
                    self._pdf_page_to_image,
                    pdf_content,
                    page.page_num - 1,
                )
                result = await self._ocr.ocr_image_bytes(img_bytes, page.page_num)
                results.append(result)
            except Exception as exc:
                logger.warning(
                    "pdf_page_ocr_failed",
                    page_num=page.page_num,
                    error=str(exc),
                )
                results.append(page)

        return results

    def _pdf_page_to_image(self, pdf_content: bytes, page_index: int) -> bytes:
        """Render PDF page to PNG bytes using PyMuPDF."""
        import fitz  # type: ignore[import-untyped]
        import io

        doc = fitz.open(stream=pdf_content, filetype="pdf")
        page = doc[page_index]
        mat = fitz.Matrix(2.0, 2.0)  # 2x scale for better OCR accuracy
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        doc.close()
        return img_bytes

    async def _save_chunks(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        chunks: list[Chunk],
    ) -> None:
        """Bulk insert chunks into document_chunks table."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        if not chunks:
            return

        rows = [
            {
                "id": chunk.chunk_id,
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "page_number": chunk.page_number,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "token_count": chunk.token_count,
                "chunk_metadata": chunk.metadata,
            }
            for chunk in chunks
        ]

        # Use PostgreSQL INSERT ... ON CONFLICT DO NOTHING for idempotency
        from sqlalchemy import text

        # Batch insert in groups of 500
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            await session.execute(
                text(
                    """
                    INSERT INTO document_chunks
                        (id, document_id, chunk_index, content, page_number,
                         start_char, end_char, token_count, chunk_metadata)
                    VALUES
                        (:id, :document_id, :chunk_index, :content, :page_number,
                         :start_char, :end_char, :token_count, :chunk_metadata::jsonb)
                    ON CONFLICT DO NOTHING
                    """
                ),
                batch,
            )

    async def _update_document_stats(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        chunk_count: int,
        page_count: int,
        word_count: int,
        status: str,
    ) -> None:
        """Update document statistics after processing."""
        from sqlalchemy import text

        await session.execute(
            text(
                """
                UPDATE documents
                SET chunk_count = :chunk_count,
                    page_count = :page_count,
                    word_count = :word_count,
                    status = :status,
                    updated_at = now()
                WHERE id = :document_id
                """
            ),
            {
                "chunk_count": chunk_count,
                "page_count": page_count,
                "word_count": word_count,
                "status": status,
                "document_id": document_id,
            },
        )

    async def _update_status(
        self,
        document_id: uuid.UUID,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Update document status in DB."""
        if not self._session_factory:
            return

        async with self._session_factory() as session:
            from sqlalchemy import text

            params: dict[str, Any] = {
                "status": status,
                "document_id": document_id,
                "error_message": error_message,
            }
            await session.execute(
                text(
                    """
                    UPDATE documents
                    SET status = :status,
                        error_message = :error_message,
                        updated_at = now()
                    WHERE id = :document_id
                    """
                ),
                params,
            )
            await session.commit()

    async def _publish_processed_event(self, event: DocProcessedEvent) -> None:
        """Publish doc.processed to RabbitMQ."""
        if not self._rmq:
            return

        try:
            from aio_pika import Message

            async with self._rmq.channel() as channel:
                exchange = await channel.declare_exchange(
                    self._config.rabbitmq_exchange, durable=True
                )
                message = Message(
                    body=event.model_dump_json().encode(),
                    content_type="application/json",
                    delivery_mode=2,
                )
                await exchange.publish(
                    message,
                    routing_key=self._config.rabbitmq_doc_processed_routing_key,
                )
                self._log.info(
                    "event_published",
                    routing_key=self._config.rabbitmq_doc_processed_routing_key,
                    document_id=event.document_id,
                )
        except Exception as exc:
            self._log.error("event_publish_failed", error=str(exc))
