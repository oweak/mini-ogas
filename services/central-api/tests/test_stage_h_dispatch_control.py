from copy import deepcopy

from app.main import app
from app.store import store
from fastapi.testclient import TestClient


AUTH_HEADERS = {"X-OGAS-Token": "mini-ogas-dev-token"}


def _grinding_heartbeat(target_rate: float = 1.08) -> dict[str, object]:
    return {
        "node_code": "grinding-workshop-01",
        "status": "running",
        "runtime": {
            "simulation_engine": "simpy",
            "simulation_mode": "stage-h-test",
            "runtime_source": "simulated",
            "run_id": "RUN-STAGE-H-TEST",
            "scenario_id": "SCN-STAGE-H-TEST",
            "random_seed": 4103,
        },
        "metrics": {"cpu_usage": 30, "memory_usage": 40, "disk_usage": 50},
        "production": {
            "machine_code": "GRIND-01",
            "workshop_type": "grinding",
            "target_rate": target_rate,
            "actual_rate": 0.82,
            "rate_unit": "parts_per_minute",
            "nominal_capacity_per_hour": 64.8,
            "machine_count": 1,
            "process_time_sec": 55.56,
            "utilization": 0.76,
            "wip_input": 8,
            "wip_output": 5,
            "finished_quantity": 20,
            "defect_quantity": 0,
            "defect_rate": 0,
        },
        "alarms": [],
        "sync": {"last_sync_id": 1, "pending_records": 0},
    }


def test_order_to_dispatch_command_requires_approval_before_node_claim() -> None:
    original = {
        "allocation_orders": deepcopy(store.allocation_orders),
        "production_plans": deepcopy(store.production_plans),
        "dispatch_tasks": deepcopy(store.dispatch_tasks),
        "commands": deepcopy(store.commands),
        "heartbeats": deepcopy(store.node_heartbeats_v2),
        "audit_logs": deepcopy(store.audit_logs),
        "incident_events": deepcopy(store.incident_events),
        "order_seq": store.order_seq,
        "dispatch_seq": store.dispatch_seq,
    }
    try:
        store.allocation_orders = []
        store.production_plans = []
        store.dispatch_tasks = []
        store.command_repository.replace_projection([])
        store.node_heartbeats_v2.clear()
        store.audit_logs = []
        store.incident_events = []
        store.order_seq = 0
        store.dispatch_seq = 0

        with TestClient(app) as client:
            heartbeat = client.post(
                "/api/node-heartbeats",
                headers=AUTH_HEADERS,
                json=_grinding_heartbeat(),
            )
            assert heartbeat.status_code == 200

            order_response = client.post(
                "/api/allocation-orders",
                headers=AUTH_HEADERS,
                json={
                    "product_code": "P3",
                    "required_quantity": 72,
                    "priority": 1,
                    "deadline_hours": 2,
                    "source_unit": "stage-h-test",
                    "reason": "prove order-to-command causality",
                },
            )
            assert order_response.status_code == 200
            order = order_response.json()["order"]
            plan = next(
                item
                for item in order_response.json()["plans"]
                if item["product_code"] == "P3"
            )
            assert plan["target_quantity"] >= 72
            assert order["order_id"] in plan["reason"]

            proposal_response = client.post(
                "/api/dispatch/target-rate-proposals",
                headers=AUTH_HEADERS,
                json={
                    "order_id": order["order_id"],
                    "node_code": "grinding-workshop-01",
                },
            )
            assert proposal_response.status_code == 200
            proposal = proposal_response.json()
            command = proposal["commands"][0]
            assert proposal["requested_rate"] == 0.6
            assert proposal["requires_approval"] is True
            assert command["risk_level"] == "high"
            assert command["status"] == "waiting_approval"
            assert command["parameters"]["source_order_id"] == order["order_id"]

            before_approval = client.get(
                "/api/agents/grinding-workshop-01/commands/pending",
                headers=AUTH_HEADERS,
            )
            assert before_approval.status_code == 200
            assert before_approval.json() == []

            denied = client.post(
                f"/api/ops/approve/{command['id']}",
                headers=AUTH_HEADERS,
                params={"confirmation_code": ""},
            )
            assert denied.status_code == 200
            assert denied.json()["accepted"] is False
            assert denied.json()["safety"]["reason_code"] == "confirmation_code_required"

            approved = client.post(
                f"/api/ops/approve/{command['id']}",
                headers=AUTH_HEADERS,
                params={"confirmation_code": "CONFIRM"},
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "pending"

            claimed = client.get(
                "/api/agents/grinding-workshop-01/commands/pending",
                headers=AUTH_HEADERS,
            )
            assert claimed.status_code == 200
            assert [item["id"] for item in claimed.json()] == [command["id"]]
            assert claimed.json()[0]["claimed_by"] == "grinding-workshop-01"

        persisted_order = next(
            item for item in store.allocation_orders if item.order_id == order["order_id"]
        )
        assert persisted_order.status == "dispatched"
        actions = [item.action for item in store.audit_logs]
        assert "allocation-order:create" in actions
        assert "dispatch:target-rate-proposed" in actions
        assert "dispatch:propose" in actions
        assert "command:approve" in actions
    finally:
        store.allocation_orders = original["allocation_orders"]
        store.production_plans = original["production_plans"]
        store.dispatch_tasks = original["dispatch_tasks"]
        store.command_repository.replace_projection(original["commands"])
        store.node_heartbeats_v2.clear()
        store.node_heartbeats_v2.update(original["heartbeats"])
        store.audit_logs = original["audit_logs"]
        store.incident_events = original["incident_events"]
        store.order_seq = original["order_seq"]
        store.dispatch_seq = original["dispatch_seq"]
