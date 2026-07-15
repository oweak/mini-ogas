from __future__ import annotations

import hashlib
import re
from io import BytesIO
from typing import Any

from ..domain.data_platform import DataPlatformError
from ..repositories.data_platform import data_platform_repository
from .config import settings

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DocumentObjectStorage:
    """Checksum-gated MinIO storage for controlled-document payloads."""

    def _client(self) -> Any:
        if not settings.object_storage_enabled:
            raise DataPlatformError(
                503,
                "OBJECT_STORAGE_UNAVAILABLE",
                "object storage is disabled; no document object was accepted",
            )
        if not settings.object_storage_access_key or not settings.object_storage_secret_key:
            raise DataPlatformError(
                503,
                "OBJECT_STORAGE_UNAVAILABLE",
                "object storage credentials are not configured",
            )
        try:
            from minio import Minio
        except (ImportError, ModuleNotFoundError) as exc:
            raise DataPlatformError(
                503,
                "OBJECT_STORAGE_DEPENDENCY_UNAVAILABLE",
                "MinIO client dependencies could not be loaded",
                error_type=type(exc).__name__,
            ) from exc
        return Minio(
            settings.object_storage_endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            secure=settings.object_storage_secure,
        )

    def store(
        self,
        *,
        original_name: str,
        content: bytes,
        content_type: str,
        expected_sha256: str,
        actor: str,
    ) -> dict[str, Any]:
        observed_sha256 = hashlib.sha256(content).hexdigest()
        if not SHA256_PATTERN.fullmatch(expected_sha256) or expected_sha256 != observed_sha256:
            raise DataPlatformError(
                409,
                "OBJECT_CHECKSUM_MISMATCH",
                "request checksum does not match the supplied object bytes",
                expected_sha256=expected_sha256,
                observed_sha256=observed_sha256,
            )
        if len(content) > settings.object_storage_max_bytes:
            raise DataPlatformError(
                413,
                "OBJECT_TOO_LARGE",
                "document object exceeds the configured maximum byte length",
                maximum_bytes=settings.object_storage_max_bytes,
                observed_bytes=len(content),
            )
        client = self._client()
        from minio.error import S3Error

        bucket = settings.object_storage_bucket
        object_key = (
            f"{settings.tenant_id}/{settings.site_id}/sha256/"
            f"{observed_sha256[:2]}/{observed_sha256}"
        )
        manifest = data_platform_repository.create_object_manifest(
            object_key=object_key,
            content_sha256=observed_sha256,
            byte_length=len(content),
            content_type=content_type or "application/octet-stream",
            original_name=original_name,
            actor=actor,
        )
        if manifest["status"] == "available":
            return manifest
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            result = client.put_object(
                bucket,
                object_key,
                BytesIO(content),
                length=len(content),
                content_type=content_type or "application/octet-stream",
                metadata={"x-amz-meta-sha256": observed_sha256},
            )
            response = client.get_object(bucket, object_key)
            try:
                stored = response.read()
            finally:
                response.close()
                response.release_conn()
        except (S3Error, OSError) as exc:
            raise DataPlatformError(
                503,
                "OBJECT_STORAGE_UNAVAILABLE",
                "MinIO upload or read-back verification failed",
                error_type=type(exc).__name__,
            ) from exc
        stored_sha256 = hashlib.sha256(stored).hexdigest()
        status = "available" if stored_sha256 == observed_sha256 else "quarantined"
        completed = data_platform_repository.complete_object_manifest(
            int(manifest["id"]),
            status=status,
            expected_sha256=observed_sha256,
            observed_sha256=stored_sha256,
            byte_length=len(stored),
            etag=str(result.etag or ""),
            storage_version=str(result.version_id or ""),
            actor=actor,
        )
        if status != "available":
            raise DataPlatformError(
                409,
                "OBJECT_READBACK_CHECKSUM_MISMATCH",
                "stored object failed read-back checksum verification and was quarantined",
                object_id=manifest["id"],
            )
        return completed

    def retrieve(self, *, object_id: int, actor: str) -> tuple[bytes, dict[str, Any]]:
        manifest = data_platform_repository.require_available_object(object_id)
        expected_length = int(manifest["byte_length"])
        expected_sha256 = str(manifest["content_sha256"])
        if expected_length > settings.object_storage_max_bytes:
            raise DataPlatformError(
                409,
                "OBJECT_MANIFEST_LIMIT_VIOLATION",
                "object manifest exceeds the configured retrieval limit",
                object_id=object_id,
                maximum_bytes=settings.object_storage_max_bytes,
                manifest_bytes=expected_length,
            )
        client = self._client()
        from minio.error import S3Error

        try:
            response = client.get_object(str(manifest["bucket"]), str(manifest["object_key"]))
            try:
                stored = response.read(expected_length + 1)
            finally:
                response.close()
                response.release_conn()
        except (KeyError, OSError, S3Error) as exc:
            raise DataPlatformError(
                503,
                "OBJECT_STORAGE_UNAVAILABLE",
                "MinIO retrieval failed before integrity verification completed",
                object_id=object_id,
                error_type=type(exc).__name__,
            ) from exc

        observed_sha256 = hashlib.sha256(stored).hexdigest()
        verified = len(stored) == expected_length and observed_sha256 == expected_sha256
        completed = data_platform_repository.complete_object_manifest(
            object_id,
            status="available" if verified else "quarantined",
            expected_sha256=expected_sha256,
            observed_sha256=observed_sha256,
            byte_length=len(stored),
            etag=str(manifest.get("etag") or ""),
            storage_version=str(manifest.get("storage_version") or ""),
            actor=actor,
        )
        if not verified:
            raise DataPlatformError(
                409,
                "OBJECT_READBACK_CHECKSUM_MISMATCH",
                "retrieved object failed checksum or length verification and was quarantined",
                object_id=object_id,
                expected_sha256=expected_sha256,
                observed_sha256=observed_sha256,
                expected_bytes=expected_length,
                observed_bytes=len(stored),
            )
        return stored, completed


document_object_storage = DocumentObjectStorage()
