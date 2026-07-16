import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.core.database import get_db, init_db
from app.core.config import settings
from app.core.nats_contracts import (
    TransportEnvelope,
    build_heartbeat_envelope,
    subject_for_envelope,
)
from app.core.nats_publisher import NATSEventWorker, NATSPublisher, NATSShadowRuntime
from app.core.security import ActorInfo
from app.models import AuditLog, IncidentEvent, NodeCommand, Severity
from app.persistence_repository import CentralFactRepository
from app.routers import nodes as nodes_router
from app.store import MemoryStore
from nats.js.api import AckPolicy
from pydantic import ValidationError


def heartbeat_payload() -> dict[str, object]:
    return {
        "node_code": "turning-workshop-01",
        "status": "running",
        "timestamp": "2026-07-13T08:00:05+00:00",
        "agent_version": "0.2.0",
        "uptime_sec": 5,
        "metrics": {
            "cpu_usage": 20.0,
            "memory_usage": 31.0,
            "disk_usage": 22.0,
            "db_latency_ms": 3,
            "network_latency_ms": 4,
        },
        "production": {
            "workshop_type": "turning",
            "machine_code": "LATHE-01",
            "machine_count": 1,
            "active_order": "ORDER-001",
            "active_part_id": "PART-001",
            "finished_quantity": 2,
            "raw_finished_quantity": 2,
            "defect_quantity": 0,
            "target_rate": 1.0,
            "actual_rate": 0.9,
            "target_rate_per_hour": 60.0,
            "actual_rate_per_hour": 54.0,
            "nominal_capacity_per_hour": 60.0,
            "rate_unit": "parts_per_minute",
            "utilization": 0.9,
            "defect_rate": 0.0,
            "wip_input": 3,
            "wip_output": 2,
            "process_time_sec": 60,
            "spindle_temp": 54.2,
            "tool_wear_level": 12.0,
            "dispatch_policy": "central",
        },
        "alarms": [],
        "sync": {"last_sync_id": 5, "pending_records": 0},
        "runtime": {
            "run_id": "RUN-001",
            "scenario_id": "SCN-001",
            "simulation_engine": "simpy",
            "simulation_mode": "normal",
            "simulation_speed": 1,
            "random_seed": 20260713,
            "simulation_started_at": "2026-07-13T08:00:00+00:00",
            "simulation_time": "2026-07-13T08:00:05+00:00",
            "wall_clock_time": "2026-07-13T08:00:05+00:00",
            "deployment_mode": "process",
            "runtime_source": "live",
            "part_flow_mode": "central",
            "heartbeat_sec": 5,
            "host": "test-host",
            "pid": 1234,
        },
    }


def test_heartbeat_adapter_builds_deterministic_strict_envelope() -> None:
    published_at = datetime(2026, 7, 13, 8, 0, 6, tzinfo=UTC)
    first = build_heartbeat_envelope(heartbeat_payload(), published_at=published_at)
    second = build_heartbeat_envelope(heartbeat_payload(), published_at=published_at)

    assert first.message_id == second.message_id
    assert first.message_type == "heartbeat"
    assert first.sequence == 5
    assert first.data.runtime.clock_source == "central-arrival-skew"
    assert subject_for_envelope(first) == "ogas.heartbeats.turning-workshop-01"

    invalid = first.model_dump(mode="json")
    invalid["unexpected"] = True
    with pytest.raises(ValidationError):
        TransportEnvelope.model_validate(invalid)


def test_subject_builder_rejects_wildcard_injection() -> None:
    envelope = build_heartbeat_envelope(heartbeat_payload())
    invalid = envelope.model_dump(mode="json")
    invalid["node_code"] = "turning.>"

    with pytest.raises(ValidationError):
        TransportEnvelope.model_validate(invalid)


def test_v2_node_agent_runtime_source_maps_to_simulated_for_simpy() -> None:
    payload = heartbeat_payload()
    payload["runtime"]["runtime_source"] = "node-agent"

    envelope = build_heartbeat_envelope(payload)

    assert envelope.data.runtime.runtime_source == "simulated"


def test_compose_node_heartbeat_accepts_container_deployment_mode() -> None:
    payload = heartbeat_payload()
    payload["runtime"]["deployment_mode"] = "container"
    payload["runtime"]["runtime_source"] = "simulated"

    envelope = build_heartbeat_envelope(payload)

    assert envelope.data.runtime.deployment_mode == "container"
    assert envelope.data.runtime.runtime_source == "simulated"


def test_container_heartbeat_persists_and_queues_outbox_in_one_transaction(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(tmp_path / "container-heartbeat.db"))
    monkeypatch.setattr(settings, "nats_enabled", True)
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    init_db()
    runtime_store = MemoryStore()
    payload = heartbeat_payload()
    payload["runtime"]["deployment_mode"] = "container"
    payload["runtime"]["runtime_source"] = "simulated"

    result = runtime_store.record_node_heartbeat_v2(payload)

    with get_db() as db:
        heartbeat_count = db.execute(
            "SELECT count(*) AS count FROM heartbeat_shadow WHERE run_id = ?",
            ("RUN-001",),
        ).fetchone()["count"]
        outbox_count = db.execute(
            """SELECT count(*) AS count FROM outbox_messages
               WHERE message_type = ? AND aggregate_id = ?""",
            ("heartbeat", "turning-workshop-01"),
        ).fetchone()["count"]
    assert result["_transport_outbox_accepted"] is True
    assert heartbeat_count == 1
    assert outbox_count == 1


def test_v2_node_agent_runtime_source_maps_to_live_for_physical_runtime() -> None:
    payload = heartbeat_payload()
    payload["runtime"].update({
        "runtime_source": "node-agent",
        "simulation_engine": "physical",
        "deployment_mode": "physical",
    })

    envelope = build_heartbeat_envelope(payload)

    assert envelope.data.runtime.runtime_source == "live"


class FakeJetStream:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str]]] = []
        self.stream_created = False

    async def stream_info(self, _name: str):
        return {"name": "OGAS_V3_SHADOW"}

    async def publish(self, subject: str, payload: bytes, **kwargs):
        self.published.append((subject, payload, kwargs.get("headers") or {}))
        return {"stream": "OGAS_V3_SHADOW", "seq": 1}


class FakeConnection:
    def __init__(self, jetstream: FakeJetStream) -> None:
        self._jetstream = jetstream
        self.is_connected = True
        self.is_closed = False

    def jetstream(self):
        return self._jetstream

    async def drain(self) -> None:
        self.is_connected = False


def test_publisher_emits_schema_valid_message_with_dedup_header() -> None:
    js = FakeJetStream()

    async def connect(**_kwargs):
        return FakeConnection(js)

    async def exercise():
        publisher = NATSPublisher(enabled=True, connector=connect)
        assert await publisher.start() is True
        result = await publisher.publish_heartbeat(heartbeat_payload())
        await publisher.stop()
        return result

    result = asyncio.run(exercise())

    assert result.status == "published"
    subject, raw, headers = js.published[0]
    body = json.loads(raw)
    assert subject == "ogas.heartbeats.turning-workshop-01"
    assert headers["Nats-Msg-Id"] == body["message_id"]
    assert TransportEnvelope.model_validate(body).message_type == "heartbeat"


def test_publisher_emits_all_four_v3_contract_message_types() -> None:
    js = FakeJetStream()

    async def connect(**_kwargs):
        return FakeConnection(js)

    event = IncidentEvent(
        id=7,
        node_code="turning-workshop-01",
        source_node="turning-workshop-01",
        stage="machine_alarm",
        event_type="machine_alarm",
        severity=Severity.high,
        message="Spindle temperature exceeded the configured threshold.",
        run_id="RUN-001",
        scenario_id="SCN-001",
        local_sequence=7,
        payload={"temperature_c": 89.0, "threshold_c": 82.0},
    )
    command = NodeCommand(
        id=11,
        node_code="turning-workshop-01",
        command_type="set_target_rate",
        risk_level="medium",
        status="pending",
        operator="central-policy",
        parameters={"target_rate": 0.8},
    )
    audit = AuditLog(
        id=13,
        actor="system-admin",
        action="command:created",
        resource_type="command",
        resource_id="11",
        result="success",
    )

    async def exercise():
        publisher = NATSPublisher(enabled=True, connector=connect)
        assert await publisher.start() is True
        results = [
            await publisher.publish_event(event),
            await publisher.publish_heartbeat(heartbeat_payload()),
            await publisher.publish_command(command),
            await publisher.publish_audit(audit, run_id="RUN-001"),
        ]
        await publisher.stop()
        return results

    results = asyncio.run(exercise())
    envelopes = [TransportEnvelope.model_validate_json(raw) for _, raw, _ in js.published]

    assert [result.status for result in results] == ["published"] * 4
    assert [envelope.message_type for envelope in envelopes] == [
        "event",
        "heartbeat",
        "command",
        "audit",
    ]
    assert [subject for subject, _, _ in js.published] == [
        "ogas.events.machine_alarm.turning-workshop-01",
        "ogas.heartbeats.turning-workshop-01",
        "ogas.commands.turning-workshop-01",
        "ogas.audit.command",
    ]


def test_publisher_reports_degraded_when_nats_is_unavailable() -> None:
    options: dict[str, object] = {}

    async def unavailable(**kwargs):
        options.update(kwargs)
        raise OSError("connection refused")

    async def exercise():
        publisher = NATSPublisher(enabled=True, connector=unavailable)
        assert await publisher.start() is False
        result = await publisher.publish_heartbeat(heartbeat_payload())
        state = publisher.health()
        await publisher.stop()
        return result, state

    result, state = asyncio.run(exercise())

    assert result.status == "degraded"
    assert state["status"] == "degraded"
    assert state["last_error_category"] == "connection"
    assert options["max_reconnect_attempts"] == 1


def test_shadow_runtime_replaces_consumer_after_new_connection() -> None:
    class ReconnectedPublisher:
        enabled = True
        connected = True
        jetstream = object()

    class RecordingWorker:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def run(self, jetstream, stop_event) -> None:
            assert jetstream is publisher.jetstream
            self.started.set()
            await stop_event.wait()

    publisher = ReconnectedPublisher()
    worker = RecordingWorker()
    runtime = NATSShadowRuntime(publisher=publisher, worker=worker)

    async def exercise() -> None:
        old_cancelled = asyncio.Event()

        async def stale_consumer() -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                old_cancelled.set()
                raise

        runtime._worker_task = asyncio.create_task(stale_consumer())
        stale_task = runtime._worker_task
        await asyncio.sleep(0)
        await runtime._replace_worker()
        await asyncio.wait_for(worker.started.wait(), timeout=1)

        assert stale_task.done()
        assert old_cancelled.is_set()
        assert runtime._worker_task is not stale_task

        runtime._stop_event.set()
        assert runtime._worker_task is not None
        await runtime._worker_task

    asyncio.run(exercise())


def test_rest_heartbeat_queues_outbox_without_request_side_publish(monkeypatch) -> None:
    recorded: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> dict[str, object]:
        recorded.append(payload)
        return {
            "accepted": True,
            "node_code": payload["node_code"],
            "_transport_outbox_accepted": True,
        }

    monkeypatch.setattr(nodes_router.store, "record_node_heartbeat_v2", record)
    monkeypatch.setattr(nodes_router.settings, "nats_enabled", True)

    heartbeat = nodes_router.NodeHeartbeatV2In.model_validate(heartbeat_payload())
    result = asyncio.run(
        nodes_router.ingest_agent_heartbeat(
            heartbeat.node_code,
            heartbeat,
            ActorInfo(
                principal_id=f"node:{heartbeat.node_code}",
                principal_type="node",
                username=f"node:{heartbeat.node_code}",
                display_name=heartbeat.node_code,
                role="node_agent",
                roles=["node_agent"],
                permissions={"node:heartbeat"},
                node_code=heartbeat.node_code,
            ),
        )
    )

    assert recorded and recorded[0]["node_code"] == "turning-workshop-01"
    assert result["ok"] is True
    assert result["transport"]["rest"] == "accepted"
    assert result["transport"]["nats"] == {
        "status": "queued",
        "mode": "outbox",
        "publisher": "background-worker",
    }


class FakeMessage:
    def __init__(self, envelope: TransportEnvelope) -> None:
        self.subject = subject_for_envelope(envelope)
        self.data = envelope.model_dump_json().encode("utf-8")
        self.acked = 0
        self.terminated = 0

    async def ack(self) -> None:
        self.acked += 1

    async def term(self) -> None:
        self.terminated += 1


def test_worker_persists_one_idempotent_shadow_receipt() -> None:
    init_db()
    repository = CentralFactRepository()
    worker = NATSEventWorker(repository=repository)
    envelope = build_heartbeat_envelope(heartbeat_payload())
    first = FakeMessage(envelope)
    duplicate = FakeMessage(envelope)

    asyncio.run(worker.process_message(first))
    asyncio.run(worker.process_message(duplicate))

    with get_db() as db:
        count = db.execute(
            "SELECT count(*) AS count FROM nats_shadow_receipts WHERE message_id = ?",
            (envelope.message_id,),
        ).fetchone()["count"]

    assert count == 1
    assert first.acked == 1
    assert duplicate.acked == 1
    assert worker.health()["persisted_count"] >= 1
    assert worker.health()["duplicate_count"] >= 1


def test_worker_terminates_invalid_schema_without_writing() -> None:
    init_db()
    worker = NATSEventWorker(repository=CentralFactRepository())

    class InvalidMessage(FakeMessage):
        def __init__(self) -> None:
            self.subject = "ogas.heartbeats.turning-workshop-01"
            self.data = b'{"schema_version":"3.0","message_type":"heartbeat"}'
            self.acked = 0
            self.terminated = 0

    message = InvalidMessage()
    asyncio.run(worker.process_message(message))

    assert message.acked == 0
    assert message.terminated == 1
    assert worker.health()["invalid_count"] == 1


def test_worker_treats_empty_pull_timeout_as_idle_not_degraded() -> None:
    stop_event = asyncio.Event()

    class IdleSubscription:
        async def fetch(self, **_kwargs):
            stop_event.set()
            raise asyncio.TimeoutError

    class ExistingConsumerJetStream:
        async def consumer_info(self, _stream: str, _durable: str):
            return SimpleNamespace(
                config=SimpleNamespace(
                    filter_subjects=NATSPublisher._stream_subjects(),
                    filter_subject="",
                    ack_policy=AckPolicy.EXPLICIT,
                )
            )

        async def pull_subscribe_bind(self, **_kwargs):
            return IdleSubscription()

    worker = NATSEventWorker()
    asyncio.run(worker.run(ExistingConsumerJetStream(), stop_event))

    assert worker.health()["status"] == "live"
    assert worker.health()["failure_count"] == 0
    assert worker.health()["last_error_type"] == ""
