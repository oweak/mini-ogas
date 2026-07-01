from __future__ import annotations

from hashlib import sha1
from typing import Any


Number = int | float


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _evidence(field: str, operator: str, value: Any, threshold: Any, detail: str) -> dict[str, Any]:
    return {
        "field": field,
        "operator": operator,
        "value": value,
        "threshold": threshold,
        "detail": detail,
    }


def _source(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    run = snapshot.get("run") if isinstance(snapshot.get("run"), dict) else {}
    runtime = node.get("runtime") if isinstance(node.get("runtime"), dict) else {}
    return {
        "data_source": snapshot.get("data_source", "unknown"),
        "run_id": run.get("run_id") or runtime.get("run_id") or "RUN-UNKNOWN",
        "scenario_id": run.get("scenario_id") or runtime.get("scenario_id") or "SCN-UNKNOWN",
        "simulation_time": run.get("simulation_time") or runtime.get("simulation_time"),
        "simulation_engine": run.get("simulation_engine") or runtime.get("simulation_engine"),
    }


def _conclusion_id(rule_id: str, node_code: str, source: dict[str, Any]) -> str:
    digest = sha1(
        f"{rule_id}:{node_code}:{source.get('run_id')}:{source.get('scenario_id')}".encode("utf-8")
    ).hexdigest()[:10].upper()
    return f"CONC-{digest}"


def _bottleneck_actions(workshop_type: str, machine_code: str) -> list[str]:
    if workshop_type == "milling":
        return [
            f"Keep {machine_code} online, then reduce upstream release rate for one simulation window.",
            "Check coolant flow and tool compensation before moving blocked orders.",
            "If backlog remains after the next heartbeat, ask dispatch to shift overflow to an idle node.",
        ]
    if workshop_type == "grinding":
        return [
            f"Inspect abrasive wheel load on {machine_code} before increasing feed.",
            "Hold upstream WIP release until output WIP recovers.",
            "Prepare a wheel dressing task if utilization stays high with low output.",
        ]
    return [
        f"Review spindle load and fixture cycle time on {machine_code}.",
        "Throttle upstream WIP release for one simulation window.",
        "Escalate to maintenance only if throughput gap widens on the next heartbeat.",
    ]


def _starvation_actions(workshop_type: str, machine_code: str) -> list[str]:
    route_hint = {
        "turning": "upstream raw-material release",
        "milling": "turning-to-milling transfer",
        "grinding": "milling-to-grinding transfer",
    }.get(workshop_type, "upstream transfer")
    return [
        f"Check {route_hint} before changing machine parameters on {machine_code}.",
        "Keep the node running if health metrics are stable; this is a flow problem first.",
        "Ask dispatch to release or reroute the next batch if WIP input is still empty next heartbeat.",
    ]


def _build_conclusion(
    *,
    snapshot: dict[str, Any],
    node: dict[str, Any],
    rule_id: str,
    rule_type: str,
    risk_level: str,
    title: str,
    summary: str,
    evidence: list[dict[str, Any]],
    recommended_actions: list[str],
) -> dict[str, Any]:
    node_code = _text(node.get("node_code"), "unknown-node")
    source = _source(snapshot, node)
    return {
        "schema_version": "2.2",
        "conclusion_id": _conclusion_id(rule_id, node_code, source),
        "rule_id": rule_id,
        "type": rule_type,
        "node_code": node_code,
        "machine_code": _text(node.get("machine_code"), node_code),
        "risk_level": risk_level,
        "severity": risk_level,
        "title": title,
        "summary": summary,
        "evidence": evidence,
        "recommended_actions": recommended_actions,
        "source": source,
        "read_only": True,
    }


def _bottleneck_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    production = node.get("production") if isinstance(node.get("production"), dict) else {}
    node_code = _text(node.get("node_code"), "unknown-node")
    machine_code = _text(node.get("machine_code"), node_code)
    workshop_type = _text(node.get("workshop_type"), "")
    wip_input = _number(production.get("wip_input"))
    wip_output = _number(production.get("wip_output"))
    target_rate = _number(production.get("target_rate"))
    actual_rate = _number(production.get("actual_rate"))
    utilization = _number(production.get("utilization"))
    backlog = wip_input - wip_output
    throughput_gap = (target_rate - actual_rate) / target_rate if target_rate > 0 else 0

    backlog_trigger = backlog >= 12
    rate_trigger = utilization >= 0.82 and throughput_gap >= 0.25 and wip_input >= 6
    if not backlog_trigger and not rate_trigger:
        return None

    risk_level = "high" if backlog >= 14 or (utilization >= 0.92 and throughput_gap >= 0.4) else "medium"
    evidence = [
        _evidence(
            "production.wip_input - production.wip_output",
            ">=",
            round(backlog, 3),
            12,
            "Input WIP is accumulating faster than output WIP.",
        ),
        _evidence("production.utilization", ">=", round(utilization, 3), 0.82, "The node is heavily loaded."),
        _evidence("production.actual_rate / production.target_rate", "<=", round(actual_rate / target_rate, 3) if target_rate else 0, 0.75, "Actual throughput is below the target rate."),
    ]
    return _build_conclusion(
        snapshot=snapshot,
        node=node,
        rule_id="RULE-BOTTLENECK-LOW-OUTPUT",
        rule_type="bottleneck_alert",
        risk_level=risk_level,
        title=f"{machine_code} flow bottleneck",
        summary=(
            f"{node_code} is accumulating WIP while output rate is below target; "
            "treat this as a flow bottleneck before creating a repair command."
        ),
        evidence=evidence,
        recommended_actions=_bottleneck_actions(workshop_type, machine_code),
    )


def _starvation_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    production = node.get("production") if isinstance(node.get("production"), dict) else {}
    node_code = _text(node.get("node_code"), "unknown-node")
    machine_code = _text(node.get("machine_code"), node_code)
    workshop_type = _text(node.get("workshop_type"), "")
    wip_input = _number(production.get("wip_input"))
    target_rate = _number(production.get("target_rate"))
    actual_rate = _number(production.get("actual_rate"))
    utilization = _number(production.get("utilization"))
    starving = wip_input <= 2 and utilization <= 0.45 and (target_rate <= 0 or actual_rate <= target_rate * 0.55)
    if not starving:
        return None

    risk_level = "high" if wip_input == 0 and utilization <= 0.25 else "medium"
    evidence = [
        _evidence("production.wip_input", "<=", round(wip_input, 3), 2, "The node has little or no input WIP."),
        _evidence("production.utilization", "<=", round(utilization, 3), 0.45, "The machine is under-used."),
        _evidence("production.actual_rate", "<=", round(actual_rate, 3), round(target_rate * 0.55, 3), "Actual output is too low for the planned target."),
    ]
    return _build_conclusion(
        snapshot=snapshot,
        node=node,
        rule_id="RULE-STARVATION-LOW-WIP",
        rule_type="starvation_alert",
        risk_level=risk_level,
        title=f"{machine_code} input starvation",
        summary=(
            f"{node_code} is under-utilized because input WIP is too low; "
            "diagnose upstream flow before changing equipment settings."
        ),
        evidence=evidence,
        recommended_actions=_starvation_actions(workshop_type, machine_code),
    )


def evaluate_snapshot_rules(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Return read-only rule conclusions derived from dashboard snapshot metrics."""
    nodes = snapshot.get("nodes") if isinstance(snapshot.get("nodes"), list) else []
    conclusions: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for rule in (_bottleneck_rule, _starvation_rule):
            conclusion = rule(snapshot, node)
            if conclusion:
                conclusions.append(conclusion)
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    conclusions.sort(
        key=lambda item: (
            severity_rank.get(_text(item.get("severity"), "low"), 4),
            _text(item.get("node_code")),
            _text(item.get("rule_id")),
        )
    )
    return conclusions
