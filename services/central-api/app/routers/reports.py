from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from ..core.ai.vault import runtime_status
from ..store import store
from .demo import _build_dashboard_snapshot

router = APIRouter(tags=["reports"])


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _production_totals(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    finished = 0
    defects = 0
    utilizations: list[float] = []
    target_rates: list[float] = []
    actual_rates: list[float] = []

    for node in nodes:
        production = node.get("production") if isinstance(node.get("production"), dict) else {}
        finished += int(_number(production.get("finished_quantity")))
        defects += int(_number(production.get("defect_quantity")))
        if production.get("utilization") is not None:
            utilizations.append(_number(production.get("utilization")))
        if production.get("target_rate") is not None:
            target_rates.append(_number(production.get("target_rate")))
        if production.get("actual_rate") is not None:
            actual_rates.append(_number(production.get("actual_rate")))

    produced = finished + defects
    return {
        "finished_quantity": finished,
        "defect_quantity": defects,
        "defect_rate": round(defects / produced, 4) if produced else 0.0,
        "average_utilization": round(mean(utilizations), 4) if utilizations else 0.0,
        "average_target_rate": round(mean(target_rates), 4) if target_rates else 0.0,
        "average_actual_rate": round(mean(actual_rates), 4) if actual_rates else 0.0,
    }


def _dispatch_summary(dispatch_tasks: list[Any]) -> dict[str, Any]:
    rows = [_model_dump(task) for task in dispatch_tasks]
    total = len(rows)
    blocked = [row for row in rows if row.get("status") in {"blocked", "waiting_approval", "not_calculated"}]
    completed = [row for row in rows if row.get("status") in {"done", "completed"}]
    active = [row for row in rows if row.get("status") in {"scheduled", "queued", "in_progress"}]
    quantity = sum(int(_number(row.get("quantity"))) for row in rows)
    return {
        "task_count": total,
        "active_task_count": len(active),
        "blocked_task_count": len(blocked),
        "completed_task_count": len(completed),
        "scheduled_quantity": quantity,
        "completion_rate": round(len(completed) / total, 4) if total else 0.0,
        "blocked_tasks": blocked[:10],
    }


def _market_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    signals = [_model_dump(item) for item in snapshot.get("market_signals", [])]
    inventory = [_model_dump(item) for item in snapshot.get("inventory", [])]
    demand_values = [_number(item.get("demand_index")) for item in signals]
    inventory_pressure = [_number(item.get("pressure_score")) for item in inventory]
    return {
        "signal_count": len(signals),
        "average_demand_index": round(mean(demand_values), 4) if demand_values else 0.0,
        "average_inventory_pressure": round(mean(inventory_pressure), 4) if inventory_pressure else 0.0,
        "top_demand_signals": sorted(signals, key=lambda item: _number(item.get("demand_index")), reverse=True)[:5],
        "high_pressure_inventory": sorted(
            inventory,
            key=lambda item: _number(item.get("pressure_score")),
            reverse=True,
        )[:5],
    }


def _node_rows(snapshot_nodes: list[dict[str, Any]], management_nodes: list[Any]) -> list[dict[str, Any]]:
    status_by_code = {_model_dump(node).get("node_code"): _model_dump(node) for node in management_nodes}
    rows: list[dict[str, Any]] = []
    for node in snapshot_nodes:
        code = str(node.get("node_code") or "")
        production = node.get("production") if isinstance(node.get("production"), dict) else {}
        metrics = node.get("metrics") if isinstance(node.get("metrics"), dict) else {}
        runtime = node.get("runtime") if isinstance(node.get("runtime"), dict) else {}
        rows.append({
            "node_code": code,
            "node_name": status_by_code.get(code, {}).get("node_name", code),
            "workshop_type": node.get("workshop_type") or production.get("workshop_type"),
            "status": node.get("status"),
            "machine_code": node.get("machine_code") or production.get("machine_code"),
            "active_order": production.get("active_order"),
            "finished_quantity": production.get("finished_quantity", metrics.get("finished_quantity", 0)),
            "defect_quantity": production.get("defect_quantity", metrics.get("defect_quantity", 0)),
            "target_rate": production.get("target_rate"),
            "actual_rate": production.get("actual_rate"),
            "utilization": production.get("utilization"),
            "alarms": node.get("alarms", []),
            "runtime": {
                "run_id": runtime.get("run_id"),
                "scenario_id": runtime.get("scenario_id"),
                "simulation_engine": runtime.get("simulation_engine"),
                "simulation_time": runtime.get("simulation_time"),
            },
        })
    return rows


def _report_filename(report: dict[str, Any], suffix: str) -> str:
    generated_at = str(report.get("generated_at") or "")
    safe_stamp = generated_at.replace(":", "").replace("-", "").split(".")[0]
    if not safe_stamp:
        safe_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"mini-ogas-production-report-{safe_stamp}.{suffix}"


def _markdown_report(report: dict[str, Any]) -> str:
    overview = report["factory_overview"]
    production = report["production_statistics"]
    dispatch = report["dispatch_summary"]
    market = report["market_summary"]
    ai = report.get("ai_summary") or {}
    persistence = report.get("persistence") or {}
    lines = [
        "# Mini-OGAS Production Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Data source: {overview.get('data_source', '-')}",
        f"- Nodes online: {overview.get('online_count', 0)}/{overview.get('node_count', 0)}",
        f"- Active alerts: {overview.get('active_alert_count', 0)}",
        f"- Critical alerts: {overview.get('critical_alert_count', 0)}",
        f"- Persistence: {persistence.get('backend', '-')} / {persistence.get('status', '-')}",
        f"- AI runtime: {ai.get('provider', '-')} / {ai.get('status', '-')}",
        "",
        "## Production Statistics",
        "",
        f"- Finished quantity: {production.get('finished_quantity', 0)}",
        f"- Defect quantity: {production.get('defect_quantity', 0)}",
        f"- Defect rate: {production.get('defect_rate', 0)}",
        f"- Average utilization: {production.get('average_utilization', 0)}",
        f"- Average target rate: {production.get('average_target_rate', 0)}",
        f"- Average actual rate: {production.get('average_actual_rate', 0)}",
        "",
        "## Dispatch",
        "",
        f"- Task count: {dispatch.get('task_count', 0)}",
        f"- Active tasks: {dispatch.get('active_task_count', 0)}",
        f"- Blocked tasks: {dispatch.get('blocked_task_count', 0)}",
        f"- Completed tasks: {dispatch.get('completed_task_count', 0)}",
        f"- Scheduled quantity: {dispatch.get('scheduled_quantity', 0)}",
        "",
        "## Market",
        "",
        f"- Signal count: {market.get('signal_count', 0)}",
        f"- Average demand index: {market.get('average_demand_index', 0)}",
        f"- Average inventory pressure: {market.get('average_inventory_pressure', 0)}",
        "",
        "## Nodes",
        "",
        "| Node | Machine | Status | Order | Finished | Defects | Target rate | Actual rate | Utilization |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for node in report.get("nodes", []):
        lines.append(
            "| {node_code} | {machine_code} | {status} | {active_order} | {finished_quantity} | "
            "{defect_quantity} | {target_rate} | {actual_rate} | {utilization} |".format(
                node_code=node.get("node_code") or "-",
                machine_code=node.get("machine_code") or "-",
                status=node.get("status") or "-",
                active_order=node.get("active_order") or "-",
                finished_quantity=node.get("finished_quantity", 0),
                defect_quantity=node.get("defect_quantity", 0),
                target_rate=node.get("target_rate", "-"),
                actual_rate=node.get("actual_rate", "-"),
                utilization=node.get("utilization", "-"),
            )
        )
    conclusions = report.get("rule_engine", {}).get("conclusions", [])
    lines.extend(["", "## Rule Conclusions", ""])
    if not conclusions:
        lines.append("No active rule conclusions.")
    else:
        for item in conclusions:
            lines.append(
                f"- {item.get('machine_code', '-')}: {item.get('title', '-')} "
                f"({item.get('risk_level', '-')}) - {item.get('summary', '-')}"
            )
    return "\n".join(lines) + "\n"


def _csv_report(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "node_code",
            "node_name",
            "workshop_type",
            "machine_code",
            "status",
            "active_order",
            "finished_quantity",
            "defect_quantity",
            "target_rate",
            "actual_rate",
            "utilization",
        ],
    )
    writer.writeheader()
    for node in report.get("nodes", []):
        writer.writerow({key: node.get(key, "") for key in writer.fieldnames})
    return output.getvalue()


@router.get("/api/reports/production")
@router.get("/reports/production")
def production_report(include_ai_summary: bool = Query(default=True)) -> dict[str, Any]:
    """Return a structured production report backed by live management data."""
    management = store.management_snapshot()
    dashboard = _build_dashboard_snapshot()
    nodes = dashboard.get("nodes") if isinstance(dashboard.get("nodes"), list) else []
    production_node_codes = {str(node.get("node_code") or "") for node in nodes}
    online_nodes = [node for node in nodes if node.get("status") == "online"]
    isolated_nodes = [node for node in nodes if node.get("status") == "isolated"]
    rule_conclusions = dashboard.get("rule_conclusions") if isinstance(dashboard.get("rule_conclusions"), list) else []
    dispatch = _dispatch_summary(list(management.get("dispatch_tasks", [])))
    active_alerts = [
        _model_dump(alert)
        for alert in management.get("alerts", [])
        if _model_dump(alert).get("status") not in {"closed", "resolved"}
    ]
    production_alerts = [
        alert
        for alert in active_alerts
        if not production_node_codes or str(alert.get("node_code") or "") in production_node_codes
    ]
    ai_runtime = runtime_status()

    ai_summary = None
    if include_ai_summary:
        ai_summary = {
            "status": ai_runtime.get("status"),
            "provider": ai_runtime.get("provider"),
            "model": ai_runtime.get("model"),
            "message": (
                "AI runtime is live and can be used for report narration."
                if ai_runtime.get("status") == "live"
                else "AI runtime is not live; report uses deterministic rules only."
            ),
        }

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "report_type": "production",
        "factory_overview": {
            "node_count": len(nodes),
            "online_count": len(online_nodes),
            "isolated_count": len(isolated_nodes),
            "active_alert_count": len(production_alerts),
            "critical_alert_count": len([alert for alert in production_alerts if alert.get("severity") == "critical"]),
            "data_source": dashboard.get("data_source"),
            "run": dashboard.get("run", {}),
        },
        "production_statistics": _production_totals(nodes),
        "market_summary": _market_summary(management),
        "dispatch_summary": dispatch,
        "rule_engine": {
            "conclusion_count": len(rule_conclusions),
            "conclusions": rule_conclusions[:20],
        },
        "ai_summary": ai_summary,
        "persistence": management.get("persistence", {}),
        "replay_readiness": store.replay_readiness_report(),
        "nodes": _node_rows(nodes, list(management.get("nodes", []))),
        "active_alerts": production_alerts,
        "recent_events": [
            _model_dump(event)
            for event in list(management.get("events", []))[-20:]
        ],
    }


@router.get("/api/reports/production/export")
@router.get("/reports/production/export")
def production_report_export(
    format: str = Query(default="markdown", pattern="^(json|markdown|csv)$"),
    include_ai_summary: bool = Query(default=True),
) -> Response:
    """Download the live production report as JSON, Markdown, or node CSV."""
    report = production_report(include_ai_summary=include_ai_summary)
    selected_format = format.lower()
    if selected_format == "json":
        body = json.dumps(report, ensure_ascii=False, indent=2)
        media_type = "application/json; charset=utf-8"
        suffix = "json"
    elif selected_format == "markdown":
        body = _markdown_report(report)
        media_type = "text/markdown; charset=utf-8"
        suffix = "md"
    elif selected_format == "csv":
        body = _csv_report(report)
        media_type = "text/csv; charset=utf-8"
        suffix = "csv"
    else:
        raise HTTPException(status_code=400, detail="unsupported report export format")
    filename = _report_filename(report, suffix)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
