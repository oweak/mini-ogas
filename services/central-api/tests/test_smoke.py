from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app, setup_middleware
from app.store import store

AUTH_HEADERS = {"X-OGAS-Token": "mini-ogas-dev-token"}


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
    assert payload["order"]["product_name"] == "变速箱齿轮"
    assert any(plan["product_code"] == "A3" for plan in payload["plans"])


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
            },
        )
        pending = client.get(f"/api/nodes/{node_code}/pending-commands", headers=AUTH_HEADERS)

    assert heartbeat.status_code == 200
    assert heartbeat.json()["local_db_size_bytes"] == 4096
    assert pending.status_code == 200
    assert isinstance(pending.json(), list)


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
