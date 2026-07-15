from app.rules import evaluate_snapshot_rules


def _snapshot_with_node(production: dict, **node_overrides: object) -> dict:
    node = {
        "node_code": "milling-workshop-01",
        "machine_code": "MILL-02",
        "workshop_type": "milling",
        "status": "running",
        "runtime": {
            "run_id": "RUN-RULE-TEST",
            "scenario_id": "SCN-RULE-TEST",
            "simulation_engine": "simpy",
            "simulation_time": "2026-06-13T11:00:00+08:00",
        },
        "production": production,
    }
    node.update(node_overrides)
    return {
        "schema_version": "2.2",
        "generated_at": "2026-06-13T11:00:00+08:00",
        "data_source": "live",
        "run": {
            "run_id": "RUN-RULE-TEST",
            "scenario_id": "SCN-RULE-TEST",
            "simulation_engine": "simpy",
            "simulation_time": "2026-06-13T11:00:00+08:00",
        },
        "nodes": [node],
    }


def test_milling_bottleneck_rule_is_read_only_and_traceable() -> None:
    snapshot = _snapshot_with_node({
        "wip_input": 18,
        "wip_output": 4,
        "target_rate": 1.2,
        "actual_rate": 0.62,
        "utilization": 0.91,
        "defect_rate": 0.01,
    })

    conclusions = evaluate_snapshot_rules(snapshot)

    assert len(conclusions) == 1
    conclusion = conclusions[0]
    assert conclusion["type"] == "bottleneck_alert"
    assert conclusion["rule_id"] == "RULE-BOTTLENECK-LOW-OUTPUT"
    assert conclusion["node_code"] == "milling-workshop-01"
    assert conclusion["machine_code"] == "MILL-02"
    assert conclusion["read_only"] is True
    assert conclusion["source"]["run_id"] == "RUN-RULE-TEST"
    assert any(item["field"] == "production.wip_input - production.wip_output" for item in conclusion["evidence"])
    assert len(conclusion["recommended_actions"]) >= 2


def test_backlog_only_bottleneck_excludes_unmatched_rate_evidence() -> None:
    snapshot = _snapshot_with_node({
        "wip_input": 18,
        "wip_output": 4,
        "target_rate": 1.0,
        "actual_rate": 0.94,
        "utilization": 0.94,
        "defect_rate": 0.01,
    })

    conclusion = evaluate_snapshot_rules(snapshot)[0]
    evidence_fields = {item["field"] for item in conclusion["evidence"]}

    assert conclusion["rule_id"] == "RULE-BOTTLENECK-LOW-OUTPUT"
    assert "production.wip_input - production.wip_output" in evidence_fields
    assert "production.actual_rate / production.target_rate" not in evidence_fields
    assert "below target" not in conclusion["summary"]


def test_starvation_rule_triggers_from_low_input_wip() -> None:
    snapshot = _snapshot_with_node(
        {
            "wip_input": 0,
            "wip_output": 0,
            "target_rate": 1.0,
            "actual_rate": 0.1,
            "utilization": 0.18,
            "defect_rate": 0.0,
        },
        node_code="grinding-workshop-01",
        machine_code="GRIND-01",
        workshop_type="grinding",
    )

    conclusions = evaluate_snapshot_rules(snapshot)

    assert len(conclusions) == 1
    conclusion = conclusions[0]
    assert conclusion["type"] == "starvation_alert"
    assert conclusion["rule_id"] == "RULE-STARVATION-LOW-WIP"
    assert conclusion["severity"] == "high"
    assert any(item["field"] == "production.wip_input" for item in conclusion["evidence"])


def test_nominal_snapshot_has_no_rule_conclusion() -> None:
    snapshot = _snapshot_with_node({
        "wip_input": 6,
        "wip_output": 5,
        "target_rate": 1.0,
        "actual_rate": 0.95,
        "utilization": 0.66,
        "defect_rate": 0.01,
    })

    assert evaluate_snapshot_rules(snapshot) == []


def test_rule_output_contains_deterministic_calculation_contract() -> None:
    conclusion = evaluate_snapshot_rules(_snapshot_with_node({
        "wip_input": 18, "wip_output": 4, "target_rate": 1.0,
        "actual_rate": 0.5, "utilization": 0.9, "defect_rate": 0.01,
    }))[0]

    assert conclusion["result"] == "triggered"
    assert conclusion["trigger_data"]
    assert conclusion["thresholds"]
    assert conclusion["candidate_actions"] == conclusion["recommended_actions"]
    assert "observed=" in conclusion["calculation_summary"]


def test_turning_overproduction_rule_uses_cross_node_capacity_and_wip() -> None:
    snapshot = _snapshot_with_node({
        "wip_input": 7, "wip_output": 5, "target_rate": 1.333,
        "actual_rate": 1.1, "utilization": 0.8, "defect_rate": 0.01,
    }, node_code="turning-workshop-01", machine_code="LATHE-01", workshop_type="turning")
    snapshot["nodes"].append({
        "node_code": "milling-workshop-01", "machine_code": "MILL-02",
        "workshop_type": "milling", "status": "running", "runtime": {},
        "production": {"wip_input": 18, "wip_output": 6, "target_rate": 0.833,
                       "actual_rate": 0.68, "utilization": 0.9, "defect_rate": 0.01},
    })

    ids = {item["rule_id"] for item in evaluate_snapshot_rules(snapshot)}
    assert "RULE-TURNING-OVERPRODUCTION" in ids
    assert "RULE-BOTTLENECK-LOW-OUTPUT" in ids


def test_offline_and_stale_node_rules_are_distinct() -> None:
    offline = _snapshot_with_node({}, status="offline")
    stale = _snapshot_with_node(
        {"wip_input": 6, "wip_output": 5, "target_rate": 1.0, "actual_rate": 0.95,
         "utilization": 0.66, "defect_rate": 0.01},
        received_at="2026-06-13T10:59:00+08:00",
    )

    assert {item["rule_id"] for item in evaluate_snapshot_rules(offline)} == {"RULE-NODE-HEARTBEAT-LOST"}
    assert "RULE-NODE-DATA-STALE" in {item["rule_id"] for item in evaluate_snapshot_rules(stale)}


def test_quality_wear_and_network_rules_use_observed_metrics() -> None:
    quality = _snapshot_with_node({
        "wip_input": 6, "wip_output": 5, "target_rate": 1.0, "actual_rate": 0.9,
        "utilization": 0.7, "defect_rate": 0.07, "defect_rate_delta": 0.03,
    })
    wear = _snapshot_with_node({
        "wip_input": 6, "wip_output": 5, "target_rate": 1.0, "actual_rate": 0.9,
        "utilization": 0.7, "defect_rate": 0.01, "tool_wear_level": 72,
    })
    network = _snapshot_with_node({
        "wip_input": 6, "wip_output": 5, "target_rate": 1.0, "actual_rate": 0.9,
        "utilization": 0.7, "defect_rate": 0.01,
    }, metrics={"network_latency_ms": 420, "network_in": 1000, "network_out": 1000})

    assert "RULE-QUALITY-DEFECT-RISE" in {item["rule_id"] for item in evaluate_snapshot_rules(quality)}
    assert "RULE-TOOL-WEAR-LIMIT" in {item["rule_id"] for item in evaluate_snapshot_rules(wear)}
    assert "RULE-NETWORK-ANOMALY" in {item["rule_id"] for item in evaluate_snapshot_rules(network)}


def test_ineffective_command_rule_consumes_verifier_result() -> None:
    snapshot = _snapshot_with_node({
        "wip_input": 6, "wip_output": 5, "target_rate": 1.0, "actual_rate": 0.95,
        "utilization": 0.66, "defect_rate": 0.01,
    })
    snapshot["commands"] = [{
        "id": 91,
        "node_code": "milling-workshop-01",
        "verification_status": "failed",
    }]

    conclusion = next(item for item in evaluate_snapshot_rules(snapshot) if item["rule_id"] == "RULE-COMMAND-INEFFECTIVE")
    assert conclusion["type"] == "command_effect_alert"
    assert conclusion["risk_level"] == "high"


def test_latest_effective_command_supersedes_an_old_partial_result() -> None:
    snapshot = _snapshot_with_node({
        "wip_input": 6, "wip_output": 5, "target_rate": 1.0, "actual_rate": 0.95,
        "utilization": 0.66, "defect_rate": 0.01,
    })
    snapshot["commands"] = [
        {
            "id": 54,
            "node_code": "milling-workshop-01",
            "command_type": "set_target_rate",
            "verification_status": "partial",
        },
        {
            "id": 55,
            "node_code": "milling-workshop-01",
            "command_type": "set_target_rate",
            "verification_status": "effective",
        },
    ]

    ids = {item["rule_id"] for item in evaluate_snapshot_rules(snapshot)}

    assert "RULE-COMMAND-INEFFECTIVE" not in ids
