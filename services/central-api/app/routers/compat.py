"""
Compatibility routes for Codex dashboard frontend.

These routes bridge the Codex frontend's expected API paths to the
existing backend store methods.  The security middleware strips /api/
prefix from incoming requests, so all routes here are defined *without*
/api/.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.ai.registry import registry
from ..core.ai.vault import runtime_status, unlock_ai_runtime, vault_present
from ..core.auth import authenticate_user, issue_access_token
from ..core.config import settings
from ..core.security import (
    PERM_AI_DIAGNOSE,
    PERM_COMMAND_APPROVE,
    PERM_COMMAND_ISSUE,
    PERM_COMMAND_REJECT,
    ActorInfo,
    require_permission,
)
from ..models import AiDiagnoseRequest, AuditLog, ControlCommandRequest, Severity
from ..safety_governor import safety_governor
from ..store import store

router = APIRouter(tags=["compat"])


# ---------------------------------------------------------------------------
# Request body models for compat endpoints
# ---------------------------------------------------------------------------

class _LoginBody(BaseModel):
    operator: str = "车间主管"
    password: str = ""


class _ActorPayload(BaseModel):
    actor: str = "车间主管"
    operator: str = "车间主管"
    confirmation_code: str = ""


class _ConfirmAlertBody(BaseModel):
    action: str = "确认真实报警"
    operator: str = "车间主管"


class _IssueActionBody(BaseModel):
    action: str = "验证完成并关闭问题"
    operator: str = "车间主管"


class _IssueDecisionBody(BaseModel):
    decision: str = "observe"  # 'observe' | 'ignore'
    operator: str = "车间主管"
    note: str = ""


class _EscalationDecisionBody(BaseModel):
    actor: str = "车间主管"
    decision: str = "approve"  # 'approve' | 'reject'
    confirmation_code: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ai_runtime() -> dict:
    """Return verified AI provenance without treating configuration as a call."""
    return runtime_status(verified_provider=registry.verified_provider())


def _parse_issue_id(issue_id: str) -> tuple[str, str]:
    """Split a Codex issue_id like 'milling-workshop-01-SPINDLE_TEMP_HIGH'
    into (node_code, alert_type)."""
    parts = issue_id.split("-")
    node_end = 0
    for index, part in enumerate(parts):
        if part.isdigit() and len(part) <= 3:
            node_end = index + 1
            break
    if node_end == 0:
        for index, part in enumerate(parts):
            if part == part.upper() and len(part) > 2 and not part.isdigit():
                node_end = index
                break
    if node_end <= 0 or node_end >= len(parts):
        node_end = min(3, max(1, len(parts) - 1))
    node_code = "-".join(parts[:node_end])
    alert_type = "-".join(parts[node_end:])
    return node_code, alert_type


def _find_alert(issue_id: str):
    """Find an alert by matching issue_id = f'{node_code}-{alert_type}'."""
    node_code, alert_type = _parse_issue_id(issue_id)
    for a in store.alerts:
        if a.node_code == node_code and a.alert_type == alert_type:
            return a
    return None


def _make_audit_event(action: str, message: str, severity: str = "info",
                      node_code: str = "central-api", actor: str = "系统",
                      resource_type: str = "issue", resource_id: str = "",
                      result: str = "success", extra: Optional[dict] = None) -> dict:
    """Build an audit event dict matching the unified events format."""
    from datetime import datetime, timezone
    import hashlib
    raw = f"{action}-{message}-{datetime.now(timezone.utc).isoformat()}"
    eid = f"audit-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
    return {
        "id": eid,
        "source_type": "audit_log",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node_code": node_code,
        "actor": actor,
        "severity": severity,
        "action": action,
        "message": message,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "result": result,
        "detail": extra or {},
    }


def _dispatch_payload(status_override: str | None = None, result: str | None = None) -> dict[str, object]:
    from .demo import _build_work_orders, _snapshot_dispatch_plan

    work_orders = _build_work_orders(store)
    dispatch_plan = _snapshot_dispatch_plan(work_orders)
    if status_override:
        dispatch_plan["status"] = status_override
    if result:
        dispatch_plan["result"] = result
    return {"dispatch_plan": dispatch_plan, "work_orders": work_orders}


def _approve_waiting_dispatch_tasks(actor: str) -> int:
    approved = 0
    for task in store.dispatch_tasks:
        if task.status != "blocked":
            continue
        process = task.route[0] if task.route else ""
        machine = store._available_machine_for(process) if process else None
        if machine is not None:
            task.assigned_node = machine.node_code
            task.assigned_machine = machine.machine_code
            task.status = "scheduled"
            task.reason = f"Approved reroute by {actor}; assigned to {machine.machine_code}."
        else:
            task.assigned_node = "manual-capacity-review"
            task.assigned_machine = "manual-review"
            task.status = "queued"
            task.reason = f"Approved by {actor}; queued for manual capacity recovery."
        approved += 1
    return approved


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.get("/auth/status")
def auth_status():
    """Return AI runtime status — used by Codex frontend on mount."""
    return {"runtime": _ai_runtime()}


@router.post("/auth/login")
def login(payload: _LoginBody):
    """Codex login — accepts {operator, password}, returns token + ai_smoke."""
    user = authenticate_user(payload.operator, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="密码错误")

    vault_error = ""
    if settings.ai_enabled and vault_present():
        try:
            unlock_ai_runtime(payload.password)
        except ValueError as exc:
            vault_error = str(exc)

    ai_smoke: dict = {"ok": False, "detail": "not_configured", "source": "rule_fallback"}
    if settings.ai_enabled and registry.is_any_live_provider():
        _, provider, errors = registry.chat_with_provenance(
            [
                {"role": "system", "content": "You are a Mini-OGAS connectivity probe."},
                {"role": "user", "content": "Reply with exactly: OK"},
            ],
            timeout=max(10, min(settings.ai_timeout_seconds, 60)),
        )
        if provider != "rule_fallback":
            ai_smoke = {
                "ok": True,
                "detail": "live provider call completed",
                "source": "api",
                "provider": provider,
                "model": settings.deepseek_model,
            }
        else:
            ai_smoke = {
                "ok": False,
                "detail": "all live providers failed; rule fallback returned",
                "source": "rule_fallback",
                "status": "api_error",
                "error": "; ".join(errors) or "no live provider response",
            }
    elif vault_error:
        ai_smoke = {
            "ok": False,
            "detail": "vault_unlock_failed",
            "source": "rule_fallback",
            "status": "vault_locked",
            "error": vault_error,
        }
    runtime = _ai_runtime()
    return {
        "ok": True,
        "role": user["roles"][0] if user["roles"] else "viewer",
        "operator": user["display_name"],
        "message": "验证通过，欢迎进入 Mini-OGAS 控制台",
        "access_token": issue_access_token(user),
        "token_type": "bearer",
        "runtime": runtime,
        "preflight": None,
        "ai_smoke": ai_smoke,
    }


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

@router.get("/system/preflight")
def system_preflight():
    """Enhanced preflight — returns checks[] format Codex expects."""
    result = store.run_preflight()
    runtime = _ai_runtime()

    checks = []
    for step in result.steps:
        status = "ok" if step.status == "pass" else ("error" if step.status == "fail" else "checking")
        checks.append({
            "id": step.key,
            "label": step.label,
            "status": status,
            "detail": step.detail,
        })

    return {
        "ok": result.all_pass,
        "status": "ok" if result.all_pass else "warning",
        "checks": checks,
        "nodes": [n.model_dump(mode="json") for n in store.nodes.values()],
        "ai_runtime": runtime,
    }


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@router.get("/audit/events")
def audit_events(
    source_type: str = Query(default=""),
    node_code: str = Query(default=""),
    severity: str = Query(default=""),
    actor: str = Query(default=""),
    action: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    search: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    """Alias for /events."""
    from .audit import list_unified_events
    return list_unified_events(
        source_type=source_type,
        node_code=node_code,
        severity=severity,
        actor=actor,
        action=action,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/audit/diagnoses")
def audit_diagnoses():
    """Alias for /diagnoses."""
    return store.ai_diagnoses


# ---------------------------------------------------------------------------
# Dispatch plan
# ---------------------------------------------------------------------------

@router.post("/ops/dispatch-plan/recalculate")
def recalculate_dispatch_plan():
    """Alias for /dispatch/rebuild."""
    store.generate_production_plan()
    tasks = store.rebuild_dispatch()
    blocked = sum(1 for t in tasks if t.status == "blocked")
    payload = _dispatch_payload()
    return {
        "ok": True,
        "accepted": True,
        "total": len(tasks),
        "dispatched": len(tasks) - blocked,
        "blocked": blocked,
        **payload,
    }


@router.post("/ops/dispatch-plan/approve")
def approve_dispatch_plan(payload: _ActorPayload,
                          actor: ActorInfo = Depends(require_permission(PERM_COMMAND_APPROVE))):
    """Approve a dispatch plan and return the updated dashboard contract."""
    safety = safety_governor.review_manual_approval(
        action="dispatch_plan_approve",
        actor_role=actor.role,
        confirmation_code=payload.confirmation_code,
    )
    if not safety.allow:
        current = _dispatch_payload()
        return {
            "ok": False,
            "accepted": False,
            "executed": False,
            "status": "confirmation_required",
            "message": safety.message,
            "safety": safety.model_dump(mode="json"),
            **current,
        }
    if not store.dispatch_tasks:
        store.rebuild_dispatch()
    waiting = sum(1 for task in store.dispatch_tasks if task.status == "blocked")
    if waiting == 0:
        current = _dispatch_payload()
        return {
            "ok": False,
            "accepted": False,
            "executed": False,
            "status": "dispatch_plan_not_waiting_approval",
            "message": "No blocked dispatch task is waiting for approval.",
            **current,
        }
    approved = _approve_waiting_dispatch_tasks(payload.actor)
    store.persist_dispatch_task_shadow()
    store.add_event(
        node_code="central-api",
        stage="dispatch-approved",
        severity=Severity.info,
        message=f"Dispatch plan approved by {payload.actor}; {approved} blocked task(s) rerouted.",
    )
    store.audit_logs.append(AuditLog(
        id=len(store.audit_logs) + 1,
        actor=payload.actor,
        action="dispatch:approve",
        resource_type="dispatch_plan",
        resource_id="current",
        result="success",
    ))
    result = f"Approved and rerouted {approved} blocked dispatch task(s)."
    updated = _dispatch_payload(status_override="approved_executed", result=result)
    return {
        "ok": True,
        "accepted": True,
        "executed": True,
        "status": "approved_executed",
        "message": result,
        "safety": safety.model_dump(mode="json"),
        **updated,
        "audit_event": _make_audit_event(
            action="dispatch:approve",
            message=result,
            actor=payload.actor,
            resource_type="dispatch_plan",
            resource_id="current",
            result="success",
            extra={"approved_tasks": approved},
        ),
    }


@router.post("/ops/dispatch-plan/approve-legacy")
def approve_dispatch_plan_legacy(payload: _ActorPayload,
                                 actor: ActorInfo = Depends(require_permission(PERM_COMMAND_APPROVE))):
    """Approve a dispatch plan — creates audit event and returns success."""
    store.add_event(
        node_code="central-api",
        stage="dispatch-approved",
        severity=Severity.info,
        message=f"排产计划已由 {payload.actor} 审批通过。确认码: {payload.confirmation_code}",
    )
    return {
        "ok": True,
        "accepted": True,
        "executed": False,
        "status": "approved",
        "plan": None,
        "message": "排产计划已审批通过。",
        "audit_event": _make_audit_event(
            action="dispatch:approve",
            message="排产计划审批通过",
            actor=payload.actor,
            resource_type="dispatch_plan",
            resource_id="current",
        ),
    }


# ---------------------------------------------------------------------------
# Alerts — confirm
# ---------------------------------------------------------------------------

@router.post("/alerts/{issue_id:path}/confirm")
def confirm_alert(issue_id: str, payload: _ConfirmAlertBody):
    """Confirm an alert as real.  issue_id = '{node_code}-{alert_type}'."""
    alert = _find_alert(issue_id)
    if alert is None:
        node_code, alert_type = _parse_issue_id(issue_id)
        alert = store.create_alert(
            node_code=node_code,
            alert_type=alert_type,
            severity=Severity.medium,
            description=f"Codex 前端确认报警：{alert_type}",
            handled_by=payload.operator,
        )
    alert.status = "confirmed"
    store.add_event(
        node_code=alert.node_code,
        stage="alert-confirmed",
        severity=alert.severity,
        message=f"报警已确认：{alert.alert_type}，操作员 {payload.operator} 已记录。",
    )
    return {
        "ok": True,
        "message": "报警已确认为真实事件",
        "alert_id": alert.id,
        "lifecycle": {
            "issue_id": issue_id,
            "status": alert.status,
            "handled_by": alert.handled_by,
        },
    }


# ---------------------------------------------------------------------------
# AI Diagnose via issue_id
# ---------------------------------------------------------------------------

@router.post("/ai/diagnose/{issue_id:path}")
def diagnose_by_issue_id(issue_id: str,
                         actor: ActorInfo = Depends(require_permission(PERM_AI_DIAGNOSE))):
    """Run AI diagnosis using an issue_id like 'milling-workshop-01-SPINDLE_TEMP_HIGH'."""
    node_code, alert_type = _parse_issue_id(issue_id)
    alert = _find_alert(issue_id)
    if alert is None:
        alert = store.create_alert(
            node_code=node_code,
            alert_type=alert_type,
            severity=Severity.medium,
            description=f"AI 诊断触发：{alert_type}",
            handled_by="ai",
        )

    from ..routers.ai import _rule_diagnosis

    used_deepseek = False
    try:
        if settings.ai_enabled and registry.is_any_live_provider():
            prompt = (
                f"车间节点: {node_code}\n"
                f"告警: {alert.description}\n"
                f"请判断根因、建议动作、置信度，以及是否需要隔离该车间节点。"
            )
            result = registry.diagnose(prompt)
            used_deepseek = True
        else:
            result = _rule_diagnosis(node_code)
    except Exception as exc:
        result = _rule_diagnosis(node_code, str(exc))

    diagnosis = store.add_ai_diagnosis(
        alert_id=alert.id,
        node_code=node_code,
        root_cause=result.root_cause,
        recommended_action=result.recommended_action,
        confidence=result.confidence,
        need_isolation=result.need_isolation,
        model_name=settings.deepseek_model if used_deepseek else "local-fallback",
        raw_response=result.raw_text,
    )
    alert.status = "diagnosed"
    requires_human = alert.severity in {Severity.high, Severity.critical} or bool(result.need_isolation)
    escalation = None
    if requires_human:
        matching_escalations = [
            event for event in store.pending_escalations()
            if event.node_code == node_code and f"{alert_type}:" in event.message
        ]
        already_pending = any(
            event.stage == "escalation"
            for event in matching_escalations
        )
        if not already_pending:
            store.escalate_to_human(node_code, alert_type, diagnosis.recommended_action)
        escalation = next(
            (
                event for event in reversed(store.pending_escalations())
                if event.node_code == node_code and f"{alert_type}:" in event.message
            ),
            None,
        )
    escalation_payload = None
    if escalation is not None:
        escalation_payload = escalation.model_dump(mode="json")
        escalation_payload["issue_id"] = issue_id
        escalation_payload["status"] = "waiting_human"
    return {
        "ok": True,
        "accepted": True,
        "used_deepseek": used_deepseek,
        "status": "ai-live" if used_deepseek else "local-fallback",
        "diagnosis": diagnosis.model_dump(mode="json"),
        "root_cause": diagnosis.root_cause,
        "recommended_action": diagnosis.recommended_action,
        "confidence": diagnosis.confidence,
        "need_isolation": diagnosis.need_isolation,
        "decision": {
            "requires_human": requires_human,
            "risk_level": "high" if requires_human else "low",
            "issue_id": issue_id,
        },
        "escalation": escalation_payload,
        "provider": "multi-backend",
        "model_name": diagnosis.model_name,
        "source": "api" if used_deepseek else "rule_fallback",
    }


# ---------------------------------------------------------------------------
# Issues — close / decide (observe / ignore)
# ---------------------------------------------------------------------------

@router.post("/issues/{issue_id:path}/actions")
def issue_actions(issue_id: str, payload: _IssueActionBody):
    """Close / act on an issue.  Returns an audit event."""
    alert = _find_alert(issue_id)
    action_text = payload.action
    operator = payload.operator
    if alert is not None:
        alert.status = "closed"
        alert.handled_by = operator
        store.add_event(
            node_code=alert.node_code,
            stage="issue-closed",
            severity=Severity.info,
            message=f"问题已关闭：{alert.alert_type}，操作员 {operator}。动作: {action_text}",
        )
    elif issue_id.startswith("HUMAN-"):
        store.add_event(
            node_code="central-api",
            stage="notification-acknowledged",
            severity=Severity.info,
            message=f"{issue_id} acknowledged by {operator}: {action_text}",
        )
    return {
        "ok": True,
        "message": f"问题已处理：{action_text}",
        "audit_event": _make_audit_event(
            action="issue:close",
            message=f"问题已处理：{action_text}",
            actor=operator,
            severity="info",
            node_code=alert.node_code if alert else "central-api",
            resource_type="issue",
            resource_id=issue_id,
            result="closed",
        ),
        "effect": {"issue_id": issue_id, "status": "closed",
                    "action": action_text, "operator": operator},
    }


@router.post("/issues/{issue_id:path}/decision")
def issue_decision(issue_id: str, payload: _IssueDecisionBody):
    """Decide to observe or ignore an issue.  Returns an audit event."""
    decision = payload.decision  # 'observe' | 'ignore'
    note = payload.note
    operator = payload.operator
    alert = _find_alert(issue_id)
    if alert is not None:
        new_status = "observing" if decision == "observe" else "closed"
        alert.status = new_status
        alert.handled_by = operator
        verb = "进入观察" if decision == "observe" else "按误报/无需处置关闭"
        store.add_event(
            node_code=alert.node_code,
            stage="issue-decision",
            severity=Severity.info,
            message=f"问题决策：{alert.alert_type} → {verb}。操作员: {operator}。备注: {note or '无'}",
        )
    return {
        "ok": True,
        "message": f"决策已记录：{'观察' if decision == 'observe' else '忽略'}",
        "decision": decision,
        "audit_event": _make_audit_event(
            action=f"issue:decide:{decision}",
            message=f"决策: {decision} / {note}",
            actor=operator,
            severity="info",
            node_code=alert.node_code if alert else "central-api",
            resource_type="issue",
            resource_id=issue_id,
            result=decision,
        ),
        "effect": {"issue_id": issue_id, "decision": decision,
                    "operator": operator},
    }


# ---------------------------------------------------------------------------
# Escalation decision
# ---------------------------------------------------------------------------

@router.post("/ops/escalations/{escalation_id:int}/decision")
def escalation_decision(escalation_id: int, payload: _EscalationDecisionBody,
                        actor: ActorInfo = Depends(require_permission(PERM_COMMAND_APPROVE))):
    """Approve or reject an escalation."""
    decision = payload.decision  # 'approve' | 'reject'
    confirmation_code = payload.confirmation_code
    operator = payload.actor

    escalation = None
    for e in store.incident_events:
        if e.id == escalation_id:
            escalation = e
            break

    closed_alerts: list[str] = []
    if decision == "approve":
        safety = safety_governor.review_manual_approval(
            action="escalation_approve",
            actor_role=actor.role,
            confirmation_code=confirmation_code,
        )
        if not safety.allow:
            return {
                "ok": False,
                "error": safety.reason_code,
                "status": "blocked",
                "safety": safety.model_dump(mode="json"),
            }
        msg = f"人工升级 #{escalation_id} 已批准。操作员: {operator}。确认码: {confirmation_code}"
        store.add_event(
            node_code=escalation.node_code if escalation else "central-api",
            stage="escalation-approved",
            severity=Severity.high,
            message=msg,
        )
        if escalation is not None:
            for alert in store.alerts:
                if (
                    alert.node_code == escalation.node_code
                    and alert.status not in {"closed", "resolved"}
                    and f"{alert.alert_type}:" in escalation.message
                ):
                    alert.status = "closed"
                    alert.handled_by = operator
                    closed_alerts.append(f"{alert.node_code}-{alert.alert_type}")
            store.add_event(
                node_code=escalation.node_code,
                stage="human-escalation",
                severity=Severity.info,
                message=f"Human approval closed {len(closed_alerts)} alert(s): {', '.join(closed_alerts)}",
            )
    else:
        msg = f"人工升级 #{escalation_id} 已驳回。操作员: {operator}。"
        store.add_event(
            node_code=escalation.node_code if escalation else "central-api",
            stage="escalation-rejected",
            severity=Severity.medium,
            message=msg,
        )

    return {
        "ok": True,
        "message": msg,
        "notification": {"detail": msg},
        "effect": {
            "escalation_id": escalation_id,
            "decision": decision,
            "operator": operator,
            "issue_id": closed_alerts[0] if closed_alerts else getattr(escalation, 'node_code', None),
            "verification": {
                "issue_closed": bool(closed_alerts) if decision == "approve" else False,
                "alarm_removed": bool(closed_alerts) if decision == "approve" else False,
                "closed_alerts": closed_alerts,
            },
        },
    }
