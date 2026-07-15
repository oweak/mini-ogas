from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..core.config import settings
from ..core.security import PERM_SIMULATION_CONTROL, ActorInfo, require_permission
from ..models import DemoScenario, IncidentEvent, Alert, utc_now
from ..rules import evaluate_snapshot_rules
from ..safety_governor import safety_governor
from ..store import store, product_name

router = APIRouter(tags=["demo"])


@router.post("/demo/scenario")
def apply_demo_scenario(
    payload: DemoScenario,
    actor: ActorInfo = Depends(require_permission(PERM_SIMULATION_CONTROL)),
):
    if settings.app_env == "production" or not settings.demo_seed_enabled:
        raise HTTPException(
            status_code=409,
            detail={"code": "demo_disabled", "message": "Demo scenarios are disabled in this environment."},
        )
    action = "simulate_hostile_attack" if payload.scenario == "hostile_attack" else f"simulate_{payload.scenario}"
    target = "turning-workshop-01" if payload.scenario == "hostile_attack" else ""
    decision = safety_governor.review_control_action(
        action=action,
        target_node=target,
        risk_level="high" if payload.scenario == "hostile_attack" else "low",
        actor_role=actor.role,
        known_nodes=set(store.nodes),
        confirmation_code=payload.confirmation_code,
    )
    store.record_safety_decision(decision)
    if not decision.allow:
        raise HTTPException(
            status_code=409,
            detail={"error": decision.reason_code, "safety": decision.model_dump(mode="json")},
        )
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
        "run_id": alert.run_id,
    }


def _event_to_log(event: IncidentEvent) -> str:
    ts = event.created_at.strftime("%H:%M:%S") if event.created_at else ""
    return f"{ts} [{event.severity.value.upper()}] {event.node_code}: {event.message}"


def _enrich_node(node, store) -> dict:
    """Attach production, metrics, alarms, and sync data to a node dict."""
    data = node.model_dump(mode="json")
    heartbeat_v2 = store.node_heartbeats_v2.get(node.node_code, {})
    heartbeat_production = heartbeat_v2.get("production") if isinstance(heartbeat_v2.get("production"), dict) else {}
    heartbeat_metrics = heartbeat_v2.get("metrics") if isinstance(heartbeat_v2.get("metrics"), dict) else {}

    # Latest metrics snapshot
    lm = store.latest_metrics().get(node.node_code)
    data["metrics"] = heartbeat_metrics or (lm.model_dump(mode="json") if lm else None)

    # Production data derived from machines + dispatch tasks
    node_machines = [m for m in store.machines if m.node_code == node.node_code]
    first_machine = node_machines[0] if node_machines else None

    # Find an active dispatch task for this node
    active_task = None
    for t in store.dispatch_tasks:
        if t.assigned_node == node.node_code and t.status in ("scheduled", "queued", "in_progress"):
            active_task = t
            break

    active_order = (
        active_task.product_code if active_task
        else (store.production_plans[0].product_code if store.production_plans else None)
    )

    production = {
        "workshop_type": node.workshop_type,
        "machine_code": first_machine.machine_code if first_machine else node.node_code,
        "active_order": active_order,
        "dispatch_policy": "FIFO",
        "finished_quantity": lm.finished_quantity if lm else 0,
        "defect_quantity": lm.defect_quantity if lm else 0,
        "tool_wear_level": first_machine.tool_wear_level if first_machine else 0,
    }
    reported_production = {**production, **heartbeat_production}
    data["production"] = store.part_queue_flow_projection(node.node_code, reported_production)
    runtime = heartbeat_v2.get("runtime")
    if isinstance(runtime, dict):
        data["runtime"] = runtime
        data["deployment_mode"] = runtime.get("deployment_mode", "unknown")
        data["simulation_mode"] = runtime.get("simulation_mode", "unknown")

    # Recent alarms scoped to this node
    data["alarms"] = [
        a.model_dump(mode="json")
        for a in store.alerts
        if (
            a.node_code == node.node_code
            and a.status not in {"closed", "resolved"}
            and store.alert_in_current_run(a)
        )
    ][-5:]

    # Sync status (Node model has no sync field; backends signal online via heartbeat)
    heartbeat_sync = heartbeat_v2.get("sync") if isinstance(heartbeat_v2.get("sync"), dict) else {}
    data["sync"] = {"pending_records": int(heartbeat_sync.get("pending_records") or 0)}
    data["received_at"] = heartbeat_v2.get("_received_at")

    return data


def _build_work_orders(store) -> list[dict]:
    """Build frontend-compatible work orders from production plans and allocation orders."""
    if store.dispatch_tasks:
        return [
            {
                "id": f"DT-{task.id}",
                "product": task.product_name,
                "route": task.route,
                "priority": f"P{min(3, max(1, task.priority // 3 + 1))}",
                "quantity": task.quantity,
                "completed": None,
                "due": None,
                "assigned_node": task.assigned_node,
                "assigned_machine": task.assigned_machine,
                "status": task.status,
                "reason": task.reason,
            }
            for task in store.dispatch_tasks
        ]

    orders: list[dict] = []
    for plan in store.production_plans:
        orders.append({
            "id": plan.product_code,
            "product": product_name(plan.product_code),
            "route": plan.route,
            "priority": f"P{min(3, max(1, plan.priority // 3 + 1))}",
            "quantity": plan.target_quantity,
            "completed": None,
            "due": None,
            "status": "scheduled",
        })
    for ao in store.allocation_orders[-20:]:
        orders.append({
            "id": ao.order_id,
            "product": ao.product_name,
            "route": [],
            "priority": f"P{min(3, max(1, ao.priority // 3 + 1))}",
            "quantity": ao.required_quantity,
            "completed": None,
            "due": None,
            "status": "in_progress",
        })
    return orders


def _safe_number(value, default=0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _snapshot_data_source(nodes: list[dict]) -> str:
    if not nodes:
        return "fallback"
    runtime_sources: set[str] = set()
    for node in nodes:
        runtime = node.get("runtime")
        if not isinstance(runtime, dict) or not runtime:
            continue
        source = str(runtime.get("runtime_source") or "").strip().lower()
        engine = str(runtime.get("simulation_engine") or "").strip().lower()
        deployment = str(runtime.get("deployment_mode") or "").strip().lower()
        if source == "fixture":
            runtime_sources.add("fixture")
        elif source == "replay":
            runtime_sources.add("replay")
        elif source == "simulated" or engine in {"simple", "simpy"}:
            runtime_sources.add("simulated")
        elif source == "live" or engine == "physical" or deployment == "physical":
            runtime_sources.add("live")
        elif source == "fallback":
            runtime_sources.add("fallback")
    if not runtime_sources:
        return "fallback"
    if len(runtime_sources) == 1:
        return next(iter(runtime_sources))
    return "mixed"


def _snapshot_run(nodes: list[dict]) -> dict:
    runtime_candidates: list[dict] = []
    for node in nodes:
        runtime = node.get("runtime")
        if not isinstance(runtime, dict):
            continue
        if runtime.get("run_id") or runtime.get("scenario_id") or runtime.get("simulation_time"):
            runtime_candidates.append(runtime)
    if runtime_candidates:
        runtime = next(
            (candidate for candidate in runtime_candidates if candidate.get("simulation_engine") == "simpy"),
            runtime_candidates[0],
        )
        return {
            "run_id": runtime.get("run_id") or "RUN-UNKNOWN",
            "scenario_id": runtime.get("scenario_id") or "SCN-UNKNOWN",
            "simulation_time": runtime.get("simulation_time"),
            "simulation_speed": runtime.get("simulation_speed") or 1,
            "simulation_engine": runtime.get("simulation_engine") or "simple",
        }
    return {
        "run_id": "RUN-FALLBACK",
        "scenario_id": "SCN-FALLBACK",
        "simulation_time": utc_now().isoformat(),
        "simulation_speed": 1,
        "simulation_engine": "simple",
    }


def _snapshot_node(node: dict) -> dict:
    production = node.get("production") if isinstance(node.get("production"), dict) else {}
    metrics = node.get("metrics") if isinstance(node.get("metrics"), dict) else {}
    runtime = node.get("runtime") if isinstance(node.get("runtime"), dict) else {}
    alarms = node.get("alarms") if isinstance(node.get("alarms"), list) else []
    active_order = production.get("active_order")
    finished_quantity = _safe_int(production.get("finished_quantity"), _safe_int(metrics.get("finished_quantity")))
    defect_quantity = _safe_int(production.get("defect_quantity"), _safe_int(metrics.get("defect_quantity")))
    return {
        "node_code": node.get("node_code"),
        "node_name": node.get("node_name"),
        "status": node.get("status"),
        "workshop_type": node.get("workshop_type") or production.get("workshop_type"),
        "machine_code": production.get("machine_code") or node.get("node_code"),
        "active_order": active_order,
        "runtime_source": runtime.get("runtime_source") or _snapshot_data_source([node]),
        "runtime": runtime,
        "deployment_mode": runtime.get("deployment_mode") or node.get("deployment_mode") or "unknown",
        "simulation_mode": runtime.get("simulation_mode") or node.get("simulation_mode") or "unknown",
        "last_heartbeat": node.get("last_heartbeat"),
        "received_at": node.get("received_at"),
        "production": {
            "finished_quantity": finished_quantity,
            "raw_finished_quantity": _safe_int(
                production.get("raw_finished_quantity"),
                finished_quantity,
            ),
            "defect_quantity": defect_quantity,
            "wip_input": _safe_int(production.get("wip_input")),
            "wip_output": _safe_int(production.get("wip_output")),
            "reported_wip_input": _safe_int(production.get("reported_wip_input")),
            "reported_wip_output": _safe_int(production.get("reported_wip_output")),
            "wip_source": production.get("wip_source") or "heartbeat",
            "flow_run_id": production.get("flow_run_id") or "",
            "milling_queue_depth": _safe_int(production.get("milling_queue_depth")),
            "grinding_queue_depth": _safe_int(production.get("grinding_queue_depth")),
            "finished_goods_buffer": _safe_int(production.get("finished_goods_buffer")),
            "target_rate": _safe_number(production.get("target_rate")),
            "actual_rate": _safe_number(production.get("actual_rate")),
            "utilization": _safe_number(production.get("utilization")),
            "defect_rate": _safe_number(production.get("defect_rate")),
            "defect_rate_delta": _safe_number(production.get("defect_rate_delta")),
            "tool_wear_level": _safe_number(production.get("tool_wear_level")),
            "machine_count": _safe_int(production.get("machine_count")),
            "process_time_sec": _safe_int(production.get("process_time_sec")),
            "nominal_capacity_per_hour": _safe_number(production.get("nominal_capacity_per_hour")),
            "target_rate_per_hour": _safe_number(production.get("target_rate_per_hour")),
            "actual_rate_per_hour": _safe_number(production.get("actual_rate_per_hour")),
            "rate_unit": production.get("rate_unit") or "parts_per_minute",
        },
        "metrics": metrics,
        "sync": node.get("sync") or {"pending_records": 0},
        "alarms": alarms,
    }


def _snapshot_alert(issue: dict) -> dict:
    return {
        "id": issue.get("id"),
        "severity": issue.get("severity"),
        "title": issue.get("title"),
        "detail": issue.get("detail"),
        "status": issue.get("status"),
        "actions": issue.get("actions", []),
        "run_id": issue.get("run_id", ""),
    }


def _snapshot_dispatch_plan(work_orders: list[dict]) -> dict:
    blocked = [order for order in work_orders if order.get("status") == "blocked"]
    rerouted = [order for order in work_orders if order.get("status") in {"approved", "approved_executed"}]
    status = "waiting_approval" if blocked else "no_action"
    if rerouted and not blocked:
        status = "approved_executed"
    summary = (
        f"{len(blocked)} blocked dispatch tasks require supervisor approval."
        if blocked else
        "Current dispatch plan has no blocking constraint."
    )
    source = blocked[0] if blocked else (rerouted[0] if rerouted else (work_orders[0] if work_orders else {}))
    return {
        "id": "DP-CURRENT",
        "status": status,
        "summary": summary,
        "source_order": str(source.get("id", "")),
        "from_node": str(source.get("assigned_node") or source.get("assigned_machine") or "current-route"),
        "to_node": "available-capacity" if blocked else str(source.get("assigned_node") or "current-route"),
        "risk": "medium" if blocked else "low",
        "steps": [
            "Review blocked dispatch tasks.",
            "Approve supervisor reroute with confirmation code.",
            "Archive the result in the audit log.",
        ] if blocked else ["Keep the current dispatch route."],
        "confirmation_code_hint": "CONFIRM" if blocked else "",
        "result": "Supervisor approval is required." if blocked else "No dispatch approval is waiting.",
        "work_order_count": len(work_orders),
        "blocked_count": len(blocked),
    }


def _apply_rule_demo_mode(mode: str, nodes: list[dict]) -> list[dict]:
    if mode not in {"milling_bottleneck", "grinding_starvation"}:
        return nodes
    adjusted: list[dict] = []
    for node in nodes:
        item = {**node}
        production = dict(item.get("production") or {})
        if mode == "milling_bottleneck" and item.get("node_code") == "milling-workshop-01":
            item["status"] = "warning"
            production.update({
                "wip_input": 22,
                "wip_output": 6,
                "target_rate": 1.0,
                "actual_rate": 0.52,
                "utilization": 0.88,
            })
        if mode == "grinding_starvation" and item.get("node_code") == "grinding-workshop-01":
            item["status"] = "warning"
            production.update({
                "wip_input": 0,
                "wip_output": 0,
                "target_rate": 0.8,
                "actual_rate": 0.08,
                "utilization": 0.18,
            })
        item["production"] = production
        adjusted.append(item)
    return adjusted


def _build_dashboard_snapshot(mode: str = "normal") -> dict:
    if mode != "normal" and (settings.app_env == "production" or not settings.demo_seed_enabled):
        raise HTTPException(
            status_code=409,
            detail={"code": "demo_disabled", "message": "Dashboard demo overlays are disabled."},
        )
    projection = store.refresh_primary_projection()
    state = _build_legacy_dashboard_state(mode)
    expected_node_codes = set(settings.expected_production_nodes)
    nodes = [
        node for node in state.get("nodes", [])
        if str(node.get("node_code", "")) in expected_node_codes
    ]
    node_codes = {str(node.get("node_code")) for node in nodes}
    work_orders = state.get("work_orders", [])
    connected = sum(1 for node in nodes if node.get("status") not in {"offline", "isolated"})
    try:
        from .compat import _ai_runtime
        ai_runtime = _ai_runtime()
    except Exception:
        ai_runtime = {"status": "unknown", "provider": "unknown", "model": "unknown"}
    snapshot_nodes = _apply_rule_demo_mode(mode, [_snapshot_node(node) for node in nodes])
    snapshot_run = _snapshot_run(nodes)
    data_source = "fixture" if mode != "normal" else _snapshot_data_source(nodes)
    active_run_id = str(snapshot_run.get("run_id") or "")
    current_notifications = _current_run_notifications(state.get("notifications", []), active_run_id)
    snapshot = {
        "schema_version": "2.2",
        "generated_at": utc_now().isoformat(),
        "data_source": data_source,
        "presentation_mode": mode,
        "run": snapshot_run,
        "system": {
            "status": "ok" if connected == len(expected_node_codes) and nodes else "degraded",
            "nodes_connected": connected,
            "nodes_expected": len(expected_node_codes),
            "logical_nodes_registered": len(state.get("nodes", [])),
            "ai_runtime": ai_runtime,
            "persistence": projection,
            "environment": settings.environment_status(),
            "data_provenance": {
                "node_telemetry": {
                    "source": data_source,
                    "authority": "edge-heartbeat",
                },
                "machine_and_work_order_context": {
                    "source": "mixed",
                    "authority": "postgresql-shadow-and-demo-seed",
                },
                "market_and_inventory": {
                    "source": "demo-seed",
                    "authority": "central-memory-store",
                },
                "device_connection": {
                    "source": "none",
                    "write_enabled": settings.physical_write_enabled,
                },
            },
        },
        "nodes": snapshot_nodes,
        "work_orders": work_orders,
        "part_queue": store.part_queue_snapshot(),
        "alerts": [
            _snapshot_alert(issue)
            for issue in state.get("issues", [])
            if any(node_code and node_code in str(issue.get("title", "")) for node_code in node_codes)
        ],
        "notifications": current_notifications,
        "dispatch_plan": _snapshot_dispatch_plan(work_orders),
        "commands": [command.model_dump(mode="json") for command in store.commands[-20:]],
        "pending_commands": [
            command.model_dump(mode="json")
            for command in store.commands
            if command.status in {"pending", "queued", "claimed", "applied"}
        ],
        "pending_approvals": [
            command.model_dump(mode="json")
            for command in store.commands
            if command.status == "waiting_approval"
        ],
        "audit": {
            "recent_events": [
                event.model_dump(mode="json")
                for event in store.incident_events[-20:]
            ],
        },
        "timeline": {
            "recent_logs": state.get("logs", [])[-20:],
        },
    }
    snapshot["rule_conclusions"] = evaluate_snapshot_rules(snapshot)
    return snapshot


def _current_run_notifications(notifications: list[dict], active_run_id: str) -> list[dict]:
    """Keep result acknowledgements in the live run; history remains available via audit/replay."""
    return [
        notification
        for notification in notifications
        if not active_run_id or str(notification.get("run_id") or "") == active_run_id
    ]


def _build_legacy_dashboard_state(mode: str = "normal") -> dict:
    alerts = [
        alert
        for alert in store.alerts
        if alert.status not in {"closed", "resolved"} and store.alert_in_current_run(alert)
    ][-10:]
    issues = [_alert_to_issue(a) for a in alerts if a.handled_by != "system"]

    events = store.incident_events[-30:]
    logs = [_event_to_log(e) for e in events]
    acknowledged_notifications = {
        token
        for event in store.incident_events
        if event.stage == "notification-acknowledged"
        for token in event.message.split()
        if token.startswith("HUMAN-")
    }
    notifications = [
        {
            "id": f"HUMAN-{event.id}",
            "source_node": event.node_code,
            "severity": event.severity.value,
            "title": "人工处置完成",
            "detail": event.message,
            "message": event.message,
            "actions": ["关闭结果通知"],
            "status": "unacknowledged",
            "run_id": event.run_id,
        }
        for event in events
        if event.stage == "human-escalation" and f"HUMAN-{event.id}" not in acknowledged_notifications
    ]

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
        "notifications": notifications,
        "logs": logs,
        "nodes": [_enrich_node(n, store) for n in store.nodes.values()],
        "work_orders": _build_work_orders(store),
    }


def _dashboard_state_from_snapshot(snapshot: dict) -> dict:
    """Legacy dashboard-state wrapper backed by the v2.2 snapshot contract."""
    timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), dict) else {}
    return {
        "issues": snapshot.get("alerts", []),
        "notifications": snapshot.get("notifications", []),
        "logs": timeline.get("recent_logs", []),
        "nodes": snapshot.get("nodes", []),
        "work_orders": snapshot.get("work_orders", []),
        "dispatch_plan": snapshot.get("dispatch_plan"),
        "snapshot": snapshot,
    }


@router.get("/dashboard-state")
def get_dashboard_state(response: Response, mode: str = Query("normal")):
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</dashboard/snapshot>; rel="successor-version"'
    return _dashboard_state_from_snapshot(_build_dashboard_snapshot(mode))


@router.get("/dashboard/snapshot")
def get_dashboard_snapshot(mode: str = Query("normal")):
    return _build_dashboard_snapshot(mode)


@router.get("/rules/conclusions")
def get_rule_conclusions(mode: str = Query("normal")):
    snapshot = _build_dashboard_snapshot(mode)
    return {
        "schema_version": "2.2",
        "generated_at": snapshot["generated_at"],
        "data_source": snapshot["data_source"],
        "run": snapshot["run"],
        "conclusions": snapshot["rule_conclusions"],
    }
