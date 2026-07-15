from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from app.core.auth import issue_access_token
from app.core.database import get_db
from app.core.outbox import outbox_repository
from app.main import app
from fastapi.testclient import TestClient


def _post(
    context: dict,
    path: str,
    payload: dict | None = None,
    *,
    expected: int = 201,
    headers: dict[str, str] | None = None,
) -> dict:
    response = context["client"].post(
        path,
        headers=headers or context["headers"],
        json=payload or {},
    )
    assert response.status_code == expected, response.text
    return response.json()


def _seed_master(context: dict) -> None:
    for code, name, unit_type, parent in (
        ("P6-ENT", "P6 Enterprise", "enterprise", None),
        ("P6-SITE", "P6 Site", "site", "P6-ENT"),
        ("P6-AREA", "P6 Area", "area", "P6-SITE"),
        ("P6-LINE", "P6 Line", "line", "P6-AREA"),
        ("P6-CELL", "P6 Cell", "cell", "P6-LINE"),
    ):
        payload = {"unit_code": code, "name": name, "unit_type": unit_type}
        if parent:
            payload["parent_code"] = parent
        _post(context, "/master-data/organization-units", payload)
    for code, name, dimension in (
        ("P6-EA", "Each", "count"),
        ("P6-KG", "Kilogram", "mass"),
    ):
        _post(
            context,
            "/master-data/uoms",
            {"uom_code": code, "name": name, "dimension": dimension, "scale": 1},
        )
    for code, name, material_type, uom in (
        ("P6-RAW", "P6 Steel", "raw", "P6-KG"),
        ("P6-PART", "P6 Part", "finished", "P6-EA"),
        ("P6-SPARE", "P6 Bearing", "consumable", "P6-EA"),
    ):
        _post(
            context,
            "/master-data/materials",
            {
                "material_code": code,
                "name": name,
                "material_type": material_type,
                "base_uom_code": uom,
            },
        )
    _post(
        context,
        "/master-data/products",
        {"product_code": "P6-PART", "name": "P6 Product", "material_code": "P6-PART"},
    )
    for code, name, equipment_type in (
        ("P6-LINE-EQ", "P6 Line Asset", "line"),
        ("P6-LATHE-01", "P6 Lathe", "lathe"),
    ):
        _post(
            context,
            "/master-data/equipment",
            {
                "equipment_code": code,
                "name": name,
                "equipment_type": equipment_type,
                "organization_unit_code": "P6-CELL",
            },
        )
    _post(
        context,
        "/master-data/equipment/P6-LATHE-01/capabilities",
        {"capability_code": "P6-TURN", "name": "P6 Turning"},
    )
    _post(
        context,
        "/master-data/skills",
        {"skill_code": "P6-MAINT-L2", "name": "P6 Maintenance", "level_min": 2},
    )
    now = datetime.now(UTC)
    for code, display_name in (
        ("P6-OP", "P6 Operator"),
        ("P6-TECH", "P6 Technician"),
    ):
        _post(
            context,
            "/master-data/personnel",
            {"personnel_code": code, "display_name": display_name},
        )
        _post(
            context,
            "/master-data/qualifications",
            {
                "personnel_code": code,
                "skill_code": "P6-MAINT-L2",
                "level": 2,
                "valid_from": (now - timedelta(days=1)).isoformat(),
                "valid_to": (now + timedelta(days=365)).isoformat(),
                "evidence_reference": f"P6-CERT-{code}",
            },
        )
    _post(
        context,
        "/master-data/calendars",
        {"calendar_code": "P6-CAL", "name": "P6 Calendar", "timezone": "Asia/Shanghai"},
    )
    _post(
        context,
        "/master-data/calendars/P6-CAL/shifts",
        {"shift_code": "P6-DAY", "name": "P6 Day", "start_time": "08:00", "end_time": "16:00"},
    )
    _post(
        context,
        "/master-data/documents",
        {
            "document_code": "P6-WI",
            "title": "P6 Work Instruction",
            "document_type": "work_instruction",
        },
    )
    document = _post(
        context,
        "/master-data/documents/P6-WI/revisions",
        {"revision": "A", "content": "P6 controlled instruction"},
    )
    _post(
        context,
        f"/master-data/document-revisions/{document['id']}/approve",
        expected=200,
    )
    _post(
        context,
        f"/master-data/document-revisions/{document['id']}/effective",
        expected=200,
    )
    _post(
        context,
        "/master-data/boms",
        {"bom_code": "P6-BOM", "product_code": "P6-PART", "name": "P6 BOM"},
    )
    bom = _post(
        context,
        "/master-data/boms/P6-BOM/revisions",
        {
            "revision": 1,
            "items": [{"material_code": "P6-RAW", "quantity": 1, "uom_code": "P6-KG"}],
        },
    )
    _post(context, f"/master-data/bom-revisions/{bom['id']}/approve", expected=200)
    _post(context, f"/master-data/bom-revisions/{bom['id']}/effective", expected=200)
    _post(
        context,
        "/master-data/routings",
        {"routing_code": "P6-ROUTE", "product_code": "P6-PART", "name": "P6 Route"},
    )
    routing = _post(
        context,
        "/master-data/routings/P6-ROUTE/revisions",
        {
            "revision": 1,
            "operations": [
                {
                    "sequence": 10,
                    "operation_code": "P6-TURN-OP",
                    "name": "P6 Turn",
                    "capability_code": "P6-TURN",
                    "required_skill_code": "P6-MAINT-L2",
                    "required_skill_level": 2,
                    "document_code": "P6-WI",
                    "standard_time_seconds": 60,
                }
            ],
        },
    )
    _post(context, f"/master-data/routing-revisions/{routing['id']}/approve", expected=200)
    _post(context, f"/master-data/routing-revisions/{routing['id']}/effective", expected=200)
    context.update(
        {
            "document_revision_id": document["id"],
            "bom_revision_id": bom["id"],
            "routing_revision_id": routing["id"],
        }
    )


def _seed_spare_inventory(context: dict) -> None:
    _post(
        context,
        "/material-flow/warehouses",
        {"warehouse_code": "P6-MRO-WH", "name": "P6 MRO", "warehouse_type": "raw"},
    )
    _post(
        context,
        "/material-flow/locations",
        {
            "location_code": "P6-MRO-LOC",
            "warehouse_code": "P6-MRO-WH",
            "name": "P6 MRO location",
            "location_type": "storage",
        },
    )
    _post(
        context,
        "/material-flow/lots",
        {
            "lot_code": "P6-SPARE-LOT",
            "material_code": "P6-SPARE",
            "tracking_kind": "lot",
            "evidence_reference": "P6-SPARE-CERT",
        },
    )
    _post(
        context,
        "/material-flow/movements",
        {
            "movement_id": "P6-SPARE-RECEIPT",
            "movement_type": "receipt",
            "lot_code": "P6-SPARE-LOT",
            "quantity": 10,
            "to_location_code": "P6-MRO-LOC",
            "source": "manual",
            "reason": "P6 spare receipt",
            "evidence_reference": "P6-SPARE-RECEIPT-EVIDENCE",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )


@pytest.fixture(scope="module")
def maintenance_context() -> dict:
    client = TestClient(app)
    client.__enter__()
    login = client.post(
        "/auth/login",
        json={"operator": "admin", "password": "mini-ogas-dev-token"},
    )
    assert login.status_code == 200
    context = {
        "client": client,
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }
    _seed_master(context)
    _seed_spare_inventory(context)
    yield context
    client.__exit__(None, None, None)


def _new_ready_task(context: dict, suffix: str) -> int:
    work_order = f"P6-WO-{suffix}"
    production_order = f"P6-PO-{suffix}"
    _post(
        context,
        "/master-data/work-orders",
        {
            "work_order_code": work_order,
            "product_code": "P6-PART",
            "quantity": 2,
            "bom_revision_id": context["bom_revision_id"],
            "routing_revision_id": context["routing_revision_id"],
            "document_revision_ids": [context["document_revision_id"]],
            "calendar_code": "P6-CAL",
            "shift_code": "P6-DAY",
            "operation_assignments": [
                {
                    "sequence": 10,
                    "equipment_code": "P6-LATHE-01",
                    "personnel_code": "P6-OP",
                }
            ],
        },
    )
    _post(context, f"/master-data/work-orders/{work_order}/release", expected=200)
    _post(
        context,
        "/execution/production-orders",
        {
            "production_order_code": production_order,
            "product_code": "P6-PART",
            "quantity": 2,
            "priority": 5,
            "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    _post(
        context,
        f"/execution/production-orders/{production_order}/work-orders/{work_order}/attach",
        {"idempotency_key": f"P6-ATTACH-{suffix}"},
        expected=200,
    )
    _post(
        context,
        f"/execution/production-orders/{production_order}/release",
        {"idempotency_key": f"P6-RELEASE-{suffix}"},
        expected=200,
    )
    dispatched = _post(
        context,
        f"/execution/work-orders/{work_order}/dispatch",
        {"idempotency_key": f"P6-DISPATCH-{suffix}"},
        expected=200,
    )
    task_id = int(dispatched["tasks"][0]["id"])
    _post(
        context,
        f"/execution/tasks/{task_id}/setup/start",
        {"idempotency_key": f"P6-SETUP-START-{suffix}"},
        expected=200,
    )
    _post(
        context,
        f"/execution/tasks/{task_id}/setup/complete",
        {
            "idempotency_key": f"P6-SETUP-COMPLETE-{suffix}",
            "evidence_reference": f"P6-SETUP-EVIDENCE-{suffix}",
            "parameters": {"fixture_verified": True},
        },
        expected=200,
    )
    return task_id


@pytest.fixture(scope="module")
def maintenance_authority(maintenance_context: dict) -> dict:
    context = maintenance_context
    parent = _post(
        context,
        "/maintenance/assets",
        {
            "asset_code": "P6-ASSET-LINE",
            "equipment_code": "P6-LINE-EQ",
            "name": "P6 Line Asset",
            "criticality": "high",
        },
    )
    child = _post(
        context,
        "/maintenance/assets",
        {
            "asset_code": "P6-ASSET-LATHE",
            "equipment_code": "P6-LATHE-01",
            "name": "P6 Lathe Asset",
            "parent_asset_code": "P6-ASSET-LINE",
            "criticality": "critical",
        },
    )
    for code_type, code in (
        ("failure", "P6-F-BEARING"),
        ("cause", "P6-C-LUBE"),
        ("remedy", "P6-R-REPLACE"),
    ):
        _post(
            context,
            "/maintenance/codes",
            {
                "code": code,
                "code_type": code_type,
                "description": f"P6 {code_type}",
            },
        )
    checklist = _post(
        context,
        "/maintenance/checklists",
        {
            "checklist_code": "P6-CHECK",
            "revision": 1,
            "name": "P6 Bearing Replacement",
            "items": [
                {"sequence": 10, "instruction": "Lockout verified", "required": True},
                {"sequence": 20, "instruction": "Guard restored", "required": True},
            ],
        },
    )
    _post(
        context,
        "/maintenance/checklists/P6-CHECK/revisions/1/approve",
        {"evidence_reference": "P6-CHECK-APPROVAL"},
        expected=200,
    )
    effective = _post(
        context,
        "/maintenance/checklists/P6-CHECK/revisions/1/effective",
        {"evidence_reference": "P6-CHECK-EFFECTIVE"},
        expected=200,
    )
    context.update(
        {
            "parent_asset": parent,
            "child_asset": child,
            "checklist": checklist,
            "effective_checklist": effective,
        }
    )
    return context


def _create_request_order(
    context: dict,
    suffix: str,
    task_id: int | None = None,
    downtime_id: int | None = None,
) -> dict:
    request_code = f"P6-REQ-{suffix}"
    order_code = f"P6-MO-{suffix}"
    _post(
        context,
        "/maintenance/requests",
        {
            "request_code": request_code,
            "asset_code": "P6-ASSET-LATHE",
            "source_type": "alarm",
            "source_reference": f"P6-ALARM-{suffix}",
            "description": "Bearing temperature and vibration require inspection",
            "priority": "high",
            "observed_at": datetime.now(UTC).isoformat(),
        },
    )
    order = _post(
        context,
        "/maintenance/orders",
        {
            "order_code": order_code,
            "request_code": request_code,
            "asset_code": "P6-ASSET-LATHE",
            "order_type": "corrective",
            "priority": "high",
            "assigned_personnel_code": "P6-TECH",
            "checklist_code": "P6-CHECK",
            "checklist_revision": 1,
            "operation_task_id": task_id,
            "operation_downtime_id": downtime_id,
            "production_impact": "equipment_unavailable",
            "planned_start_at": datetime.now(UTC).isoformat(),
            "planned_end_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        },
    )
    approved = _post(
        context,
        f"/maintenance/orders/{order_code}/approve",
        {"evidence_reference": f"P6-APPROVE-{suffix}"},
        expected=200,
    )
    refreshed_request = context["client"].get(
        f"/maintenance/requests/{request_code}", headers=context["headers"]
    )
    assert refreshed_request.status_code == 200, refreshed_request.text
    return {
        "request": refreshed_request.json(),
        "order": order,
        "approved": approved,
        "order_code": order_code,
    }


def _complete_checklist(context: dict, order_code: str) -> None:
    for sequence in (10, 20):
        _post(
            context,
            f"/maintenance/orders/{order_code}/checklist-results",
            {
                "item_sequence": sequence,
                "result": "pass",
                "evidence_reference": f"{order_code}-CHECK-{sequence}",
            },
        )


def _work_complete(context: dict, order_code: str) -> dict:
    return _post(
        context,
        f"/maintenance/orders/{order_code}/work-complete",
        {
            "failure_code": "P6-F-BEARING",
            "cause_code": "P6-C-LUBE",
            "remedy_code": "P6-R-REPLACE",
            "work_evidence_reference": f"{order_code}-WORK-EVIDENCE",
        },
        expected=200,
    )


def _verifier_headers() -> dict[str, str]:
    token = issue_access_token(
        {
            "username": "p6-verifier",
            "display_name": "P6 Independent Verifier",
            "roles": ["maintenance_verifier"],
            "permissions": ["maintenance:verify"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_asset_hierarchy_criticality_and_codes_are_governed(
    maintenance_authority: dict,
) -> None:
    assert maintenance_authority["parent_asset"]["criticality"] == "high"
    assert maintenance_authority["child_asset"]["parent_asset_code"] == "P6-ASSET-LINE"
    assert maintenance_authority["child_asset"]["criticality"] == "critical"
    assert maintenance_authority["effective_checklist"]["status"] == "effective"
    assert len(maintenance_authority["effective_checklist"]["items"]) == 2


def test_alarm_source_is_not_maintenance_completion(maintenance_authority: dict) -> None:
    task_id = _new_ready_task(maintenance_authority, "ALARM")
    workflow = _create_request_order(maintenance_authority, "ALARM", task_id)
    assert workflow["request"]["status"] == "converted"
    assert workflow["approved"]["status"] == "approved"
    premature = maintenance_authority["client"].post(
        f"/maintenance/orders/{workflow['order_code']}/verify",
        headers=_verifier_headers(),
        json={
            "verification_reference": "P6-PREMATURE-VERIFY",
            "verification_result": "restored",
        },
    )
    assert premature.status_code == 409
    assert premature.json()["detail"]["code"] == "MAINTENANCE_NOT_READY_FOR_VERIFICATION"


def test_work_requires_checklist_and_independent_verification_before_task_start(
    maintenance_authority: dict,
) -> None:
    task_id = _new_ready_task(maintenance_authority, "VERIFY")
    workflow = _create_request_order(maintenance_authority, "VERIFY", task_id)
    order_code = workflow["order_code"]
    started = _post(
        maintenance_authority,
        f"/maintenance/orders/{order_code}/start",
        {"evidence_reference": "P6-MAINT-START"},
        expected=200,
    )
    assert started["status"] == "in_progress"
    blocked_task = maintenance_authority["client"].post(
        f"/execution/tasks/{task_id}/start",
        headers=maintenance_authority["headers"],
        json={"idempotency_key": "P6-BLOCKED-BY-MAINTENANCE"},
    )
    assert blocked_task.status_code == 409
    assert blocked_task.json()["detail"]["code"] == "ACTIVE_MAINTENANCE_BLOCKS_TASK"
    incomplete = maintenance_authority["client"].post(
        f"/maintenance/orders/{order_code}/work-complete",
        headers=maintenance_authority["headers"],
        json={
            "failure_code": "P6-F-BEARING",
            "cause_code": "P6-C-LUBE",
            "remedy_code": "P6-R-REPLACE",
            "work_evidence_reference": "P6-INCOMPLETE-CHECKLIST",
        },
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"]["code"] == "CHECKLIST_INCOMPLETE"
    _complete_checklist(maintenance_authority, order_code)
    completed = _work_complete(maintenance_authority, order_code)
    assert completed["status"] == "work_completed"
    same_actor = maintenance_authority["client"].post(
        f"/maintenance/orders/{order_code}/verify",
        headers=maintenance_authority["headers"],
        json={
            "verification_reference": "P6-SAME-ACTOR",
            "verification_result": "restored",
        },
    )
    assert same_actor.status_code == 409
    assert same_actor.json()["detail"]["code"] == "INDEPENDENT_VERIFIER_REQUIRED"
    verified = _post(
        maintenance_authority,
        f"/maintenance/orders/{order_code}/verify",
        {
            "verification_reference": "P6-INDEPENDENT-VERIFY",
            "verification_result": "restored",
        },
        expected=200,
        headers=_verifier_headers(),
    )
    assert verified["status"] == "verified"
    task = _post(
        maintenance_authority,
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": "P6-START-AFTER-VERIFY"},
        expected=200,
    )
    assert task["status"] == "running"


def test_tool_life_and_calibration_block_operation_task(
    maintenance_authority: dict,
) -> None:
    task_id = _new_ready_task(maintenance_authority, "TOOL")
    now = datetime.now(UTC)
    tool = _post(
        maintenance_authority,
        "/maintenance/tools",
        {
            "tool_code": "P6-TOOL-OVERLIFE",
            "asset_code": "P6-ASSET-LATHE",
            "name": "P6 Turning Insert",
            "tool_type": "turning_insert",
            "life_limit": 100,
            "life_used": 90,
            "life_uom": "cycles",
            "calibration_required": True,
            "calibration_due_at": (now + timedelta(days=30)).isoformat(),
        },
    )
    assert tool["status"] == "active"
    _post(
        maintenance_authority,
        "/maintenance/tools/P6-TOOL-OVERLIFE/assignments",
        {"operation_task_id": task_id, "evidence_reference": "P6-TOOL-ASSIGN"},
    )
    event = _post(
        maintenance_authority,
        "/maintenance/tools/P6-TOOL-OVERLIFE/life-events",
        {
            "event_id": "P6-TOOL-LIFE-001",
            "usage_delta": 15,
            "operation_task_id": task_id,
            "occurred_at": now.isoformat(),
            "evidence_reference": "P6-TOOL-COUNTER",
        },
    )
    assert event["tool_status"] == "over_life"
    blocked = maintenance_authority["client"].post(
        f"/execution/tasks/{task_id}/start",
        headers=maintenance_authority["headers"],
        json={"idempotency_key": "P6-TOOL-LIFE-BLOCK"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "TOOL_LIFE_EXCEEDED"

    calibration_task = _new_ready_task(maintenance_authority, "CAL")
    _post(
        maintenance_authority,
        "/maintenance/tools",
        {
            "tool_code": "P6-TOOL-CAL",
            "asset_code": "P6-ASSET-LATHE",
            "name": "P6 Torque Tool",
            "tool_type": "torque_tool",
            "life_limit": 500,
            "life_used": 20,
            "life_uom": "cycles",
            "calibration_required": True,
            "calibration_due_at": (now + timedelta(days=30)).isoformat(),
        },
    )
    _post(
        maintenance_authority,
        "/maintenance/tools/P6-TOOL-CAL/assignments",
        {"operation_task_id": calibration_task, "evidence_reference": "P6-CAL-ASSIGN"},
    )
    failed_calibration = _post(
        maintenance_authority,
        "/maintenance/tools/P6-TOOL-CAL/calibrations",
        {
            "calibration_code": "P6-CAL-FAIL",
            "result": "fail",
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "performed_by_personnel_code": "P6-TECH",
            "evidence_reference": "P6-CAL-FAIL-EVIDENCE",
        },
    )
    assert failed_calibration["tool_status"] == "calibration_invalid"
    blocked_calibration = maintenance_authority["client"].post(
        f"/execution/tasks/{calibration_task}/start",
        headers=maintenance_authority["headers"],
        json={"idempotency_key": "P6-CAL-BLOCK"},
    )
    assert blocked_calibration.status_code == 409
    assert blocked_calibration.json()["detail"]["code"] == "TOOL_CALIBRATION_INVALID"


def test_downtime_is_bound_to_order_and_production_task(
    maintenance_authority: dict,
) -> None:
    task_id = _new_ready_task(maintenance_authority, "DOWN")
    _post(
        maintenance_authority,
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": "P6-DOWN-START"},
        expected=200,
    )
    downtime = _post(
        maintenance_authority,
        f"/execution/tasks/{task_id}/downtime",
        {
            "downtime_code": "P6-DOWN-001",
            "idempotency_key": "P6-DOWN-OPEN",
            "reason": "Bearing replacement",
            "evidence_reference": "P6-DOWN-EVIDENCE",
        },
    )
    workflow = _create_request_order(maintenance_authority, "DOWN", task_id, int(downtime["id"]))
    started = _post(
        maintenance_authority,
        f"/maintenance/orders/{workflow['order_code']}/start",
        {"evidence_reference": "P6-DOWN-MAINT-START"},
        expected=200,
    )
    assert started["operation_task_id"] == task_id
    assert started["operation_downtime_id"] == downtime["id"]
    assert started["production_impact"] == "equipment_unavailable"
    _complete_checklist(maintenance_authority, workflow["order_code"])
    _work_complete(maintenance_authority, workflow["order_code"])
    _post(
        maintenance_authority,
        f"/maintenance/orders/{workflow['order_code']}/verify",
        {
            "verification_reference": "P6-DOWN-INDEPENDENT-VERIFY",
            "verification_result": "restored",
        },
        expected=200,
        headers=_verifier_headers(),
    )
    closed = _post(
        maintenance_authority,
        f"/execution/downtime/{downtime['id']}/end",
        {
            "idempotency_key": "P6-DOWN-CLOSE",
            "evidence_reference": "P6-DOWN-CLOSE-EVIDENCE",
        },
        expected=200,
    )
    assert closed["status"] == "closed"


def test_preventive_plan_generates_due_request_and_order(
    maintenance_authority: dict,
) -> None:
    plan = _post(
        maintenance_authority,
        "/maintenance/preventive-plans",
        {
            "plan_code": "P6-PM-PLAN",
            "asset_code": "P6-ASSET-LATHE",
            "checklist_code": "P6-CHECK",
            "checklist_revision": 1,
            "interval_hours": 168,
            "next_due_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "production_impact": "equipment_unavailable",
        },
    )
    assert plan["status"] == "draft"
    _post(
        maintenance_authority,
        "/maintenance/preventive-plans/P6-PM-PLAN/effective",
        {"evidence_reference": "P6-PM-EFFECTIVE"},
        expected=200,
    )
    generated = _post(
        maintenance_authority,
        "/maintenance/preventive-plans/P6-PM-PLAN/generate",
        {
            "request_code": "P6-PM-REQ",
            "order_code": "P6-PM-MO",
            "assigned_personnel_code": "P6-TECH",
            "planned_start_at": datetime.now(UTC).isoformat(),
            "planned_end_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
        expected=200,
    )
    assert generated["request"]["source_type"] == "preventive"
    assert generated["order"]["order_type"] == "preventive"
    assert generated["plan"]["next_due_at"] > plan["next_due_at"]


def test_spare_usage_references_phase4_consume_movement(
    maintenance_authority: dict,
) -> None:
    workflow = _create_request_order(maintenance_authority, "SPARE")
    order_code = workflow["order_code"]
    _post(
        maintenance_authority,
        f"/maintenance/orders/{order_code}/start",
        {"evidence_reference": "P6-SPARE-START"},
        expected=200,
    )
    movement = _post(
        maintenance_authority,
        "/material-flow/movements",
        {
            "movement_id": "P6-SPARE-CONSUME",
            "movement_type": "consume",
            "lot_code": "P6-SPARE-LOT",
            "quantity": 1,
            "from_location_code": "P6-MRO-LOC",
            "maintenance_order_code": order_code,
            "source": "manual",
            "reason": "P6 maintenance bearing use",
            "evidence_reference": "P6-SPARE-CONSUME-EVIDENCE",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    usage = _post(
        maintenance_authority,
        f"/maintenance/orders/{order_code}/spares",
        {
            "usage_id": "P6-SPARE-USE-001",
            "movement_id": movement["movement_id"],
            "evidence_reference": "P6-SPARE-LINK-EVIDENCE",
        },
    )
    assert usage["movement_id"] == "P6-SPARE-CONSUME"
    assert usage["movement_type"] == "consume"
    assert usage["lot_code"] == "P6-SPARE-LOT"


def test_maintenance_evidence_is_append_only(maintenance_authority: dict) -> None:
    with get_db() as db:
        checklist_result = db.execute("SELECT id FROM maintenance_check_results LIMIT 1").fetchone()
        history = db.execute("SELECT id FROM maintenance_status_history LIMIT 1").fetchone()
        verified_order = db.execute(
            "SELECT id FROM maintenance_orders WHERE status='verified' LIMIT 1"
        ).fetchone()
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                "UPDATE maintenance_check_results SET result='fail' WHERE id=?",
                (int(dict(checklist_result)["id"]),),
            )
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                "DELETE FROM maintenance_status_history WHERE id=?",
                (int(dict(history)["id"]),),
            )
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                "UPDATE maintenance_orders SET verified_by=completed_by WHERE id=?",
                (int(dict(verified_order)["id"]),),
            )


def test_maintenance_write_rolls_back_when_outbox_fails(
    maintenance_authority: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbox_repository, "enqueue_in_transaction", lambda *_args: False)
    response = maintenance_authority["client"].post(
        "/maintenance/requests",
        headers=maintenance_authority["headers"],
        json={
            "request_code": "P6-ROLLBACK-REQ",
            "asset_code": "P6-ASSET-LATHE",
            "source_type": "manual",
            "source_reference": "P6-ROLLBACK-SOURCE",
            "description": "Must roll back",
            "priority": "medium",
            "observed_at": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 500
    with get_db() as db:
        row = db.execute(
            "SELECT COUNT(*) AS count FROM maintenance_requests WHERE request_code=?",
            ("P6-ROLLBACK-REQ",),
        ).fetchone()
    assert int(dict(row)["count"]) == 0
