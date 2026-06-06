"""
Document and DocumentChunk SQLAlchemy models.

Document     — uploaded file record (PDF, DOCX, TXT, etc.)
DocumentChunk — text chunks with pgvector embeddings for semantic search.

pgvector extension must be installed: CREATE EXTENSION vector;
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import TenantModel

if TYPE_CHECKING:
    from shared.models.organization import Organization


class DocumentStatus(str, enum.Enum):
    """
    Processing pipeline status for uploaded documents.

    pending     → uploading (upload complete, queued for processing)
    uploading   → processing (file ingested into storage)
    processing  → indexed | failed
    indexed     — chunks created and embedded, searchable
    failed      — processing error (see error_message)
    archived    — soft-deleted, not searchable
    """

    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    ARCHIVED = "archived"


class Document(TenantModel):
    """
    Uploaded knowledge base document.

    Tracks the full lifecycle from upload to vector-indexed.
    Storage path points to the raw file in MinIO/S3.
    """

    __tablename__ = "documents"

    # ------------------------------------------------------------------ #
    # Core metadata                                                         #
    # ------------------------------------------------------------------ #
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Document display title",
    )

    filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Original filename as uploaded by user",
    )

    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="MIME type (e.g. application/pdf)",
    )

    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="File size in bytes",
    )

    # ------------------------------------------------------------------ #
    # Storage                                                               #
    # ------------------------------------------------------------------ #
    storage_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Object storage path: bucket/prefix/uuid.ext",
    )

    storage_bucket: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Object storage bucket name",
    )

    # ------------------------------------------------------------------ #
    # Processing state                                                      #
    # ------------------------------------------------------------------ #
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status_enum", create_type=True),
        nullable=False,
        default=DocumentStatus.PENDING,
        server_default=DocumentStatus.PENDING.value,
        index=True,
        comment="Current pipeline processing status",
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error details when status=failed",
    )

    # ------------------------------------------------------------------ #
    # Content                                                               #
    # ------------------------------------------------------------------ #
    page_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of pages / sections extracted",
    )

    chunk_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of chunks indexed into vector store",
    )

    language: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="ISO 639-1 language code detected from content",
    )

    # ------------------------------------------------------------------ #
    # Classification                                                        #
    # ------------------------------------------------------------------ #
    tags: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String(100)),
        nullable=True,
        default=list,
        comment="User-defined tags for filtering",
    )

    doc_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        server_default="{}",
        comment="Extracted document metadata (author, date, title from PDF, etc.)",
    )

    # ------------------------------------------------------------------ #
    # Timestamps                                                            #
    # ------------------------------------------------------------------ #
    indexed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When document finished vector indexing",
    )

    # ------------------------------------------------------------------ #
    # Uploader                                                              #
    # ------------------------------------------------------------------ #
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User who uploaded this document",
    )

    # ------------------------------------------------------------------ #
    # Soft delete                                                           #
    # ------------------------------------------------------------------ #
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Soft delete flag — excluded from all queries when True",
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="documents",
        lazy="noload",
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} title={self.title!r} status={self.status.value!r}>"
        )


class DocumentChunk(TenantModel):
    """
    Text chunk from a document with pgvector embedding.

    Chunks are the unit of retrieval. Each chunk maps back to a position
    in the source document for citation purposes.

    Vector dimension: 1536 (OpenAI text-embedding-ada-002 / text-embedding-3-small).
    """

    __tablename__ = "document_chunks"

    # ------------------------------------------------------------------ #
    # Parent document                                                       #
    # ------------------------------------------------------------------ #
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Source document",
    )

    # ------------------------------------------------------------------ #
    # Content                                                               #
    # ------------------------------------------------------------------ #
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Raw text of the chunk",
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 of content for deduplication",
    )

    # ------------------------------------------------------------------ #
    # Position                                                              #
    # ------------------------------------------------------------------ #
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Zero-based sequential chunk number within document",
    )

    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Source page number for citation",
    )

    start_char: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Character offset start in source text",
    )

    end_char: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Character offset end in source text",
    )

    # ------------------------------------------------------------------ #
    # Embedding                                                             #
    # ------------------------------------------------------------------ #
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536),
        nullable=True,
        comment="Dense vector embedding (OpenAI 1536-dim)",
    )

    embedding_model: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Model used to generate embedding (e.g. text-embedding-3-small)",
    )

    # ------------------------------------------------------------------ #
    # Extra metadata                                                        #
    # ------------------------------------------------------------------ #
    chunk_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        server_default="{}",
        comment="Chunk-level metadata (section heading, table, etc.)",
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"
        )
