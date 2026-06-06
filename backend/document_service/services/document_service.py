"""
Document business logic service.

Orchestrates: validation → virus scan → storage → DB → queue.
"""

from __future__ import annotations

import io
import json
import uuid
from typing import Any

import magic  # type: ignore[import-untyped]
import structlog
from aio_pika import Message, connect_robust
from aio_pika.abc import AbstractRobustConnection

from document_service.config import DocumentServiceConfig
from document_service.exceptions import (
    DocumentNotFoundError,
    FileTooLargeError,
    ProcessingQueueError,
    StorageError,
    UnsupportedFileTypeError,
    VirusScanError,
)
from document_service.models.schemas import (
    DocumentChunkListResponse,
    DocumentChunkResponse,
    DocumentCreate,
    DocumentListFilter,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentStatusResponse,
    DocumentSummary,
    DocumentUploadResponse,
    PresignedUrlResponse,
)
from document_service.repositories.document_repository import (
    DocumentChunkORM,
    DocumentORM,
    DocumentRepository,
)
from document_service.services.virus_scanner import VirusScannerService

logger = structlog.get_logger(__name__)


def _orm_to_response(doc: DocumentORM) -> DocumentResponse:
    """Convert ORM model → response schema."""
    return DocumentResponse(
        id=doc.id,
        title=doc.title,
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        status=DocumentStatus(doc.status),
        department=doc.department,
        tags=doc.tags or [],
        source_url=doc.source_url,
        storage_key=doc.storage_key,
        storage_backend=doc.storage_backend,
        chunk_count=doc.chunk_count,
        page_count=doc.page_count,
        word_count=doc.word_count,
        error_message=doc.error_message,
        metadata=doc.document_metadata or {},
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        indexed_at=doc.indexed_at,
    )


def _orm_to_summary(doc: DocumentORM) -> DocumentSummary:
    """Convert ORM model → lightweight summary schema."""
    return DocumentSummary(
        id=doc.id,
        title=doc.title,
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        status=DocumentStatus(doc.status),
        department=doc.department,
        tags=doc.tags or [],
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _chunk_orm_to_response(chunk: DocumentChunkORM) -> DocumentChunkResponse:
    return DocumentChunkResponse(
        id=chunk.id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        page_number=chunk.page_number,
        start_char=chunk.start_char,
        end_char=chunk.end_char,
        token_count=chunk.token_count,
        metadata=chunk.chunk_metadata or {},
        created_at=chunk.created_at,
    )


class DocumentService:
    """
    Orchestrates all document operations.

    Injected dependencies:
      - repo: database operations
      - storage: S3/MinIO client
      - virus_scanner: ClamAV wrapper
      - config: service configuration
      - rabbitmq_connection: shared AMQP connection
    """

    def __init__(
        self,
        repo: DocumentRepository,
        storage: "StorageClient",
        virus_scanner: VirusScannerService,
        config: DocumentServiceConfig,
        rabbitmq_connection: AbstractRobustConnection | None,
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._scanner = virus_scanner
        self._config = config
        self._rmq = rabbitmq_connection
        self._log = logger.bind(service="DocumentService")

    async def upload_document(
        self,
        filename: str,
        content: bytes,
        metadata: DocumentCreate,
    ) -> DocumentUploadResponse:
        """
        Full upload pipeline:
        1. Validate file size
        2. Detect MIME type
        3. Virus scan
        4. Upload to storage
        5. Create DB record
        6. Publish doc.uploaded event
        """
        log = self._log.bind(filename=filename, size_bytes=len(content))

        # 1. Size check
        if len(content) > self._config.max_file_size_bytes:
            raise FileTooLargeError(len(content), self._config.max_file_size_bytes)

        # 2. MIME detection (use libmagic, not content-type header — can be spoofed)
        detected_mime = magic.from_buffer(content, mime=True)
        log.info("mime_detected", mime=detected_mime)

        if detected_mime not in self._config.allowed_mime_types:
            raise UnsupportedFileTypeError(detected_mime, self._config.allowed_mime_types)

        # 3. Virus scan
        if self._config.virus_scan_enabled:
            scan_result = await self._scanner.scan_file(content)
            if not scan_result.is_clean:
                raise VirusScanError(scan_result.virus_name or "UNKNOWN")

        # 4. Upload to storage
        storage_key = f"documents/{uuid.uuid4()}/{filename}"
        try:
            await self._storage.upload(
                key=storage_key,
                data=content,
                content_type=detected_mime,
            )
        except Exception as exc:
            log.error("storage_upload_failed", error=str(exc))
            raise StorageError(str(exc))

        # 5. Create DB record
        title = metadata.title or filename
        doc = await self._repo.create(
            title=title,
            filename=filename,
            content_type=detected_mime,
            size_bytes=len(content),
            storage_key=storage_key,
            storage_backend=self._config.storage_backend,
            department=metadata.department,
            tags=metadata.tags,
            source_url=metadata.source_url,
            metadata=metadata.metadata,
            content=content,
        )
        log.info("document_db_created", document_id=str(doc.id))

        # 6. Publish event
        await self._publish_event(
            routing_key=self._config.rabbitmq_doc_uploaded_routing_key,
            payload={
                "document_id": str(doc.id),
                "storage_key": storage_key,
                "storage_backend": self._config.storage_backend,
                "content_type": detected_mime,
                "filename": filename,
                "size_bytes": len(content),
                "metadata": metadata.model_dump(),
            },
        )

        return DocumentUploadResponse(
            id=doc.id,
            title=title,
            filename=filename,
            status=DocumentStatus.PENDING,
            storage_key=storage_key,
        )

    async def list_documents(
        self, filters: DocumentListFilter
    ) -> DocumentListResponse:
        """Return paginated document list matching filters."""
        items, total = await self._repo.list_documents(filters)
        return DocumentListResponse(
            items=[_orm_to_summary(d) for d in items],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            pages=0,  # model_validator computes this
        )

    async def get_document(self, document_id: uuid.UUID) -> DocumentResponse:
        """Fetch single document by ID."""
        doc = await self._repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(str(document_id))
        return _orm_to_response(doc)

    async def delete_document(self, document_id: uuid.UUID) -> None:
        """
        Soft-delete document:
        1. Mark as deleted in DB
        2. Remove from storage
        3. Note: vector removal triggered by embedding service via event
        """
        doc = await self._repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(str(document_id))

        deleted = await self._repo.soft_delete(document_id)
        if not deleted:
            raise DocumentNotFoundError(str(document_id))

        # Remove from storage (best-effort — don't fail if already gone)
        try:
            await self._storage.delete(doc.storage_key)
        except Exception as exc:
            self._log.warning(
                "storage_delete_failed",
                document_id=str(document_id),
                storage_key=doc.storage_key,
                error=str(exc),
            )

        # Publish delete event for embedding service to remove vectors
        await self._publish_event(
            routing_key="doc.deleted",
            payload={"document_id": str(document_id)},
        )

        self._log.info("document_deleted", document_id=str(document_id))

    async def get_download_url(
        self, document_id: uuid.UUID
    ) -> PresignedUrlResponse:
        """Generate presigned URL for direct S3/MinIO download."""
        doc = await self._repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(str(document_id))

        try:
            url = await self._storage.presign_get(
                key=doc.storage_key,
                expires_seconds=self._config.presigned_url_expiry_seconds,
            )
        except Exception as exc:
            raise StorageError(f"Failed to generate presigned URL: {exc}")

        return PresignedUrlResponse(
            document_id=document_id,
            url=url,
            expires_in_seconds=self._config.presigned_url_expiry_seconds,
            filename=doc.filename,
        )

    async def get_status(self, document_id: uuid.UUID) -> DocumentStatusResponse:
        """Lightweight status check."""
        doc = await self._repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(str(document_id))
        return DocumentStatusResponse(
            id=doc.id,
            status=DocumentStatus(doc.status),
            error_message=doc.error_message,
            chunk_count=doc.chunk_count,
            updated_at=doc.updated_at,
        )

    async def get_chunks(
        self,
        document_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> DocumentChunkListResponse:
        """Get paginated chunks for a document."""
        doc = await self._repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(str(document_id))

        chunks, total = await self._repo.get_chunks(document_id, page, page_size)
        return DocumentChunkListResponse(
            items=[_chunk_orm_to_response(c) for c in chunks],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def _publish_event(self, routing_key: str, payload: dict[str, Any]) -> None:
        """Publish JSON event to RabbitMQ exchange."""
        if not self._rmq:
            self._log.warning(
                "rabbitmq_not_connected",
                routing_key=routing_key,
                reason="RabbitMQ connection not available — skipping event publish",
            )
            return

        try:
            async with self._rmq.channel() as channel:
                exchange = await channel.declare_exchange(
                    self._config.rabbitmq_exchange,
                    durable=True,
                )
                message = Message(
                    body=json.dumps(payload).encode(),
                    content_type="application/json",
                    delivery_mode=2,  # persistent
                )
                await exchange.publish(message, routing_key=routing_key)
                self._log.info(
                    "event_published",
                    routing_key=routing_key,
                    document_id=payload.get("document_id"),
                )
        except Exception as exc:
            self._log.error(
                "event_publish_failed",
                routing_key=routing_key,
                error=str(exc),
            )
            raise ProcessingQueueError(str(exc))


# ── Storage client abstraction ────────────────────────────────────────────────


class StorageClient:
    """
    Thin async wrapper over boto3 S3 / MinIO.

    Runs blocking boto3 calls in a thread pool executor.
    """

    def __init__(self, config: DocumentServiceConfig) -> None:
        self._config = config
        self._client: Any = None

    def _build_client(self) -> Any:
        """Build boto3 S3 client (or MinIO-compatible endpoint)."""
        import boto3  # type: ignore[import-untyped]

        kwargs: dict[str, Any] = {
            "aws_access_key_id": self._config.aws_access_key_id,
            "aws_secret_access_key": self._config.aws_secret_access_key,
            "region_name": self._config.aws_region,
        }

        if self._config.storage_backend == "minio":
            scheme = "https" if self._config.minio_secure else "http"
            kwargs["endpoint_url"] = f"{scheme}://{self._config.minio_endpoint}"
        elif self._config.s3_endpoint_url:
            kwargs["endpoint_url"] = self._config.s3_endpoint_url

        return boto3.client("s3", **kwargs)

    async def initialize(self) -> None:
        """Initialize S3 client and ensure bucket exists."""
        import asyncio

        loop = asyncio.get_event_loop()
        self._client = await loop.run_in_executor(None, self._build_client)

        # Ensure bucket exists
        await loop.run_in_executor(None, self._ensure_bucket)
        logger.info(
            "storage_initialized",
            backend=self._config.storage_backend,
            bucket=self._config.storage_bucket,
        )

    def _ensure_bucket(self) -> None:
        """Create bucket if it doesn't exist (idempotent)."""
        try:
            self._client.head_bucket(Bucket=self._config.storage_bucket)
        except self._client.exceptions.ClientError:
            self._client.create_bucket(Bucket=self._config.storage_bucket)
            logger.info("bucket_created", bucket=self._config.storage_bucket)

    async def upload(
        self, key: str, data: bytes, content_type: str
    ) -> None:
        """Upload bytes to storage."""
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.put_object(
                Bucket=self._config.storage_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            ),
        )

    async def delete(self, key: str) -> None:
        """Delete object from storage."""
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.delete_object(
                Bucket=self._config.storage_bucket, Key=key
            ),
        )

    async def presign_get(self, key: str, expires_seconds: int = 3600) -> str:
        """Generate presigned GET URL."""
        import asyncio

        loop = asyncio.get_event_loop()
        url: str = await loop.run_in_executor(
            None,
            lambda: self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._config.storage_bucket, "Key": key},
                ExpiresIn=expires_seconds,
            ),
        )
        return url
