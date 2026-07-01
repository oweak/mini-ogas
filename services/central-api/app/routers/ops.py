from fastapi import APIRouter, Depends, Query

from ..core.security import (
    PERM_COMMAND_APPROVE,
    PERM_COMMAND_REJECT,
    PERM_COMMAND_ISSUE,
    ActorInfo,
    require_permission,
)
from ..models import ControlCommandRequest, ControlCommandResponse
from ..store import store
from .control import execute_plan, plan_command

router = APIRouter(prefix="/ops", tags=["ops"])


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


@router.get("/escalations")
def list_escalations():
    rows = []
    for event in store.pending_escalations():
        alert = next(
            (
                item for item in reversed(store.alerts)
                if item.node_code == event.node_code
                and item.status not in {"closed", "resolved"}
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
def issue_command(payload: ControlCommandRequest, actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE))) -> ControlCommandResponse:
    plan, used_deepseek = plan_command(payload.text)
    if not payload.execute:
        return ControlCommandResponse(
            accepted=True,
            executed=False,
            used_deepseek=used_deepseek,
            status="planned",
            plan=plan,
            result=None,
            message="命令已解析但未执行。确认后可再次提交 execute=true。",
        )
    if plan.requires_confirmation and payload.confirm != "CONFIRM":
        return ControlCommandResponse(
            accepted=True,
            executed=False,
            used_deepseek=used_deepseek,
            status="blocked-confirmation-required",
            plan=plan,
            result=None,
            message="高风险命令需要确认码 CONFIRM。",
        )
    result = execute_plan(plan, actor.role)
    return ControlCommandResponse(
        accepted=True,
        executed=True,
        used_deepseek=used_deepseek,
        status="executed",
        plan=plan,
        result=result,
        message="命令已通过运维操作网关转发执行。",
    )
