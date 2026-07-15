import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..command_control_service import command_control_service
from ..core.config import settings
from ..core.security import (
    PERM_COMMAND_ISSUE,
    PERM_COMMAND_RECEIVE,
    PERM_COMMAND_REPORT,
    PERM_METRIC_INGEST,
    PERM_NODE_HEARTBEAT,
    PERM_NODE_ISOLATE,
    PERM_NODE_RESTORE,
    PERM_PRODUCTION_EXECUTE,
    PERM_TELEMETRY_INGEST,
    ActorInfo,
    actor_identity,
    assert_node_resource_access,
    require_permission,
)
from ..models import MetricIn
from ..safety_governor import safety_governor
from ..store import store

router = APIRouter(tags=["nodes"])
logger = logging.getLogger(__name__)
MetricIngester = Depends(require_permission(PERM_METRIC_INGEST))
NodeHeartbeater = Depends(require_permission(PERM_NODE_HEARTBEAT))
NodeRecordIngester = Depends(require_permission(PERM_TELEMETRY_INGEST))
CommandReceiver = Depends(require_permission(PERM_COMMAND_RECEIVE))
CommandReporter = Depends(require_permission(PERM_COMMAND_REPORT))
ProductionExecutor = Depends(require_permission(PERM_PRODUCTION_EXECUTE))


def _require_operator_control() -> None:
    if settings.control_mode == "read_only":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "control_mode_read_only",
                "message": "The configured CONTROL_MODE does not permit control actions.",
            },
        )


class NodeHeartbeatIn(BaseModel):
    node_code: str
    agent_version: str = "0.1.0"
    uptime_seconds: int = Field(ge=0)
    local_db_size_bytes: int = Field(ge=0)
    db_size_source: str = "reported"
    status: str = "online"
    session_token: str = ""


class NodeHeartbeatV2In(BaseModel):
    node_code: str
    status: str = "running"
    timestamp: str | None = None
    schema_version: str | None = None
    agent_version: str = "0.2.0"
    uptime_sec: int = Field(default=0, ge=0)
    metrics: dict[str, Any] | None = None
    production: dict[str, Any] | None = None
    alarms: list[dict[str, Any]] = Field(default_factory=list)
    sync: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None


class CommandResultIn(BaseModel):
    command_id: int
    command_type: str
    status: str
    message: str = ""


class AgentCommandResultIn(BaseModel):
    status: str
    message: str = ""


class AgentCommandCreateIn(BaseModel):
    command_type: str = "set_target_rate"
    target_rate: float = Field(gt=0, le=5)
    operator: str = "central-policy"


class PartCompleteIn(BaseModel):
    claim_token: str = Field(min_length=1)


class NodeRecordIn(BaseModel):
    local_id: int = Field(ge=1)
    payload: dict[str, Any] | str
    created_at: str
    original_request_id: str = ""
    original_http_status: int = Field(default=0, ge=0)
    original_error: str = ""


class NodeRecordSyncIn(BaseModel):
    node_code: str
    records: list[NodeRecordIn] = Field(default_factory=list, max_length=100)


class NodeSafetyActionIn(BaseModel):
    confirmation_code: str = ""
    run_mode: str = "normal"


@router.get("/nodes")
def list_nodes():
    return list(store.nodes.values())


@router.get("/metrics/latest")
def latest_metrics():
    return store.latest_metrics()


@router.post("/metrics")
def ingest_metric(metric: MetricIn, actor: ActorInfo = MetricIngester):
    assert_node_resource_access(actor, metric.node_code)
    alerts = store.record_metric(metric)
    return {"accepted": True, "generated_alerts": alerts}


async def ingest_agent_heartbeat(
    node_code: str,
    heartbeat: NodeHeartbeatV2In,
    actor: ActorInfo,
):
    assert_node_resource_access(actor, node_code)
    if heartbeat.node_code != node_code:
        raise HTTPException(status_code=400, detail="node_code mismatch")
    payload = heartbeat.model_dump(exclude_none=True)
    runtime = dict(payload.get("runtime") or {})
    try:
        runtime["runtime_source"] = settings.validate_runtime_source(runtime)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "data_source_mismatch", "message": str(exc)},
        ) from exc
    payload["runtime"] = runtime
    try:
        result = await asyncio.to_thread(store.record_node_heartbeat_v2, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    outbox_accepted = bool(result.pop("_transport_outbox_accepted", False))
    nats_status = "queued" if outbox_accepted and settings.nats_enabled else "disabled"
    return {
        "ok": True,
        **result,
        "transport": {
            "rest": "accepted",
            "nats": {
                "status": nats_status,
                "mode": "outbox",
                "publisher": "background-worker",
            },
        },
    }


@router.post("/agents/{node_code}/heartbeat")
async def agent_heartbeat_v2(
    node_code: str,
    heartbeat: NodeHeartbeatV2In,
    actor: ActorInfo = NodeHeartbeater,
):
    return await ingest_agent_heartbeat(node_code, heartbeat, actor)


@router.post("/node-heartbeats")
async def node_heartbeat_v2(
    heartbeat: NodeHeartbeatV2In,
    response: Response,
    actor: ActorInfo = NodeHeartbeater,
):
    logger.warning("deprecated_api path=/node-heartbeats replacement=/agents/{node_code}/heartbeat node=%s", heartbeat.node_code)
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'</agents/{heartbeat.node_code}/heartbeat>; rel="successor-version"'
    return await ingest_agent_heartbeat(heartbeat.node_code, heartbeat, actor)


@router.get("/node-dispatches/{node_code}")
def node_dispatch(node_code: str, actor: ActorInfo = CommandReceiver):
    assert_node_resource_access(actor, node_code)
    return store.node_dispatch_for_node(node_code)


@router.post("/node-records/sync")
def sync_node_records(payload: NodeRecordSyncIn, actor: ActorInfo = NodeRecordIngester):
    assert_node_resource_access(actor, payload.node_code)
    try:
        return store.record_node_records(payload.node_code, [record.model_dump() for record in payload.records])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/nodes/{node_code}/heartbeat")
def node_heartbeat(
    node_code: str,
    heartbeat: NodeHeartbeatIn,
    actor: ActorInfo = NodeHeartbeater,
):
    assert_node_resource_access(actor, node_code)
    if heartbeat.node_code != node_code:
        raise HTTPException(status_code=400, detail="node_code mismatch")
    return store.record_heartbeat(
        node_code=node_code,
        agent_version=heartbeat.agent_version,
        uptime_seconds=heartbeat.uptime_seconds,
        local_db_size_bytes=heartbeat.local_db_size_bytes,
        db_size_source=heartbeat.db_size_source,
        status=heartbeat.status,
        session_token=heartbeat.session_token,
    )


@router.get("/nodes/{node_code}/pending-commands")
def pending_commands(node_code: str, actor: ActorInfo = CommandReceiver):
    assert_node_resource_access(actor, node_code)
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.pending_commands_for_node(node_code)


@router.get("/agents/{node_code}/commands/pending")
def claim_agent_pending_commands(node_code: str, actor: ActorInfo = CommandReceiver):
    assert_node_resource_access(actor, node_code)
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.claim_pending_commands_for_node(node_code, agent_id=node_code)


@router.post("/agents/{node_code}/commands")
def create_agent_command(
    node_code: str,
    payload: AgentCommandCreateIn,
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
):
    if payload.command_type != "set_target_rate":
        raise HTTPException(status_code=400, detail="only set_target_rate is supported in v2.2.8")
    return command_control_service.issue_target_rate(
        node_code=node_code,
        target_rate=payload.target_rate,
        actor=actor,
    )


@router.post("/nodes/{node_code}/command-results")
def command_results(
    node_code: str,
    result: CommandResultIn,
    actor: ActorInfo = CommandReporter,
):
    assert_node_resource_access(actor, node_code)
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.record_command_result(node_code, result.command_id, result.status, result.message)


@router.post("/commands/{command_id}/result")
def agent_command_result(
    command_id: int,
    result: AgentCommandResultIn,
    actor: ActorInfo = CommandReporter,
):
    command = next((item for item in store.commands if item.id == command_id), None)
    if command is None:
        raise HTTPException(status_code=404, detail=f"command {command_id} not found")
    assert_node_resource_access(actor, command.node_code)
    return store.record_agent_command_result(command_id, result.status, result.message)


@router.get("/part-queue")
def part_queue():
    return store.part_queue_snapshot()


@router.post("/agents/{node_code}/parts/claim-next")
def claim_next_part(
    node_code: str,
    ttl_seconds: int = 30,
    actor: ActorInfo = ProductionExecutor,
):
    assert_node_resource_access(actor, node_code)
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.claim_next_part_for_node(node_code, ttl_seconds=ttl_seconds)


@router.post("/agents/{node_code}/parts/{part_id}/complete")
def complete_part(
    node_code: str,
    part_id: str,
    payload: PartCompleteIn,
    actor: ActorInfo = ProductionExecutor,
):
    assert_node_resource_access(actor, node_code)
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.complete_claimed_part(node_code, part_id, payload.claim_token)


@router.get("/topology")
def list_topology():
    return store.topology_edges


@router.post("/nodes/{node_code}/isolate")
def isolate_node(
    node_code: str,
    payload: NodeSafetyActionIn,
    actor: ActorInfo = Depends(require_permission(PERM_NODE_ISOLATE)),
):
    _require_operator_control()
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    decision = safety_governor.review_control_action(
        action="isolate_node",
        target_node=node_code,
        risk_level="high",
        actor_role=actor.role,
        actor_id=actor_identity(actor),
        known_nodes=set(store.nodes),
        confirmation_code=payload.confirmation_code,
        run_mode=payload.run_mode,
    )
    store.record_safety_decision(decision)
    if not decision.allow:
        raise HTTPException(status_code=409, detail={"error": decision.reason_code, "safety": decision.model_dump(mode="json")})
    return store.isolate_node(node_code, actor_identity(actor), decision)


@router.post("/nodes/{node_code}/restore")
def restore_node(
    node_code: str,
    payload: NodeSafetyActionIn,
    actor: ActorInfo = Depends(require_permission(PERM_NODE_RESTORE)),
):
    _require_operator_control()
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    decision = safety_governor.review_control_action(
        action="restore_node",
        target_node=node_code,
        risk_level="high",
        actor_role=actor.role,
        actor_id=actor_identity(actor),
        known_nodes=set(store.nodes),
        confirmation_code=payload.confirmation_code,
        run_mode=payload.run_mode,
    )
    store.record_safety_decision(decision)
    if not decision.allow:
        raise HTTPException(status_code=409, detail={"error": decision.reason_code, "safety": decision.model_dump(mode="json")})
    return store.restore_node(node_code, actor_identity(actor), decision)


@router.post("/nodes/{node_code}/retire")
def retire_node(
    node_code: str,
    payload: NodeSafetyActionIn,
    actor: ActorInfo = Depends(require_permission(PERM_NODE_RESTORE)),
):
    _require_operator_control()
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        decision = safety_governor.review_control_action(
            action="retire_node",
            target_node=node_code,
            risk_level="high",
            actor_role=actor.role,
            actor_id=actor_identity(actor),
            known_nodes=set(store.nodes),
            confirmation_code=payload.confirmation_code,
            run_mode=payload.run_mode,
        )
        store.record_safety_decision(decision)
        if not decision.allow:
            raise HTTPException(status_code=409, detail={"error": decision.reason_code, "safety": decision.model_dump(mode="json")})
        return store.retire_node(node_code, actor_identity(actor), decision)
    except KeyError:
        raise HTTPException(status_code=404, detail="node not found") from None
