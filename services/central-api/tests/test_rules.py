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
