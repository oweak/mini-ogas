from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..command_control_service import command_control_service
from ..core.security import (
    PERM_COMMAND_APPROVE,
    PERM_COMMAND_ISSUE,
    PERM_COMMAND_REJECT,
    ActorInfo,
    actor_identity,
    require_permission,
)
from ..models import ControlCommandRequest, ControlCommandResponse
from ..repositories.ai_suggestions import ai_suggestion_repository
from ..safety_governor import safety_governor
from ..store import store
from .control import execute_plan, plan_command

router = APIRouter(prefix="/ops", tags=["ops"])


class OperatorAgentCommandIn(BaseModel):
    command_type: str = "set_target_rate"
    target_rate: float = Field(gt=0, le=5)


@router.post("/agents/{node_code}/commands")
def issue_agent_command(
    node_code: str,
    payload: OperatorAgentCommandIn,
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
):
    if payload.command_type != "set_target_rate":
        raise HTTPException(status_code=400, detail="only set_target_rate is supported")
    return command_control_service.issue_target_rate(
        node_code=node_code,
        target_rate=payload.target_rate,
        actor=actor,
    )


@router.get("/pending-approvals")
def list_pending_approvals():
    approvals = store.pending_approvals()
    diagnoses = [d for d in store.ai_diagnoses]
    result = []
    for cmd in approvals:
        related_diag = next((d for d in diagnoses if d.node_code == cmd.node_code), None)
        suggestion = ai_suggestion_repository.find_by_command(cmd.id)
        result.append({
            "command": cmd.model_dump(mode="json"),
            "ai_diagnosis": related_diag.model_dump(mode="json") if related_diag else None,
            "ai_suggestion": suggestion,
        })
    return result


@router.post("/approve/{command_id}")
def approve_command(
    command_id: int,
    confirmation_code: str = Query(default=""),
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_APPROVE)),
):
    return command_control_service.approve(
        command_id,
        actor=actor,
        confirmation_code=confirmation_code,
    )


@router.post("/reject/{command_id}")
def reject_command(command_id: int, reason: str = Query(default=""), actor: ActorInfo = Depends(require_permission(PERM_COMMAND_REJECT))):
    return command_control_service.reject(command_id, actor=actor, reason=reason)


@router.post("/commands/{command_id}/cancel")
def cancel_command(
    command_id: int,
    reason: str = Query(default=""),
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_REJECT)),
):
    return command_control_service.cancel(command_id, actor=actor, reason=reason)


@router.post("/commands/{command_id}/retry")
def retry_command(
    command_id: int,
    confirmation_code: str = Query(default=""),
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
):
    return command_control_service.retry(
        command_id,
        actor=actor,
        confirmation_code=confirmation_code,
    )


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
def escalate(
    node_code: str,
    issue_type: str,
    description: str,
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
):
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
        actor_id=actor_identity(actor),
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

    result = execute_plan(plan, actor_identity(actor), decision)
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
