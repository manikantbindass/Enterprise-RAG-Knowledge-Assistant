"""
Storage abstraction layer — MinIO and S3 backends.

Provides a unified async interface regardless of backend:
- upload_file()       — stream file to object storage
- download_file()     — stream file from object storage
- get_presigned_url() — generate time-limited download URL
- delete_file()       — remove object
- file_exists()       — head-check without downloading

MinioStorage  — uses minio-py async client (miniopy-async)
S3Storage     — uses aioboto3 for AWS S3

Both implement BaseStorage. Services depend on BaseStorage only.

Configuration determines which backend is instantiated (see config.py).
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import AsyncGenerator, BinaryIO

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class BaseStorage(ABC):
    """
    Unified interface for object storage operations.

    All methods are async. Implementations must not block the event loop.
    """

    @abstractmethod
    async def upload_file(
        self,
        bucket: str,
        object_path: str,
        data: BinaryIO | bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """
        Upload a file to object storage.

        Args:
            bucket: Bucket/container name.
            object_path: Full object path within bucket (e.g. "org-id/docs/uuid.pdf").
            data: File-like object or raw bytes.
            content_type: MIME type.
            metadata: Optional key-value metadata to attach to the object.

        Returns:
            Object path (same as input — for chaining).
        """

    @abstractmethod
    async def download_file(
        self,
        bucket: str,
        object_path: str,
    ) -> bytes:
        """
        Download a file from object storage.

        Args:
            bucket: Bucket name.
            object_path: Object path within bucket.

        Returns:
            File content as bytes.

        Raises:
            StorageError: Object not found or read failure.
        """

    @abstractmethod
    async def get_presigned_url(
        self,
        bucket: str,
        object_path: str,
        *,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """
        Generate a pre-signed URL for temporary direct access.

        Args:
            bucket: Bucket name.
            object_path: Object path.
            expires_in_seconds: URL validity window.
            method: HTTP method ('GET' for download, 'PUT' for upload).

        Returns:
            Pre-signed URL string.
        """

    @abstractmethod
    async def delete_file(self, bucket: str, object_path: str) -> None:
        """
        Delete an object from storage.

        Args:
            bucket: Bucket name.
            object_path: Object path.

        Raises:
            StorageError: Deletion failure.
        """

    @abstractmethod
    async def file_exists(self, bucket: str, object_path: str) -> bool:
        """
        Check if an object exists without downloading it.

        Args:
            bucket: Bucket name.
            object_path: Object path.

        Returns:
            True if object exists.
        """

    @abstractmethod
    async def ensure_bucket_exists(self, bucket: str) -> None:
        """
        Create bucket if it does not exist.

        Args:
            bucket: Bucket name.
        """


# ---------------------------------------------------------------------------
# MinIO implementation (miniopy-async)
# ---------------------------------------------------------------------------


class MinioStorage(BaseStorage):
    """
    Async MinIO object storage implementation.

    Uses miniopy-async — the async fork of the official minio-py client.
    Install: pip install miniopy-async

    MinIO is S3-compatible so this also works with on-prem S3-like stores.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        *,
        secure: bool = False,
        region: str = "us-east-1",
    ) -> None:
        try:
            from miniopy_async import Minio  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "miniopy-async is required for MinioStorage. "
                "Install: pip install miniopy-async"
            ) from exc

        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region,
        )
        self._region = region
        logger.info("minio_storage_initialized", endpoint=endpoint, secure=secure)

    async def upload_file(
        self,
        bucket: str,
        object_path: str,
        data: BinaryIO | bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        from shared.exceptions import StorageError

        try:
            if isinstance(data, bytes):
                stream = io.BytesIO(data)
                length = len(data)
            else:
                # Seek to end to determine length, then reset
                data.seek(0, 2)
                length = data.tell()
                data.seek(0)
                stream = data

            await self._client.put_object(
                bucket_name=bucket,
                object_name=object_path,
                data=stream,
                length=length,
                content_type=content_type,
                metadata=metadata or {},
            )

            logger.info(
                "file_uploaded",
                backend="minio",
                bucket=bucket,
                path=object_path,
                size_bytes=length,
            )
            return object_path

        except Exception as exc:
            logger.error(
                "file_upload_failed",
                backend="minio",
                bucket=bucket,
                path=object_path,
                error=str(exc),
            )
            raise StorageError(
                f"Upload failed: {exc}",
                operation="upload",
                path=f"{bucket}/{object_path}",
            ) from exc

    async def download_file(self, bucket: str, object_path: str) -> bytes:
        from shared.exceptions import StorageError

        try:
            response = await self._client.get_object(bucket, object_path)
            data = await response.read()
            logger.debug(
                "file_downloaded",
                backend="minio",
                bucket=bucket,
                path=object_path,
                size_bytes=len(data),
            )
            return data
        except Exception as exc:
            logger.error(
                "file_download_failed",
                backend="minio",
                bucket=bucket,
                path=object_path,
                error=str(exc),
            )
            raise StorageError(
                f"Download failed: {exc}",
                operation="download",
                path=f"{bucket}/{object_path}",
            ) from exc

    async def get_presigned_url(
        self,
        bucket: str,
        object_path: str,
        *,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        from shared.exceptions import StorageError

        try:
            url = await self._client.presigned_get_object(
                bucket,
                object_path,
                expires=timedelta(seconds=expires_in_seconds),
            )
            return url
        except Exception as exc:
            raise StorageError(
                f"Presigned URL generation failed: {exc}",
                operation="presign",
                path=f"{bucket}/{object_path}",
            ) from exc

    async def delete_file(self, bucket: str, object_path: str) -> None:
        from shared.exceptions import StorageError

        try:
            await self._client.remove_object(bucket, object_path)
            logger.info(
                "file_deleted", backend="minio", bucket=bucket, path=object_path
            )
        except Exception as exc:
            raise StorageError(
                f"Delete failed: {exc}",
                operation="delete",
                path=f"{bucket}/{object_path}",
            ) from exc

    async def file_exists(self, bucket: str, object_path: str) -> bool:
        try:
            stat = await self._client.stat_object(bucket, object_path)
            return stat is not None
        except Exception:
            return False

    async def ensure_bucket_exists(self, bucket: str) -> None:
        try:
            exists = await self._client.bucket_exists(bucket)
            if not exists:
                await self._client.make_bucket(bucket, location=self._region)
                logger.info("bucket_created", backend="minio", bucket=bucket)
        except Exception as exc:
            logger.error("bucket_ensure_failed", bucket=bucket, error=str(exc))
            raise


# ---------------------------------------------------------------------------
# AWS S3 implementation (aioboto3)
# ---------------------------------------------------------------------------


class S3Storage(BaseStorage):
    """
    Async AWS S3 object storage implementation using aioboto3.

    aioboto3 wraps botocore with asyncio support.
    Install: pip install aioboto3

    Also works with S3-compatible services (Wasabi, Backblaze B2, etc.)
    by setting endpoint_url.
    """

    def __init__(
        self,
        *,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
    ) -> None:
        try:
            import aioboto3  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "aioboto3 is required for S3Storage. Install: pip install aioboto3"
            ) from exc

        self._session = aioboto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )
        self._region = region_name
        self._endpoint_url = endpoint_url
        logger.info(
            "s3_storage_initialized",
            region=region_name,
            endpoint=endpoint_url or "aws",
        )

    def _s3_client(self):
        """Context manager that yields an aioboto3 S3 client."""
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
        )

    async def upload_file(
        self,
        bucket: str,
        object_path: str,
        data: BinaryIO | bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        from shared.exceptions import StorageError

        try:
            if isinstance(data, bytes):
                body: BinaryIO | bytes = io.BytesIO(data)
            else:
                body = data

            extra_args: dict = {"ContentType": content_type}
            if metadata:
                extra_args["Metadata"] = metadata

            async with self._s3_client() as s3:
                await s3.upload_fileobj(body, bucket, object_path, ExtraArgs=extra_args)

            logger.info(
                "file_uploaded", backend="s3", bucket=bucket, path=object_path
            )
            return object_path

        except Exception as exc:
            raise StorageError(
                f"S3 upload failed: {exc}",
                operation="upload",
                path=f"s3://{bucket}/{object_path}",
            ) from exc

    async def download_file(self, bucket: str, object_path: str) -> bytes:
        from shared.exceptions import StorageError

        try:
            buf = io.BytesIO()
            async with self._s3_client() as s3:
                await s3.download_fileobj(bucket, object_path, buf)
            return buf.getvalue()
        except Exception as exc:
            raise StorageError(
                f"S3 download failed: {exc}",
                operation="download",
                path=f"s3://{bucket}/{object_path}",
            ) from exc

    async def get_presigned_url(
        self,
        bucket: str,
        object_path: str,
        *,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        from shared.exceptions import StorageError

        client_method = "get_object" if method.upper() == "GET" else "put_object"

        try:
            async with self._s3_client() as s3:
                url = await s3.generate_presigned_url(
                    ClientMethod=client_method,
                    Params={"Bucket": bucket, "Key": object_path},
                    ExpiresIn=expires_in_seconds,
                )
            return url
        except Exception as exc:
            raise StorageError(
                f"S3 presign failed: {exc}",
                operation="presign",
                path=f"s3://{bucket}/{object_path}",
            ) from exc

    async def delete_file(self, bucket: str, object_path: str) -> None:
        from shared.exceptions import StorageError

        try:
            async with self._s3_client() as s3:
                await s3.delete_object(Bucket=bucket, Key=object_path)
            logger.info("file_deleted", backend="s3", bucket=bucket, path=object_path)
        except Exception as exc:
            raise StorageError(
                f"S3 delete failed: {exc}",
                operation="delete",
                path=f"s3://{bucket}/{object_path}",
            ) from exc

    async def file_exists(self, bucket: str, object_path: str) -> bool:
        try:
            async with self._s3_client() as s3:
                await s3.head_object(Bucket=bucket, Key=object_path)
            return True
        except Exception:
            return False

    async def ensure_bucket_exists(self, bucket: str) -> None:
        try:
            async with self._s3_client() as s3:
                try:
                    await s3.head_bucket(Bucket=bucket)
                except Exception:
                    create_kwargs: dict = {"Bucket": bucket}
                    if self._region != "us-east-1":
                        create_kwargs["CreateBucketConfiguration"] = {
                            "LocationConstraint": self._region
                        }
                    await s3.create_bucket(**create_kwargs)
                    logger.info("bucket_created", backend="s3", bucket=bucket)
        except Exception as exc:
            logger.error("bucket_ensure_failed", bucket=bucket, error=str(exc))
            raise


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_storage(
    backend: str,
    *,
    minio_endpoint: str = "localhost:9000",
    minio_access_key: str = "minioadmin",
    minio_secret_key: str = "minioadmin",
    minio_secure: bool = False,
    aws_access_key_id: str = "",
    aws_secret_access_key: str = "",
    aws_region: str = "us-east-1",
    s3_endpoint_url: str | None = None,
) -> BaseStorage:
    """
    Factory function — create the right storage backend from config.

    Args:
        backend: "minio" or "s3".
        ... remaining args match config fields.

    Returns:
        Configured BaseStorage implementation.

    Usage:
        storage = create_storage(backend=settings.STORAGE_BACKEND, ...)
    """
    if backend == "minio":
        return MinioStorage(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure,
        )
    elif backend == "s3":
        return S3Storage(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region,
            endpoint_url=s3_endpoint_url,
        )
    else:
        raise ValueError(f"Unknown storage backend: {backend!r}. Use 'minio' or 's3'.")
