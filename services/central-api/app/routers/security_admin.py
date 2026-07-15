from fastapi import APIRouter, Depends

from ..core.principals import (
    revoke_node_credentials,
    revoke_principal_credentials,
    rotate_ai_agent_credential,
    rotate_node_credential,
    rotate_service_credential,
)
from ..core.security import (
    PERM_PRINCIPAL_MANAGE,
    ActorInfo,
    actor_identity,
    get_current_actor,
    require_permission,
)
from ..store import store

router = APIRouter(prefix="/security", tags=["security"])
CurrentActor = Depends(get_current_actor)
PrincipalManager = Depends(require_permission(PERM_PRINCIPAL_MANAGE))


@router.get("/whoami")
def whoami(actor: ActorInfo = CurrentActor):
    return actor


@router.post("/node-credentials/{node_code}/rotate")
def rotate_node_token(
    node_code: str,
    actor: ActorInfo = PrincipalManager,
):
    issued = rotate_node_credential(node_code)
    store.add_audit_log(
        actor_identity(actor),
        "principal:credential:rotate",
        "node",
        node_code,
        "success",
        issued["credential_id"],
    )
    return issued


@router.post("/node-credentials/{node_code}/revoke")
def revoke_node_token(
    node_code: str,
    actor: ActorInfo = PrincipalManager,
):
    revoked = revoke_node_credentials(node_code)
    store.add_audit_log(
        actor_identity(actor),
        "principal:credential:revoke",
        "node",
        node_code,
        "success",
        f"revoked={revoked}",
    )
    return {"accepted": True, "node_code": node_code, "revoked_credentials": revoked}


def _record_nonhuman_rotation(actor: ActorInfo, issued: dict[str, str]) -> dict[str, str]:
    store.add_audit_log(
        actor_identity(actor),
        "principal:credential:rotate",
        issued["principal_type"],
        issued["principal_id"],
        "success",
        issued["credential_id"],
    )
    return issued


@router.post("/service-credentials/{service_id}/rotate")
def rotate_service_token(
    service_id: str,
    actor: ActorInfo = PrincipalManager,
):
    return _record_nonhuman_rotation(actor, rotate_service_credential(service_id))


@router.post("/service-credentials/{service_id}/revoke")
def revoke_service_token(
    service_id: str,
    actor: ActorInfo = PrincipalManager,
):
    principal_id = f"service:{service_id}"
    revoked = revoke_principal_credentials(principal_id)
    store.add_audit_log(
        actor_identity(actor),
        "principal:credential:revoke",
        "service",
        principal_id,
        "success",
        f"revoked={revoked}",
    )
    return {"accepted": True, "principal_id": principal_id, "revoked_credentials": revoked}


@router.post("/ai-agent-credentials/{agent_id}/rotate")
def rotate_ai_agent_token(
    agent_id: str,
    actor: ActorInfo = PrincipalManager,
):
    return _record_nonhuman_rotation(actor, rotate_ai_agent_credential(agent_id))


@router.post("/ai-agent-credentials/{agent_id}/revoke")
def revoke_ai_agent_token(
    agent_id: str,
    actor: ActorInfo = PrincipalManager,
):
    principal_id = f"ai:{agent_id}"
    revoked = revoke_principal_credentials(principal_id)
    store.add_audit_log(
        actor_identity(actor),
        "principal:credential:revoke",
        "ai_agent",
        principal_id,
        "success",
        f"revoked={revoked}",
    )
    return {"accepted": True, "principal_id": principal_id, "revoked_credentials": revoked}
