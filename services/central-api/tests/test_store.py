from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core import database
from app.models import Machine, MetricIn, NodeStatus, ProductionPlanIn, Severity, utc_now
from app.core.config import settings
from app.safety_governor import SafetyDecision
import app.store as store_module
from app.store import MemoryStore, canonical_product_code, product_name, product_route


@pytest.fixture()
def store() -> MemoryStore:
    return MemoryStore()


def approved_safety(action: str, node_code: str, actor: str = "system_admin") -> SafetyDecision:
    return SafetyDecision(
        allow=True,
        requires_human=True,
        confirmation_required=False,
        reason_code="allowed",
        message="approved by test safety gate",
        action=action,
        target_node=node_code,
        risk_level="high",
        actor_role=actor,
    )


def test_record_metric_creates_new_node(store: MemoryStore) -> None:
    store.record_metric(
        MetricIn(
            node_code="quality-cloud-01",
            workshop_type="cloud",
            cpu_usage=35,
            memory_usage=42,
            disk_usage=51,
            network_in=1_000_000,
            network_out=900_000,
            db_latency_ms=20,
            api_latency_ms=60,
        )
    )

    assert "quality-cloud-01" in store.nodes
    assert store.nodes["quality-cloud-01"].workshop_type == "cloud"


def test_heartbeat_rejects_run_and_scenario_identity_conflicts_before_state_mutation(store: MemoryStore) -> None:
    base = {
        "status": "running",
        "metrics": {},
        "production": {"workshop_type": "turning"},
        "runtime": {
            "run_id": "RUN-IDENTITY-001",
            "scenario_id": "SCN-IDENTITY-001",
            "simulation_engine": "simpy",
            "random_seed": 42,
        },
    }
    store.record_node_heartbeat_v2({**base, "node_code": "identity-node-a"})

    conflicting_run = {
        **base,
        "node_code": "identity-node-b",
        "runtime": {**base["runtime"], "scenario_id": "SCN-OTHER"},
    }
    with pytest.raises(ValueError, match="cannot mix multiple scenario_id"):
        store.record_node_heartbeat_v2(conflicting_run)

    conflicting_seed = {
        **base,
        "node_code": "identity-node-c",
        "runtime": {**base["runtime"], "run_id": "RUN-IDENTITY-002", "random_seed": 99},
    }
    with pytest.raises(ValueError, match="scenario .* cannot mix multiple random_seed"):
        store.record_node_heartbeat_v2(conflicting_seed)

    assert "identity-node-b" not in store.nodes
    assert "identity-node-c" not in store.nodes


def test_live_alert_projection_excludes_previous_runs(store: MemoryStore) -> None:
    node_code = "turning-workshop-01"
    store.record_node_heartbeat_v2({
        "node_code": node_code,
        "status": "running",
        "metrics": {},
        "production": {"workshop_type": "turning"},
        "runtime": {
            "run_id": "RUN-CURRENT",
            "scenario_id": "SCN-CURRENT",
            "simulation_engine": "simpy",
            "random_seed": 42,
        },
    })
    current = store.create_alert(node_code, "current_fault", Severity.medium, "current run")
    previous = current.model_copy(update={"id": current.id + 1, "run_id": "RUN-PREVIOUS"})
    store.alerts.append(previous)

    assert store.alert_in_current_run(current) is True
    assert store.alert_in_current_run(previous) is False
    assert store.summary().alert_count == 1
    assert [item.id for item in store.management_snapshot()["alerts"]] == [current.id]


def test_product_catalog_uses_shared_microservice_codes(store: MemoryStore) -> None:
    assert list(store_module.PRODUCTS) == ["P1", "P2", "P3", "P4", "P5"]
    assert canonical_product_code("A3") == "P3"
    assert product_name("A3") == product_name("P3")
    assert product_route("P3") == ["turning", "milling", "grinding"]
    assert all(item.product_code.startswith("P") for item in store.market_signals)
    assert all(item.product_code.startswith("P") for item in store.inventory)
    assert store.allocation_orders[0].product_code == "P3"


def test_incident_event_ids_remain_unique_after_retention_window(store: MemoryStore) -> None:
    generated = [
        store.add_event("turning-workshop-01", "retention-check", Severity.info, str(index))
        for index in range(220)
    ]

    generated_ids = [event.id for event in generated]
    assert generated_ids == sorted(generated_ids)
    assert len(generated_ids) == len(set(generated_ids))
    assert len(store.incident_events) == 160


def test_escalation_reuses_existing_open_alert(store: MemoryStore) -> None:
    alert = store.create_alert(
        "milling-workshop-01",
        "SPINDLE_TEMP_HIGH",
        Severity.high,
        "existing spindle alert",
    )
    alerts_before = len(store.alerts)

    result = store.escalate_to_human(
        alert.node_code,
        alert.alert_type,
        "dispatch technician and stop machine",
    )

    assert len(store.alerts) == alerts_before
    assert alert.handled_by == "human-required"
    assert result["alert_id"] == alert.id
    assert result["issue_id"] == f"{alert.node_code}-{alert.alert_type}"


def test_heartbeat_resolves_cleared_non_escalated_alarm(store: MemoryStore) -> None:
    payload = {
        "node_code": "milling-workshop-01",
        "status": "warning",
        "production": {"machine_code": "MILL-02", "workshop_type": "milling"},
        "alarms": [{"type": "COOLANT_FLOW_LOW", "severity": "medium", "status": "open"}],
    }

    created = store.record_node_heartbeat_v2(payload)
    alert = next(item for item in store.alerts if item.alert_type == "COOLANT_FLOW_LOW")
    cleared = store.record_node_heartbeat_v2({**payload, "status": "running", "alarms": []})

    assert created["alarms_accepted"] == 1
    assert alert.source == "node-heartbeat"
    assert cleared["alarms_resolved"] == 1
    assert alert.status == "resolved"


def test_heartbeat_does_not_auto_resolve_human_required_alarm(store: MemoryStore) -> None:
    payload = {
        "node_code": "milling-workshop-01",
        "status": "fault",
        "production": {"machine_code": "MILL-02", "workshop_type": "milling"},
        "alarms": [{"type": "SPINDLE_TEMP_HIGH", "severity": "high", "status": "open"}],
    }
    store.record_node_heartbeat_v2(payload)
    store.escalate_to_human("milling-workshop-01", "SPINDLE_TEMP_HIGH", "dispatch technician")

    cleared = store.record_node_heartbeat_v2({**payload, "status": "running", "alarms": []})
    alert = next(item for item in store.alerts if item.alert_type == "SPINDLE_TEMP_HIGH")

    assert cleared["alarms_resolved"] == 0
    assert alert.status != "resolved"
    assert alert.handled_by == "human-required"


def test_refresh_market_via_service_consumes_signals(monkeypatch, store: MemoryStore) -> None:
    monkeypatch.setattr(settings, "microservices_enabled", True)
    monkeypatch.setattr(settings, "market_simulator_url", "http://market.test")

    def fake_get_json(url: str, timeout: float | None = None):
        assert url == "http://market.test/signals"
        return True, [
            {
                "product_code": "P1",
                "current_price": 121.5,
                "competitor_price": 119.0,
                "demand_index": 135.0,
                "season_factor": 1.2,
                "inventory_pressure": 77.0,
            }
        ]

    monkeypatch.setattr(store_module, "get_json", fake_get_json)

    store.refresh_market_via_service()

    assert [signal.product_code for signal in store.market_signals] == ["P1"]
    assert store.market_signals[0].demand_index == 135.0
    assert next(item for item in store.inventory if item.product_code == "P1").pressure_score == 77.0
    edge = next(edge for edge in store.topology_edges if edge.target == "market-simulator")
    assert edge.status == "healthy"


def test_generate_production_plan_uses_planner_service(monkeypatch, store: MemoryStore) -> None:
    monkeypatch.setattr(settings, "microservices_enabled", True)
    monkeypatch.setattr(settings, "market_simulator_url", "http://market.test")
    monkeypatch.setattr(settings, "production_planner_url", "http://planner.test")

    def fake_get_json(url: str, timeout: float | None = None):
        return True, [
            {
                "product_code": "P2",
                "current_price": 180.0,
                "competitor_price": 176.0,
                "demand_index": 122.0,
                "season_factor": 1.1,
                "inventory_pressure": 12.0,
            }
        ]

    def fake_post_json(url: str, payload: dict, timeout: float | None = None):
        assert url == "http://planner.test/plan"
        assert payload["market_signals"][0]["product_code"] == "P2"
        assert any(node["workshop_type"] == "turning" for node in payload["node_health"])
        return True, [
            {
                "product_code": "P2",
                "target_quantity": 88,
                "priority": 2,
                "route": ["turning", "milling"],
                "reason": "pytest planner",
            }
        ]

    monkeypatch.setattr(store_module, "get_json", fake_get_json)
    monkeypatch.setattr(store_module, "post_json", fake_post_json)

    plans = store.generate_production_plan()

    assert len(plans) == 1
    assert plans[0].product_code == "P2"
    assert plans[0].target_quantity == 88
    assert plans[0].reason == "pytest planner"
    edge = next(edge for edge in store.topology_edges if edge.target == "production-planner")
    assert edge.status == "healthy"


def test_record_node_heartbeat_v2_updates_runtime_production_and_alerts(store: MemoryStore) -> None:
    result = store.record_node_heartbeat_v2({
        "node_code": "milling-workshop-01",
        "status": "warning",
        "schema_version": "2.2",
        "runtime": {
            "deployment_mode": "process",
            "simulation_mode": "normal",
            "simulation_engine": "simpy",
            "run_id": "RUN-20260613-001",
            "scenario_id": "SCN-MILLING-COOLANT-LOW-001",
            "simulation_time": "2026-06-13T10:20:00+08:00",
            "simulation_speed": 12,
            "runtime_source": "node-agent",
        },
        "metrics": {
            "cpu_usage": 42,
            "memory_usage": 50,
            "disk_usage": 61,
            "network_latency_ms": 35,
            "db_latency_ms": 12,
        },
        "production": {
            "machine_code": "MILL-02",
            "workshop_type": "milling",
            "active_order": "WO-1",
            "finished_quantity": 33,
            "defect_quantity": 1,
            "tool_wear_level": 28,
            "spindle_temp": 66.5,
            "wip_input": 8,
            "wip_output": 5,
            "target_rate": 1.0,
            "actual_rate": 0.82,
            "utilization": 0.76,
            "defect_rate": 0.03,
        },
        "alarms": [{"type": "COOLANT_FLOW_LOW", "severity": "medium", "status": "open"}],
        "sync": {"pending_records": 2},
    })

    assert result["accepted"] is True
    assert result["schema_version"] == "2.2"
    assert store.node_heartbeats_v2["milling-workshop-01"]["runtime"]["simulation_engine"] == "simpy"
    assert store.latest_metrics()["milling-workshop-01"].finished_quantity == 33
    assert any(machine.machine_code == "MILL-02" and machine.today_output == 33 for machine in store.machines)
    assert any(alert.alert_type == "COOLANT_FLOW_LOW" for alert in store.alerts)


def test_turning_heartbeat_creates_ready_parts_for_milling_claim(store: MemoryStore) -> None:
    base_payload = {
        "node_code": "turning-workshop-01",
        "status": "running",
        "runtime": {"simulation_engine": "simpy", "run_id": "RUN-PARTS", "scenario_id": "SCN-PARTS"},
        "metrics": {"cpu_usage": 30, "memory_usage": 40, "disk_usage": 50},
        "production": {
            "machine_code": "LATHE-01",
            "workshop_type": "turning",
            "active_order": "WO-PARTS-001",
            "product_code": "A3",
            "finished_quantity": 10,
            "target_rate": 1.0,
            "actual_rate": 0.9,
            "utilization": 0.7,
        },
    }
    first = store.record_node_heartbeat_v2(base_payload)
    second = store.record_node_heartbeat_v2({
        **base_payload,
        "production": {**base_payload["production"], "finished_quantity": 12},
    })

    first_claim = store.claim_next_part_for_node("milling-workshop-01")
    second_claim = store.claim_next_part_for_node("milling-workshop-01")
    third_claim = store.claim_next_part_for_node("milling-workshop-01")

    assert first["parts_created"] == 0
    assert second["parts_created"] == 2
    assert first_claim["claimed"] is True
    assert second_claim["claimed"] is True
    assert third_claim == {"claimed": False, "part": None}
    assert first_claim["part"].part_id != second_claim["part"].part_id


def test_part_claim_completion_and_expiry_recovery(store: MemoryStore) -> None:
    part = store.create_ready_part("WO-PARTS-EXPIRE", "A3")
    claimed = store.claim_next_part_for_node("milling-workshop-01")
    claimed_part = claimed["part"]
    assert claimed_part.part_id == part.part_id
    assert claimed_part.claim_token

    with store._lock:
        claimed_part.claim_expires_at = utc_now() - timedelta(seconds=1)
    released = store.release_expired_part_claims()
    reclaimed = store.claim_next_part_for_node("milling-workshop-01")
    reclaimed_part = reclaimed["part"]
    completed = store.complete_claimed_part(
        "milling-workshop-01",
        reclaimed_part.part_id,
        reclaimed_part.claim_token,
    )

    assert released == 1
    assert reclaimed["claimed"] is True
    assert reclaimed_part.part_id == part.part_id
    assert completed["accepted"] is True
    assert completed["part"].status == "completed"
    snapshot = store.part_queue_snapshot()
    assert snapshot["counts"]["completed"] == 1


def test_milling_completion_creates_grinding_downstream_part(store: MemoryStore) -> None:
    source = store.create_ready_part("WO-PARTS-GRIND", "A3")
    source_sequence = source.event_sequence
    milling_claim = store.claim_next_part_for_node("milling-workshop-01")
    milling_part = milling_claim["part"]
    claimed_sequence = milling_part.event_sequence

    milling_done = store.complete_claimed_part(
        "milling-workshop-01",
        milling_part.part_id,
        milling_part.claim_token,
    )
    downstream_created = milling_done["downstream_part"].model_copy(deep=True)
    grinding_claim = store.claim_next_part_for_node("grinding-workshop-01")
    grinding_claim_again = store.claim_next_part_for_node("grinding-workshop-01")
    grinding_part = grinding_claim["part"]
    grinding_done = store.complete_claimed_part(
        "grinding-workshop-01",
        grinding_part.part_id,
        grinding_part.claim_token,
    )

    assert milling_done["accepted"] is True
    assert milling_done["part"].part_id == source.part_id
    assert downstream_created.parent_part_id == source.part_id
    assert downstream_created.current_step == "grinding"
    assert downstream_created.current_operation == "grinding"
    assert downstream_created.next_operation == ""
    assert downstream_created.target_node == "grinding-workshop-01"
    assert downstream_created.batch_id == source.batch_id
    assert downstream_created.run_id == source.run_id
    assert downstream_created.scenario_id == source.scenario_id
    assert source_sequence < claimed_sequence < milling_done["part"].event_sequence
    assert milling_done["part"].event_sequence < downstream_created.event_sequence
    assert milling_done["part"].quality_status == "accepted"
    assert downstream_created.quality_status == "pending"
    assert grinding_claim["claimed"] is True
    assert grinding_claim_again == {"claimed": False, "part": None}
    assert grinding_done["accepted"] is True
    assert grinding_done["part"].status == "completed"
    assert grinding_done["part"].quality_status == "accepted"
    assert grinding_done["part"].event_sequence > downstream_created.event_sequence
    assert grinding_done["downstream_part"] is None
    assert store.part_queue_snapshot()["counts"]["completed"] == 2


def test_part_queue_flow_projection_is_causal_and_preserves_reported_wip(store: MemoryStore) -> None:
    source = store.create_ready_part("WO-FLOW-PROJECTION", "A3")
    reported = {"wip_input": 99, "wip_output": 77, "actual_rate": 0.8}

    turning_before = store.part_queue_flow_projection("turning-workshop-01", reported)
    milling_before = store.part_queue_flow_projection("milling-workshop-01", reported)
    milling_claim = store.claim_next_part_for_node("milling-workshop-01")
    milling_done = store.complete_claimed_part(
        "milling-workshop-01",
        source.part_id,
        milling_claim["part"].claim_token,
    )
    milling_after = store.part_queue_flow_projection("milling-workshop-01", reported)
    grinding_before = store.part_queue_flow_projection("grinding-workshop-01", reported)
    grinding_claim = store.claim_next_part_for_node("grinding-workshop-01")
    store.complete_claimed_part(
        "grinding-workshop-01",
        grinding_claim["part"].part_id,
        grinding_claim["part"].claim_token,
    )
    grinding_after = store.part_queue_flow_projection("grinding-workshop-01", reported)

    assert turning_before["wip_output"] == 1
    assert milling_before["wip_input"] == 1
    assert milling_after["wip_input"] == 0
    assert milling_after["wip_output"] == 1
    assert grinding_before["wip_input"] == 1
    assert grinding_after["wip_input"] == 0
    assert grinding_after["wip_output"] == 1
    assert milling_done["downstream_part"].current_operation == "grinding"
    assert grinding_after["reported_wip_input"] == 99
    assert grinding_after["reported_wip_output"] == 77
    assert grinding_after["wip_source"] == "part_queue"
    assert grinding_after["actual_rate"] == 0.8


def test_simpy_finished_deltas_advance_only_available_parts(store: MemoryStore) -> None:
    def heartbeat(node_code: str, workshop: str, finished: int) -> dict:
        return {
            "node_code": node_code,
            "status": "running",
            "runtime": {
                "simulation_engine": "simpy",
                "run_id": "RUN-CAUSAL-FLOW",
                "scenario_id": "SCN-CAUSAL-FLOW",
                "random_seed": 42,
            },
            "metrics": {"cpu_usage": 20, "memory_usage": 30, "disk_usage": 40},
            "production": {
                "machine_code": node_code,
                "workshop_type": workshop,
                "active_order": "WO-CAUSAL-FLOW",
                "product_code": "A3",
                "finished_quantity": finished,
                "target_rate": 1.0,
                "actual_rate": 0.8,
                "utilization": 0.7,
            },
        }

    store.record_node_heartbeat_v2(heartbeat("turning-workshop-01", "turning", 0))
    store.record_node_heartbeat_v2(heartbeat("milling-workshop-01", "milling", 0))
    store.record_node_heartbeat_v2(heartbeat("grinding-workshop-01", "grinding", 0))

    turning = store.record_node_heartbeat_v2(heartbeat("turning-workshop-01", "turning", 3))
    milling = store.record_node_heartbeat_v2(heartbeat("milling-workshop-01", "milling", 2))
    grinding = store.record_node_heartbeat_v2(heartbeat("grinding-workshop-01", "grinding", 1))

    milling_flow = store.part_queue_flow_projection("milling-workshop-01")
    grinding_flow = store.part_queue_flow_projection("grinding-workshop-01")
    assert turning["parts_created"] == 3
    assert milling["parts_completed"] == 2
    assert grinding["parts_completed"] == 1
    assert milling_flow["wip_input"] == 1
    assert grinding_flow["wip_input"] == 1
    assert grinding_flow["wip_output"] == 1

    # Grinding reports two more physical completions, but only one part remains.
    constrained = store.record_node_heartbeat_v2(heartbeat("grinding-workshop-01", "grinding", 3))
    constrained_flow = store.part_queue_flow_projection("grinding-workshop-01")
    assert constrained["parts_completed"] == 1
    assert constrained["flow_limited_by_input"] is True
    assert constrained_flow["wip_input"] == 0
    assert constrained_flow["wip_output"] == 2
    assert constrained_flow["wip_output"] <= turning["parts_created"]


def test_current_system_run_follows_latest_received_heartbeat(store: MemoryStore) -> None:
    store.node_heartbeats_v2 = {
        "turning-workshop-01": {
            "runtime": {"run_id": "RUN-OLD"},
            "_received_at": "2026-07-13T01:00:00+00:00",
        },
        "milling-workshop-01": {
            "runtime": {"run_id": "RUN-NEW"},
            "_received_at": "2026-07-13T02:00:00+00:00",
        },
        "grinding-workshop-01": {
            "runtime": {"run_id": "RUN-OLD"},
            "_received_at": "2026-07-13T01:30:00+00:00",
        },
        "workflow-check-node-newer": {
            "runtime": {"run_id": "RUN-WORKFLOW-TEMP"},
            "_received_at": "2026-07-13T03:00:00+00:00",
        },
    }

    assert store.current_run_id_for_system() == "RUN-NEW"


def test_shadow_persistence_restores_part_queue_and_commands(tmp_path) -> None:
    original_enabled = settings.persist_enabled
    original_path = settings.central_db_path
    settings.persist_enabled = True
    settings.central_db_path = str(tmp_path / "central-shadow.db")
    try:
        database.init_db()
        first = MemoryStore()
        part = first.create_ready_part("WO-SHADOW", "A3")
        claimed = first.claim_next_part_for_node("milling-workshop-01")
        claimed_part = claimed["part"]
        first.complete_claimed_part("milling-workshop-01", claimed_part.part_id, claimed_part.claim_token)

        command = first.add_command(
            "milling-workshop-01",
            "set_target_rate",
            "low",
            "pending",
            "pytest",
            parameters={"target_rate": 0.81},
        )
        first.claim_pending_commands_for_node("milling-workshop-01", "pytest-agent")
        first.record_command_result("milling-workshop-01", command.id, "executed", "applied")
        first_status = first.persistence_status()

        second = MemoryStore()
        second_status = second.persistence_status()
    finally:
        settings.persist_enabled = original_enabled
        settings.central_db_path = original_path

    assert first_status["status"] == "ok"
    assert second_status["status"] == "ok"
    assert first_status["counts"]["part_queue_shadow"] >= 2
    assert first_status["counts"]["command_shadow"] >= 1
    restored_part = next(item for item in second.part_queue if item.part_id == part.part_id)
    restored_downstream = next(item for item in second.part_queue if item.parent_part_id == part.part_id)
    restored_command = next(item for item in second.commands if item.id == command.id)
    assert restored_part.status == "completed"
    assert restored_downstream.current_step == "grinding"
    assert restored_downstream.current_operation == "grinding"
    assert restored_downstream.batch_id == restored_part.batch_id
    assert restored_downstream.parent_part_id == restored_part.part_id
    assert restored_downstream.event_sequence > restored_part.event_sequence
    assert restored_part.quality_status == "accepted"
    assert restored_downstream.quality_status == "pending"
    assert restored_downstream.status == "ready"
    assert restored_command.status == "applied"
    assert restored_command.claimed_by == "pytest-agent"
    assert restored_command.parameters["target_rate"] == 0.81
    assert restored_command.result_message == "applied"


def test_command_manager_supersedes_pending_same_node_command(store: MemoryStore) -> None:
    first = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.7},
    )
    second = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.8},
    )

    assert first.status == "superseded"
    assert first.result_message == f"superseded by command_id={second.id}"
    assert second.status == "pending"
    assert any(
        event.stage == "command-superseded" and str(first.id) in event.message
        for event in store.incident_events
    )


def test_command_manager_expires_stale_claimed_commands(store: MemoryStore) -> None:
    command = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.7},
    )
    claimed = store.claim_pending_commands_for_node("milling-workshop-01", "pytest-agent")
    assert [item.id for item in claimed] == [command.id]
    with store._lock:
        command.updated_at = utc_now() - timedelta(seconds=settings.command_claim_timeout_seconds + 5)

    pending = store.pending_commands_for_node("milling-workshop-01")

    assert pending == []
    assert command.status == "expired"
    assert "timed out" in command.result_message
    assert any(
        event.stage == "command-expired" and str(command.id) in event.message
        for event in store.incident_events
    )


def test_command_manager_accepts_duplicate_result_idempotently(store: MemoryStore) -> None:
    command = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.72},
    )
    store.claim_pending_commands_for_node("milling-workshop-01", "pytest-agent")

    first = store.record_command_result("milling-workshop-01", command.id, "executed", "applied")
    before_events = len(store.incident_events)
    second = store.record_command_result("milling-workshop-01", command.id, "executed", "applied")

    assert first["status"] == "applied"
    assert second["status"] == "applied"
    assert command.status == "applied"
    assert command.result_message == "applied"
    assert len(store.incident_events) == before_events


def test_command_manager_idempotency_key_prevents_reexecution_after_terminal_result(store: MemoryStore) -> None:
    parameters = {"target_rate": 0.72, "idempotency_key": "rate-change-20260713-001"}
    first = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters=parameters,
    )
    store.claim_pending_commands_for_node("milling-workshop-01", "pytest-agent")
    store.record_command_result("milling-workshop-01", first.id, "executed", "applied")

    duplicate = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters=parameters,
    )

    assert duplicate is first
    assert len([item for item in store.commands if item.parameters.get("idempotency_key") == parameters["idempotency_key"]]) == 1


def test_command_manager_claim_is_atomic_across_concurrent_agents(store: MemoryStore) -> None:
    command = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.77},
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda agent: store.claim_pending_commands_for_node("milling-workshop-01", agent),
            ["agent-a", "agent-b"],
        ))

    claimed = [item for batch in results for item in batch]
    assert [item.id for item in claimed] == [command.id]
    assert command.status == "claimed"
    assert command.claimed_by in {"agent-a", "agent-b"}


def test_command_manager_cancels_pending_command(store: MemoryStore) -> None:
    command = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.7},
    )

    cancelled = store.cancel_command(command.id, actor="pytest", reason="operator changed plan")

    assert cancelled.status == "cancelled"
    assert "operator changed plan" in cancelled.result_message
    assert store.pending_commands_for_node("milling-workshop-01") == []
    assert any(event.stage == "command-cancelled" for event in store.incident_events)


def test_command_manager_retries_failed_command_as_new_command(store: MemoryStore) -> None:
    command = store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.7},
    )
    store.record_command_result(command.node_code, command.id, "failed", "temporary actuator error")

    retried = store.retry_command(command.id, actor="pytest")

    assert command.status == "failed"
    assert retried.id != command.id
    assert retried.status == "pending"
    assert retried.parameters["retry_of"] == command.id
    assert retried.parameters["target_rate"] == 0.7
    assert any(event.stage == "command-retried" for event in store.incident_events)


def test_record_metric_disk_90_generates_alert(store: MemoryStore) -> None:
    alerts = store.record_metric(
        MetricIn(
            node_code="turning-workshop-01",
            cpu_usage=40,
            memory_usage=50,
            disk_usage=90,
            network_in=1_000_000,
            network_out=900_000,
            db_latency_ms=20,
            api_latency_ms=60,
        )
    )

    assert any(alert.alert_type == "disk_pressure" for alert in alerts)
    assert any(command.command_type == "clean_temp_cache" for command in store.commands)


def test_record_metric_cpu_92_and_latency_800_triggers_ai_diagnosis(store: MemoryStore) -> None:
    alerts = store.record_metric(
        MetricIn(
            node_code="milling-workshop-01",
            cpu_usage=92,
            memory_usage=70,
            disk_usage=60,
            network_in=1_000_000,
            network_out=900_000,
            db_latency_ms=100,
            api_latency_ms=800,
        )
    )

    assert any(alert.alert_type == "cpu_latency_correlation" for alert in alerts)
    assert len(store.ai_diagnoses) >= 1
    assert store.nodes["milling-workshop-01"].status == NodeStatus.degraded


def test_record_metric_persists_actual_ai_fallback_provenance(store: MemoryStore, monkeypatch) -> None:
    from app.core.ai.base import DiagnosisResult
    from app import store as store_module

    fallback = DiagnosisResult("rule root cause", "manual review", 0.55)
    monkeypatch.setattr(store_module.registry, "diagnose", lambda *_args, **_kwargs: fallback)
    monkeypatch.setattr(
        store_module.registry,
        "diagnose_with_provenance",
        lambda *_args, **_kwargs: (fallback, "rule_fallback", ["deepseek: timeout"]),
    )
    monkeypatch.setattr(
        store_module.registry,
        "first_available",
        lambda: type("Provider", (), {"name": "deepseek"})(),
    )

    store.record_metric(
        MetricIn(
            node_code="milling-workshop-01",
            cpu_usage=95,
            memory_usage=70,
            disk_usage=60,
            network_in=1_000_000,
            network_out=900_000,
            db_latency_ms=100,
            api_latency_ms=900,
        )
    )

    assert store.ai_diagnoses[-1].model_name == "local-fallback"


def test_record_metric_network_100m_isolates_node(store: MemoryStore) -> None:
    alerts = store.record_metric(
        MetricIn(
            node_code="grinding-workshop-01",
            cpu_usage=45,
            memory_usage=55,
            disk_usage=60,
            network_in=100_000_000,
            network_out=5_000_000,
            db_latency_ms=40,
            api_latency_ms=80,
        )
    )

    assert any(alert.severity == Severity.high for alert in alerts)
    assert store.nodes["grinding-workshop-01"].status == NodeStatus.isolated


def test_heartbeat_timeout_ignores_control_plane_placeholders(store: MemoryStore) -> None:
    cutoff = utc_now() - timedelta(seconds=settings.heartbeat_timeout_seconds + 5)
    store.nodes["cloud-workshop-01"].last_heartbeat = cutoff
    store.nodes["cloud-db-01"].last_heartbeat = cutoff
    store.nodes["turning-workshop-01"].last_heartbeat = cutoff

    expired = store.check_heartbeat_timeout()

    assert expired == 1
    assert store.nodes["turning-workshop-01"].status == NodeStatus.offline
    assert store.nodes["cloud-workshop-01"].status == NodeStatus.online
    assert store.nodes["cloud-db-01"].status == NodeStatus.online
    assert not any(
        event.stage == "heartbeat-timeout" and event.node_code in {"cloud-workshop-01", "cloud-db-01"}
        for event in store.incident_events
    )


def test_record_metric_does_not_apply_production_fault_rules_to_control_plane(store: MemoryStore) -> None:
    alerts = store.record_metric(
        MetricIn(
            node_code="cloud-workshop-01",
            workshop_type="cloud",
            cpu_usage=98,
            memory_usage=82,
            disk_usage=94,
            network_in=120_000_000,
            network_out=20_000_000,
            db_latency_ms=180,
            api_latency_ms=950,
        )
    )

    assert alerts == []
    assert store.nodes["cloud-workshop-01"].status == NodeStatus.online
    assert not any(alert.node_code == "cloud-workshop-01" for alert in store.alerts)
    assert not any(command.node_code == "cloud-workshop-01" for command in store.commands)


def test_simulation_step_does_not_inject_anomalies_into_control_plane_nodes(store: MemoryStore) -> None:
    with store._lock:
        store.nodes = {
            code: node for code, node in store.nodes.items()
            if code in {"cloud-workshop-01", "cloud-db-01"}
        }
        store.metrics = [
            metric for metric in store.metrics
            if metric.node_code in {"cloud-workshop-01", "cloud-db-01"}
        ]
    store.simulation_anomaly_rate = 1.0

    before_events = store.simulation_generated_events
    state = store.simulation_step()

    assert state.tick == 1
    assert store.simulation_generated_events == before_events
    assert store.nodes["cloud-workshop-01"].status == NodeStatus.online
    assert store.nodes["cloud-db-01"].status == NodeStatus.online
    assert not any(alert.node_code in {"cloud-workshop-01", "cloud-db-01"} for alert in store.alerts)


def test_isolate_node_changes_topology_edges(store: MemoryStore) -> None:
    store.isolate_node(
        "turning-workshop-01",
        "system_admin",
        approved_safety("isolate_node", "turning-workshop-01"),
    )

    edge = next(edge for edge in store.topology_edges if edge.target == "turning-workshop-01")
    assert edge.status == "isolated"
    assert edge.latency_ms == 999


def test_restore_node_regenerates_plan(store: MemoryStore) -> None:
    store.isolate_node(
        "turning-workshop-01",
        "system_admin",
        approved_safety("isolate_node", "turning-workshop-01"),
    )
    store.production_plans.clear()

    node = store.restore_node(
        "turning-workshop-01",
        "system_admin",
        approved_safety("restore_node", "turning-workshop-01"),
    )

    assert node.status == NodeStatus.online
    assert len(store.production_plans) > 0


def test_apply_scenario_normal_resets_data(store: MemoryStore) -> None:
    store.isolate_node(
        "turning-workshop-01",
        "system_admin",
        approved_safety("isolate_node", "turning-workshop-01"),
    )

    result = store.apply_scenario("normal")

    assert result["scenario"] == "normal"
    assert store.nodes["turning-workshop-01"].status == NodeStatus.online
    assert len(store.dispatch_tasks) > 0


def test_direct_high_risk_store_action_requires_approved_safety_decision(store: MemoryStore) -> None:
    with pytest.raises(PermissionError, match="approved safety decision required"):
        store.isolate_node("turning-workshop-01", "system_admin")

    assert store.nodes["turning-workshop-01"].status != NodeStatus.isolated


def test_apply_scenario_unknown_raises_value_error(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        store.apply_scenario("unknown")


def test_rebuild_dispatch_creates_tasks(store: MemoryStore) -> None:
    store.production_plans = [
        ProductionPlanIn(
            product_code="P1",
            target_quantity=120,
            priority=1,
            route=["turning", "drilling", "inspection"],
            reason="pytest",
        )
    ]

    tasks = store.rebuild_dispatch()

    assert len(tasks) == 3
    assert all(task.status in {"scheduled", "queued"} for task in tasks)


def test_rebuild_dispatch_blocks_task_when_no_machine(store: MemoryStore) -> None:
    store.machines = [
        Machine(
            machine_code="MILL-OFFLINE",
            node_code="milling-workshop-01",
            machine_type="CNC Milling",
            status="maintenance",
            load_rate=10,
            tool_wear_level=10,
            today_output=0,
            defect_count=0,
        )
    ]
    store.production_plans = [
        ProductionPlanIn(
            product_code="P1",
            target_quantity=80,
            priority=1,
            route=["turning"],
            reason="pytest",
        )
    ]

    tasks = store.rebuild_dispatch()

    assert len(tasks) == 1
    assert tasks[0].status == "blocked"
    assert tasks[0].assigned_machine == "waiting-capacity"


def test_management_snapshot_includes_all_sections(store: MemoryStore) -> None:
    snapshot = store.management_snapshot()

    for key in (
        "summary",
        "hosts",
        "nodes",
        "metrics",
        "topology",
        "market_signals",
        "inventory",
        "plans",
        "dispatch_tasks",
        "resource_allocations",
        "machines",
        "alerts",
        "events",
        "commands",
        "ai_shortcuts",
        "simulation",
        "integrations",
        "persistence",
    ):
        assert key in snapshot
    assert snapshot["persistence"]["status"] == "disabled"


def test_simulation_step_increments_tick(store: MemoryStore) -> None:
    before = store.simulation_tick

    state = store.simulation_step()

    assert state.tick == before + 1
    assert store.simulation_tick == before + 1
