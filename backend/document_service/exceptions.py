"""
Custom exceptions for the Document Service.

Hierarchy:
  DocumentServiceError (base)
  ├── DocumentNotFoundError        → 404
  ├── DocumentAlreadyExistsError   → 409
  ├── FileTooLargeError            → 413
  ├── UnsupportedFileTypeError     → 415
  ├── VirusScanError               → 422
  ├── StorageError                 → 502
  ├── ProcessingQueueError         → 502
  └── PermissionDeniedError        → 403
"""

from __future__ import annotations


class DocumentServiceError(Exception):
    """Base exception for Document Service."""

    status_code: int = 500
    error_code: str = "DOCUMENT_SERVICE_ERROR"

    def __init__(self, message: str, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class DocumentNotFoundError(DocumentServiceError):
    """Document with given ID does not exist or was soft-deleted."""

    status_code = 404
    error_code = "DOCUMENT_NOT_FOUND"

    def __init__(self, document_id: str) -> None:
        super().__init__(
            message=f"Document '{document_id}' not found",
            detail="Document may have been deleted or never existed",
        )
        self.document_id = document_id


class DocumentAlreadyExistsError(DocumentServiceError):
    """Document with identical content hash already exists."""

    status_code = 409
    error_code = "DOCUMENT_ALREADY_EXISTS"

    def __init__(self, content_hash: str) -> None:
        super().__init__(
            message="Document with identical content already exists",
            detail=f"Content hash: {content_hash}",
        )
        self.content_hash = content_hash


class FileTooLargeError(DocumentServiceError):
    """Uploaded file exceeds configured size limit."""

    status_code = 413
    error_code = "FILE_TOO_LARGE"

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        size_mb = size_bytes / (1024 * 1024)
        max_mb = max_bytes / (1024 * 1024)
        super().__init__(
            message=f"File size {size_mb:.1f} MB exceeds limit of {max_mb:.1f} MB",
            detail=f"Received {size_bytes} bytes, maximum allowed is {max_bytes} bytes",
        )
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class UnsupportedFileTypeError(DocumentServiceError):
    """MIME type not in allowed list."""

    status_code = 415
    error_code = "UNSUPPORTED_FILE_TYPE"

    def __init__(self, content_type: str, allowed_types: list[str]) -> None:
        super().__init__(
            message=f"File type '{content_type}' is not supported",
            detail=f"Allowed types: {', '.join(allowed_types)}",
        )
        self.content_type = content_type
        self.allowed_types = allowed_types


class VirusScanError(DocumentServiceError):
    """ClamAV detected malware in uploaded file."""

    status_code = 422
    error_code = "VIRUS_DETECTED"

    def __init__(self, virus_name: str) -> None:
        super().__init__(
            message="Malware detected in uploaded file",
            detail=f"Threat: {virus_name}",
        )
        self.virus_name = virus_name


class StorageError(DocumentServiceError):
    """Error communicating with S3/MinIO storage backend."""

    status_code = 502
    error_code = "STORAGE_ERROR"

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message=f"Storage error: {message}", detail=detail)


class ProcessingQueueError(DocumentServiceError):
    """Failed to publish message to RabbitMQ."""

    status_code = 502
    error_code = "QUEUE_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(
            message=f"Failed to queue document for processing: {message}",
            detail="RabbitMQ may be unavailable",
        )


class PermissionDeniedError(DocumentServiceError):
    """Caller lacks permissions for this operation."""

    status_code = 403
    error_code = "PERMISSION_DENIED"

    def __init__(self, resource: str, action: str) -> None:
        super().__init__(
            message=f"Permission denied: cannot {action} {resource}",
        )
