from __future__ import annotations

from app.core.database import get_db
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


def _ai_headers(client: TestClient, admin: dict[str, str], name: str) -> dict[str, str]:
    issued = client.post(
        f"/security/ai-agent-credentials/{name}/rotate",
        headers=admin,
    )
    assert issued.status_code == 200
    return {"Authorization": f"Bearer {issued.json()['token']}"}


def test_high_risk_suggestion_rejection_closes_command_and_suggestion() -> None:
    with TestClient(app) as client:
        admin = _admin_headers(client)
        ai = _ai_headers(client, admin, "stage-g-reject-agent")
        submitted = client.post(
            "/ai/suggestions",
            json={
                "node_code": "turning-workshop-01",
                "risk_level": "critical",
                "recommendation": "Isolate the spindle controller pending a human safety review.",
                "evidence": {"source": "stage-g-test", "confidence": 0.91},
            },
            headers=ai,
        )
        assert submitted.status_code == 201
        body = submitted.json()
        command_id = body["command_id"]

        rejected = client.post(
            f"/ops/reject/{command_id}?reason=insufficient+evidence",
            headers=admin,
        )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["suggestion_status"] == "rejected"
    assert store.pending_commands_for_node("turning-workshop-01") == []
    with get_db() as db:
        row = db.execute(
            """SELECT status, command_id, decided_at FROM ai_suggestions
               WHERE suggestion_id = ?""",
            (body["suggestion_id"],),
        ).fetchone()
    assert row["status"] == "rejected"
    assert row["command_id"] == command_id
    assert row["decided_at"] is not None


def test_rule_diagnosis_creates_auditable_human_only_review() -> None:
    node_code = "grinding-workshop-01"
    with TestClient(app) as client:
        admin = _admin_headers(client)
        diagnosed = client.post(
            "/ai/diagnose",
            json={"node_code": node_code, "provider": "rule_fallback"},
            headers=admin,
        )
        assert diagnosed.status_code == 200
        suggestion = diagnosed.json()["suggestion"]
        command_id = suggestion["command_id"]
        command = next(item for item in store.commands if item.id == command_id)

        assert suggestion["status"] == "pending_human_review"
        assert command.status == "waiting_approval"
        assert command.parameters["node_executable"] is False
        assert store.pending_commands_for_node(node_code) == []

        approved = client.post(f"/ops/approve/{command_id}", headers=admin)

    assert approved.status_code == 200
    assert approved.json()["status"] == "verified"
    assert approved.json()["suggestion_status"] == "accepted"
    assert store.pending_commands_for_node(node_code) == []
    with get_db() as db:
        row = db.execute(
            """SELECT principal_id, status, command_id FROM ai_suggestions
               WHERE suggestion_id = ?""",
            (suggestion["suggestion_id"],),
        ).fetchone()
    assert tuple(row) == ("ai:dispatcher", "accepted", command_id)


def test_low_risk_suggestion_remains_advisory_without_node_command() -> None:
    with TestClient(app) as client:
        admin = _admin_headers(client)
        ai = _ai_headers(client, admin, "stage-g-low-risk-agent")
        command_count = len(store.commands)
        submitted = client.post(
            "/ai/suggestions",
            json={
                "node_code": "milling-workshop-01",
                "risk_level": "low",
                "recommendation": "Review the next maintenance window for optional inspection.",
                "evidence": {"source": "stage-g-test"},
            },
            headers=ai,
        )

    assert submitted.status_code == 201
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["command_id"] is None
    assert submitted.json()["approval_url"] is None
    assert len(store.commands) == command_count
