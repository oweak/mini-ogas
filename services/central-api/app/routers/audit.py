from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

from ..models import AiDiagnosis, Alert, AuditLog, IncidentEvent, NodeCommand
from ..store import store

router = APIRouter(tags=["audit"])


@router.get("/alerts")
def list_alerts():
    return store.alerts


@router.get("/commands")
def list_commands():
    return store.commands


@router.get("/incident-events")
def list_incident_events():
    return store.incident_events


@router.get("/audit-logs")
def list_audit_logs():
    return store.audit_logs


@router.get("/diagnoses")
def list_diagnoses():
    return store.ai_diagnoses


# ---------------------------------------------------------------------------
# Unified event stream for log management
# ---------------------------------------------------------------------------

def _event_entry(
    eid: str,
    source_type: str,
    timestamp: datetime,
    node_code: str,
    actor: str,
    severity: str,
    action: str,
    message: str,
    resource_type: str = "",
    resource_id: str = "",
    result: str = "",
    detail: Optional[dict] = None,
) -> dict:
    return {
        "id": eid,
        "source_type": source_type,
        "timestamp": timestamp.isoformat(),
        "node_code": node_code,
        "actor": actor,
        "severity": severity,
        "action": action,
        "message": message,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "result": result,
        "detail": detail or {},
    }


def _collect_all_events() -> list[dict]:
    events: list[dict] = []

    for a in store.alerts:
        events.append(_event_entry(
            eid=f"alert-{a.id}",
            source_type="alert",
            timestamp=a.created_at,
            node_code=a.node_code,
            actor=a.handled_by or "system",
            severity=a.severity.value,
            action=f"alert:{a.alert_type}",
            message=a.description,
            resource_type="alert",
            resource_id=str(a.id),
            result=a.status,
            detail={"alert_type": a.alert_type, "status": a.status},
        ))

    for c in store.commands:
        events.append(_event_entry(
            eid=f"command-{c.id}",
            source_type="command",
            timestamp=c.created_at,
            node_code=c.node_code,
            actor=c.operator,
            severity=c.risk_level,
            action=f"command:{c.command_type}",
            message=f"命令 #{c.id}：{c.command_type}（{c.risk_level} 风险）→ {c.status}",
            resource_type="command",
            resource_id=str(c.id),
            result=c.status,
            detail={"command_type": c.command_type, "risk_level": c.risk_level},
        ))

    for e in store.incident_events:
        events.append(_event_entry(
            eid=f"event-{e.id}",
            source_type="incident_event",
            timestamp=e.created_at,
            node_code=e.node_code,
            actor="system",
            severity=e.severity.value,
            action=f"incident:{e.stage}",
            message=e.message,
            resource_type="incident_event",
            resource_id=str(e.id),
            detail={"stage": e.stage},
        ))

    for l in store.audit_logs:
        events.append(_event_entry(
            eid=f"audit-{l.id}",
            source_type="audit_log",
            timestamp=l.created_at,
            node_code=l.resource_id if l.resource_type == "node" else "central-api",
            actor=l.actor,
            severity="info",
            action=l.action,
            message=f"{l.actor} → {l.action}（{l.resource_type}/{l.resource_id}）→ {l.result}",
            resource_type=l.resource_type,
            resource_id=l.resource_id,
            result=l.result,
        ))

    for d in store.ai_diagnoses:
        events.append(_event_entry(
            eid=f"diagnosis-{d.id}",
            source_type="ai_diagnosis",
            timestamp=d.created_at,
            node_code=d.node_code,
            actor=f"AI:{d.model_name}",
            severity="medium",
            action="ai:diagnose",
            message=f"AI 诊断 #{d.id}：{d.root_cause[:120]} → {d.recommended_action[:120]}（置信度 {d.confidence:.0%}）",
            resource_type="ai_diagnosis",
            resource_id=str(d.id),
            result="needs_isolation" if d.need_isolation else "advisory",
            detail={
                "model_name": d.model_name,
                "confidence": d.confidence,
                "need_isolation": d.need_isolation,
                "alert_id": d.alert_id,
            },
        ))

    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events


@router.get("/events")
def list_unified_events(
    source_type: str = Query(
        default="",
        description="Comma-separated filter: alert,command,incident_event,audit_log,ai_diagnosis",
    ),
    node_code: str = Query(default="", description="Filter by node code"),
    severity: str = Query(default="", description="Comma-separated: info,low,medium,high,critical"),
    actor: str = Query(default="", description="Filter by actor substring"),
    action: str = Query(default="", description="Filter by action substring"),
    date_from: str = Query(default="", description="ISO datetime lower bound"),
    date_to: str = Query(default="", description="ISO datetime upper bound"),
    search: str = Query(default="", description="Free-text search in message"),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    """Return a unified, filterable stream of all audit-relevant events.

    Source types:
    - ``alert`` — alerts from rule/heartbeat evaluation
    - ``command`` — operator/AI commands issued to nodes
    - ``incident_event`` — lifecycle events (startup, isolation, ticks, etc.)
    - ``audit_log`` — operator action audit trail
    - ``ai_diagnosis`` — AI diagnosis records
    """
    all_events = _collect_all_events()

    types = set(t.strip() for t in source_type.split(",") if t.strip())
    if types:
        all_events = [e for e in all_events if e["source_type"] in types]

    if node_code:
        codes = set(c.strip() for c in node_code.split(",") if c.strip())
        all_events = [e for e in all_events if e["node_code"] in codes]

    if severity:
        sevs = set(s.strip().lower() for s in severity.split(",") if s.strip())
        all_events = [e for e in all_events if e["severity"].lower() in sevs]

    if actor:
        al = actor.strip().lower()
        all_events = [e for e in all_events if al in e["actor"].lower()]

    if action:
        ac = action.strip().lower()
        all_events = [e for e in all_events if ac in e["action"].lower()]

    if search:
        sq = search.strip().lower()
        all_events = [e for e in all_events if sq in e["message"].lower()]

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            if dt_from.tzinfo is None:
                dt_from = dt_from.replace(tzinfo=timezone.utc)
            all_events = [e for e in all_events if datetime.fromisoformat(e["timestamp"]) >= dt_from]
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            if dt_to.tzinfo is None:
                dt_to = dt_to.replace(tzinfo=timezone.utc)
            all_events = [e for e in all_events if datetime.fromisoformat(e["timestamp"]) <= dt_to]
        except ValueError:
            pass

    total = len(all_events)
    page = all_events[offset : offset + limit]
    return {"total": total, "limit": limit, "offset": offset, "events": page}
