"""
Compatibility routes for Codex dashboard frontend.

These routes bridge the Codex frontend's expected API paths to the
existing backend store methods.  The security middleware strips /api/
prefix from incoming requests, so all routes here are defined *without*
/api/.
"""

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.ai.registry import registry
from ..core.config import settings
from ..core.security import (
    PERM_AI_DIAGNOSE,
    PERM_COMMAND_APPROVE,
    PERM_COMMAND_ISSUE,
    PERM_COMMAND_REJECT,
    ActorInfo,
    require_permission,
)
from ..models import AiDiagnoseRequest, ControlCommandRequest, Severity
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
    """Return the AI runtime status payload Codex expects."""
    configured = registry.is_any_live_provider()
    active = registry.first_available()
    ai_enabled = settings.ai_enabled and configured
    return {
        "status": "live" if ai_enabled else "rule_fallback",
        "provider": active.name if active else "rule_fallback",
        "model": settings.deepseek_model,
        "source": "multi-backend" if configured else "rule_fallback",
        "vault_present": bool(settings.deepseek_api_key),
        "vault_unlocked": configured,
    }


def _parse_issue_id(issue_id: str) -> tuple[str, str]:
    """Split a Codex issue_id like 'milling-workshop-01-SPINDLE_TEMP_HIGH'
    into (node_code, alert_type)."""
    parts = issue_id.split("-")
    node_end = 0
    for i, p in enumerate(parts):
        if p.isdigit() and len(p) <= 3:
            node_end = i
            break
    if node_end == 0:
        for i, p in enumerate(parts):
            if p == p.upper() and len(p) > 2 and not p.isdigit():
                node_end = i
                break
        if node_end == 0:
            node_end = 2
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
    expected = settings.api_access_token
    if not payload.password or not secrets.compare_digest(payload.password, expected):
        raise HTTPException(status_code=401, detail="密码错误")

    runtime = _ai_runtime()
    ai_smoke: dict = {"ok": False, "detail": "not_configured"}

    if runtime["vault_unlocked"] and settings.ai_enabled:
        ai_smoke = {"ok": True, "detail": "deepseek-chat configured",
                     "model": settings.deepseek_model}

    return {
        "ok": True,
        "role": "system_admin",
        "message": "验证通过，欢迎进入 Mini-OGAS 控制台",
        "api_token": expected,
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
    tasks = store.rebuild_dispatch()
    blocked = sum(1 for t in tasks if t.status == "blocked")
    return {
        "accepted": True,
        "total": len(tasks),
        "dispatched": len(tasks) - blocked,
        "blocked": blocked,
    }


@router.post("/ops/dispatch-plan/approve")
def approve_dispatch_plan(payload: _ActorPayload,
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
    return {"ok": True, "message": "报警已确认为真实事件", "alert_id": alert.id}


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
    return {
        "accepted": True,
        "used_deepseek": used_deepseek,
        "status": "ai-live" if used_deepseek else "local-fallback",
        "diagnosis": diagnosis.model_dump(mode="json"),
        "root_cause": diagnosis.root_cause,
        "recommended_action": diagnosis.recommended_action,
        "confidence": diagnosis.confidence,
        "need_isolation": diagnosis.need_isolation,
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

    if decision == "approve":
        msg = f"人工升级 #{escalation_id} 已批准。操作员: {operator}。确认码: {confirmation_code}"
        store.add_event(
            node_code=escalation.node_code if escalation else "central-api",
            stage="escalation-approved",
            severity=Severity.high,
            message=msg,
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
            "issue_id": getattr(escalation, 'node_code', None),
        },
    }
