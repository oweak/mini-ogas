from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from ..domain.data_platform import DataPlatformError
from ..repositories.data_platform import data_platform_repository
from .config import settings


class RedisTelemetryProjection:
    """Disposable latest-value projection rebuilt only from durable telemetry facts."""

    def _client(self) -> Redis:
        if not settings.redis_enabled:
            raise DataPlatformError(
                503,
                "REDIS_PROJECTION_UNAVAILABLE",
                "Redis projection is disabled; PostgreSQL historian remains authoritative",
            )
        return Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_socket_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
        )

    def _root(self) -> str:
        return f"miniogas:{settings.tenant_id}:{settings.site_id}:telemetry"

    def rebuild(self, reason: str, actor: str) -> dict[str, Any]:
        source = data_platform_repository.projection_source()
        generation = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
        root = self._root()
        namespace = f"{root}:{generation}:latest"
        active_pointer = f"{root}:active-generation"
        lock_key = f"{root}:rebuild-lock"
        client = self._client()
        lock_value = uuid4().hex
        created_keys: list[str] = []
        try:
            client.ping()
            if not client.set(lock_key, lock_value, nx=True, ex=60):
                raise DataPlatformError(
                    409,
                    "REDIS_PROJECTION_REBUILD_IN_PROGRESS",
                    "another projection rebuild currently owns the Redis lock",
                )
            pipeline = client.pipeline(transaction=False)
            for row in source["rows"]:
                key = f"{namespace}:{row['source_id']}:{row['signal_code']}"
                created_keys.append(key)
                payload = {
                    key_name: row.get(key_name)
                    for key_name in (
                        "id",
                        "sample_id",
                        "source",
                        "source_id",
                        "equipment_code",
                        "signal_code",
                        "numeric_value",
                        "text_value",
                        "unit",
                        "quality_code",
                        "quality_reason",
                        "source_timestamp",
                        "central_ingested_at",
                    )
                }
                pipeline.set(
                    key,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
                )
            pipeline.execute()
            if created_keys:
                present = sum(value is not None for value in client.mget(created_keys))
            else:
                present = 0
            if present != len(created_keys):
                raise DataPlatformError(
                    503,
                    "REDIS_PROJECTION_VERIFICATION_FAILED",
                    "Redis did not retain every projected latest-value key",
                    expected=len(created_keys),
                    observed=present,
                )
            client.set(active_pointer, generation)
            checkpoint = data_platform_repository.record_projection_checkpoint(
                generation,
                source["measurement_count"],
                len(created_keys),
                source["maximum_id"],
                "active",
                reason,
                actor,
            )
            return {
                "status": "active",
                "provider": "redis",
                "authority": "postgresql-historian",
                "generation": generation,
                "measurement_count": source["measurement_count"],
                "projected_key_count": len(created_keys),
                "max_measurement_id": source["maximum_id"],
                "checkpoint": checkpoint,
            }
        except DataPlatformError:
            if created_keys:
                client.delete(*created_keys)
            raise
        except RedisError as exc:
            if created_keys:
                try:
                    client.delete(*created_keys)
                except RedisError:
                    pass
            raise DataPlatformError(
                503,
                "REDIS_PROJECTION_UNAVAILABLE",
                "Redis projection could not be reached or verified",
                error_type=type(exc).__name__,
            ) from exc
        finally:
            try:
                if client.get(lock_key) == lock_value:
                    client.delete(lock_key)
            except RedisError:
                pass

    def status(self) -> dict[str, Any]:
        client = self._client()
        try:
            client.ping()
            generation = client.get(f"{self._root()}:active-generation")
        except RedisError as exc:
            raise DataPlatformError(
                503,
                "REDIS_PROJECTION_UNAVAILABLE",
                "Redis projection could not be reached",
                error_type=type(exc).__name__,
            ) from exc
        return {
            "provider": "redis",
            "available": True,
            "active_generation": generation,
            "authority": "postgresql-historian",
        }


redis_telemetry_projection = RedisTelemetryProjection()
