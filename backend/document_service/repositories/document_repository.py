"""
Document repository — all database operations for documents and chunks.

Uses SQLAlchemy 2.0 async ORM throughout.
No raw SQL except for bulk operations where performance demands it.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any, Sequence

import structlog
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from document_service.models.schemas import DocumentListFilter, DocumentStatus

logger = structlog.get_logger(__name__)


# ── ORM Models ────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class DocumentORM(Base):
    """Documents table."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_status", "status"),
        Index("ix_documents_department", "department"),
        Index("ix_documents_created_at", "created_at"),
        Index("ix_documents_content_hash", "content_hash"),
        Index(
            "ix_documents_title_fts",
            func.to_tsvector("english", "title"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocumentStatus.PENDING.value
    )
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    chunks: Mapped[list["DocumentChunkORM"]] = relationship(
        "DocumentChunkORM",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class DocumentChunkORM(Base):
    """Document chunks table — stores extracted text segments."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_chunk_index", "document_id", "chunk_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["DocumentORM"] = relationship(
        "DocumentORM", back_populates="chunks"
    )


# ── Repository ────────────────────────────────────────────────────────────────


class DocumentRepository:
    """
    All database operations for documents.

    Receives an AsyncSession per request (injected via FastAPI dependency).
    Never commits/rollbacks here — that's the caller's responsibility.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._log = logger.bind(repository="DocumentRepository")

    # ── Documents ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        title: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_key: str,
        storage_backend: str,
        department: str | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
        metadata: dict[str, Any] | None = None,
        content: bytes | None = None,
    ) -> DocumentORM:
        """Insert new document record."""
        content_hash: str | None = None
        if content:
            content_hash = hashlib.sha256(content).hexdigest()

        doc = DocumentORM(
            title=title,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            content_hash=content_hash,
            storage_key=storage_key,
            storage_backend=storage_backend,
            department=department,
            tags=tags or [],
            source_url=source_url,
            document_metadata=metadata or {},
            status=DocumentStatus.PENDING.value,
        )
        self._session.add(doc)
        await self._session.flush()
        self._log.info("document_created", document_id=str(doc.id), filename=filename)
        return doc

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentORM | None:
        """Fetch single document (excludes soft-deleted)."""
        stmt = select(DocumentORM).where(
            DocumentORM.id == document_id,
            DocumentORM.is_deleted.is_(False),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_include_deleted(
        self, document_id: uuid.UUID
    ) -> DocumentORM | None:
        """Fetch document regardless of deletion status."""
        stmt = select(DocumentORM).where(DocumentORM.id == document_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        filters: DocumentListFilter,
    ) -> tuple[Sequence[DocumentORM], int]:
        """
        Paginated list with filters.

        Returns:
            Tuple of (items, total_count).
        """
        base_stmt = select(DocumentORM).where(DocumentORM.is_deleted.is_(False))

        # Apply filters
        if filters.status:
            base_stmt = base_stmt.where(DocumentORM.status == filters.status.value)
        if filters.department:
            base_stmt = base_stmt.where(
                DocumentORM.department.ilike(f"%{filters.department}%")
            )
        if filters.tags:
            for tag in filters.tags:
                base_stmt = base_stmt.where(
                    DocumentORM.tags.contains([tag])  # type: ignore[attr-defined]
                )
        if filters.date_from:
            base_stmt = base_stmt.where(DocumentORM.created_at >= filters.date_from)
        if filters.date_to:
            base_stmt = base_stmt.where(DocumentORM.created_at <= filters.date_to)
        if filters.search:
            search_term = f"%{filters.search}%"
            base_stmt = base_stmt.where(
                or_(
                    DocumentORM.title.ilike(search_term),
                    DocumentORM.filename.ilike(search_term),
                )
            )

        # Count total
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        # Apply pagination
        offset = (filters.page - 1) * filters.page_size
        paged_stmt = (
            base_stmt.order_by(DocumentORM.created_at.desc())
            .offset(offset)
            .limit(filters.page_size)
        )

        items_result = await self._session.execute(paged_stmt)
        items = items_result.scalars().all()

        return items, total

    async def update_status(
        self,
        document_id: uuid.UUID,
        status: DocumentStatus,
        error_message: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """Update document status (and optionally other fields)."""
        values: dict[str, Any] = {
            "status": status.value,
            "updated_at": func.now(),
        }
        if error_message is not None:
            values["error_message"] = error_message
        if extra:
            values.update(extra)
        if status == DocumentStatus.INDEXED:
            values["indexed_at"] = func.now()

        stmt = (
            update(DocumentORM)
            .where(DocumentORM.id == document_id)
            .values(**values)
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    async def soft_delete(self, document_id: uuid.UUID) -> bool:
        """Mark document as deleted without physical row removal."""
        stmt = (
            update(DocumentORM)
            .where(DocumentORM.id == document_id, DocumentORM.is_deleted.is_(False))
            .values(is_deleted=True, status=DocumentStatus.DELETED.value, updated_at=func.now())
        )
        result = await self._session.execute(stmt)
        deleted = result.rowcount > 0
        if deleted:
            self._log.info("document_soft_deleted", document_id=str(document_id))
        return deleted

    async def get_content_hash(self, content_hash: str) -> DocumentORM | None:
        """Check if document with same content already exists."""
        stmt = select(DocumentORM).where(
            DocumentORM.content_hash == content_hash,
            DocumentORM.is_deleted.is_(False),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Chunks ────────────────────────────────────────────────────────────────

    async def get_chunks(
        self,
        document_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[Sequence[DocumentChunkORM], int]:
        """Get paginated chunks for a document."""
        base_stmt = select(DocumentChunkORM).where(
            DocumentChunkORM.document_id == document_id
        )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        paged_stmt = (
            base_stmt.order_by(DocumentChunkORM.chunk_index)
            .offset(offset)
            .limit(page_size)
        )
        items_result = await self._session.execute(paged_stmt)
        return items_result.scalars().all(), total
