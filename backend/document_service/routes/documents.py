"""
Document routes — full CRUD + upload/download/status/chunks.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import JSONResponse

from document_service.dependencies import ServiceDep
from document_service.exceptions import (
    DocumentNotFoundError,
    DocumentServiceError,
    FileTooLargeError,
    UnsupportedFileTypeError,
    VirusScanError,
)
from document_service.models.schemas import (
    DocumentChunkListResponse,
    DocumentCreate,
    DocumentListFilter,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentStatusResponse,
    DocumentUploadResponse,
    ErrorResponse,
    PresignedUrlResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


# ── Upload ────────────────────────────────────────────────────────────────────


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        413: {"model": ErrorResponse, "description": "File too large"},
        415: {"model": ErrorResponse, "description": "Unsupported file type"},
        422: {"model": ErrorResponse, "description": "Virus detected"},
        502: {"model": ErrorResponse, "description": "Storage or queue error"},
    },
    summary="Upload a document",
    description=(
        "Accept a file upload, perform virus scanning, store in S3/MinIO, "
        "persist metadata in Postgres, and enqueue for async processing."
    ),
)
async def upload_document(
    service: ServiceDep,
    file: UploadFile = File(..., description="Document file to upload"),
    title: str | None = Form(default=None, max_length=512),
    description: str | None = Form(default=None, max_length=4096),
    department: str | None = Form(default=None, max_length=128),
    tags: str | None = Form(
        default=None,
        description="Comma-separated tags, e.g. 'finance,q1,report'",
    ),
) -> DocumentUploadResponse:
    """Upload and enqueue a document for processing."""
    log = logger.bind(filename=file.filename, content_type=file.content_type)
    log.info("upload_request_received")

    content = await file.read()
    parsed_tags: list[str] = []
    if tags:
        parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

    metadata = DocumentCreate(
        title=title,
        description=description,
        department=department,
        tags=parsed_tags,
    )

    return await service.upload_document(
        filename=file.filename or "unnamed",
        content=content,
        metadata=metadata,
    )


# ── List ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Paginated document list with optional filters.",
)
async def list_documents(
    service: ServiceDep,
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    department: str | None = Query(default=None, max_length=128),
    tags: list[str] | None = Query(default=None),
    date_from: str | None = Query(default=None, description="ISO 8601 datetime"),
    date_to: str | None = Query(default=None, description="ISO 8601 datetime"),
    search: str | None = Query(default=None, max_length=256),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DocumentListResponse:
    """Return paginated document list."""
    from datetime import datetime

    filters = DocumentListFilter(
        status=status_filter,
        department=department,
        tags=tags,
        date_from=datetime.fromisoformat(date_from) if date_from else None,
        date_to=datetime.fromisoformat(date_to) if date_to else None,
        search=search,
        page=page,
        page_size=page_size,
    )
    return await service.list_documents(filters)


# ── Get single document ────────────────────────────────────────────────────────


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get document by ID",
)
async def get_document(
    document_id: uuid.UUID,
    service: ServiceDep,
) -> DocumentResponse:
    """Fetch full document metadata including processing status."""
    return await service.get_document(document_id)


# ── Status ─────────────────────────────────────────────────────────────────────


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get document processing status",
)
async def get_document_status(
    document_id: uuid.UUID,
    service: ServiceDep,
) -> DocumentStatusResponse:
    """Lightweight status check — poll this during async processing."""
    return await service.get_status(document_id)


# ── Download ───────────────────────────────────────────────────────────────────


@router.get(
    "/{document_id}/download",
    response_model=PresignedUrlResponse,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="Get presigned download URL",
)
async def get_download_url(
    document_id: uuid.UUID,
    service: ServiceDep,
) -> PresignedUrlResponse:
    """Return a time-limited presigned URL for direct storage download."""
    return await service.get_download_url(document_id)


# ── Chunks ─────────────────────────────────────────────────────────────────────


@router.get(
    "/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
    responses={404: {"model": ErrorResponse}},
    summary="List document chunks",
)
async def get_document_chunks(
    document_id: uuid.UUID,
    service: ServiceDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> DocumentChunkListResponse:
    """Return paginated text chunks extracted from the document."""
    return await service.get_chunks(document_id, page=page, page_size=page_size)


# ── Delete ─────────────────────────────────────────────────────────────────────


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
    summary="Delete document",
    description="Soft-deletes record, removes from storage, triggers vector removal.",
)
async def delete_document(
    document_id: uuid.UUID,
    service: ServiceDep,
) -> None:
    """Soft-delete document and queue vector removal."""
    await service.delete_document(document_id)
