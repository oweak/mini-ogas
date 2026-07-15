from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from app.core.auth import issue_access_token
from app.core.database import get_db
from app.core.outbox import outbox_repository
from app.main import app
from fastapi.testclient import TestClient


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"operator": "admin", "password": "mini-ogas-dev-token"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _post(
    client: TestClient,
    headers: dict[str, str],
    path: str,
    payload: dict | None = None,
    expected: int = 201,
) -> dict:
    response = client.post(path, headers=headers, json=payload or {})
    assert response.status_code == expected, response.text
    return response.json()


@pytest.fixture(scope="module")
def execution_master() -> dict:
    client = TestClient(app)
    client.__enter__()
    headers = _auth_headers(client)

    hierarchy = [
        ("P3-ENTERPRISE", "P3 Enterprise", "enterprise", None),
        ("P3-SITE", "P3 Site", "site", "P3-ENTERPRISE"),
        ("P3-AREA", "P3 Area", "area", "P3-SITE"),
        ("P3-LINE", "P3 Line", "line", "P3-AREA"),
        ("P3-CELL", "P3 Cell", "cell", "P3-LINE"),
    ]
    for code, name, unit_type, parent in hierarchy:
        payload = {"unit_code": code, "name": name, "unit_type": unit_type}
        if parent:
            payload["parent_code"] = parent
        _post(client, headers, "/master-data/organization-units", payload)
    _post(client, headers, "/master-data/uoms", {
        "uom_code": "P3-EA", "name": "Each", "dimension": "count", "scale": 1,
    })
    _post(client, headers, "/master-data/uoms", {
        "uom_code": "P3-KG", "name": "Kilogram", "dimension": "mass", "scale": 1,
    })
    _post(client, headers, "/master-data/materials", {
        "material_code": "P3-STEEL", "name": "P3 Steel", "material_type": "raw",
        "base_uom_code": "P3-KG",
    })
    _post(client, headers, "/master-data/materials", {
        "material_code": "P3-SHAFT", "name": "P3 Shaft", "material_type": "finished",
        "base_uom_code": "P3-EA",
    })
    _post(client, headers, "/master-data/products", {
        "product_code": "P3-SHAFT", "name": "P3 Governed Shaft", "material_code": "P3-SHAFT",
    })
    _post(client, headers, "/master-data/equipment", {
        "equipment_code": "P3-LATHE-01", "name": "P3 Lathe", "equipment_type": "lathe",
        "organization_unit_code": "P3-CELL",
    })
    _post(client, headers, "/master-data/equipment/P3-LATHE-01/capabilities", {
        "capability_code": "P3-TURNING", "name": "P3 precision turning",
    })
    _post(client, headers, "/master-data/skills", {
        "skill_code": "P3-TURN-L2", "name": "P3 Turning Level 2", "level_min": 2,
    })
    _post(client, headers, "/master-data/personnel", {
        "personnel_code": "P3-OP-QUAL", "display_name": "P3 Qualified Operator",
    })
    now = datetime.now(UTC)
    _post(client, headers, "/master-data/qualifications", {
        "personnel_code": "P3-OP-QUAL", "skill_code": "P3-TURN-L2", "level": 2,
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_to": (now + timedelta(days=365)).isoformat(),
        "evidence_reference": "CERT-P3-001",
    })
    _post(client, headers, "/master-data/calendars", {
        "calendar_code": "P3-CALENDAR", "name": "P3 Calendar", "timezone": "Asia/Shanghai",
    })
    _post(client, headers, "/master-data/calendars/P3-CALENDAR/shifts", {
        "shift_code": "P3-DAY", "name": "P3 Day", "start_time": "08:00", "end_time": "16:00",
    })
    _post(client, headers, "/master-data/documents", {
        "document_code": "P3-WI-TURN", "title": "P3 Turning Instruction",
        "document_type": "work_instruction",
    })
    document_revision = _post(
        client,
        headers,
        "/master-data/documents/P3-WI-TURN/revisions",
        {"revision": "A", "content": "Use the approved P3 turning setup."},
    )
    _post(
        client,
        headers,
        f"/master-data/document-revisions/{document_revision['id']}/approve",
        expected=200,
    )
    _post(
        client,
        headers,
        f"/master-data/document-revisions/{document_revision['id']}/effective",
        expected=200,
    )
    _post(client, headers, "/master-data/boms", {
        "bom_code": "P3-BOM-SHAFT", "product_code": "P3-SHAFT", "name": "P3 Shaft BOM",
    })
    bom_revision = _post(client, headers, "/master-data/boms/P3-BOM-SHAFT/revisions", {
        "revision": 1,
        "items": [{"material_code": "P3-STEEL", "quantity": 2.5, "uom_code": "P3-KG"}],
    })
    _post(
        client,
        headers,
        f"/master-data/bom-revisions/{bom_revision['id']}/approve",
        expected=200,
    )
    _post(
        client,
        headers,
        f"/master-data/bom-revisions/{bom_revision['id']}/effective",
        expected=200,
    )
    _post(client, headers, "/master-data/routings", {
        "routing_code": "P3-RT-SHAFT", "product_code": "P3-SHAFT", "name": "P3 Routing",
    })
    routing_revision = _post(client, headers, "/master-data/routings/P3-RT-SHAFT/revisions", {
        "revision": 1,
        "operations": [{
            "sequence": 10,
            "operation_code": "P3-OP-TURN",
            "name": "P3 Precision Turn",
            "capability_code": "P3-TURNING",
            "required_skill_code": "P3-TURN-L2",
            "required_skill_level": 2,
            "document_code": "P3-WI-TURN",
            "standard_time_seconds": 135,
        }],
    })
    _post(
        client,
        headers,
        f"/master-data/routing-revisions/{routing_revision['id']}/approve",
        expected=200,
    )
    _post(
        client,
        headers,
        f"/master-data/routing-revisions/{routing_revision['id']}/effective",
        expected=200,
    )

    yield {
        "client": client,
        "headers": headers,
        "bom_revision_id": bom_revision["id"],
        "routing_revision_id": routing_revision["id"],
        "document_revision_id": document_revision["id"],
    }
    client.__exit__(None, None, None)


def _new_execution(context: dict, suffix: str, quantity: int = 10) -> dict:
    client = context["client"]
    headers = context["headers"]
    work_order_code = f"P3-WO-{suffix}"
    production_order_code = f"P3-PO-{suffix}"
    _post(client, headers, "/master-data/work-orders", {
        "work_order_code": work_order_code,
        "product_code": "P3-SHAFT",
        "quantity": quantity,
        "bom_revision_id": context["bom_revision_id"],
        "routing_revision_id": context["routing_revision_id"],
        "document_revision_ids": [context["document_revision_id"]],
        "calendar_code": "P3-CALENDAR",
        "shift_code": "P3-DAY",
        "operation_assignments": [{
            "sequence": 10,
            "equipment_code": "P3-LATHE-01",
            "personnel_code": "P3-OP-QUAL",
        }],
    })
    _post(
        client,
        headers,
        f"/master-data/work-orders/{work_order_code}/release",
        expected=200,
    )
    production_order = _post(client, headers, "/execution/production-orders", {
        "production_order_code": production_order_code,
        "product_code": "P3-SHAFT",
        "quantity": quantity,
        "priority": 5,
        "due_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
    })
    _post(
        client,
        headers,
        f"/execution/production-orders/{production_order_code}/work-orders/{work_order_code}/attach",
        {"idempotency_key": f"attach-{suffix}"},
        expected=200,
    )
    _post(
        client,
        headers,
        f"/execution/production-orders/{production_order_code}/release",
        {"idempotency_key": f"release-{suffix}", "reason": "approved plan"},
        expected=200,
    )
    dispatched = _post(
        client,
        headers,
        f"/execution/work-orders/{work_order_code}/dispatch",
        {"idempotency_key": f"dispatch-{suffix}"},
        expected=200,
    )
    return {
        "production_order": production_order,
        "production_order_code": production_order_code,
        "work_order_code": work_order_code,
        "task": dispatched["tasks"][0],
    }


def _prepare_running(context: dict, suffix: str, quantity: int = 10) -> dict:
    execution = _new_execution(context, suffix, quantity)
    client = context["client"]
    headers = context["headers"]
    task_id = execution["task"]["id"]
    _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/setup/start",
        {"idempotency_key": f"setup-start-{suffix}"},
        expected=200,
    )
    _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/setup/complete",
        {
            "idempotency_key": f"setup-complete-{suffix}",
            "evidence_reference": f"SETUP-EVIDENCE-{suffix}",
            "parameters": {"chuck_pressure_bar": 18.5},
        },
        expected=200,
    )
    started = _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": f"start-{suffix}"},
        expected=200,
    )
    assert started["status"] == "running"
    return execution


def test_operation_cannot_skip_required_setup(execution_master: dict) -> None:
    execution = _new_execution(execution_master, "NO-SKIP")
    task_id = execution["task"]["id"]
    response = execution_master["client"].post(
        f"/execution/tasks/{task_id}/start",
        headers=execution_master["headers"],
        json={"idempotency_key": "skip-setup"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_OPERATION_TRANSITION"


def test_completion_requires_quantity_conservation_and_evidence(execution_master: dict) -> None:
    execution = _prepare_running(execution_master, "COMPLETE", quantity=10)
    client = execution_master["client"]
    headers = execution_master["headers"]
    task_id = execution["task"]["id"]

    premature = client.post(
        f"/execution/tasks/{task_id}/complete",
        headers=headers,
        json={"idempotency_key": "complete-before-quantity", "evidence_reference": "INSPECTION-1"},
    )
    assert premature.status_code == 409
    assert premature.json()["detail"]["code"] == "QUANTITY_NOT_CONSERVED"

    _post(client, headers, f"/execution/tasks/{task_id}/quantity-reports", {
        "report_id": "P3-REPORT-COMPLETE-1",
        "good_quantity": 9,
        "scrap_quantity": 1,
        "rework_quantity": 0,
        "evidence_reference": "COUNTER-P3-001",
        "occurred_at": datetime.now(UTC).isoformat(),
    })
    no_evidence = client.post(
        f"/execution/tasks/{task_id}/complete",
        headers=headers,
        json={"idempotency_key": "complete-no-evidence", "evidence_reference": ""},
    )
    assert no_evidence.status_code == 409
    assert no_evidence.json()["detail"]["code"] == "COMPLETION_EVIDENCE_REQUIRED"

    completed = _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/complete",
        {"idempotency_key": "complete-valid", "evidence_reference": "INSPECTION-P3-001"},
        expected=200,
    )
    assert completed["status"] == "completed"
    state = client.get(
        f"/execution/work-orders/{execution['work_order_code']}", headers=headers
    )
    assert state.status_code == 200
    assert state.json()["execution_status"] == "completed"
    assert state.json()["production_order_status"] == "completed"


def test_quantity_report_is_idempotent_and_cannot_exceed_plan(execution_master: dict) -> None:
    execution = _prepare_running(execution_master, "QUANTITY", quantity=10)
    client = execution_master["client"]
    headers = execution_master["headers"]
    task_id = execution["task"]["id"]
    payload = {
        "report_id": "P3-REPORT-IDEMPOTENT",
        "good_quantity": 6,
        "scrap_quantity": 0,
        "rework_quantity": 0,
        "evidence_reference": "COUNTER-P3-002",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    first = _post(client, headers, f"/execution/tasks/{task_id}/quantity-reports", payload)
    second = _post(client, headers, f"/execution/tasks/{task_id}/quantity-reports", payload)
    assert second["id"] == first["id"]

    over = client.post(
        f"/execution/tasks/{task_id}/quantity-reports",
        headers=headers,
        json={
            **payload,
            "report_id": "P3-REPORT-OVER",
            "good_quantity": 5,
            "evidence_reference": "COUNTER-P3-003",
        },
    )
    assert over.status_code == 409
    assert over.json()["detail"]["code"] == "QUANTITY_EXCEEDS_PLAN"

    replay = client.get(
        f"/execution/work-orders/{execution['work_order_code']}/replay", headers=headers
    )
    assert replay.status_code == 200
    reports = replay.json()["quantity_reports"]
    assert [item["report_id"] for item in reports].count("P3-REPORT-IDEMPOTENT") == 1
    assert not any(item["report_id"] == "P3-REPORT-OVER" for item in reports)


def test_hold_pause_resume_and_downtime_are_durable_history(execution_master: dict) -> None:
    execution = _new_execution(execution_master, "CONTROL", quantity=4)
    client = execution_master["client"]
    headers = execution_master["headers"]
    task_id = execution["task"]["id"]

    held = _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/hold",
        {"idempotency_key": "hold-control", "reason": "fixture verification"},
        expected=200,
    )
    assert held["status"] == "held"
    released = _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/release-hold",
        {"idempotency_key": "release-hold-control", "reason": "fixture verified"},
        expected=200,
    )
    assert released["status"] == "dispatched"

    _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/setup/start",
        {"idempotency_key": "setup-start-control"},
        expected=200,
    )
    _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/setup/complete",
        {
            "idempotency_key": "setup-complete-control",
            "evidence_reference": "SETUP-CONTROL",
            "parameters": {},
        },
        expected=200,
    )
    _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": "start-control"},
        expected=200,
    )
    paused = _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/pause",
        {"idempotency_key": "pause-control", "reason": "planned check"},
        expected=200,
    )
    assert paused["status"] == "paused"
    resumed = _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/resume",
        {"idempotency_key": "resume-control", "reason": "check complete"},
        expected=200,
    )
    assert resumed["status"] == "running"
    downtime = _post(client, headers, f"/execution/tasks/{task_id}/downtime", {
        "downtime_code": "P3-DT-001",
        "idempotency_key": "downtime-control",
        "reason": "coolant inspection",
        "evidence_reference": "MAINT-P3-001",
    })
    assert downtime["status"] == "open"
    task = client.get(f"/execution/tasks/{task_id}", headers=headers).json()
    assert task["status"] == "paused"
    ended = _post(
        client,
        headers,
        f"/execution/downtime/{downtime['id']}/end",
        {"idempotency_key": "downtime-end-control", "evidence_reference": "MAINT-P3-002"},
        expected=200,
    )
    assert ended["status"] == "closed"
    assert client.get(f"/execution/tasks/{task_id}", headers=headers).json()["status"] == "running"

    history = client.get(f"/execution/tasks/{task_id}/history", headers=headers)
    assert history.status_code == 200
    statuses = [item["to_status"] for item in history.json()]
    assert statuses == [
        "dispatched", "held", "dispatched", "setup", "ready", "running",
        "paused", "running", "paused", "running",
    ]


def test_close_requires_completed_tasks_and_closes_aggregates(execution_master: dict) -> None:
    execution = _prepare_running(execution_master, "CLOSE", quantity=3)
    client = execution_master["client"]
    headers = execution_master["headers"]
    task_id = execution["task"]["id"]

    early_close = client.post(
        f"/execution/work-orders/{execution['work_order_code']}/close",
        headers=headers,
        json={"idempotency_key": "wo-close-early"},
    )
    assert early_close.status_code == 409
    assert early_close.json()["detail"]["code"] == "WORK_ORDER_NOT_COMPLETE"

    _post(client, headers, f"/execution/tasks/{task_id}/quantity-reports", {
        "report_id": "P3-REPORT-CLOSE",
        "good_quantity": 3,
        "scrap_quantity": 0,
        "rework_quantity": 0,
        "evidence_reference": "COUNTER-P3-CLOSE",
        "occurred_at": datetime.now(UTC).isoformat(),
    })
    _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/complete",
        {
            "idempotency_key": "operation-complete-close",
            "evidence_reference": "INSPECTION-P3-CLOSE",
        },
        expected=200,
    )
    _post(
        client,
        headers,
        f"/execution/tasks/{task_id}/close",
        {"idempotency_key": "operation-close"},
        expected=200,
    )
    work_order = _post(
        client,
        headers,
        f"/execution/work-orders/{execution['work_order_code']}/close",
        {"idempotency_key": "wo-close"},
        expected=200,
    )
    assert work_order["execution_status"] == "closed"
    production_order = _post(
        client,
        headers,
        f"/execution/production-orders/{execution['production_order_code']}/close",
        {"idempotency_key": "po-close"},
        expected=200,
    )
    assert production_order["status"] == "closed"


def test_execution_history_is_append_only(execution_master: dict) -> None:
    execution = _new_execution(execution_master, "IMMUTABLE", quantity=2)
    task_id = execution["task"]["id"]
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM operation_status_history WHERE operation_task_id=? ORDER BY id LIMIT 1",
            (task_id,),
        ).fetchone()
    history_id = int(dict(row)["id"])
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                "UPDATE operation_status_history SET to_status='fake' WHERE id=?",
                (history_id,),
            )
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute("DELETE FROM operation_status_history WHERE id=?", (history_id,))


def test_database_rejects_direct_state_jump_and_quantity_overrun(
    execution_master: dict,
) -> None:
    guarded = _new_execution(execution_master, "DB-STATE-GUARD", quantity=2)
    guarded_task_id = guarded["task"]["id"]
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                """UPDATE operation_tasks
                   SET status='completed', completion_evidence_reference='BYPASS'
                   WHERE id=?""",
                (guarded_task_id,),
            )
    assert execution_master["client"].get(
        f"/execution/tasks/{guarded_task_id}", headers=execution_master["headers"]
    ).json()["status"] == "dispatched"

    running = _prepare_running(execution_master, "DB-QUANTITY-GUARD", quantity=2)
    running_task_id = running["task"]["id"]
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                """INSERT INTO operation_quantity_reports (
                       tenant_id, site_id, operation_task_id, report_id, good_quantity,
                       scrap_quantity, rework_quantity, evidence_reference, occurred_at,
                       reported_by
                   ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)""",
                (
                    "tenant-test",
                    "site-test",
                    running_task_id,
                    "P3-DIRECT-OVERREPORT",
                    3,
                    "BYPASS",
                    datetime.now(UTC).isoformat(),
                    "bypass-attempt",
                ),
            )
    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(*) AS count FROM operation_quantity_reports WHERE report_id=?",
            ("P3-DIRECT-OVERREPORT",),
        ).fetchone()
    assert int(dict(count)["count"]) == 0


def test_execution_mutation_requires_permission(execution_master: dict) -> None:
    viewer_token = issue_access_token({
        "username": "phase3-viewer",
        "display_name": "Phase 3 Viewer",
        "roles": ["viewer"],
        "permissions": ["node:view"],
    })
    response = execution_master["client"].post(
        "/execution/production-orders",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={
            "production_order_code": "P3-PO-DENIED",
            "product_code": "P3-SHAFT",
            "quantity": 1,
            "priority": 5,
            "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 403


def test_execution_write_rolls_back_when_transactional_outbox_fails(
    execution_master: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(outbox_repository, "enqueue_in_transaction", lambda *_args: False)
    response = execution_master["client"].post(
        "/execution/production-orders",
        headers=execution_master["headers"],
        json={
            "production_order_code": "P3-PO-ATOMIC-ROLLBACK",
            "product_code": "P3-SHAFT",
            "quantity": 1,
            "priority": 5,
            "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 500
    with get_db() as db:
        order_count = db.execute(
            "SELECT COUNT(*) AS count FROM production_orders WHERE production_order_code=?",
            ("P3-PO-ATOMIC-ROLLBACK",),
        ).fetchone()
        audit_count = db.execute(
            "SELECT COUNT(*) AS count FROM audit_logs WHERE resource_id=?",
            ("P3-PO-ATOMIC-ROLLBACK",),
        ).fetchone()
    assert int(dict(order_count)["count"]) == 0
    assert int(dict(audit_count)["count"]) == 0
