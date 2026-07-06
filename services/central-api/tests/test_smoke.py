from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app, setup_middleware
from app.models import DispatchTask, Severity
from app.store import store

AUTH_HEADERS = {"X-OGAS-Token": "mini-ogas-dev-token"}


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["process_id"] > 0
    assert "T" in payload["process_started_at"]
    assert payload["session_token"]
    assert "supervisor" in payload


def test_health_supervisor_ok(monkeypatch) -> None:
    from app.core.config import settings
    from app.routers import health as health_router

    monkeypatch.setattr(settings, "expected_supervisor_processes", ["central-api", "dashboard"])
    monkeypatch.setattr(
        health_router,
        "get_json",
        lambda url, timeout=None: (
            True,
            {
                "session_id": "SESSION-1",
                "processes": [
                    {"name": "central-api", "state": "healthy", "pid": 100, "crash_count": 0},
                    {"name": "dashboard", "state": "healthy", "pid": 101, "crash_count": 0},
                ],
            },
        ),
    )

    payload = health_router._supervisor_health("SESSION-1")

    assert payload["status"] == "ok"
    assert payload["session_match"] is True
    assert payload["healthy_processes"] == 2
    assert payload["missing_processes"] == []
    assert payload["unhealthy_processes"] == []


def test_health_supervisor_offline(monkeypatch) -> None:
    from app.core.config import settings
    from app.routers import health as health_router

    monkeypatch.setattr(settings, "expected_supervisor_processes", ["central-api"])
    monkeypatch.setattr(health_router, "get_json", lambda url, timeout=None: (False, {"error": "URLError"}))

    payload = health_router._supervisor_health("SESSION-1")

    assert payload["status"] == "offline"
    assert payload["session_match"] is False
    assert payload["missing_processes"] == ["central-api"]


def test_health_supervisor_session_mismatch(monkeypatch) -> None:
    from app.core.config import settings
    from app.routers import health as health_router

    monkeypatch.setattr(settings, "expected_supervisor_processes", ["central-api"])
    monkeypatch.setattr(
        health_router,
        "get_json",
        lambda url, timeout=None: (
            True,
            {
                "session_id": "OTHER-SESSION",
                "processes": [
                    {"name": "central-api", "state": "healthy", "pid": 100, "crash_count": 0},
                ],
            },
        ),
    )

    payload = health_router._supervisor_health("SESSION-1")

    assert payload["status"] == "session_mismatch"
    assert payload["session_match"] is False
    assert payload["missing_processes"] == []


def test_summary_has_required_dashboard_fields() -> None:
    with TestClient(app) as client:
        response = client.get("/summary", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    for key in (
        "node_count",
        "online_count",
        "alert_count",
        "avg_cpu_usage",
        "avg_memory_usage",
    ):
        assert key in payload


def test_management_snapshot_exposes_dispatch_and_integrations() -> None:
    with TestClient(app) as client:
        response = client.get("/management/snapshot", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["dispatch_tasks"]) > 0
    assert len(payload["resource_allocations"]) > 0
    assert len(payload["ai_shortcuts"]) >= 4
    assert "integrations" in payload
    assert len(payload["allocation_orders"]) > 0
    assert len(payload["cloud_roles"]) >= 2
    assert len(payload["authority_matrix"]) >= 4
    assert payload["persistence"]["status"] == "disabled"


def test_persistence_status_endpoint_reports_test_mode() -> None:
    with TestClient(app) as client:
        response = client.get("/persistence/status", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "sqlite-local"
    assert payload["enabled"] is False
    assert payload["status"] == "disabled"


def test_create_allocation_order_regenerates_plan() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/allocation-orders",
            headers=AUTH_HEADERS,
            json={
                "product_code": "A3",
                "required_quantity": 77,
                "priority": 2,
                "deadline_hours": 12,
                "assigned_cloud_role": "辅助调配",
                "reason": "pytest upper dispatch",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["order"]["product_code"] == "P3"
    assert any(plan["product_code"] == "P3" for plan in payload["plans"])


def test_node_heartbeat_and_pending_commands() -> None:
    node_code = "turning-workshop-01"
    with TestClient(app) as client:
        heartbeat = client.put(
            f"/api/nodes/{node_code}/heartbeat",
            headers=AUTH_HEADERS,
            json={
                "node_code": node_code,
                "agent_version": "0.1.0",
                "uptime_seconds": 12,
                "local_db_size_bytes": 4096,
                "db_size_source": "local_file",
            },
        )
        pending = client.get(f"/api/nodes/{node_code}/pending-commands", headers=AUTH_HEADERS)

    assert heartbeat.status_code == 200
    assert heartbeat.json()["local_db_size_bytes"] == 4096
    assert heartbeat.json()["db_size_source"] == "local_file"
    assert pending.status_code == 200
    assert isinstance(pending.json(), list)


def test_production_report_endpoint_aggregates_runtime_facts() -> None:
    with TestClient(app) as client:
        response = client.get("/api/reports/production", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "production"
    assert payload["factory_overview"]["node_count"] >= 3
    assert payload["factory_overview"]["node_count"] == len(payload["nodes"])
    assert payload["factory_overview"]["online_count"] <= payload["factory_overview"]["node_count"]
    assert "production_statistics" in payload
    assert "dispatch_summary" in payload
    assert "rule_engine" in payload
    assert isinstance(payload["nodes"], list)
    assert payload["persistence"]["status"] == "disabled"


def test_production_report_export_markdown_and_csv() -> None:
    with TestClient(app) as client:
        markdown = client.get("/api/reports/production/export?format=markdown", headers=AUTH_HEADERS)
        csv_response = client.get("/api/reports/production/export?format=csv", headers=AUTH_HEADERS)

    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "attachment;" in markdown.headers["content-disposition"]
    assert "# Mini-OGAS Production Report" in markdown.text
    assert "## Nodes" in markdown.text

    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "attachment;" in csv_response.headers["content-disposition"]
    assert "node_code,node_name,workshop_type,machine_code,status" in csv_response.text
    assert "turning-workshop-01" in csv_response.text


def test_protected_api_401_keeps_dashboard_cors_visible() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/reports/production",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Authorization": "Bearer stale-token",
            },
        )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_agent_set_target_rate_command_lifecycle() -> None:
    node_code = "milling-workshop-01"
    with TestClient(app) as client:
        heartbeat = client.post(
            "/api/node-heartbeats",
            headers=AUTH_HEADERS,
            json={
                "node_code": node_code,
                "status": "running",
                "runtime": {"simulation_engine": "simpy", "run_id": "RUN-CMD", "scenario_id": "SCN-CMD"},
                "metrics": {"cpu_usage": 30, "memory_usage": 40, "disk_usage": 50},
                "production": {
                    "machine_code": "MILL-02",
                    "workshop_type": "milling",
                    "target_rate": 1.0,
                    "actual_rate": 0.8,
                    "utilization": 0.7,
                    "wip_input": 8,
                    "wip_output": 4,
                },
            },
        )
        created = client.post(
            f"/api/agents/{node_code}/commands",
            headers=AUTH_HEADERS,
            json={"command_type": "set_target_rate", "target_rate": 0.72, "operator": "pytest"},
        )
        claimed = client.get(f"/api/agents/{node_code}/commands/pending", headers=AUTH_HEADERS)
        claimed_again = client.get(f"/api/agents/{node_code}/commands/pending", headers=AUTH_HEADERS)
        command_id = claimed.json()[0]["id"]
        result = client.post(
            f"/api/commands/{command_id}/result",
            headers=AUTH_HEADERS,
            json={"status": "executed", "message": "target rate override applied"},
        )
        verified_heartbeat = client.post(
            "/api/node-heartbeats",
            headers=AUTH_HEADERS,
            json={
                "node_code": node_code,
                "status": "running",
                "runtime": {"simulation_engine": "simpy", "run_id": "RUN-CMD", "scenario_id": "SCN-CMD"},
                "metrics": {"cpu_usage": 31, "memory_usage": 41, "disk_usage": 51},
                "production": {
                    "machine_code": "MILL-02",
                    "workshop_type": "milling",
                    "target_rate": 0.72,
                    "actual_rate": 0.62,
                    "utilization": 0.7,
                    "wip_input": 8,
                    "wip_output": 4,
                },
            },
        )

    assert heartbeat.status_code == 200
    assert created.status_code == 200
    assert created.json()["parameters"]["target_rate"] == 0.72
    assert claimed.status_code == 200
    assert claimed.json()[0]["status"] == "claimed"
    assert claimed_again.status_code == 200
    assert claimed_again.json() == []
    assert result.status_code == 200
    assert result.json()["status"] == "executed"
    assert verified_heartbeat.status_code == 200
    command = next(item for item in store.commands if item.id == command_id)
    assert command.status == "verified"
    assert "target_rate=0.72" in command.result_message


def test_node_agent_dispatch_and_local_record_sync() -> None:
    node_code = "turning-workshop-01"
    with store._lock:
        store.node_record_sync_ids.clear()

    with TestClient(app) as client:
        dispatch = client.get(f"/api/node-dispatches/{node_code}", headers=AUTH_HEADERS)
        first_sync = client.post(
            "/api/node-records/sync",
            headers=AUTH_HEADERS,
            json={
                "node_code": node_code,
                "records": [{
                    "local_id": 101,
                    "payload": {"kind": "heartbeat", "tick": 1},
                    "created_at": "2026-06-22T00:00:00+00:00",
                    "original_request_id": "req-101",
                    "original_http_status": 503,
                    "original_error": "temporary outage",
                }],
            },
        )
        duplicate_sync = client.post(
            "/api/node-records/sync",
            headers=AUTH_HEADERS,
            json={
                "node_code": node_code,
                "records": [{
                    "local_id": 101,
                    "payload": "{\"kind\": \"heartbeat\"}",
                    "created_at": "2026-06-22T00:00:00+00:00",
                }],
            },
        )

    assert dispatch.status_code == 200
    assert dispatch.json()["dispatch"]["active_order"]
    assert first_sync.status_code == 200
    assert first_sync.json()["records_accepted"] == 1
    assert duplicate_sync.status_code == 200
    assert duplicate_sync.json()["records_accepted"] == 0


def test_part_queue_api_claims_once_and_completes() -> None:
    node_code = "milling-workshop-01"
    with store._lock:
        store.part_queue.clear()
        store.part_seq = 0
    created = store.create_ready_part("WO-API-PARTS", "A3")

    with TestClient(app) as client:
        first = client.post(f"/api/agents/{node_code}/parts/claim-next", headers=AUTH_HEADERS)
        second = client.post(f"/api/agents/{node_code}/parts/claim-next", headers=AUTH_HEADERS)
        claimed_part = first.json()["part"]
        completed = client.post(
            f"/api/agents/{node_code}/parts/{claimed_part['part_id']}/complete",
            headers=AUTH_HEADERS,
            json={"claim_token": claimed_part["claim_token"]},
        )
        queue = client.get("/api/part-queue", headers=AUTH_HEADERS)
        snapshot = client.get("/api/dashboard/snapshot", headers=AUTH_HEADERS)

    assert first.status_code == 200
    assert first.json()["claimed"] is True
    assert first.json()["part"]["part_id"] == created.part_id
    assert second.status_code == 200
    assert second.json() == {"claimed": False, "part": None}
    assert completed.status_code == 200
    assert completed.json()["part"]["status"] == "completed"
    assert completed.json()["downstream_part"]["target_node"] == "grinding-workshop-01"
    assert queue.status_code == 200
    assert queue.json()["counts"]["completed"] == 1
    assert queue.json()["counts"]["ready"] == 1
    assert snapshot.status_code == 200
    assert "part_queue" in snapshot.json()


def test_part_queue_api_milling_to_grinding_chain() -> None:
    with store._lock:
        store.part_queue.clear()
        store.part_seq = 0
    store.create_ready_part("WO-API-CHAIN", "A3")

    with TestClient(app) as client:
        milling_claim = client.post("/api/agents/milling-workshop-01/parts/claim-next", headers=AUTH_HEADERS)
        milling_part = milling_claim.json()["part"]
        milling_done = client.post(
            f"/api/agents/milling-workshop-01/parts/{milling_part['part_id']}/complete",
            headers=AUTH_HEADERS,
            json={"claim_token": milling_part["claim_token"]},
        )
        grinding_claim = client.post("/api/agents/grinding-workshop-01/parts/claim-next", headers=AUTH_HEADERS)
        grinding_part = grinding_claim.json()["part"]
        grinding_done = client.post(
            f"/api/agents/grinding-workshop-01/parts/{grinding_part['part_id']}/complete",
            headers=AUTH_HEADERS,
            json={"claim_token": grinding_part["claim_token"]},
        )
        queue = client.get("/api/part-queue", headers=AUTH_HEADERS)

    assert milling_claim.status_code == 200
    assert milling_done.status_code == 200
    assert milling_done.json()["downstream_part"]["parent_part_id"] == milling_part["part_id"]
    assert grinding_claim.status_code == 200
    assert grinding_claim.json()["part"]["current_step"] == "grinding"
    assert grinding_done.status_code == 200
    assert grinding_done.json()["downstream_part"] is None
    assert queue.json()["counts"]["completed"] == 2


def test_v2_node_heartbeat_flows_into_dashboard_state() -> None:
    with TestClient(app) as client:
        heartbeat = client.post(
            "/api/node-heartbeats",
            headers=AUTH_HEADERS,
            json={
                "node_code": "milling-workshop-01",
                "status": "warning",
                "schema_version": "2.2",
                "agent_version": "0.2.0",
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
            },
        )
        dashboard = client.get("/api/dashboard-state", headers=AUTH_HEADERS)

    assert heartbeat.status_code == 200
    assert heartbeat.json()["ok"] is True
    assert dashboard.status_code == 200
    nodes = dashboard.json()["nodes"]
    milling = next(node for node in nodes if node["node_code"] == "milling-workshop-01")
    assert milling["runtime"]["run_id"] == "RUN-20260613-001"
    assert milling["runtime"]["simulation_engine"] == "simpy"
    assert milling["production"]["wip_input"] == 8
    assert milling["production"]["actual_rate"] == 0.82
    assert milling["sync"]["pending_records"] == 2
    assert any(alert["alert_type"] == "COOLANT_FLOW_LOW" for alert in milling["alarms"])


def test_dashboard_snapshot_exposes_v2_contract() -> None:
    store.create_alert(
        "cloud-workshop-01",
        "cpu_latency_correlation",
        Severity.medium,
        "pytest non-production control-node alert",
    )
    with TestClient(app) as client:
        heartbeat = client.post(
            "/api/node-heartbeats",
            headers=AUTH_HEADERS,
            json={
                "node_code": "turning-workshop-01",
                "status": "running",
                "schema_version": "2.2",
                "agent_version": "0.2.0",
                "runtime": {
                    "deployment_mode": "process",
                    "simulation_mode": "normal",
                    "simulation_engine": "simpy",
                    "run_id": "RUN-20260613-SNAPSHOT",
                    "scenario_id": "SCN-TURNING-NORMAL-001",
                    "simulation_time": "2026-06-13T11:30:00+08:00",
                    "simulation_speed": 10,
                    "runtime_source": "node-agent",
                },
                "metrics": {
                    "cpu_usage": 31,
                    "memory_usage": 48,
                    "disk_usage": 42,
                    "network_latency_ms": 18,
                    "db_latency_ms": 9,
                },
                "production": {
                    "machine_code": "LATHE-01",
                    "workshop_type": "turning",
                    "active_order": "WO-SNAPSHOT",
                    "finished_quantity": 91,
                    "defect_quantity": 0,
                    "tool_wear_level": 14,
                    "wip_input": 12,
                    "wip_output": 11,
                    "target_rate": 1.2,
                    "actual_rate": 1.1,
                    "utilization": 0.68,
                    "defect_rate": 0.0,
                },
                "alarms": [{"type": "VIBRATION_DRIFT", "severity": "low", "status": "open"}],
                "sync": {"pending_records": 0},
            },
        )
        snapshot = client.get("/api/dashboard/snapshot", headers=AUTH_HEADERS)

    assert heartbeat.status_code == 200
    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["schema_version"] == "2.2"
    assert payload["data_source"] == "live"
    assert payload["run"]["run_id"] == "RUN-20260613-SNAPSHOT"
    assert payload["run"]["scenario_id"] == "SCN-TURNING-NORMAL-001"
    assert payload["system"]["nodes_expected"] >= 3
    assert "ai_runtime" in payload["system"]
    turning = next(node for node in payload["nodes"] if node["node_code"] == "turning-workshop-01")
    assert turning["machine_code"] == "LATHE-01"
    assert turning["active_order"] == "WO-SNAPSHOT"
    assert turning["runtime"]["simulation_engine"] == "simpy"
    assert turning["runtime"]["scenario_id"] == "SCN-TURNING-NORMAL-001"
    assert turning["production"]["wip_input"] == 12
    assert turning["production"]["target_rate"] == 1.2
    assert any(alert["alert_type"] == "VIBRATION_DRIFT" for alert in turning["alarms"])
    assert all("cloud-workshop-01" not in str(alert.get("title", "")) for alert in payload["alerts"])
    assert payload["dispatch_plan"]["id"] == "DP-CURRENT"
    assert "rule_conclusions" in payload
    assert isinstance(payload["rule_conclusions"], list)
    assert "recent_events" in payload["audit"]
    assert "recent_logs" in payload["timeline"]


def test_dashboard_state_is_snapshot_wrapper() -> None:
    with TestClient(app) as client:
        response = client.get("/api/dashboard-state", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    snapshot = payload["snapshot"]
    assert snapshot["schema_version"] == "2.2"
    assert payload["issues"] == snapshot["alerts"]
    assert payload["notifications"] == snapshot.get("notifications", [])
    assert payload["nodes"] == snapshot["nodes"]
    assert payload["work_orders"] == snapshot["work_orders"]
    assert payload["dispatch_plan"] == snapshot["dispatch_plan"]
    assert payload["logs"] == snapshot["timeline"]["recent_logs"]


def test_rules_conclusions_endpoint_uses_snapshot_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/rules/conclusions", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "2.2"
    assert "run" in payload
    assert isinstance(payload["conclusions"], list)


def test_rule_demo_modes_create_read_only_conclusions() -> None:
    alert_count_before = len(store.alerts)
    with TestClient(app) as client:
        bottleneck = client.get("/api/dashboard/snapshot?mode=milling_bottleneck", headers=AUTH_HEADERS)
        starvation = client.get("/api/dashboard/snapshot?mode=grinding_starvation", headers=AUTH_HEADERS)
        explanation = client.get(
            "/api/ai/rule-explanation?mode=milling_bottleneck&use_live=false",
            headers=AUTH_HEADERS,
        )

    assert bottleneck.status_code == 200
    bottleneck_payload = bottleneck.json()
    assert any(item["type"] == "bottleneck_alert" for item in bottleneck_payload["rule_conclusions"])
    assert len(store.alerts) == alert_count_before
    assert starvation.status_code == 200
    assert any(item["type"] == "starvation_alert" for item in starvation.json()["rule_conclusions"])
    assert explanation.status_code == 200
    assert explanation.json()["status"] == "fallback"
    assert explanation.json()["rule_count"] >= 1


def test_cors_preflight_allows_dashboard_origin() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/summary",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_value_error_handler_returns_400() -> None:
    local_app = FastAPI()
    setup_middleware(local_app)

    @local_app.get("/boom")
    def boom():
        raise ValueError("bad input")

    with TestClient(local_app) as client:
        response = client.get("/boom", headers=AUTH_HEADERS)

    assert response.status_code == 400
    assert response.json() == {"detail": "bad input"}


def test_runtime_error_handler_hides_detail_by_default() -> None:
    local_app = FastAPI()
    setup_middleware(local_app)

    @local_app.get("/boom")
    def boom():
        raise RuntimeError("database password leaked in stack")

    with TestClient(local_app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers=AUTH_HEADERS)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_ops_pending_approve_and_reject_flow() -> None:
    approve_cmd = store.add_command("milling-workshop-01", "restart_production_simulator", "medium", "waiting_approval", "pytest")
    reject_cmd = store.add_command("grinding-workshop-01", "restart_production_simulator", "medium", "waiting_approval", "pytest")

    with TestClient(app) as client:
        pending = client.get("/ops/pending-approvals", headers=AUTH_HEADERS)
        approved = client.post(f"/ops/approve/{approve_cmd.id}", headers=AUTH_HEADERS)
        rejected = client.post(f"/ops/reject/{reject_cmd.id}?reason=nope", headers=AUTH_HEADERS)

    assert pending.status_code == 200
    pending_ids = {item["command"]["id"] for item in pending.json()}
    assert approve_cmd.id in pending_ids
    assert approved.status_code == 200
    assert approved.json()["status"] == "pending"
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_ops_escalation_and_metrics_history() -> None:
    with TestClient(app) as client:
        escalated = client.post(
            "/ops/escalate",
            headers=AUTH_HEADERS,
            params={
                "node_code": "turning-workshop-01",
                "issue_type": "manual_review",
                "description": "pytest escalation",
            },
        )
        escalations = client.get("/ops/escalations", headers=AUTH_HEADERS)
        history = client.get("/metrics/history?node_code=turning-workshop-01&limit=5", headers=AUTH_HEADERS)

    assert escalated.status_code == 200
    assert escalated.json()["escalated"] is True
    assert escalations.status_code == 200
    assert any(item["stage"] == "escalation" for item in escalations.json())
    assert history.status_code == 200
    assert len(history.json()) >= 1


def test_ops_issue_command_uses_control_contract() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/ops/issue-command",
            headers=AUTH_HEADERS,
            json={"text": "刷新系统状态", "execute": False},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["status"] == "planned"
    assert payload["plan"]["action"] == "refresh_status"


def test_ops_issue_command_uses_safety_governor() -> None:
    with TestClient(app) as client:
        missing_confirm = client.post(
            "/ops/issue-command",
            headers=AUTH_HEADERS,
            json={"text": "isolate milling", "execute": True},
        )
        control_plane = client.post(
            "/ops/issue-command",
            headers=AUTH_HEADERS,
            json={"text": "isolate cloud", "execute": True, "confirm": "CONFIRM"},
        )

    assert missing_confirm.status_code == 200
    assert missing_confirm.json()["status"] == "blocked-confirmation-required"
    assert missing_confirm.json()["safety"]["reason_code"] == "confirmation_code_required"
    assert control_plane.status_code == 200
    assert control_plane.json()["status"] == "blocked-safety-governor"
    assert control_plane.json()["safety"]["reason_code"] == "control_plane_isolation_blocked"


def test_dispatch_recalculate_returns_dashboard_contract() -> None:
    with TestClient(app) as client:
        response = client.post("/api/ops/dispatch-plan/recalculate", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["accepted"] is True
    assert "dispatch_plan" in payload
    assert "work_orders" in payload
    assert payload["dispatch_plan"]["id"] == "DP-CURRENT"
    assert isinstance(payload["work_orders"], list)


def test_dispatch_approval_executes_and_archives_blocked_tasks() -> None:
    original_tasks = list(store.dispatch_tasks)
    original_audit = list(store.audit_logs)
    store.dispatch_tasks = [
        DispatchTask(
            id=9901,
            product_code="P1",
            product_name="pytest part",
            route=["turning"],
            assigned_node="",
            assigned_machine="waiting-capacity",
            quantity=12,
            priority=1,
            status="blocked",
            reason="pytest capacity block",
        )
    ]
    audit_count = len(store.audit_logs)
    try:
        with TestClient(app) as client:
            rejected = client.post(
                "/api/ops/dispatch-plan/approve",
                headers=AUTH_HEADERS,
                json={"actor": "pytest-supervisor", "confirmation_code": "WRONG"},
            )
            assert rejected.status_code == 200
            assert rejected.json()["status"] == "confirmation_required"
            assert rejected.json()["safety"]["reason_code"] == "confirmation_code_required"
            assert store.dispatch_tasks[0].status == "blocked"

            approved = client.post(
                "/api/ops/dispatch-plan/approve",
                headers=AUTH_HEADERS,
                json={"actor": "pytest-supervisor", "confirmation_code": "CONFIRM"},
            )

        assert approved.status_code == 200
        payload = approved.json()
        assert payload["ok"] is True
        assert payload["executed"] is True
        assert payload["safety"]["reason_code"] == "allowed"
        assert payload["dispatch_plan"]["status"] == "approved_executed"
        assert payload["dispatch_plan"]["result"].startswith("Approved and rerouted")
        assert all(task.status != "blocked" for task in store.dispatch_tasks)
        assert len(store.audit_logs) == audit_count + 1
        assert store.audit_logs[-1].action == "dispatch:approve"
    finally:
        store.dispatch_tasks = original_tasks
        store.audit_logs = original_audit


def test_escalation_approval_matches_issue_type_not_only_node() -> None:
    node_code = "workflow-check-node-escalation-match"
    old_issue = "OLD_MANUAL_REVIEW"
    new_issue = "SPINDLE_TEMP_HIGH"
    original_alerts = list(store.alerts)
    original_events = list(store.incident_events)
    original_diagnoses = list(store.ai_diagnoses)
    try:
        store.escalate_to_human(node_code, old_issue, "pytest old pending escalation")
        store.create_alert(node_code, new_issue, Severity.high, "pytest new issue requiring approval")

        with TestClient(app) as client:
            diagnosed = client.post(f"/api/ai/diagnose/{node_code}-{new_issue}", headers=AUTH_HEADERS)
            queue = client.get("/api/ops/escalations", headers=AUTH_HEADERS)

            assert diagnosed.status_code == 200
            assert diagnosed.json()["escalation"]["issue_id"] == f"{node_code}-{new_issue}"
            matching_items = [
                item for item in queue.json()
                if item.get("node_code") == node_code
            ]
            assert {item.get("issue_id") for item in matching_items} >= {
                f"{node_code}-{old_issue}",
                f"{node_code}-{new_issue}",
            }
            new_item = next(item for item in matching_items if item.get("issue_id") == f"{node_code}-{new_issue}")
            approved = client.post(
                f"/api/ops/escalations/{new_item['id']}/decision",
                headers=AUTH_HEADERS,
                json={"actor": "pytest-supervisor", "decision": "approve", "confirmation_code": "CONFIRM"},
            )

        assert approved.status_code == 200
        closed = approved.json()["effect"]["verification"]["closed_alerts"]
        assert closed
        assert all(item == f"{node_code}-{new_issue}" for item in closed)
        assert any(
            alert.node_code == node_code
            and alert.alert_type == old_issue
            and alert.status not in {"closed", "resolved"}
            for alert in store.alerts
        )
    finally:
        store.alerts = original_alerts
        store.incident_events = original_events
        store.ai_diagnoses = original_diagnoses


def test_issue_id_parser_preserves_numeric_node_suffix() -> None:
    from app.routers.compat import _parse_issue_id

    node_code, alert_type = _parse_issue_id("milling-workshop-01-COOLANT_FLOW_LOW")

    assert node_code == "milling-workshop-01"
    assert alert_type == "COOLANT_FLOW_LOW"
