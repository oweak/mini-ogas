from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest
from app.core.auth import issue_access_token
from app.core.database import get_db
from app.core.outbox import outbox_repository
from app.main import app
from fastapi.testclient import TestClient


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
def material_context() -> dict:
    client = TestClient(app)
    client.__enter__()
    login = client.post(
        "/auth/login",
        json={"operator": "admin", "password": "mini-ogas-dev-token"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    _post(
        client,
        headers,
        "/master-data/uoms",
        {"uom_code": "P4-EA", "name": "Each", "dimension": "count", "scale": 1},
    )
    _post(
        client,
        headers,
        "/master-data/materials",
        {
            "material_code": "P4-MATERIAL",
            "name": "Phase 4 traced material",
            "material_type": "intermediate",
            "base_uom_code": "P4-EA",
        },
    )
    for code, name, warehouse_type in (
        ("P4-RAW-WH", "Raw warehouse", "raw"),
        ("P4-WIP-WH", "WIP warehouse", "wip"),
        ("P4-SCRAP-WH", "Scrap warehouse", "scrap"),
    ):
        _post(
            client,
            headers,
            "/material-flow/warehouses",
            {"warehouse_code": code, "name": name, "warehouse_type": warehouse_type},
        )
    for code, name, warehouse, location_type in (
        ("P4-RAW-01", "Raw storage", "P4-RAW-WH", "storage"),
        ("P4-WIP-01", "WIP input", "P4-WIP-WH", "wip"),
        ("P4-WIP-02", "WIP output", "P4-WIP-WH", "wip"),
        ("P4-SCRAP-01", "Scrap cage", "P4-SCRAP-WH", "scrap"),
    ):
        _post(
            client,
            headers,
            "/material-flow/locations",
            {
                "location_code": code,
                "warehouse_code": warehouse,
                "name": name,
                "location_type": location_type,
            },
        )
    for code, location in (("P4-CONT-A", "P4-RAW-01"), ("P4-CONT-B", "P4-WIP-01")):
        _post(
            client,
            headers,
            "/material-flow/containers",
            {
                "container_code": code,
                "container_type": "tote",
                "location_code": location,
            },
        )
    lot_codes = (
        "P4-IDEMPOTENT",
        "P4-OPERATIONS",
        "P4-CONSUME-IN",
        "P4-PRODUCE-OUT",
        "P4-SPLIT-PARENT",
        "P4-SPLIT-A",
        "P4-SPLIT-B",
        "P4-MERGE-A",
        "P4-MERGE-B",
        "P4-MERGED",
        "P4-RECONCILE",
        "P4-CONTAINER",
        "P4-ROLLBACK",
    )
    for lot_code in lot_codes:
        _post(
            client,
            headers,
            "/material-flow/lots",
            {
                "lot_code": lot_code,
                "material_code": "P4-MATERIAL",
                "tracking_kind": "lot",
                "evidence_reference": f"CREATE-{lot_code}",
            },
        )
    _post(
        client,
        headers,
        "/material-flow/lots",
        {
            "lot_code": "P4-SERIAL-001",
            "material_code": "P4-MATERIAL",
            "tracking_kind": "serial",
            "evidence_reference": "SERIAL-CERT-001",
        },
    )

    # Focused Phase 4 tests use explicit execution fixtures. The live gate binds
    # material flow to a fully released and completed Phase 3 task through HTTP.
    with get_db() as db:
        for task_id, task_status in ((9401, "running"), (9402, "completed")):
            db.execute(
                """INSERT INTO operation_tasks (
                       id, tenant_id, site_id, work_order_execution_id, work_order_id,
                       routing_revision_id, sequence, operation_code, name,
                       planned_quantity, status, completion_evidence_reference
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    "tenant-test",
                    "site-test",
                    task_id,
                    task_id,
                    task_id,
                    10,
                    f"P4-OP-{task_id}",
                    f"P4 task {task_id}",
                    10,
                    task_status,
                    "P4-TASK-EVIDENCE" if task_status == "completed" else None,
                ),
            )

    yield {"client": client, "headers": headers}
    client.__exit__(None, None, None)


def _movement(
    context: dict,
    movement_id: str,
    movement_type: str,
    lot_code: str,
    quantity: float,
    *,
    from_location: str | None = None,
    to_location: str | None = None,
    from_container: str | None = None,
    to_container: str | None = None,
    operation_task_id: int | None = None,
    source: str = "manual",
    expected: int = 201,
) -> dict:
    payload = {
        "movement_id": movement_id,
        "movement_type": movement_type,
        "lot_code": lot_code,
        "quantity": quantity,
        "from_location_code": from_location,
        "to_location_code": to_location,
        "from_container_code": from_container,
        "to_container_code": to_container,
        "operation_task_id": operation_task_id,
        "source": source,
        "reason": "phase 4 acceptance",
        "evidence_reference": f"EVIDENCE-{movement_id}",
        "occurred_at": "2026-07-14T00:00:00+00:00",
    }
    return _post(
        context["client"],
        context["headers"],
        "/material-flow/movements",
        payload,
        expected=expected,
    )


def _balances(context: dict, lot_code: str) -> list[dict]:
    response = context["client"].get(
        f"/material-flow/lots/{lot_code}/balances",
        headers=context["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_movement_is_idempotent_and_negative_inventory_is_rejected(
    material_context: dict,
) -> None:
    receipt = _movement(
        material_context,
        "P4-MOVE-RECEIPT-IDEMP",
        "receipt",
        "P4-IDEMPOTENT",
        10,
        to_location="P4-RAW-01",
    )
    repeated = _movement(
        material_context,
        "P4-MOVE-RECEIPT-IDEMP",
        "receipt",
        "P4-IDEMPOTENT",
        10,
        to_location="P4-RAW-01",
    )
    assert repeated["id"] == receipt["id"]

    changed = material_context["client"].post(
        "/material-flow/movements",
        headers=material_context["headers"],
        json={
            "movement_id": "P4-MOVE-RECEIPT-IDEMP",
            "movement_type": "receipt",
            "lot_code": "P4-IDEMPOTENT",
            "quantity": 11,
            "to_location_code": "P4-RAW-01",
            "source": "manual",
            "reason": "changed retry",
            "evidence_reference": "CHANGED",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    _movement(
        material_context,
        "P4-MOVE-IDEMP-TRANSFER",
        "transfer",
        "P4-IDEMPOTENT",
        6,
        from_location="P4-RAW-01",
        to_location="P4-WIP-01",
    )
    rejected = material_context["client"].post(
        "/material-flow/movements",
        headers=material_context["headers"],
        json={
            "movement_id": "P4-MOVE-NEGATIVE",
            "movement_type": "transfer",
            "lot_code": "P4-IDEMPOTENT",
            "quantity": 7,
            "from_location_code": "P4-RAW-01",
            "to_location_code": "P4-WIP-01",
            "source": "manual",
            "reason": "must fail",
            "evidence_reference": "NEGATIVE-PROBE",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "NEGATIVE_INVENTORY"
    balances = _balances(material_context, "P4-IDEMPOTENT")
    assert {(item["location_code"], item["quantity"]) for item in balances} == {
        ("P4-RAW-01", 4.0),
        ("P4-WIP-01", 6.0),
    }


def test_issue_return_scrap_and_container_transfer_conserve_total(
    material_context: dict,
) -> None:
    _movement(
        material_context,
        "P4-OPS-RECEIPT",
        "receipt",
        "P4-OPERATIONS",
        10,
        to_location="P4-RAW-01",
    )
    _movement(
        material_context,
        "P4-OPS-ISSUE",
        "issue",
        "P4-OPERATIONS",
        6,
        from_location="P4-RAW-01",
        to_location="P4-WIP-01",
    )
    _movement(
        material_context,
        "P4-OPS-RETURN",
        "return",
        "P4-OPERATIONS",
        2,
        from_location="P4-WIP-01",
        to_location="P4-RAW-01",
    )
    _movement(
        material_context,
        "P4-OPS-SCRAP",
        "scrap",
        "P4-OPERATIONS",
        1,
        from_location="P4-WIP-01",
        to_location="P4-SCRAP-01",
    )
    assert {(item["location_code"], item["quantity"]) for item in _balances(
        material_context, "P4-OPERATIONS"
    )} == {("P4-RAW-01", 6.0), ("P4-WIP-01", 3.0), ("P4-SCRAP-01", 1.0)}

    _movement(
        material_context,
        "P4-CONTAINER-RECEIPT",
        "receipt",
        "P4-CONTAINER",
        5,
        to_location="P4-RAW-01",
        to_container="P4-CONT-A",
    )
    _movement(
        material_context,
        "P4-CONTAINER-TRANSFER",
        "transfer",
        "P4-CONTAINER",
        5,
        from_location="P4-RAW-01",
        to_location="P4-WIP-01",
        from_container="P4-CONT-A",
        to_container="P4-CONT-B",
    )
    container_balance = _balances(material_context, "P4-CONTAINER")
    assert [(item["location_code"], item["container_code"], item["quantity"])
            for item in container_balance] == [("P4-WIP-01", "P4-CONT-B", 5.0)]


def test_consume_and_produce_require_compatible_execution_state(material_context: dict) -> None:
    _movement(
        material_context,
        "P4-CONSUME-RECEIPT",
        "receipt",
        "P4-CONSUME-IN",
        5,
        to_location="P4-WIP-01",
    )
    consumed = _movement(
        material_context,
        "P4-CONSUME",
        "consume",
        "P4-CONSUME-IN",
        2,
        from_location="P4-WIP-01",
        operation_task_id=9401,
        source="execution",
    )
    assert consumed["operation_task_id"] == 9401
    produced = _movement(
        material_context,
        "P4-PRODUCE",
        "produce",
        "P4-PRODUCE-OUT",
        2,
        to_location="P4-WIP-02",
        operation_task_id=9402,
        source="execution",
    )
    assert produced["operation_task_id"] == 9402
    invalid = material_context["client"].post(
        "/material-flow/movements",
        headers=material_context["headers"],
        json={
            "movement_id": "P4-PRODUCE-WHILE-RUNNING",
            "movement_type": "produce",
            "lot_code": "P4-PRODUCE-OUT",
            "quantity": 1,
            "to_location_code": "P4-WIP-02",
            "operation_task_id": 9401,
            "source": "execution",
            "reason": "invalid execution state",
            "evidence_reference": "P4-INVALID",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "EXECUTION_STATE_INCOMPATIBLE"


def test_split_and_merge_support_forward_and_reverse_genealogy(material_context: dict) -> None:
    _movement(
        material_context,
        "P4-SPLIT-RECEIPT",
        "receipt",
        "P4-SPLIT-PARENT",
        10,
        to_location="P4-RAW-01",
    )
    split_payload = {
        "transformation_id": "P4-TRANSFORM-SPLIT",
        "transformation_type": "split",
        "inputs": [
            {"lot_code": "P4-SPLIT-PARENT", "quantity": 10, "location_code": "P4-RAW-01"}
        ],
        "outputs": [
            {"lot_code": "P4-SPLIT-A", "quantity": 4, "location_code": "P4-WIP-01"},
            {"lot_code": "P4-SPLIT-B", "quantity": 6, "location_code": "P4-WIP-01"},
        ],
        "reason": "controlled split",
        "evidence_reference": "P4-SPLIT-EVIDENCE",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    first = _post(
        material_context["client"],
        material_context["headers"],
        "/material-flow/transformations",
        split_payload,
    )
    repeated = _post(
        material_context["client"],
        material_context["headers"],
        "/material-flow/transformations",
        split_payload,
    )
    assert repeated["id"] == first["id"]
    forward = material_context["client"].get(
        "/material-flow/genealogy/P4-SPLIT-PARENT", headers=material_context["headers"]
    ).json()
    assert {item["lot_code"] for item in forward["descendants"]} == {
        "P4-SPLIT-A",
        "P4-SPLIT-B",
    }
    reverse = material_context["client"].get(
        "/material-flow/genealogy/P4-SPLIT-A", headers=material_context["headers"]
    ).json()
    assert {item["lot_code"] for item in reverse["ancestors"]} == {"P4-SPLIT-PARENT"}

    _movement(
        material_context,
        "P4-MERGE-RECEIPT-A",
        "receipt",
        "P4-MERGE-A",
        3,
        to_location="P4-RAW-01",
    )
    _movement(
        material_context,
        "P4-MERGE-RECEIPT-B",
        "receipt",
        "P4-MERGE-B",
        2,
        to_location="P4-RAW-01",
    )
    _post(
        material_context["client"],
        material_context["headers"],
        "/material-flow/transformations",
        {
            "transformation_id": "P4-TRANSFORM-MERGE",
            "transformation_type": "merge",
            "inputs": [
                {"lot_code": "P4-MERGE-A", "quantity": 3, "location_code": "P4-RAW-01"},
                {"lot_code": "P4-MERGE-B", "quantity": 2, "location_code": "P4-RAW-01"},
            ],
            "outputs": [
                {"lot_code": "P4-MERGED", "quantity": 5, "location_code": "P4-WIP-02"}
            ],
            "reason": "controlled merge",
            "evidence_reference": "P4-MERGE-EVIDENCE",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    merged = material_context["client"].get(
        "/material-flow/genealogy/P4-MERGED", headers=material_context["headers"]
    ).json()
    assert {item["lot_code"] for item in merged["ancestors"]} == {
        "P4-MERGE-A",
        "P4-MERGE-B",
    }


def test_serial_quantity_is_exactly_one(material_context: dict) -> None:
    invalid = material_context["client"].post(
        "/material-flow/movements",
        headers=material_context["headers"],
        json={
            "movement_id": "P4-SERIAL-INVALID",
            "movement_type": "receipt",
            "lot_code": "P4-SERIAL-001",
            "quantity": 2,
            "to_location_code": "P4-RAW-01",
            "source": "manual",
            "reason": "must fail",
            "evidence_reference": "P4-SERIAL-INVALID",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "SERIAL_QUANTITY_INVALID"
    accepted = _movement(
        material_context,
        "P4-SERIAL-VALID",
        "receipt",
        "P4-SERIAL-001",
        1,
        to_location="P4-RAW-01",
    )
    assert accepted["quantity"] == 1


def test_external_snapshot_creates_discrepancy_without_silent_overwrite(
    material_context: dict,
) -> None:
    _movement(
        material_context,
        "P4-RECON-RECEIPT",
        "receipt",
        "P4-RECONCILE",
        10,
        to_location="P4-RAW-01",
    )
    snapshot_payload = {
        "import_id": "P4-WMS-SNAPSHOT-001",
        "provider": "wms_simulator",
        "contract_version": "1.0",
        "observed_at": datetime.now(UTC).isoformat(),
        "evidence_reference": "P4-WMS-EVIDENCE",
        "items": [
            {
                "lot_code": "P4-RECONCILE",
                "location_code": "P4-RAW-01",
                "container_code": None,
                "observed_quantity": 7,
            }
        ],
    }
    imported = _post(
        material_context["client"],
        material_context["headers"],
        "/material-flow/external-snapshots",
        snapshot_payload,
    )
    repeated = _post(
        material_context["client"],
        material_context["headers"],
        "/material-flow/external-snapshots",
        snapshot_payload,
    )
    assert repeated["id"] == imported["id"]
    assert len(imported["reconciliation_cases"]) == 1
    case = imported["reconciliation_cases"][0]
    assert case["expected_quantity"] == 10
    assert case["observed_quantity"] == 7
    assert case["variance"] == -3
    assert case["status"] == "open"
    assert _balances(material_context, "P4-RECONCILE")[0]["quantity"] == 10

    adjusted = _post(
        material_context["client"],
        material_context["headers"],
        f"/material-flow/reconciliations/{case['id']}/adjust",
        {
            "movement_id": "P4-RECON-ADJUSTMENT",
            "reason": "approved cycle-count correction",
            "evidence_reference": "P4-RECON-APPROVAL",
        },
        expected=200,
    )
    assert adjusted["status"] == "adjusted"
    assert _balances(material_context, "P4-RECONCILE")[0]["quantity"] == 7


def test_material_evidence_is_append_only(material_context: dict) -> None:
    with get_db() as db:
        movement = db.execute(
            "SELECT id FROM inventory_movements ORDER BY id LIMIT 1"
        ).fetchone()
        edge = db.execute("SELECT id FROM genealogy_edges ORDER BY id LIMIT 1").fetchone()
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                "UPDATE inventory_movements SET quantity=999 WHERE id=?",
                (int(dict(movement)["id"]),),
            )
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute("DELETE FROM genealogy_edges WHERE id=?", (int(dict(edge)["id"]),))


def test_material_mutation_requires_permission(material_context: dict) -> None:
    viewer_token = issue_access_token({
        "username": "phase4-viewer",
        "display_name": "Phase 4 Viewer",
        "roles": ["viewer"],
        "permissions": ["node:view"],
    })
    response = material_context["client"].post(
        "/material-flow/warehouses",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={
            "warehouse_code": "P4-DENIED",
            "name": "Denied",
            "warehouse_type": "raw",
        },
    )
    assert response.status_code == 403


def test_material_write_rolls_back_when_transactional_outbox_fails(
    material_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(outbox_repository, "enqueue_in_transaction", lambda *_args: False)
    response = material_context["client"].post(
        "/material-flow/movements",
        headers=material_context["headers"],
        json={
            "movement_id": "P4-ROLLBACK-RECEIPT",
            "movement_type": "receipt",
            "lot_code": "P4-ROLLBACK",
            "quantity": 5,
            "to_location_code": "P4-RAW-01",
            "source": "manual",
            "reason": "atomic rollback test",
            "evidence_reference": "P4-ROLLBACK-EVIDENCE",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 500
    with get_db() as db:
        movement_count = db.execute(
            "SELECT COUNT(*) AS count FROM inventory_movements WHERE movement_id=?",
            ("P4-ROLLBACK-RECEIPT",),
        ).fetchone()
        balance_count = db.execute(
            """SELECT COUNT(*) AS count FROM inventory_balances balance
               JOIN material_lots lot ON lot.id=balance.lot_id
               WHERE lot.lot_code=? AND balance.quantity>0""",
            ("P4-ROLLBACK",),
        ).fetchone()
    assert int(dict(movement_count)["count"]) == 0
    assert int(dict(balance_count)["count"]) == 0
