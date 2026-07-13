import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Any

from pydantic import BaseModel, Field

from ..core.security import (
    PERM_NODE_ISOLATE,
    PERM_NODE_RESTORE,
    ActorInfo,
    require_permission,
)
from ..models import MetricIn
from ..safety_governor import safety_governor
from ..store import store

router = APIRouter(tags=["nodes"])
logger = logging.getLogger(__name__)


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
def ingest_metric(metric: MetricIn):
    alerts = store.record_metric(metric)
    return {"accepted": True, "generated_alerts": alerts}


def ingest_agent_heartbeat(node_code: str, heartbeat: NodeHeartbeatV2In):
    if heartbeat.node_code != node_code:
        raise HTTPException(status_code=400, detail="node_code mismatch")
    try:
        result = store.record_node_heartbeat_v2(heartbeat.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/agents/{node_code}/heartbeat")
def agent_heartbeat_v2(node_code: str, heartbeat: NodeHeartbeatV2In):
    return ingest_agent_heartbeat(node_code, heartbeat)


@router.post("/node-heartbeats")
def node_heartbeat_v2(heartbeat: NodeHeartbeatV2In, response: Response):
    logger.warning("deprecated_api path=/node-heartbeats replacement=/agents/{node_code}/heartbeat node=%s", heartbeat.node_code)
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'</agents/{heartbeat.node_code}/heartbeat>; rel="successor-version"'
    return ingest_agent_heartbeat(heartbeat.node_code, heartbeat)


@router.get("/node-dispatches/{node_code}")
def node_dispatch(node_code: str):
    return store.node_dispatch_for_node(node_code)


@router.post("/node-records/sync")
def sync_node_records(payload: NodeRecordSyncIn):
    return store.record_node_records(payload.node_code, [record.model_dump() for record in payload.records])


@router.put("/api/nodes/{node_code}/heartbeat")
@router.put("/nodes/{node_code}/heartbeat")
def node_heartbeat(node_code: str, heartbeat: NodeHeartbeatIn):
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


@router.get("/api/nodes/{node_code}/pending-commands")
@router.get("/nodes/{node_code}/pending-commands")
def pending_commands(node_code: str):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.pending_commands_for_node(node_code)


@router.get("/api/agents/{node_code}/commands/pending")
@router.get("/agents/{node_code}/commands/pending")
def claim_agent_pending_commands(node_code: str):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.claim_pending_commands_for_node(node_code, agent_id=node_code)


@router.post("/api/agents/{node_code}/commands")
@router.post("/agents/{node_code}/commands")
def create_agent_command(node_code: str, payload: AgentCommandCreateIn):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    if payload.command_type != "set_target_rate":
        raise HTTPException(status_code=400, detail="only set_target_rate is supported in v2.2.8")
    command = store.add_command(
        node_code,
        "set_target_rate",
        "low",
        "pending",
        payload.operator,
        parameters={"target_rate": payload.target_rate},
    )
    return command


@router.post("/api/nodes/{node_code}/command-results")
@router.post("/nodes/{node_code}/command-results")
def command_results(node_code: str, result: CommandResultIn):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.record_command_result(node_code, result.command_id, result.status, result.message)


@router.post("/api/commands/{command_id}/result")
@router.post("/commands/{command_id}/result")
def agent_command_result(command_id: int, result: AgentCommandResultIn):
    return store.record_agent_command_result(command_id, result.status, result.message)


@router.get("/api/part-queue")
@router.get("/part-queue")
def part_queue():
    return store.part_queue_snapshot()


@router.post("/api/agents/{node_code}/parts/claim-next")
@router.post("/agents/{node_code}/parts/claim-next")
def claim_next_part(node_code: str, ttl_seconds: int = 30):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.claim_next_part_for_node(node_code, ttl_seconds=ttl_seconds)


@router.post("/api/agents/{node_code}/parts/{part_id}/complete")
@router.post("/agents/{node_code}/parts/{part_id}/complete")
def complete_part(node_code: str, part_id: str, payload: PartCompleteIn):
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
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    decision = safety_governor.review_control_action(
        action="isolate_node",
        target_node=node_code,
        risk_level="high",
        actor_role=actor.role,
        known_nodes=set(store.nodes),
        confirmation_code=payload.confirmation_code,
        run_mode=payload.run_mode,
    )
    store.record_safety_decision(decision)
    if not decision.allow:
        raise HTTPException(status_code=409, detail={"error": decision.reason_code, "safety": decision.model_dump(mode="json")})
    return store.isolate_node(node_code, actor.role, decision)


@router.post("/nodes/{node_code}/restore")
def restore_node(
    node_code: str,
    payload: NodeSafetyActionIn,
    actor: ActorInfo = Depends(require_permission(PERM_NODE_RESTORE)),
):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    decision = safety_governor.review_control_action(
        action="restore_node",
        target_node=node_code,
        risk_level="high",
        actor_role=actor.role,
        known_nodes=set(store.nodes),
        confirmation_code=payload.confirmation_code,
        run_mode=payload.run_mode,
    )
    store.record_safety_decision(decision)
    if not decision.allow:
        raise HTTPException(status_code=409, detail={"error": decision.reason_code, "safety": decision.model_dump(mode="json")})
    return store.restore_node(node_code, actor.role, decision)


@router.post("/nodes/{node_code}/retire")
def retire_node(
    node_code: str,
    payload: NodeSafetyActionIn,
    actor: ActorInfo = Depends(require_permission(PERM_NODE_RESTORE)),
):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        decision = safety_governor.review_control_action(
            action="retire_node",
            target_node=node_code,
            risk_level="high",
            actor_role=actor.role,
            known_nodes=set(store.nodes),
            confirmation_code=payload.confirmation_code,
            run_mode=payload.run_mode,
        )
        store.record_safety_decision(decision)
        if not decision.allow:
            raise HTTPException(status_code=409, detail={"error": decision.reason_code, "safety": decision.model_dump(mode="json")})
        return store.retire_node(node_code, actor.role, decision)
    except KeyError:
        raise HTTPException(status_code=404, detail="node not found") from None
