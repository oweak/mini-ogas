from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_access_token
from app.core.database import get_db
from app.main import app
from app.repositories.master_data import outbox_repository


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"operator": "admin", "password": "mini-ogas-dev-token"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _post(client: TestClient, headers: dict[str, str], path: str, payload: dict) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="module")
def master_context() -> dict:
    client = TestClient(app)
    client.__enter__()
    headers = _auth_headers(client)

    _post(client, headers, "/master-data/organization-units", {
        "unit_code": "P2-ENTERPRISE", "name": "Phase 2 Enterprise", "unit_type": "enterprise",
    })
    _post(client, headers, "/master-data/organization-units", {
        "unit_code": "P2-SITE", "name": "Phase 2 Site", "unit_type": "site",
        "parent_code": "P2-ENTERPRISE",
    })
    _post(client, headers, "/master-data/organization-units", {
        "unit_code": "P2-AREA", "name": "Machining Area", "unit_type": "area",
        "parent_code": "P2-SITE",
    })
    _post(client, headers, "/master-data/organization-units", {
        "unit_code": "P2-LINE", "name": "Shaft Line", "unit_type": "line",
        "parent_code": "P2-AREA",
    })
    _post(client, headers, "/master-data/organization-units", {
        "unit_code": "P2-CELL", "name": "Turning Cell", "unit_type": "cell",
        "parent_code": "P2-LINE",
    })
    _post(client, headers, "/master-data/uoms", {
        "uom_code": "P2-EA", "name": "Each", "dimension": "count", "scale": 1,
    })
    _post(client, headers, "/master-data/uoms", {
        "uom_code": "P2-KG", "name": "Kilogram", "dimension": "mass", "scale": 1,
    })
    _post(client, headers, "/master-data/materials", {
        "material_code": "P2-STEEL", "name": "42CrMo Steel", "material_type": "raw",
        "base_uom_code": "P2-KG",
    })
    _post(client, headers, "/master-data/materials", {
        "material_code": "P2-SHAFT", "name": "Finished Shaft", "material_type": "finished",
        "base_uom_code": "P2-EA",
    })
    _post(client, headers, "/master-data/products", {
        "product_code": "P2-SHAFT", "name": "Phase 2 Shaft", "material_code": "P2-SHAFT",
    })
    _post(client, headers, "/master-data/equipment", {
        "equipment_code": "P2-LATHE-01", "name": "Phase 2 Lathe", "equipment_type": "lathe",
        "organization_unit_code": "P2-CELL",
    })
    _post(client, headers, "/master-data/equipment/P2-LATHE-01/capabilities", {
        "capability_code": "P2-TURNING", "name": "Precision turning",
    })
    _post(client, headers, "/master-data/skills", {
        "skill_code": "P2-TURN-L2", "name": "Turning level 2", "level_min": 2,
    })
    _post(client, headers, "/master-data/personnel", {
        "personnel_code": "P2-OP-QUAL", "display_name": "Qualified Operator",
    })
    _post(client, headers, "/master-data/personnel", {
        "personnel_code": "P2-OP-NOQUAL", "display_name": "Unqualified Administrator",
        "linked_username": "admin",
    })
    now = datetime.now(UTC)
    _post(client, headers, "/master-data/qualifications", {
        "personnel_code": "P2-OP-QUAL", "skill_code": "P2-TURN-L2", "level": 2,
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_to": (now + timedelta(days=365)).isoformat(),
        "evidence_reference": "CERT-P2-001",
    })
    _post(client, headers, "/master-data/calendars", {
        "calendar_code": "P2-CALENDAR", "name": "Phase 2 Calendar", "timezone": "Asia/Shanghai",
    })
    _post(client, headers, "/master-data/calendars/P2-CALENDAR/shifts", {
        "shift_code": "P2-DAY", "name": "Day Shift", "start_time": "08:00", "end_time": "16:00",
    })

    _post(client, headers, "/master-data/documents", {
        "document_code": "P2-WI-TURN", "title": "Turning Work Instruction", "document_type": "work_instruction",
    })
    document_revision = _post(client, headers, "/master-data/documents/P2-WI-TURN/revisions", {
        "revision": "A", "content": "Verify chuck pressure and use approved turning parameters.",
    })
    assert client.post(
        f"/master-data/document-revisions/{document_revision['id']}/approve", headers=headers
    ).status_code == 200
    assert client.post(
        f"/master-data/document-revisions/{document_revision['id']}/effective", headers=headers
    ).status_code == 200

    _post(client, headers, "/master-data/boms", {
        "bom_code": "P2-BOM-SHAFT", "product_code": "P2-SHAFT", "name": "Shaft BOM",
    })
    bom_revision = _post(client, headers, "/master-data/boms/P2-BOM-SHAFT/revisions", {
        "revision": 1,
        "items": [{"material_code": "P2-STEEL", "quantity": 2.5, "uom_code": "P2-KG"}],
    })
    assert client.post(
        f"/master-data/bom-revisions/{bom_revision['id']}/approve", headers=headers
    ).status_code == 200
    assert client.post(
        f"/master-data/bom-revisions/{bom_revision['id']}/effective", headers=headers
    ).status_code == 200

    _post(client, headers, "/master-data/routings", {
        "routing_code": "P2-RT-SHAFT", "product_code": "P2-SHAFT", "name": "Shaft Routing",
    })
    routing_revision = _post(client, headers, "/master-data/routings/P2-RT-SHAFT/revisions", {
        "revision": 1,
        "operations": [{
            "sequence": 10, "operation_code": "P2-OP-TURN", "name": "Precision turn",
            "capability_code": "P2-TURNING", "required_skill_code": "P2-TURN-L2",
            "required_skill_level": 2, "document_code": "P2-WI-TURN", "standard_time_seconds": 135,
        }],
    })
    assert client.post(
        f"/master-data/routing-revisions/{routing_revision['id']}/approve", headers=headers
    ).status_code == 200
    assert client.post(
        f"/master-data/routing-revisions/{routing_revision['id']}/effective", headers=headers
    ).status_code == 200

    yield {
        "client": client,
        "headers": headers,
        "bom_revision": bom_revision,
        "routing_revision": routing_revision,
        "document_revision": document_revision,
    }
    client.__exit__(None, None, None)


def _work_order_payload(context: dict, code: str, personnel_code: str) -> dict:
    revisions = context["client"].get(
        "/master-data/boms/P2-BOM-SHAFT/revisions",
        headers=context["headers"],
    )
    assert revisions.status_code == 200
    effective_bom = next(
        revision for revision in revisions.json() if revision["status"] == "effective"
    )
    return {
        "work_order_code": code,
        "product_code": "P2-SHAFT",
        "quantity": 20,
        "bom_revision_id": effective_bom["id"],
        "routing_revision_id": context["routing_revision"]["id"],
        "document_revision_ids": [context["document_revision"]["id"]],
        "calendar_code": "P2-CALENDAR",
        "shift_code": "P2-DAY",
        "operation_assignments": [{
            "sequence": 10,
            "equipment_code": "P2-LATHE-01",
            "personnel_code": personnel_code,
        }],
    }


def test_work_order_release_binds_effective_revisions_and_qualified_resources(master_context: dict) -> None:
    client = master_context["client"]
    headers = master_context["headers"]
    created = _post(
        client,
        headers,
        "/master-data/work-orders",
        _work_order_payload(master_context, "P2-WO-VALID", "P2-OP-QUAL"),
    )
    assert created["status"] == "draft"

    released = client.post("/master-data/work-orders/P2-WO-VALID/release", headers=headers)
    assert released.status_code == 200, released.text
    payload = released.json()
    assert payload["status"] == "released"
    assert payload["bom_revision_id"] == master_context["bom_revision"]["id"]
    assert payload["routing_revision_id"] == master_context["routing_revision"]["id"]
    assert payload["document_revision_ids"] == [master_context["document_revision"]["id"]]
    assert payload["released_by"] == "admin"


def test_account_role_cannot_substitute_for_personnel_qualification(master_context: dict) -> None:
    client = master_context["client"]
    headers = master_context["headers"]
    _post(
        client,
        headers,
        "/master-data/work-orders",
        _work_order_payload(master_context, "P2-WO-UNQUALIFIED", "P2-OP-NOQUAL"),
    )

    response = client.post("/master-data/work-orders/P2-WO-UNQUALIFIED/release", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "QUALIFICATION_MISSING"
    assert response.json()["detail"]["personnel_code"] == "P2-OP-NOQUAL"


def test_revision_content_is_immutable_and_new_revision_preserves_history(master_context: dict) -> None:
    original_id = master_context["bom_revision"]["id"]
    with pytest.raises(Exception):
        with get_db() as db:
            db.execute(
                "UPDATE bom_revisions SET content_json = ? WHERE id = ?",
                ('{"items":[]}', original_id),
            )
    with pytest.raises(Exception):
        with get_db() as db:
            db.execute("DELETE FROM bom_revisions WHERE id = ?", (original_id,))

    client = master_context["client"]
    headers = master_context["headers"]
    duplicate = client.post(
        "/master-data/boms/P2-BOM-SHAFT/revisions",
        headers=headers,
        json={
            "revision": 1,
            "items": [{"material_code": "P2-STEEL", "quantity": 1, "uom_code": "P2-KG"}],
        },
    )
    assert duplicate.status_code == 409

    revision_two = _post(client, headers, "/master-data/boms/P2-BOM-SHAFT/revisions", {
        "revision": 2,
        "items": [{"material_code": "P2-STEEL", "quantity": 2.4, "uom_code": "P2-KG"}],
    })
    assert client.post(
        f"/master-data/bom-revisions/{revision_two['id']}/approve", headers=headers
    ).status_code == 200
    assert client.post(
        f"/master-data/bom-revisions/{revision_two['id']}/effective", headers=headers
    ).status_code == 200

    revisions = client.get("/master-data/boms/P2-BOM-SHAFT/revisions", headers=headers)
    assert revisions.status_code == 200
    by_revision = {item["revision"]: item for item in revisions.json()}
    assert by_revision[1]["status"] == "superseded"
    assert by_revision[1]["items"][0]["quantity"] == 2.5
    assert by_revision[2]["status"] == "effective"


def test_phase2_master_mutations_and_release_are_durably_audited(master_context: dict) -> None:
    response = master_context["client"].get("/audit-logs", headers=master_context["headers"])
    assert response.status_code == 200
    actions = {item["action"] for item in response.json()}
    assert "master-data:revision-approved" in actions
    assert "master-data:revision-effective" in actions
    assert "master-data:qualification-issued" in actions
    assert "master-data:work-order-released" in actions
    with get_db() as db:
        outbox = db.execute(
            """SELECT COUNT(*) AS count FROM outbox_messages
               WHERE tenant_id=? AND site_id=? AND message_type='audit'
                 AND payload_json LIKE ?""",
            ("tenant-test", "site-test", "%master-data:work-order-released%"),
        ).fetchone()
    assert int(dict(outbox)["count"]) >= 1


def test_organization_hierarchy_rejects_skipped_levels(master_context: dict) -> None:
    response = master_context["client"].post(
        "/master-data/organization-units",
        headers=master_context["headers"],
        json={
            "unit_code": "P2-INVALID-AREA",
            "name": "Invalid direct enterprise area",
            "unit_type": "area",
            "parent_code": "P2-ENTERPRISE",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_ORGANIZATION_HIERARCHY"


def test_expired_qualification_cannot_release_work(master_context: dict) -> None:
    client = master_context["client"]
    headers = master_context["headers"]
    _post(client, headers, "/master-data/personnel", {
        "personnel_code": "P2-OP-EXPIRED",
        "display_name": "Expired Qualification Operator",
    })
    now = datetime.now(UTC)
    _post(client, headers, "/master-data/qualifications", {
        "personnel_code": "P2-OP-EXPIRED",
        "skill_code": "P2-TURN-L2",
        "level": 2,
        "valid_from": (now - timedelta(days=365)).isoformat(),
        "valid_to": (now - timedelta(days=1)).isoformat(),
        "evidence_reference": "CERT-P2-EXPIRED",
    })
    _post(
        client,
        headers,
        "/master-data/work-orders",
        _work_order_payload(master_context, "P2-WO-EXPIRED", "P2-OP-EXPIRED"),
    )

    response = client.post("/master-data/work-orders/P2-WO-EXPIRED/release", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "QUALIFICATION_MISSING"


def test_equipment_without_required_capability_cannot_release_work(
    master_context: dict,
) -> None:
    client = master_context["client"]
    headers = master_context["headers"]
    _post(client, headers, "/master-data/equipment", {
        "equipment_code": "P2-LATHE-NOCAP",
        "name": "Lathe without approved capability",
        "equipment_type": "lathe",
        "organization_unit_code": "P2-CELL",
    })
    payload = _work_order_payload(master_context, "P2-WO-NOCAP", "P2-OP-QUAL")
    payload["operation_assignments"][0]["equipment_code"] = "P2-LATHE-NOCAP"
    _post(client, headers, "/master-data/work-orders", payload)

    response = client.post("/master-data/work-orders/P2-WO-NOCAP/release", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EQUIPMENT_CAPABILITY_MISSING"


def test_revision_cannot_be_effective_before_approval(master_context: dict) -> None:
    client = master_context["client"]
    headers = master_context["headers"]
    revision = _post(client, headers, "/master-data/boms/P2-BOM-SHAFT/revisions", {
        "revision": 99,
        "items": [{"material_code": "P2-STEEL", "quantity": 2.3, "uom_code": "P2-KG"}],
    })

    response = client.post(
        f"/master-data/bom-revisions/{revision['id']}/effective",
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_REVISION_TRANSITION"


def test_master_data_mutation_requires_dedicated_permission(master_context: dict) -> None:
    viewer_token = issue_access_token({
        "username": "phase2-viewer",
        "display_name": "Phase 2 Viewer",
        "roles": ["viewer"],
        "permissions": ["node:view"],
    })
    response = master_context["client"].post(
        "/master-data/uoms",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"uom_code": "P2-DENIED", "name": "Denied", "dimension": "count", "scale": 1},
    )

    assert response.status_code == 403


def test_master_data_write_rolls_back_when_transactional_outbox_fails(
    master_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(outbox_repository, "enqueue_in_transaction", lambda *_args: False)
    response = master_context["client"].post(
        "/master-data/uoms",
        headers=master_context["headers"],
        json={
            "uom_code": "P2-ATOMIC-ROLLBACK",
            "name": "Must Roll Back",
            "dimension": "count",
            "scale": 1,
        },
    )

    assert response.status_code == 500
    with get_db() as db:
        uom_count = db.execute(
            "SELECT COUNT(*) AS count FROM uoms WHERE uom_code=?",
            ("P2-ATOMIC-ROLLBACK",),
        ).fetchone()
        audit_count = db.execute(
            "SELECT COUNT(*) AS count FROM audit_logs WHERE resource_id=?",
            ("P2-ATOMIC-ROLLBACK",),
        ).fetchone()
    assert int(dict(uom_count)["count"]) == 0
    assert int(dict(audit_count)["count"]) == 0
