import hashlib

from app.core.auth import decode_access_token
from app.core.config import settings
from app.core.database import get_db
from app.core.principals import (
    authenticate_node_credential,
    provision_node_credential,
    revoke_node_credentials,
)
from app.main import app
from app.store import store
from fastapi.testclient import TestClient


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/auth/login",
        json={"operator": "admin", "password": "mini-ogas-dev-token"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_human_jwt_contains_unified_principal_identity() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/auth/login",
            json={"operator": "admin", "password": "mini-ogas-dev-token"},
        )

    claims = decode_access_token(login.json()["access_token"])
    assert claims is not None
    assert claims["principal_id"] == "user:admin"
    assert claims["principal_type"] == "human"
    assert claims["node_code"] == ""


def test_node_credential_is_bound_rotatable_revocable_and_never_stored_plaintext(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "allow_legacy_node_token_auth", False)
    node_code = "credential-test-node"
    other_node = "milling-workshop-01"

    with TestClient(app) as client:
        admin = _admin_headers(client)
        first_issue = client.post(
            f"/security/node-credentials/{node_code}/rotate",
            headers=admin,
        )
        assert first_issue.status_code == 200
        first_token = first_issue.json()["token"]

        accepted = client.put(
            f"/nodes/{node_code}/heartbeat",
            json={
                "node_code": node_code,
                "status": "running",
                "uptime_seconds": 0,
                "local_db_size_bytes": 0,
            },
            headers={"X-OGAS-Token": first_token},
        )
        node_bearer_denied = client.get(
            "/security/whoami",
            headers={"Authorization": f"Bearer {first_token}"},
        )
        cross_node = client.get(
            f"/agents/{other_node}/commands/pending",
            headers={"X-OGAS-Token": first_token},
        )
        cross_heartbeat_body = client.post(
            "/node-heartbeats",
            json={"node_code": other_node, "status": "running"},
            headers={"X-OGAS-Token": first_token},
        )
        cross_metric_body = client.post(
            "/metrics",
            json={
                "node_code": other_node,
                "cpu_usage": 10,
                "memory_usage": 20,
                "disk_usage": 30,
                "network_in": 1,
                "network_out": 1,
                "db_latency_ms": 1,
                "api_latency_ms": 1,
            },
            headers={"X-OGAS-Token": first_token},
        )
        cross_record_body = client.post(
            "/node-records/sync",
            json={"node_code": other_node, "records": []},
            headers={"X-OGAS-Token": first_token},
        )

        second_issue = client.post(
            f"/security/node-credentials/{node_code}/rotate",
            headers=admin,
        )
        second_token = second_issue.json()["token"]
        old_denied = client.put(
            f"/nodes/{node_code}/heartbeat",
            json={
                "node_code": node_code,
                "status": "running",
                "uptime_seconds": 0,
                "local_db_size_bytes": 0,
            },
            headers={"X-OGAS-Token": first_token},
        )
        new_accepted = client.put(
            f"/nodes/{node_code}/heartbeat",
            json={
                "node_code": node_code,
                "status": "running",
                "uptime_seconds": 0,
                "local_db_size_bytes": 0,
            },
            headers={"X-OGAS-Token": second_token},
        )
        revoked = client.post(
            f"/security/node-credentials/{node_code}/revoke",
            headers=admin,
        )
        revoked_denied = client.put(
            f"/nodes/{node_code}/heartbeat",
            json={
                "node_code": node_code,
                "status": "running",
                "uptime_seconds": 0,
                "local_db_size_bytes": 0,
            },
            headers={"X-OGAS-Token": second_token},
        )
        retired = client.post(
            f"/nodes/{node_code}/retire",
            json={"confirmation_code": "CONFIRM"},
            headers=admin,
        )

    with get_db() as db:
        rows = db.execute(
            """SELECT token_hash, revoked_at
               FROM principal_credentials
               WHERE principal_id = ? ORDER BY created_at""",
            (f"node:{node_code}",),
        ).fetchall()

    assert accepted.status_code == 200
    assert node_bearer_denied.status_code == 401
    assert cross_node.status_code == 403
    assert cross_heartbeat_body.status_code == 403
    assert cross_metric_body.status_code == 403
    assert cross_record_body.status_code == 403
    assert second_issue.status_code == 200
    assert second_token != first_token
    assert old_denied.status_code == 401
    assert new_accepted.status_code == 200
    assert revoked.status_code == 200
    assert revoked_denied.status_code == 401
    assert retired.status_code == 200
    assert len(rows) == 2
    assert {str(row["token_hash"]) for row in rows} == {
        hashlib.sha256(first_token.encode()).hexdigest(),
        hashlib.sha256(second_token.encode()).hexdigest(),
    }
    assert all(row["revoked_at"] for row in rows)
    assert all(
        first_token not in str(value) and second_token not in str(value)
        for row in rows
        for value in row
    )


def test_bootstrap_configuration_never_resurrects_a_revoked_node_token() -> None:
    node_code = "bootstrap-revocation-test-node"
    token = "bootstrap-revocation-test-token-0123456789abcdef"

    assert provision_node_credential(node_code, token) is True
    assert authenticate_node_credential(token) is not None
    assert revoke_node_credentials(node_code) == 1
    assert provision_node_credential(node_code, token) is False
    assert authenticate_node_credential(token) is None


def test_service_and_ai_agent_principals_are_restricted_and_revocable() -> None:
    with TestClient(app) as client:
        admin = _admin_headers(client)
        service_issue = client.post(
            "/security/service-credentials/reporting-service/rotate",
            headers=admin,
        )
        ai_issue = client.post(
            "/security/ai-agent-credentials/diagnostics-agent/rotate",
            headers=admin,
        )
        assert service_issue.status_code == 200
        assert ai_issue.status_code == 200
        service_token = service_issue.json()["token"]
        ai_token = ai_issue.json()["token"]

        service_identity = client.get(
            "/security/whoami",
            headers={"Authorization": f"Bearer {service_token}"},
        )
        ai_identity = client.get(
            "/security/whoami",
            headers={"Authorization": f"Bearer {ai_token}"},
        )
        service_write = client.post(
            "/production-plans/generate",
            headers={"Authorization": f"Bearer {service_token}"},
        )
        service_credential_admin = client.post(
            "/security/service-credentials/forbidden-service/rotate",
            headers={"Authorization": f"Bearer {service_token}"},
        )
        command_count = len(store.commands)
        suggestion = client.post(
            "/ai/suggestions",
            json={
                "node_code": "milling-workshop-01",
                "risk_level": "high",
                "recommendation": "Inspect spindle cooling before changing any setpoint.",
                "evidence": {"spindle_temp": 81.5},
            },
            headers={"Authorization": f"Bearer {ai_token}"},
        )
        suggestion_body = suggestion.json()
        command_id = suggestion_body["command_id"]
        pending_for_node = store.pending_commands_for_node("milling-workshop-01")
        pending_reviews = client.get("/ops/pending-approvals", headers=admin)
        approved = client.post(
            f"/ops/approve/{command_id}?confirmation_code=CONFIRM",
            headers=admin,
        )
        retry = client.post(f"/ops/commands/{command_id}/retry", headers=admin)
        ai_control = client.post(
            "/simulation/step",
            headers={"Authorization": f"Bearer {ai_token}"},
        )
        revoked = client.post(
            "/security/ai-agent-credentials/diagnostics-agent/revoke",
            headers=admin,
        )
        revoked_identity = client.get(
            "/security/whoami",
            headers={"Authorization": f"Bearer {ai_token}"},
        )

    with get_db() as db:
        stored = db.execute(
            """SELECT principal_id, node_code, risk_level, status, command_id,
                      decided_at
               FROM ai_suggestions WHERE suggestion_id = ?""",
            (suggestion_body["suggestion_id"],),
        ).fetchone()

    assert service_identity.status_code == 200
    assert service_identity.json()["principal_type"] == "service"
    assert service_write.status_code == 403
    assert service_credential_admin.status_code == 403
    assert ai_identity.status_code == 200
    assert ai_identity.json()["principal_type"] == "ai_agent"
    assert suggestion.status_code == 201
    assert suggestion_body["status"] == "pending_human_review"
    assert suggestion_body["approval_url"] == f"/ops/approve/{command_id}"
    assert len(store.commands) == command_count + 1
    assert pending_for_node == []
    assert pending_reviews.status_code == 200
    review = next(
        item for item in pending_reviews.json()
        if item["command"]["id"] == command_id
    )
    assert review["ai_suggestion"]["suggestion_id"] == suggestion_body["suggestion_id"]
    assert approved.status_code == 200
    assert approved.json()["status"] == "verified"
    assert approved.json()["suggestion_status"] == "accepted"
    assert retry.status_code == 409
    assert store.pending_commands_for_node("milling-workshop-01") == []
    assert ai_control.status_code == 403
    assert revoked.status_code == 200
    assert revoked_identity.status_code == 401
    assert tuple(stored) == (
        "ai:diagnostics-agent",
        "milling-workshop-01",
        "high",
        "accepted",
        command_id,
        stored["decided_at"],
    )
    assert stored["decided_at"] is not None
