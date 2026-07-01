from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.store import store


def test_persisted_admin_login_issues_bearer_jwt_and_rejects_machine_token() -> None:
    with TestClient(app) as client:
        login = client.post("/auth/login", json={"operator": "admin", "password": "mini-ogas-dev-token"})
        assert login.status_code == 200
        access_token = login.json()["access_token"]

        authorized = client.get("/summary", headers={"Authorization": f"Bearer {access_token}"})
        assert authorized.status_code == 200

        rejected = client.get("/summary", headers={"X-OGAS-Token": "wrong-token"})
        assert rejected.status_code == 401


def test_node_ingest_stays_separate_from_dashboard_bearer_auth() -> None:
    with TestClient(app) as client:
        response = client.get("/summary", headers={"X-OGAS-Token": "mini-ogas-dev-token"})
        # Legacy test compatibility is enabled by conftest. Real deployments
        # disable it through the default Settings value.
        assert response.status_code == 200

        denied = client.post("/node-heartbeats", json={}, headers={"Authorization": "Bearer invalid"})
        assert denied.status_code == 401


def test_production_snapshot_count_is_explicit_and_excludes_logical_cloud_nodes() -> None:
    with TestClient(app) as client:
        snapshot = client.get("/api/dashboard/snapshot", headers={"X-OGAS-Token": "mini-ogas-dev-token"})

    assert snapshot.status_code == 200
    system = snapshot.json()["system"]
    assert system["nodes_expected"] == len(settings.expected_production_nodes) == 3
    assert system["logical_nodes_registered"] == 5


def test_legacy_browser_machine_token_is_rejected_when_compatibility_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "allow_legacy_api_token_auth", False)
    with TestClient(app) as client:
        rejected = client.get("/summary", headers={"X-OGAS-Token": "mini-ogas-dev-token"})
        login = client.post("/auth/login", json={"operator": "admin", "password": "mini-ogas-dev-token"})
        accepted = client.get("/summary", headers={"Authorization": f"Bearer {login.json()['access_token']}"})

    assert rejected.status_code == 401
    assert accepted.status_code == 200


def test_node_retire_is_admin_bearer_operation_not_node_ingest(monkeypatch) -> None:
    monkeypatch.setattr(settings, "allow_legacy_api_token_auth", False)
    node_code = "workflow-check-node-pytest-retire"
    with TestClient(app) as client:
        heartbeat = client.post(
            "/node-heartbeats",
            json={"node_code": node_code, "status": "running"},
            headers={"X-OGAS-Token": settings.node_ingest_token},
        )
        login = client.post("/auth/login", json={"operator": "admin", "password": "mini-ogas-dev-token"})
        denied = client.post(
            f"/nodes/{node_code}/retire",
            json={"actor": "pytest"},
            headers={"X-OGAS-Token": settings.node_ingest_token},
        )
        retired = client.post(
            f"/nodes/{node_code}/retire",
            json={"actor": "pytest"},
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert heartbeat.status_code == 200
    assert denied.status_code == 401
    assert retired.status_code == 200
    assert retired.json()["status"] == "retired"
    assert node_code not in store.nodes


def test_high_risk_alert_human_approval_closes_active_queues(monkeypatch) -> None:
    monkeypatch.setattr(settings, "allow_legacy_api_token_auth", False)
    node_code = "workflow-check-node-pytest-approval"
    issue_id = f"{node_code}-SPINDLE_TEMP_HIGH"
    with TestClient(app) as client:
        login = client.post("/auth/login", json={"operator": "admin", "password": "mini-ogas-dev-token"})
        auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
        heartbeat = client.post(
            "/node-heartbeats",
            json={
                "node_code": node_code,
                "status": "fault",
                "production": {"machine_code": "QA-MILL", "workshop_type": "milling", "spindle_temp": 94},
                "alarms": [{"type": "SPINDLE_TEMP_HIGH", "severity": "critical", "status": "open"}],
            },
            headers={"X-OGAS-Token": settings.node_ingest_token},
        )
        confirmed = client.post(f"/alerts/{issue_id}/confirm", json={"operator": "pytest"}, headers=auth)
        diagnosed = client.post(f"/ai/diagnose/{issue_id}", headers=auth)
        queue = client.get("/ops/escalations", headers=auth).json()
        queue_item = next(item for item in queue if item.get("issue_id") == issue_id)
        denied = client.post(
            f"/ops/escalations/{queue_item['id']}/decision",
            json={"actor": "pytest", "decision": "approve", "confirmation_code": ""},
            headers=auth,
        )
        approved = client.post(
            f"/ops/escalations/{queue_item['id']}/decision",
            json={"actor": "pytest", "decision": "approve", "confirmation_code": "CONFIRM"},
            headers=auth,
        )
        active_alerts = client.get("/alerts", headers=auth).json()
        active_queue = client.get("/ops/escalations", headers=auth).json()
        client.post(f"/nodes/{node_code}/retire", json={"actor": "pytest"}, headers=auth)

    assert heartbeat.status_code == 200
    assert confirmed.json()["lifecycle"]["status"] == "confirmed"
    assert diagnosed.json()["decision"]["requires_human"] is True
    assert denied.json()["error"] == "confirmation_code_required"
    assert denied.json()["safety"]["reason_code"] == "confirmation_code_required"
    assert approved.json()["effect"]["verification"]["issue_closed"] is True
    assert not any(item.get("issue_id") == issue_id for item in active_alerts)
    assert not any(item.get("issue_id") == issue_id for item in active_queue)
