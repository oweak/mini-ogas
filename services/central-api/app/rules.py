from __future__ import annotations

from hashlib import sha1
from datetime import datetime
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
    calculation_summary = "; ".join(
        f"{item.get('field')} {item.get('operator')} {item.get('threshold')} (observed={item.get('value')})"
        for item in evidence
    )
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
        "candidate_actions": recommended_actions,
        "trigger_data": {item["field"]: item["value"] for item in evidence},
        "thresholds": {item["field"]: item["threshold"] for item in evidence},
        "result": "triggered",
        "calculation_summary": calculation_summary,
        "source": source,
        "read_only": True,
    }


def _bottleneck_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    if _text(node.get("status")) in {"offline", "missing"}:
        return None
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
    rate_ratio = actual_rate / target_rate if target_rate else 0
    evidence = []
    if backlog_trigger:
        evidence.append(_evidence(
            "production.wip_input - production.wip_output",
            ">=",
            round(backlog, 3),
            12,
            "Input WIP is accumulating faster than output WIP.",
        ))
    if utilization >= 0.82:
        evidence.append(_evidence(
            "production.utilization", ">=", round(utilization, 3), 0.82, "The node is heavily loaded."
        ))
    if target_rate > 0 and rate_ratio <= 0.75:
        evidence.append(_evidence(
            "production.actual_rate / production.target_rate",
            "<=",
            round(rate_ratio, 3),
            0.75,
            "Actual throughput is below the target rate.",
        ))
    if rate_trigger:
        evidence.append(_evidence(
            "production.wip_input", ">=", round(wip_input, 3), 6, "Input WIP is available while throughput lags."
        ))
    if backlog_trigger and rate_trigger:
        summary = f"{node_code} is accumulating WIP while output rate is below target."
    elif rate_trigger:
        summary = f"{node_code} is heavily loaded while output rate is below target."
    else:
        summary = f"{node_code} WIP accumulation is above the operating threshold."
    return _build_conclusion(
        snapshot=snapshot,
        node=node,
        rule_id="RULE-BOTTLENECK-LOW-OUTPUT",
        rule_type="bottleneck_alert",
        risk_level=risk_level,
        title=f"{machine_code} flow bottleneck",
        summary=summary + " Treat this as a flow bottleneck before creating a repair command.",
        evidence=evidence,
        recommended_actions=_bottleneck_actions(workshop_type, machine_code),
    )


def _starvation_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    if _text(node.get("status")) in {"offline", "missing"}:
        return None
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


def _offline_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    status = _text(node.get("status"))
    if status not in {"offline", "missing"}:
        return None
    return _build_conclusion(
        snapshot=snapshot,
        node=node,
        rule_id="RULE-NODE-HEARTBEAT-LOST",
        rule_type="heartbeat_loss_alert",
        risk_level="critical",
        title=f"{_text(node.get('node_code'))} heartbeat lost",
        summary="The expected edge node is offline; production facts are no longer current.",
        evidence=[_evidence("node.status", "in", status, ["offline", "missing"], "Heartbeat supervision marked the node unavailable.")],
        recommended_actions=["Freeze new dispatch to this node.", "Preserve local buffer and inspect process/network health.", "Require fresh heartbeat identity before restore."],
    )


def _stale_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    generated = _text(snapshot.get("generated_at"))
    received = _text(node.get("received_at") or node.get("last_heartbeat"))
    if not generated or not received:
        return None
    try:
        age_seconds = (datetime.fromisoformat(generated.replace("Z", "+00:00")) - datetime.fromisoformat(received.replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        return None
    if age_seconds < 20:
        return None
    return _build_conclusion(
        snapshot=snapshot, node=node, rule_id="RULE-NODE-DATA-STALE", rule_type="stale_data_alert",
        risk_level="high" if age_seconds >= 60 else "medium",
        title=f"{_text(node.get('node_code'))} data is stale",
        summary="The node has not produced a fresh operational fact within the allowed window.",
        evidence=[_evidence("heartbeat.age_seconds", ">=", round(age_seconds, 1), 20, "Snapshot generation time exceeds the last ingest time.")],
        recommended_actions=["Stop using stale values for dispatch decisions.", "Check edge connectivity and local outbox depth.", "Resume only after monotonic sequence recovery."],
    )


def _defect_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    production = node.get("production") if isinstance(node.get("production"), dict) else {}
    defect_rate = _number(production.get("defect_rate"))
    defect_delta = _number(production.get("defect_rate_delta"))
    if defect_rate < 0.05 and defect_delta < 0.02:
        return None
    return _build_conclusion(
        snapshot=snapshot, node=node, rule_id="RULE-QUALITY-DEFECT-RISE", rule_type="defect_rate_alert",
        risk_level="high" if defect_rate >= 0.08 else "medium",
        title=f"{_text(node.get('machine_code'))} defect rate rising",
        summary="Observed defect rate or its latest change exceeds the deterministic quality threshold.",
        evidence=[
            _evidence("production.defect_rate", ">=", round(defect_rate, 4), 0.05, "Current defect share is elevated."),
            _evidence("production.defect_rate_delta", ">=", round(defect_delta, 4), 0.02, "Latest heartbeat shows an upward quality shift."),
        ],
        recommended_actions=["Hold suspect output for quality review.", "Inspect tooling and process compensation.", "Resume normal release after two stable observations."],
    )


def _tool_wear_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    production = node.get("production") if isinstance(node.get("production"), dict) else {}
    wear = _number(production.get("tool_wear_level"))
    if wear < 65:
        return None
    return _build_conclusion(
        snapshot=snapshot, node=node, rule_id="RULE-TOOL-WEAR-LIMIT", rule_type="tool_wear_alert",
        risk_level="high" if wear >= 80 else "medium",
        title=f"{_text(node.get('machine_code'))} tool wear limit",
        summary="Tool wear exceeded the preventive-maintenance threshold.",
        evidence=[_evidence("production.tool_wear_level", ">=", round(wear, 2), 65, "Wear index crossed the maintenance threshold.")],
        recommended_actions=["Create a controlled tool inspection task.", "Reduce release rate if quality is also drifting.", "Require human approval before stopping a critical machine."],
    )


def _network_rule(snapshot: dict[str, Any], node: dict[str, Any]) -> dict[str, Any] | None:
    metrics = node.get("metrics") if isinstance(node.get("metrics"), dict) else {}
    latency = _number(metrics.get("network_latency_ms") or metrics.get("api_latency_ms"))
    network_total = _number(metrics.get("network_in")) + _number(metrics.get("network_out"))
    if latency < 250 and network_total < 50_000_000:
        return None
    return _build_conclusion(
        snapshot=snapshot, node=node, rule_id="RULE-NETWORK-ANOMALY", rule_type="network_anomaly_alert",
        risk_level="high" if latency >= 1000 or network_total >= 200_000_000 else "medium",
        title=f"{_text(node.get('node_code'))} network anomaly",
        summary="Latency or traffic volume exceeds the edge communication threshold.",
        evidence=[
            _evidence("metrics.network_latency_ms", ">=", round(latency, 1), 250, "Control-plane latency is elevated."),
            _evidence("metrics.network_bytes_total", ">=", round(network_total, 1), 50_000_000, "Observed traffic is unusually high."),
        ],
        recommended_actions=["Preserve traffic evidence and validate node identity.", "Throttle nonessential synchronization.", "Escalate isolation only through Safety Governor."],
    )


def _turning_overproduction_rule(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    by_type = {_text(node.get("workshop_type")): node for node in snapshot.get("nodes", []) if isinstance(node, dict)}
    turning = by_type.get("turning")
    milling = by_type.get("milling")
    if not turning or not milling:
        return None
    turning_p = turning.get("production") if isinstance(turning.get("production"), dict) else {}
    milling_p = milling.get("production") if isinstance(milling.get("production"), dict) else {}
    turning_rate = _number(turning_p.get("target_rate"))
    milling_rate = _number(milling_p.get("target_rate"))
    backlog = _number(milling_p.get("wip_input")) - _number(milling_p.get("wip_output"))
    if milling_rate <= 0 or turning_rate <= milling_rate * 1.2 or backlog < 8:
        return None
    evidence = [
        _evidence("turning.target_rate / milling.target_rate", ">", round(turning_rate / milling_rate, 3), 1.2, "Upstream release exceeds milling capacity."),
        _evidence("milling.wip_input - milling.wip_output", ">=", round(backlog, 3), 8, "Milling-front WIP is accumulating."),
    ]
    return _build_conclusion(
        snapshot=snapshot, node=turning, rule_id="RULE-TURNING-OVERPRODUCTION", rule_type="overproduction_alert",
        risk_level="high" if backlog >= 14 else "medium",
        title="Turning release exceeds milling capacity",
        summary="Turning target rate is creating sustained WIP growth before milling.",
        evidence=evidence,
        recommended_actions=["Propose a temporary Turning target-rate reduction.", "Send the proposal through Safety Governor.", "Verify milling backlog trend and grinding starvation after execution."],
    )


def _ineffective_command_rules(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = {str(node.get("node_code")): node for node in snapshot.get("nodes", []) if isinstance(node, dict)}
    conclusions = []
    latest_by_effect: dict[tuple[str, str], dict[str, Any]] = {}
    for command in snapshot.get("commands", []):
        if not isinstance(command, dict):
            continue
        key = (
            str(command.get("node_code") or "central-api"),
            str(command.get("command_type") or "unknown"),
        )
        latest_by_effect[key] = command
    for command in latest_by_effect.values():
        if not isinstance(command, dict) or command.get("verification_status") not in {"failed", "partial", "inconclusive"}:
            continue
        node_code = str(command.get("node_code") or "central-api")
        node = nodes.get(node_code, {"node_code": node_code, "machine_code": node_code, "runtime": {}})
        status = str(command.get("verification_status"))
        conclusions.append(_build_conclusion(
            snapshot=snapshot, node=node, rule_id="RULE-COMMAND-INEFFECTIVE", rule_type="command_effect_alert",
            risk_level="high" if status == "failed" else "medium",
            title=f"Command {command.get('id')} effect is {status}",
            summary="Verifier did not confirm the requested operational improvement.",
            evidence=[_evidence("command.verification_status", "in", status, ["failed", "partial", "inconclusive"], "Post-command facts did not prove the intended effect.")],
            recommended_actions=["Do not retry automatically without reviewing evidence.", "Inspect verifier observations and downstream impact.", "Create a revised proposal with a new idempotency key."],
        ))
    return conclusions


def evaluate_snapshot_rules(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Return read-only rule conclusions derived from dashboard snapshot metrics."""
    nodes = snapshot.get("nodes") if isinstance(snapshot.get("nodes"), list) else []
    conclusions: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for rule in (_offline_rule, _stale_rule, _bottleneck_rule, _starvation_rule, _defect_rule, _tool_wear_rule, _network_rule):
            conclusion = rule(snapshot, node)
            if conclusion:
                conclusions.append(conclusion)
    overproduction = _turning_overproduction_rule(snapshot)
    if overproduction:
        conclusions.append(overproduction)
    conclusions.extend(_ineffective_command_rules(snapshot))
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    conclusions.sort(
        key=lambda item: (
            severity_rank.get(_text(item.get("severity"), "low"), 4),
            _text(item.get("node_code")),
            _text(item.get("rule_id")),
        )
    )
    return conclusions
