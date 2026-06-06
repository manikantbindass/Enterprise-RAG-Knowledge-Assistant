"""
Custom exceptions for the Vector Service.
"""

from __future__ import annotations


class VectorServiceError(Exception):
    """Base exception for all vector service errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ChunkNotFoundError(VectorServiceError):
    def __init__(self, chunk_id: str) -> None:
        super().__init__(f"Chunk {chunk_id!r} not found", status_code=404)


class EmbeddingMissingError(VectorServiceError):
    def __init__(self, chunk_id: str) -> None:
        super().__init__(f"Chunk {chunk_id!r} has no embedding vector", status_code=422)


class SearchBackendError(VectorServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"Search backend error: {detail}", status_code=503)


class InvalidFilterError(VectorServiceError):
    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"Invalid filter on {field!r}: {reason}", status_code=400)
