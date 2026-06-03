from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.security import (
    PERM_NODE_ISOLATE,
    PERM_NODE_RESTORE,
    ActorInfo,
    require_permission,
)
from ..models import MetricIn
from ..store import store

router = APIRouter(tags=["nodes"])


class NodeHeartbeatIn(BaseModel):
    node_code: str
    agent_version: str = "0.1.0"
    uptime_seconds: int = Field(ge=0)
    local_db_size_bytes: int = Field(ge=0)
    status: str = "online"
    session_token: str = ""


class CommandResultIn(BaseModel):
    command_id: int
    command_type: str
    status: str
    message: str = ""


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
        status=heartbeat.status,
        session_token=heartbeat.session_token,
    )


@router.get("/api/nodes/{node_code}/pending-commands")
@router.get("/nodes/{node_code}/pending-commands")
def pending_commands(node_code: str):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.pending_commands_for_node(node_code)


@router.post("/api/nodes/{node_code}/command-results")
@router.post("/nodes/{node_code}/command-results")
def command_results(node_code: str, result: CommandResultIn):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.record_command_result(node_code, result.command_id, result.status, result.message)


@router.get("/topology")
def list_topology():
    return store.topology_edges


@router.post("/nodes/{node_code}/isolate")
def isolate_node(node_code: str, actor: ActorInfo = Depends(require_permission(PERM_NODE_ISOLATE))):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.isolate_node(node_code, actor.role)


@router.post("/nodes/{node_code}/restore")
def restore_node(node_code: str, actor: ActorInfo = Depends(require_permission(PERM_NODE_RESTORE))):
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return store.restore_node(node_code, actor.role)
