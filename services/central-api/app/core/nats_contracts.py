from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

NODE_TOKEN_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
EVENT_TOKEN_PATTERN = NODE_TOKEN_PATTERN
ALARM_TYPE_PATTERN = r"^[A-Z][A-Z0-9_]{0,63}$"


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AlarmData(StrictModel):
    type: str = Field(pattern=ALARM_TYPE_PATTERN)
    severity: Literal["info", "low", "medium", "high", "critical"]
    status: Literal["open", "acknowledged", "resolved"]
    value: float | None = None
    threshold: float | None = None
    unit: str | None = Field(default=None, max_length=32)


class MetricsData(StrictModel):
    cpu_usage: float = Field(ge=0, le=100)
    memory_usage: float = Field(ge=0, le=100)
    disk_usage: float = Field(ge=0, le=100)
    db_latency_ms: int = Field(ge=0)
    network_latency_ms: int = Field(ge=0)


class ProductionData(StrictModel):
    workshop_type: Literal["turning", "milling", "grinding"]
    machine_code: str = Field(min_length=1, max_length=64)
    machine_count: int | None = Field(default=None, ge=1)
    active_order: str | None = Field(default=None, max_length=128)
    active_part_id: str | None = Field(default=None, max_length=128)
    finished_quantity: int = Field(ge=0)
    raw_finished_quantity: int | None = Field(default=None, ge=0)
    defect_quantity: int = Field(ge=0)
    target_rate: float = Field(ge=0)
    actual_rate: float = Field(ge=0)
    target_rate_per_hour: float | None = Field(default=None, ge=0)
    actual_rate_per_hour: float | None = Field(default=None, ge=0)
    nominal_capacity_per_hour: float | None = Field(default=None, ge=0)
    rate_unit: Literal["parts_per_minute", "parts_per_hour"]
    utilization: float = Field(ge=0, le=1)
    defect_rate: float = Field(ge=0, le=1)
    wip_input: int = Field(ge=0)
    wip_output: int = Field(ge=0)
    process_time_sec: int | None = Field(default=None, ge=0)
    spindle_temp: float | None = None
    tool_wear_level: float | None = Field(default=None, ge=0, le=100)
    dispatch_policy: str | None = Field(default=None, max_length=64)


class SyncData(StrictModel):
    last_sync_id: int = Field(ge=0)
    pending_records: int = Field(ge=0)


class RuntimeData(StrictModel):
    run_id: str = Field(min_length=1, max_length=128)
    scenario_id: str = Field(min_length=1, max_length=128)
    simulation_engine: Literal["simple", "simpy", "physical"]
    simulation_mode: str = Field(max_length=64)
    simulation_speed: float | None = Field(default=None, gt=0)
    random_seed: int = Field(ge=0)
    simulation_started_at: datetime | None = None
    simulation_time: datetime
    wall_clock_time: datetime
    deployment_mode: Literal["process", "vm", "physical"]
    runtime_source: Literal["live", "simulated", "replay", "fixture", "fallback"]
    part_flow_mode: str | None = Field(default=None, max_length=64)
    heartbeat_sec: int | None = Field(default=None, ge=1, le=60)
    host: str | None = Field(default=None, max_length=128)
    pid: int | None = Field(default=None, ge=1)
    clock_offset_ms: float
    clock_synchronized: bool
    clock_source: str | None = Field(default=None, max_length=128)


class HeartbeatData(StrictModel):
    node_code: str = Field(pattern=NODE_TOKEN_PATTERN)
    status: Literal["running", "warning", "fault", "degraded", "isolated", "shutting_down"]
    timestamp: datetime
    agent_version: str = Field(min_length=1, max_length=32)
    uptime_sec: int = Field(ge=0)
    metrics: MetricsData
    production: ProductionData
    alarms: list[AlarmData] = Field(max_length=64)
    sync: SyncData
    runtime: RuntimeData


class EventData(StrictModel):
    event_type: str = Field(pattern=EVENT_TOKEN_PATTERN)
    severity: Literal["info", "low", "medium", "high", "critical"]
    message: str = Field(min_length=1, max_length=1024)
    scenario_id: str = Field(default="", max_length=128)
    local_sequence: int = Field(default=0, ge=0)
    payload: dict[str, JsonValue]


class CommandData(StrictModel):
    command_id: int = Field(ge=1)
    version: int = Field(ge=1)
    command_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    risk_level: Literal["low", "medium", "high", "critical"]
    status: Literal[
        "pending", "approved", "dispatched", "received", "applied",
        "verified", "rejected", "expired", "failed",
    ]
    operator: str = Field(min_length=1, max_length=128)
    parameters: dict[str, JsonValue]
    expires_at: datetime
    confirmation_required: bool = False
    reason: str = Field(default="", max_length=1024)


class AuditData(StrictModel):
    actor: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(pattern=EVENT_TOKEN_PATTERN)
    resource_id: str = Field(min_length=1, max_length=128)
    result: str = Field(min_length=1, max_length=64)
    detail: str = Field(default="", max_length=4096)


class TransportEnvelope(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    message_id: str
    message_type: Literal["event", "heartbeat", "command", "audit"]
    source: str = Field(pattern=NODE_TOKEN_PATTERN)
    node_code: str = Field(pattern=NODE_TOKEN_PATTERN)
    occurred_at: datetime
    published_at: datetime
    correlation_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=0)
    data: HeartbeatData | EventData | CommandData | AuditData

    @model_validator(mode="after")
    def validate_message_data_pair(self) -> "TransportEnvelope":
        expected = {
            "heartbeat": HeartbeatData,
            "event": EventData,
            "command": CommandData,
            "audit": AuditData,
        }[self.message_type]
        if not isinstance(self.data, expected):
            raise ValueError(f"message_type {self.message_type} does not match data schema")
        UUID(self.message_id)
        return self


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(f"expected model or dict, got {type(value).__name__}")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _message_id(namespace: str, value: object) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return str(uuid5(NAMESPACE_URL, f"mini-ogas:v3:{namespace}:{digest}"))


def _as_utc(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        parsed = fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _severity(value: Any) -> str:
    return str(getattr(value, "value", value))


def build_heartbeat_envelope(
    heartbeat: dict[str, object],
    *,
    published_at: datetime | None = None,
) -> TransportEnvelope:
    published = _as_utc(published_at, utc_now())
    raw = _mapping(heartbeat)
    raw.pop("schema_version", None)
    raw.pop("_received_at", None)
    stable_source = dict(raw)
    occurred = _as_utc(raw.get("timestamp"), published)
    runtime = dict(raw.get("runtime") or {})
    if runtime.get("runtime_source") == "node-agent":
        is_physical = (
            runtime.get("simulation_engine") == "physical"
            or runtime.get("deployment_mode") == "physical"
        )
        runtime["runtime_source"] = "live" if is_physical else "simulated"
    skew_ms = round((published - occurred).total_seconds() * 1000, 3)
    runtime.setdefault("clock_offset_ms", skew_ms)
    runtime.setdefault("clock_synchronized", abs(skew_ms) <= 2000)
    runtime.setdefault("clock_source", "central-arrival-skew")
    raw["runtime"] = runtime
    data = HeartbeatData.model_validate(raw)
    sequence = data.sync.last_sync_id
    correlation_id = f"{data.runtime.run_id}:{data.node_code}:{sequence}"
    return TransportEnvelope(
        message_id=_message_id("heartbeat", stable_source),
        message_type="heartbeat",
        source=data.node_code,
        node_code=data.node_code,
        occurred_at=occurred,
        published_at=published,
        correlation_id=correlation_id,
        run_id=data.runtime.run_id,
        sequence=sequence,
        data=data,
    )


def build_event_envelope(event: Any, *, published_at: datetime | None = None) -> TransportEnvelope:
    published = _as_utc(published_at, utc_now())
    raw = _mapping(event)
    event_type = str(raw.get("event_type") or raw.get("stage") or "")
    sequence = int(raw.get("local_sequence") or raw.get("id") or 0)
    run_id = str(raw.get("run_id") or "unbound")
    node_code = str(raw.get("source_node") or raw.get("node_code") or "central")
    occurred = _as_utc(raw.get("event_time") or raw.get("created_at"), published)
    data = EventData(
        event_type=event_type,
        severity=_severity(raw.get("severity") or "info"),
        message=str(raw.get("message") or event_type),
        scenario_id=str(raw.get("scenario_id") or ""),
        local_sequence=sequence,
        payload=dict(raw.get("payload") or {}),
    )
    message_id = str(raw.get("event_id") or _message_id("event", raw))
    correlation_id = str(raw.get("correlation_id") or f"{run_id}:{node_code}:{sequence}")
    return TransportEnvelope(
        message_id=message_id,
        message_type="event",
        source=node_code,
        node_code=node_code,
        occurred_at=occurred,
        published_at=published,
        correlation_id=correlation_id,
        run_id=run_id,
        sequence=sequence,
        data=data,
    )


def build_command_envelope(command: Any, *, published_at: datetime | None = None) -> TransportEnvelope:
    published = _as_utc(published_at, utc_now())
    raw = _mapping(command)
    command_id = int(raw.get("id") or raw.get("command_id") or 0)
    version = int(raw.get("version") or 1)
    node_code = str(raw.get("node_code") or "")
    run_id = str(raw.get("run_id") or "unbound")
    occurred = _as_utc(raw.get("updated_at") or raw.get("created_at"), published)
    expires_at = _as_utc(raw.get("expires_at"), published + timedelta(seconds=120))
    data = CommandData(
        command_id=command_id,
        version=version,
        command_type=str(raw.get("command_type") or ""),
        risk_level=str(raw.get("risk_level") or "low"),
        status=str(raw.get("status") or "pending"),
        operator=str(raw.get("operator") or "central"),
        parameters=dict(raw.get("parameters") or {}),
        expires_at=expires_at,
        confirmation_required=str(raw.get("risk_level") or "low") in {"high", "critical"},
        reason=str(raw.get("result_message") or ""),
    )
    stable = {"command_id": command_id, "version": version, "status": data.status, "node_code": node_code}
    return TransportEnvelope(
        message_id=_message_id("command", stable),
        message_type="command",
        source="central-api",
        node_code=node_code,
        occurred_at=occurred,
        published_at=published,
        correlation_id=f"command:{command_id}:v{version}",
        run_id=run_id,
        sequence=command_id,
        data=data,
    )


def build_audit_envelope(
    audit: Any,
    *,
    run_id: str = "",
    published_at: datetime | None = None,
) -> TransportEnvelope:
    published = _as_utc(published_at, utc_now())
    raw = _mapping(audit)
    audit_id = int(raw.get("id") or 0)
    durable_run_id = run_id or str(raw.get("run_id") or "unbound")
    resource_type = str(raw.get("resource_type") or "system")
    occurred = _as_utc(raw.get("created_at"), published)
    data = AuditData(
        actor=str(raw.get("actor") or "central"),
        action=str(raw.get("action") or "unknown"),
        resource_type=resource_type,
        resource_id=str(raw.get("resource_id") or audit_id),
        result=str(raw.get("result") or "recorded"),
        detail=str(raw.get("detail") or ""),
    )
    stable = {"id": audit_id, "run_id": durable_run_id, **data.model_dump(mode="json")}
    return TransportEnvelope(
        message_id=_message_id("audit", stable),
        message_type="audit",
        source="central-api",
        node_code="central",
        occurred_at=occurred,
        published_at=published,
        correlation_id=f"audit:{durable_run_id}:{audit_id}",
        run_id=durable_run_id,
        sequence=audit_id,
        data=data,
    )


def subject_for_envelope(envelope: TransportEnvelope) -> str:
    if envelope.message_type == "heartbeat":
        token = envelope.node_code
        subject = f"ogas.heartbeats.{token}"
    elif envelope.message_type == "event":
        assert isinstance(envelope.data, EventData)
        subject = f"ogas.events.{envelope.data.event_type}.{envelope.node_code}"
    elif envelope.message_type == "command":
        subject = f"ogas.commands.{envelope.node_code}"
    else:
        assert isinstance(envelope.data, AuditData)
        subject = f"ogas.audit.{envelope.data.resource_type}"
    validate_subject(subject)
    return subject


def validate_subject(subject: str) -> None:
    tokens = subject.split(".")
    if len(subject) > 256 or len(tokens) < 3 or len(tokens) > 16:
        raise ValueError("invalid NATS subject length or token count")
    if any(not re.fullmatch(NODE_TOKEN_PATTERN, token) for token in tokens):
        raise ValueError("invalid NATS subject token")


def envelope_bytes(envelope: TransportEnvelope) -> bytes:
    raw = envelope.model_dump(mode="json")
    return _canonical_json(raw).encode("utf-8")
