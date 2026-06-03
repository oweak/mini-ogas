from fastapi import APIRouter, HTTPException, Query

from ..models import DemoScenario, IncidentEvent, Alert
from ..store import store

router = APIRouter(tags=["demo"])


@router.post("/demo/scenario")
def apply_demo_scenario(payload: DemoScenario):
    try:
        return store.apply_scenario(payload.scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _alert_to_issue(alert: Alert) -> dict:
    severity_label = "高危" if alert.severity.value in ("critical",) else "高" if alert.severity.value in ("high",) else "预警"
    actions: list[str]
    if alert.severity.value in ("critical",):
        actions = ["打开 AI 应急引导", "派遣维修工人", "停机挂牌", "创建轴承检查工单"]
    elif alert.severity.value in ("high",):
        actions = ["检查同步通道", "重连消息总线", "保留本地缓存等待恢复"]
    else:
        actions = ["创建维护提醒", "降低进给速度", "派发更换工单"]
    return {
        "id": f"API-ALERT-{alert.id}",
        "severity": severity_label,
        "title": f"{alert.node_code} {alert.alert_type}",
        "detail": alert.description,
        "actions": actions,
        "status": alert.status or "unacknowledged",
    }


def _event_to_log(event: IncidentEvent) -> str:
    ts = event.created_at.strftime("%H:%M:%S") if event.created_at else ""
    return f"{ts} [{event.severity.value.upper()}] {event.node_code}: {event.message}"


@router.get("/dashboard-state")
def get_dashboard_state(mode: str = Query("normal")):
    alerts = store.alerts[-10:]
    issues = [_alert_to_issue(a) for a in alerts if a.handled_by != "system"]

    events = store.incident_events[-30:]
    logs = [_event_to_log(e) for e in events]

    # In emergency mode, inject a critical spindle temp issue if one isn't already present
    if mode == "emergency":
        has_spindle = any("spindle" in i["title"].lower() or "主轴" in i["title"] for i in issues)
        if not has_spindle:
            issues.insert(0, {
                "id": "ISSUE-SPINDLE-TEMP",
                "severity": "高危",
                "title": "MILL-02 主轴温度过高",
                "detail": "物理设备风险，建议派遣维修工人停机检修，并执行工单重排。",
                "actions": ["打开 AI 应急引导", "派遣维修工人", "停机挂牌", "创建轴承检查工单"],
                "status": "unacknowledged",
            })

    return {
        "issues": issues,
        "logs": logs,
        "nodes": [n.model_dump(mode="json") for n in store.nodes.values()],
    }
