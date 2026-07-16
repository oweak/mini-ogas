from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import nats
from nats.errors import TimeoutError as NATSTimeoutError
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DiscardPolicy,
    RetentionPolicy,
    StorageType,
    StreamConfig,
)
from nats.js.errors import NotFoundError
from pydantic import ValidationError

from ..persistence_repository import CentralFactRepository
from .config import settings
from .event_publisher import EventPublisher, PublishResult
from .nats_contracts import (
    TransportEnvelope,
    build_audit_envelope,
    build_command_envelope,
    build_event_envelope,
    build_heartbeat_envelope,
    envelope_bytes,
    subject_for_envelope,
)

logger = logging.getLogger("mini_ogas.central_api.nats")

Connector = Callable[..., Awaitable[Any]]


class NATSPublisher(EventPublisher):
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        url: str | None = None,
        token: str | None = None,
        stream: str | None = None,
        connector: Connector | None = None,
    ) -> None:
        self.enabled = settings.nats_enabled if enabled is None else enabled
        self.url = url or settings.nats_url
        self.token = settings.nats_auth_token if token is None else token
        self.stream = stream or settings.nats_stream
        self._connector = connector or nats.connect
        self._connection: Any | None = None
        self._jetstream: Any | None = None
        self._status = "disabled" if not self.enabled else "not_started"
        self._last_error_category = ""
        self._last_error_type = ""
        self._published_count = 0
        self._failed_count = 0
        self._last_publish_at = ""

    @property
    def connected(self) -> bool:
        return bool(
            self._connection is not None
            and getattr(self._connection, "is_connected", False)
            and not getattr(self._connection, "is_closed", False)
        )

    @property
    def jetstream(self) -> Any | None:
        return self._jetstream

    async def start(self) -> bool:
        if not self.enabled:
            self._status = "disabled"
            return True
        if self.connected and self._jetstream is not None:
            self._status = "live"
            return True
        self._status = "connecting"
        options: dict[str, Any] = {
            "servers": [self.url],
            "name": "mini-ogas-central-shadow-publisher",
            "connect_timeout": settings.nats_connect_timeout_seconds,
            "allow_reconnect": True,
            # Initial startup must fail fast so Central can become available in
            # degraded mode. NATSShadowRuntime owns the unbounded retry loop.
            "max_reconnect_attempts": 1,
            "reconnect_time_wait": settings.nats_retry_seconds,
            "disconnected_cb": self._on_disconnected,
            "reconnected_cb": self._on_reconnected,
            "closed_cb": self._on_closed,
            "error_cb": self._on_error,
        }
        if self.token:
            options["token"] = self.token
        try:
            self._connection = await self._connector(**options)
            self._jetstream = self._connection.jetstream()
            await self._ensure_stream()
        except Exception as exc:
            self._record_failure("connection", exc)
            await self._close_failed_connection()
            return False
        self._status = "live"
        self._last_error_category = ""
        self._last_error_type = ""
        return True

    async def _ensure_stream(self) -> None:
        assert self._jetstream is not None
        try:
            info = await self._jetstream.stream_info(self.stream)
            configured_subjects = set(getattr(getattr(info, "config", None), "subjects", []) or [])
            required_subjects = set(self._stream_subjects())
            if configured_subjects and not required_subjects.issubset(configured_subjects):
                raise RuntimeError("existing NATS stream does not cover required subjects")
            return
        except NotFoundError:
            pass
        config = StreamConfig(
            name=self.stream,
            description="Mini-OGAS v3.0.1 schema-valid shadow transport",
            subjects=self._stream_subjects(),
            retention=RetentionPolicy.LIMITS,
            storage=StorageType.FILE,
            discard=DiscardPolicy.OLD,
            max_age=7 * 24 * 60 * 60,
            max_bytes=settings.nats_stream_max_bytes,
            max_msg_size=256 * 1024,
            duplicate_window=2 * 60,
            num_replicas=1,
        )
        await self._jetstream.add_stream(config=config)

    @staticmethod
    def _stream_subjects() -> list[str]:
        return ["ogas.events.>", "ogas.heartbeats.*", "ogas.commands.*", "ogas.audit.*"]

    async def _publish(self, envelope: TransportEnvelope) -> PublishResult:
        subject = subject_for_envelope(envelope)
        if not self.enabled:
            return PublishResult(status="disabled", message_id=envelope.message_id, subject=subject)
        if not self.connected or self._jetstream is None:
            self._failed_count += 1
            self._status = "degraded"
            if not self._last_error_category:
                self._last_error_category = "connection"
            return PublishResult(
                status="degraded",
                message_id=envelope.message_id,
                subject=subject,
                error_category=self._last_error_category,
            )
        try:
            await self._jetstream.publish(
                subject,
                envelope_bytes(envelope),
                timeout=settings.nats_publish_timeout_seconds,
                stream=self.stream,
                headers={"Nats-Msg-Id": envelope.message_id, "OGAS-Schema-Version": "3.0"},
            )
        except Exception as exc:
            self._record_failure("publish", exc)
            return PublishResult(
                status="degraded",
                message_id=envelope.message_id,
                subject=subject,
                error_category="publish",
            )
        self._published_count += 1
        self._last_publish_at = datetime.now(UTC).isoformat()
        self._status = "live"
        return PublishResult(status="published", message_id=envelope.message_id, subject=subject)

    async def publish_heartbeat(self, heartbeat: dict[str, object]) -> PublishResult:
        if not self.enabled:
            return PublishResult(status="disabled")
        try:
            envelope = build_heartbeat_envelope(heartbeat)
        except (TypeError, ValueError, ValidationError) as exc:
            self._record_failure("validation", exc)
            return PublishResult(status="rejected", error_category="validation")
        return await self._publish(envelope)

    async def publish_envelope(self, envelope: TransportEnvelope) -> PublishResult:
        return await self._publish(envelope)

    async def publish_event(self, event: Any) -> PublishResult:
        if not self.enabled:
            return PublishResult(status="disabled")
        try:
            envelope = build_event_envelope(event)
        except (TypeError, ValueError, ValidationError) as exc:
            self._record_failure("validation", exc)
            return PublishResult(status="rejected", error_category="validation")
        return await self._publish(envelope)

    async def publish_command(self, command: Any) -> PublishResult:
        if not self.enabled:
            return PublishResult(status="disabled")
        try:
            envelope = build_command_envelope(command)
        except (TypeError, ValueError, ValidationError) as exc:
            self._record_failure("validation", exc)
            return PublishResult(status="rejected", error_category="validation")
        return await self._publish(envelope)

    async def publish_audit(self, audit: Any, *, run_id: str = "") -> PublishResult:
        if not self.enabled:
            return PublishResult(status="disabled")
        try:
            envelope = build_audit_envelope(audit, run_id=run_id)
        except (TypeError, ValueError, ValidationError) as exc:
            self._record_failure("validation", exc)
            return PublishResult(status="rejected", error_category="validation")
        return await self._publish(envelope)

    async def stop(self) -> None:
        connection = self._connection
        self._connection = None
        self._jetstream = None
        if connection is not None and not getattr(connection, "is_closed", False):
            try:
                await asyncio.wait_for(connection.drain(), timeout=3)
            except Exception:
                logger.warning("NATS drain failed during shutdown", exc_info=True)
                try:
                    await connection.close()
                except Exception:
                    pass
        self._status = "stopped" if self.enabled else "disabled"

    def health(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "status": self._status,
            "url": self.url,
            "stream": self.stream,
            "connected": self.connected,
            "published_count": self._published_count,
            "failed_count": self._failed_count,
            "last_publish_at": self._last_publish_at,
            "last_error_category": self._last_error_category,
            "last_error_type": self._last_error_type,
        }

    def _record_failure(self, category: str, exc: Exception) -> None:
        self._status = "degraded"
        self._failed_count += 1
        self._last_error_category = category
        self._last_error_type = type(exc).__name__
        logger.warning("NATS %s failure type=%s", category, type(exc).__name__)

    async def _close_failed_connection(self) -> None:
        connection = self._connection
        self._connection = None
        self._jetstream = None
        if connection is not None and not getattr(connection, "is_closed", False):
            try:
                await connection.close()
            except Exception:
                pass

    async def _on_disconnected(self) -> None:
        self._status = "degraded"
        self._last_error_category = "connection"
        self._last_error_type = "Disconnected"

    async def _on_reconnected(self) -> None:
        self._status = "live"
        self._last_error_category = ""
        self._last_error_type = ""

    async def _on_closed(self) -> None:
        if self.enabled:
            self._status = "degraded"
            self._last_error_category = "connection"
            self._last_error_type = "Closed"

    async def _on_error(self, exc: Exception) -> None:
        self._record_failure("connection", exc)


class NATSEventWorker:
    def __init__(
        self,
        *,
        repository: CentralFactRepository | None = None,
        stream: str | None = None,
        durable: str | None = None,
    ) -> None:
        self.repository = repository or CentralFactRepository()
        self.stream = stream or settings.nats_stream
        self.durable = durable or settings.nats_consumer
        self._status = "not_started"
        self._persisted_count = 0
        self._duplicate_count = 0
        self._invalid_count = 0
        self._failure_count = 0
        self._last_error_type = ""

    async def process_message(self, message: Any) -> None:
        try:
            raw = json.loads(message.data.decode("utf-8"))
            envelope = TransportEnvelope.model_validate(raw)
            expected_subject = subject_for_envelope(envelope)
            if message.subject != expected_subject:
                raise ValueError("NATS subject does not match validated envelope")
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            self._invalid_count += 1
            self._last_error_type = type(exc).__name__
            self._status = "degraded"
            await message.term()
            return

        try:
            inserted = await asyncio.to_thread(
                self.repository.persist_nats_receipt,
                envelope.model_dump(mode="json"),
                message.subject,
            )
        except Exception as exc:
            self._failure_count += 1
            self._last_error_type = type(exc).__name__
            self._status = "degraded"
            nak = getattr(message, "nak", None)
            if callable(nak):
                await nak(delay=2)
            return

        if inserted:
            self._persisted_count += 1
        else:
            self._duplicate_count += 1
        await message.ack()
        self._status = "live"
        self._last_error_type = ""

    async def run(self, jetstream: Any, stop_event: asyncio.Event) -> None:
        self._status = "starting"
        try:
            info = await jetstream.consumer_info(self.stream, self.durable)
            self._validate_consumer(info)
        except NotFoundError:
            await jetstream.add_consumer(
                self.stream,
                config=ConsumerConfig(
                    durable_name=self.durable,
                    description="Mini-OGAS v3.0.1 PostgreSQL shadow receipt worker",
                    ack_policy=AckPolicy.EXPLICIT,
                    ack_wait=30,
                    max_deliver=5,
                    max_ack_pending=1000,
                    filter_subjects=NATSPublisher._stream_subjects(),
                ),
            )
        subscription = await jetstream.pull_subscribe_bind(
            durable=self.durable,
            stream=self.stream,
        )
        self._status = "live"
        while not stop_event.is_set():
            try:
                messages = await subscription.fetch(batch=20, timeout=1)
            except (NATSTimeoutError, asyncio.TimeoutError):
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._failure_count += 1
                self._last_error_type = type(exc).__name__
                self._status = "degraded"
                await asyncio.sleep(1)
                continue
            for message in messages:
                await self.process_message(message)

    @staticmethod
    def _validate_consumer(info: Any) -> None:
        config = getattr(info, "config", None)
        if config is None:
            raise RuntimeError("existing NATS consumer has no readable configuration")
        configured_subjects = set(getattr(config, "filter_subjects", None) or [])
        legacy_subject = str(getattr(config, "filter_subject", "") or "")
        if legacy_subject:
            configured_subjects.add(legacy_subject)
        required_subjects = set(NATSPublisher._stream_subjects())
        if configured_subjects != required_subjects:
            raise RuntimeError("existing NATS consumer filters do not match v3.0.1 contract")
        if getattr(config, "ack_policy", None) != AckPolicy.EXPLICIT:
            raise RuntimeError("existing NATS consumer must use explicit acknowledgements")

    def health(self) -> dict[str, object]:
        return {
            "status": self._status,
            "durable": self.durable,
            "persisted_count": self._persisted_count,
            "duplicate_count": self._duplicate_count,
            "invalid_count": self._invalid_count,
            "failure_count": self._failure_count,
            "last_error_type": self._last_error_type,
        }


class NATSShadowRuntime:
    def __init__(self, publisher: NATSPublisher | None = None, worker: NATSEventWorker | None = None) -> None:
        self.publisher = publisher or NATSPublisher()
        self.worker = worker or NATSEventWorker()
        self._stop_event = asyncio.Event()
        self._manager_task: asyncio.Task[None] | None = None
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._stop_event.clear()
        connected = await self.publisher.start()
        if self.publisher.enabled and connected:
            self._ensure_worker()
        if self.publisher.enabled:
            self._manager_task = asyncio.create_task(self._manager_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        for task in (self._worker_task, self._manager_task):
            if task is not None:
                task.cancel()
        for task in (self._worker_task, self._manager_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._worker_task = None
        self._manager_task = None
        await self.publisher.stop()

    async def _manager_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self.publisher.connected:
                connected = await self.publisher.start()
                if connected:
                    await self._replace_worker()
            elif self._worker_task is None or self._worker_task.done():
                self._ensure_worker()
            await asyncio.sleep(settings.nats_retry_seconds)

    async def _replace_worker(self) -> None:
        worker_task = self._worker_task
        self._worker_task = None
        if worker_task is not None and not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
        self._ensure_worker()

    def _ensure_worker(self) -> None:
        if self.publisher.jetstream is None:
            return
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(
                self.worker.run(self.publisher.jetstream, self._stop_event)
            )

    async def publish_heartbeat(self, heartbeat: dict[str, object]) -> PublishResult:
        return await self.publisher.publish_heartbeat(heartbeat)

    async def publish_envelope(self, envelope: TransportEnvelope) -> PublishResult:
        return await self.publisher.publish_envelope(envelope)

    async def publish_event(self, event: Any) -> PublishResult:
        return await self.publisher.publish_event(event)

    async def publish_command(self, command: Any) -> PublishResult:
        return await self.publisher.publish_command(command)

    async def publish_audit(self, audit: Any, *, run_id: str = "") -> PublishResult:
        return await self.publisher.publish_audit(audit, run_id=run_id)

    def health(self) -> dict[str, object]:
        publisher = self.publisher.health()
        worker = self.worker.health()
        if not self.publisher.enabled:
            status = "disabled"
        elif publisher["status"] == "live" and worker["status"] == "live":
            status = "live"
        else:
            status = "degraded"
        return {
            "enabled": self.publisher.enabled,
            "status": status,
            "mode": "shadow",
            "publisher": publisher,
            "worker": worker,
        }


nats_runtime = NATSShadowRuntime()
