from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.security import (
    PERM_COMMAND_APPROVE,
    PERM_COMMAND_ISSUE,
    PERM_COMMAND_REJECT,
    ActorInfo,
    require_permission,
)
from ..core.config import settings
from ..models import ControlCommandRequest, ControlCommandResponse
from ..safety_governor import safety_governor
from ..store import store
from .control import execute_plan, plan_command

router = APIRouter(prefix="/ops", tags=["ops"])


def _require_operator_control() -> None:
    if settings.control_mode == "read_only":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "control_mode_read_only",
                "message": "The configured CONTROL_MODE does not permit control actions.",
            },
        )


class OperatorAgentCommandIn(BaseModel):
    command_type: str = "set_target_rate"
    target_rate: float = Field(gt=0, le=5)


@router.post("/agents/{node_code}/commands")
def issue_agent_command(
    node_code: str,
    payload: OperatorAgentCommandIn,
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
):
    _require_operator_control()
    if node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    if payload.command_type != "set_target_rate":
        raise HTTPException(status_code=400, detail="only set_target_rate is supported")
    physical_limit = store.reported_physical_rate_limit_per_minute(node_code)
    if physical_limit is not None and payload.target_rate > physical_limit + 1e-9:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "target_exceeds_physical_capacity",
                "requested_rate": payload.target_rate,
                "maximum_rate": round(physical_limit, 3),
                "rate_unit": "parts_per_minute",
                "node_code": node_code,
            },
        )
    return store.add_command(
        node_code,
        "set_target_rate",
        "low",
        "pending",
        actor.username or actor.role,
        parameters={"target_rate": payload.target_rate},
    )


@router.get("/pending-approvals")
def list_pending_approvals():
    approvals = store.pending_approvals()
    diagnoses = [d for d in store.ai_diagnoses]
    result = []
    for cmd in approvals:
        related_diag = next((d for d in diagnoses if d.node_code == cmd.node_code), None)
        result.append({
            "command": cmd.model_dump(mode="json"),
            "ai_diagnosis": related_diag.model_dump(mode="json") if related_diag else None,
        })
    return result


@router.post("/approve/{command_id}")
def approve_command(command_id: int, actor: ActorInfo = Depends(require_permission(PERM_COMMAND_APPROVE))):
    return store.approve_command(command_id, actor.role)


@router.post("/reject/{command_id}")
def reject_command(command_id: int, reason: str = Query(default=""), actor: ActorInfo = Depends(require_permission(PERM_COMMAND_REJECT))):
    return store.reject_command(command_id, actor.role, reason)


@router.post("/commands/{command_id}/cancel")
def cancel_command(
    command_id: int,
    reason: str = Query(default=""),
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_REJECT)),
):
    return store.cancel_command(command_id, actor.username or actor.role, reason)


@router.post("/commands/{command_id}/retry")
def retry_command(
    command_id: int,
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
):
    return store.retry_command(command_id, actor.username or actor.role)


@router.get("/escalations")
def list_escalations():
    rows = []
    for event in store.pending_escalations():
        alert = next(
            (
                item for item in reversed(store.alerts)
                if item.node_code == event.node_code
                and item.status not in {"closed", "resolved"}
                and store.alert_in_current_run(item)
                and f"{item.alert_type}:" in event.message
            ),
            None,
        )
        item = event.model_dump(mode="json")
        if alert is not None:
            item["issue_id"] = f"{alert.node_code}-{alert.alert_type}"
            item["alert_type"] = alert.alert_type
            item["status"] = "waiting_human"
        rows.append(item)
    return rows


@router.post("/escalate")
def escalate(node_code: str, issue_type: str, description: str):
    return store.escalate_to_human(node_code, issue_type, description)


@router.post("/issue-command", response_model=ControlCommandResponse)
def issue_command(
    payload: ControlCommandRequest,
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
) -> ControlCommandResponse:
    plan, provider = plan_command(payload.text)
    used_deepseek = provider == "deepseek"
    source = "api" if provider not in {"rule_engine", "rule_fallback"} else "rule_engine"
    if not payload.execute:
        return ControlCommandResponse(
            accepted=True,
            executed=False,
            used_deepseek=used_deepseek,
            provider=provider,
            source=source,
            status="planned",
            plan=plan,
            result=None,
            message="命令已解析但未执行。确认后可再次提交 execute=true。",
        )

    decision = safety_governor.review_control_action(
        action=plan.action,
        target_node=plan.target_node,
        risk_level=plan.risk_level,
        actor_role=actor.role,
        known_nodes=set(store.nodes),
        confirmation_code=payload.confirm,
    )
    store.record_safety_decision(decision)
    if not decision.allow:
        return ControlCommandResponse(
            accepted=True,
            executed=False,
            used_deepseek=used_deepseek,
            provider=provider,
            source=source,
            status="blocked-confirmation-required" if decision.confirmation_required else "blocked-safety-governor",
            plan=plan,
            result=None,
            message=decision.message,
            safety=decision.model_dump(mode="json"),
        )

    result = execute_plan(plan, actor.role, decision)
    return ControlCommandResponse(
        accepted=True,
        executed=True,
        used_deepseek=used_deepseek,
        provider=provider,
        source=source,
        status="executed",
        plan=plan,
        result=result,
        message="命令已通过运维操作网关转发执行。",
        safety=decision.model_dump(mode="json"),
    )
