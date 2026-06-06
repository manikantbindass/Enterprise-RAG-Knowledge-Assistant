"""
Document management routes — proxied to document-service.

POST   /api/v1/documents/upload                   multipart file upload
GET    /api/v1/documents                           paginated list, filterable
GET    /api/v1/documents/{doc_id}                  get single document
DELETE /api/v1/documents/{doc_id}                  delete document
GET    /api/v1/documents/{doc_id}/chunks           list vector chunks
GET    /api/v1/documents/{doc_id}/status           processing status
"""

from __future__ import annotations

import io
from typing import Any, Literal

import structlog
from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dependencies import (
    ActiveUserDep,
    AdminOrManagerDep,
    DocumentProxyDep,
    RequestIdDep,
)
from exceptions import NotFoundException, PayloadTooLargeException

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

# 100 MB max file size
_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/json",
    "text/html",
}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    """Document metadata returned to clients."""

    doc_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    department: str | None
    tags: list[str]
    uploaded_by: str
    org_id: str | None
    chunk_count: int | None
    created_at: str
    updated_at: str
    metadata: dict[str, Any] | None


class PaginatedDocumentsResponse(BaseModel):
    """Paginated document list."""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    pages: int


class UploadResponse(BaseModel):
    """Response immediately after upload (before processing completes)."""

    doc_id: str
    filename: str
    size_bytes: int
    status: Literal["pending", "processing", "ready", "failed"]
    message: str


class DocumentChunk(BaseModel):
    """A single vector chunk of a document."""

    chunk_id: str
    doc_id: str
    chunk_index: int
    content: str
    token_count: int
    embedding_model: str | None
    metadata: dict[str, Any] | None


class ChunksResponse(BaseModel):
    """List of document chunks."""

    doc_id: str
    chunks: list[DocumentChunk]
    total: int


class ProcessingStatusResponse(BaseModel):
    """Document processing pipeline status."""

    doc_id: str
    status: Literal["pending", "processing", "ready", "failed"]
    progress_percent: float | None
    current_stage: str | None
    error_message: str | None
    started_at: str | None
    completed_at: str | None


class DeleteResponse(BaseModel):
    """Deletion acknowledgement."""

    message: str
    doc_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document for ingestion",
)
async def upload_document(
    proxy: DocumentProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
    file: UploadFile = File(..., description="Document file to ingest"),
    department: str | None = Query(None, max_length=100),
    tags: str | None = Query(
        None,
        description="Comma-separated tags, e.g. 'hr,policy,2024'",
    ),
) -> UploadResponse:
    """
    Upload a document file for asynchronous ingestion and vectorization.

    Accepted formats: PDF, DOCX, TXT, MD, CSV, XLSX, JSON, HTML.
    Max size: 100 MB.

    The document enters a processing pipeline:
    1. Text extraction
    2. Chunking
    3. Embedding generation
    4. Vector store indexing

    Poll GET /documents/{doc_id}/status for progress.
    """
    log = logger.bind(
        request_id=request_id,
        user_id=current_user.user_id,
        filename=file.filename,
        content_type=file.content_type,
    )

    # Validate content type
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        from exceptions import BadRequestException
        raise BadRequestException(
            f"Unsupported file type: {file.content_type}. "
            f"Allowed: {', '.join(sorted(_ALLOWED_CONTENT_TYPES))}"
        )

    # Read and size-check
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
        raise PayloadTooLargeException(
            f"File exceeds maximum allowed size of {_MAX_FILE_SIZE_BYTES // (1024*1024)} MB"
        )

    log.info("document_upload_start", size_bytes=len(file_bytes))

    # Build multipart form for upstream
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    form_data: dict[str, Any] = {
        "uploaded_by": current_user.user_id,
        "org_id": current_user.org_id or "",
    }
    if department:
        form_data["department"] = department
    if tag_list:
        form_data["tags"] = ",".join(tag_list)

    files = {
        "file": (file.filename, io.BytesIO(file_bytes), file.content_type),
    }

    response = await proxy.request(
        "POST",
        "/documents/upload",
        authorization=f"Bearer {current_user.token}",
        files=files,
        data=form_data,
        request_id=request_id,
    )

    proxy.raise_for_upstream(response)
    data = response.json()
    log.info("document_upload_accepted", doc_id=data.get("doc_id"))
    return UploadResponse(**data)


@router.get(
    "",
    response_model=PaginatedDocumentsResponse,
    summary="List documents with filtering and pagination",
)
async def list_documents(
    proxy: DocumentProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    department: str | None = Query(None, max_length=100),
    tags: str | None = Query(None, description="Comma-separated tag filter"),
    status_filter: str | None = Query(
        None,
        alias="status",
        pattern="^(pending|processing|ready|failed)$",
    ),
    search: str | None = Query(None, description="Full-text search on filename"),
    org_id: str | None = Query(None, description="Filter by organisation (admin only)"),
) -> PaginatedDocumentsResponse:
    """
    List documents accessible to the current user.

    Non-admin users only see documents in their own organization.
    """
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if department:
        params["department"] = department
    if tags:
        params["tags"] = tags
    if status_filter:
        params["status"] = status_filter
    if search:
        params["search"] = search

    # Scope to org for non-admins
    if current_user.role != "admin":
        params["org_id"] = current_user.org_id
    elif org_id:
        params["org_id"] = org_id

    response = await proxy.request(
        "GET",
        "/documents",
        authorization=f"Bearer {current_user.token}",
        params=params,
        request_id=request_id,
    )
    proxy.raise_for_upstream(response)
    return PaginatedDocumentsResponse(**response.json())


@router.get(
    "/{doc_id}",
    response_model=DocumentResponse,
    summary="Get document metadata by ID",
)
async def get_document(
    doc_id: str,
    proxy: DocumentProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> DocumentResponse:
    """Retrieve full metadata for a document."""
    response = await proxy.request(
        "GET",
        f"/documents/{doc_id}",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Document '{doc_id}' not found")
    if response.status_code == 403:
        from exceptions import ForbiddenException
        raise ForbiddenException("Access to this document is not permitted")

    proxy.raise_for_upstream(response)
    return DocumentResponse(**response.json())


@router.delete(
    "/{doc_id}",
    response_model=DeleteResponse,
    summary="Delete a document",
)
async def delete_document(
    doc_id: str,
    proxy: DocumentProxyDep,
    request_id: RequestIdDep,
    current_user: AdminOrManagerDep,
) -> DeleteResponse:
    """
    Delete a document and its vector chunks.

    Requires admin or manager role.
    """
    log = logger.bind(
        request_id=request_id,
        user_id=current_user.user_id,
        doc_id=doc_id,
    )
    log.info("delete_document")

    response = await proxy.request(
        "DELETE",
        f"/documents/{doc_id}",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Document '{doc_id}' not found")

    proxy.raise_for_upstream(response)
    log.info("delete_document_success")
    return DeleteResponse(message="Document deleted successfully", doc_id=doc_id)


@router.get(
    "/{doc_id}/chunks",
    response_model=ChunksResponse,
    summary="List vector chunks for a document",
)
async def get_document_chunks(
    doc_id: str,
    proxy: DocumentProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ChunksResponse:
    """Return the text chunks and metadata generated from a document."""
    response = await proxy.request(
        "GET",
        f"/documents/{doc_id}/chunks",
        authorization=f"Bearer {current_user.token}",
        params={"limit": limit, "offset": offset},
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Document '{doc_id}' not found")

    proxy.raise_for_upstream(response)
    return ChunksResponse(**response.json())


@router.get(
    "/{doc_id}/status",
    response_model=ProcessingStatusResponse,
    summary="Get document processing pipeline status",
)
async def get_document_status(
    doc_id: str,
    proxy: DocumentProxyDep,
    request_id: RequestIdDep,
    current_user: ActiveUserDep,
) -> ProcessingStatusResponse:
    """
    Poll the processing status of a document.

    Use this after upload to track progress through the ingestion pipeline.
    """
    response = await proxy.request(
        "GET",
        f"/documents/{doc_id}/status",
        authorization=f"Bearer {current_user.token}",
        request_id=request_id,
    )

    if response.status_code == 404:
        raise NotFoundException(f"Document '{doc_id}' not found")

    proxy.raise_for_upstream(response)
    return ProcessingStatusResponse(**response.json())
