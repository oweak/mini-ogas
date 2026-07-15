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


def _movement(
    context: dict,
    movement_id: str,
    lot_code: str,
    quantity: float,
    *,
    movement_type: str = "receipt",
    from_location: str | None = None,
    to_location: str | None = None,
    expected: int = 201,
) -> dict:
    return _post(
        context,
        "/material-flow/movements",
        {
            "movement_id": movement_id,
            "movement_type": movement_type,
            "lot_code": lot_code,
            "quantity": quantity,
            "from_location_code": from_location,
            "to_location_code": to_location,
            "source": "manual",
            "reason": "Phase 5 quality acceptance",
            "evidence_reference": f"EVIDENCE-{movement_id}",
            "occurred_at": "2026-07-14T00:00:00+00:00",
        },
        expected=expected,
    )


@pytest.fixture(scope="module")
def quality_context() -> dict:
    client = TestClient(app)
    client.__enter__()
    login = client.post(
        "/auth/login",
        json={"operator": "admin", "password": "mini-ogas-dev-token"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    context = {"client": client, "headers": headers}
    now = datetime.now(UTC)

    for code, name, dimension in (
        ("P5-EA", "Each", "count"),
        ("P5-MM", "Millimetre", "length"),
    ):
        _post(
            context,
            "/master-data/uoms",
            {"uom_code": code, "name": name, "dimension": dimension, "scale": 1},
        )
    _post(
        context,
        "/master-data/materials",
        {
            "material_code": "P5-PART",
            "name": "Phase 5 inspected part",
            "material_type": "finished",
            "base_uom_code": "P5-EA",
        },
    )
    _post(
        context,
        "/master-data/skills",
        {"skill_code": "P5-INSPECT", "name": "Dimensional inspection", "level_min": 2},
    )
    for code, display_name, qualified in (
        ("P5-INSPECTOR", "Qualified inspector", True),
        ("P5-UNQUALIFIED", "Unqualified inspector", False),
    ):
        _post(
            context,
            "/master-data/personnel",
            {"personnel_code": code, "display_name": display_name},
        )
        if qualified:
            _post(
                context,
                "/master-data/qualifications",
                {
                    "personnel_code": code,
                    "skill_code": "P5-INSPECT",
                    "level": 2,
                    "valid_from": (now - timedelta(days=1)).isoformat(),
                    "valid_to": (now + timedelta(days=30)).isoformat(),
                    "evidence_reference": "P5-INSPECTOR-CERT",
                },
            )
    for warehouse_code, name, warehouse_type in (
        ("P5-RAW-WH", "Quality input", "raw"),
        ("P5-WIP-WH", "Quality released", "wip"),
    ):
        _post(
            context,
            "/material-flow/warehouses",
            {
                "warehouse_code": warehouse_code,
                "name": name,
                "warehouse_type": warehouse_type,
            },
        )
    for location_code, warehouse_code, location_type in (
        ("P5-RAW-01", "P5-RAW-WH", "storage"),
        ("P5-WIP-01", "P5-WIP-WH", "wip"),
    ):
        _post(
            context,
            "/material-flow/locations",
            {
                "location_code": location_code,
                "warehouse_code": warehouse_code,
                "name": location_code,
                "location_type": location_type,
            },
        )
    lot_codes = (
        "P5-FAIL",
        "P5-PASS",
        "P5-METADATA",
        "P5-SCRAP",
        "P5-REWORK",
        "P5-ROLLBACK",
    )
    for lot_code in lot_codes:
        _post(
            context,
            "/material-flow/lots",
            {
                "lot_code": lot_code,
                "material_code": "P5-PART",
                "tracking_kind": "lot",
                "evidence_reference": f"CERT-{lot_code}",
            },
        )
        _movement(context, f"RECEIPT-{lot_code}", lot_code, 5, to_location="P5-RAW-01")

    valid_gauge = _post(
        context,
        "/quality/gauges",
        {
            "gauge_code": "P5-GAUGE-VALID",
            "name": "Calibrated micrometer",
            "gauge_type": "micrometer",
            "calibration_status": "valid",
            "valid_from": (now - timedelta(days=1)).isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "evidence_reference": "P5-GAUGE-CERT",
        },
    )
    invalid_gauge = _post(
        context,
        "/quality/gauges",
        {
            "gauge_code": "P5-GAUGE-EXPIRED",
            "name": "Expired micrometer",
            "gauge_type": "micrometer",
            "calibration_status": "expired",
            "valid_from": (now - timedelta(days=30)).isoformat(),
            "valid_to": (now - timedelta(days=1)).isoformat(),
            "evidence_reference": "P5-GAUGE-EXPIRED-CERT",
        },
    )
    plan = _post(
        context,
        "/quality/inspection-plans",
        {
            "plan_code": "P5-FINAL",
            "revision": 1,
            "name": "Phase 5 final inspection",
            "material_code": "P5-PART",
            "stage": "final",
            "characteristics": [
                {
                    "characteristic_code": "P5-DIAMETER",
                    "name": "Outside diameter",
                    "value_type": "numeric",
                    "uom_code": "P5-MM",
                    "target_value": 10,
                    "lower_spec_limit": 9.9,
                    "upper_spec_limit": 10.1,
                    "method": "digital-micrometer",
                    "sample_size": 2,
                    "gauge_type": "micrometer",
                    "required_skill_code": "P5-INSPECT",
                    "required_skill_level": 2,
                }
            ],
        },
    )
    approved = _post(
        context,
        "/quality/inspection-plans/P5-FINAL/revisions/1/approve",
        {"evidence_reference": "P5-PLAN-APPROVAL"},
        expected=200,
    )
    effective = _post(
        context,
        "/quality/inspection-plans/P5-FINAL/revisions/1/effective",
        {"evidence_reference": "P5-PLAN-EFFECTIVE"},
        expected=200,
    )
    context.update(
        {
            "plan": plan,
            "approved_plan": approved,
            "effective_plan": effective,
            "valid_gauge": valid_gauge,
            "invalid_gauge": invalid_gauge,
        }
    )
    yield context
    client.__exit__(None, None, None)


def _create_inspection(context: dict, lot_code: str) -> dict:
    return _post(
        context,
        "/quality/inspection-lots",
        {
            "inspection_lot_code": f"INSP-{lot_code}",
            "plan_code": "P5-FINAL",
            "plan_revision": 1,
            "lot_code": lot_code,
            "location_code": "P5-RAW-01",
            "quantity": 5,
            "evidence_reference": f"OPEN-{lot_code}",
        },
    )


def _measurement(
    context: dict,
    lot_code: str,
    measurement_id: str,
    sample_index: int,
    value: float,
    *,
    gauge_code: str = "P5-GAUGE-VALID",
    personnel_code: str = "P5-INSPECTOR",
    method: str = "digital-micrometer",
    uom_code: str = "P5-MM",
    expected: int = 201,
) -> dict:
    return _post(
        context,
        f"/quality/inspection-lots/INSP-{lot_code}/measurements",
        {
            "measurement_id": measurement_id,
            "characteristic_code": "P5-DIAMETER",
            "sample_index": sample_index,
            "numeric_value": value,
            "uom_code": uom_code,
            "method": method,
            "gauge_code": gauge_code,
            "personnel_code": personnel_code,
            "occurred_at": "2026-07-14T00:00:00+00:00",
            "evidence_reference": f"EVIDENCE-{measurement_id}",
        },
        expected=expected,
    )


def _fail_inspection(context: dict, lot_code: str) -> dict:
    _create_inspection(context, lot_code)
    _measurement(context, lot_code, f"{lot_code}-M1", 1, 10.0)
    _measurement(context, lot_code, f"{lot_code}-M2", 2, 10.3)
    response = context["client"].get(
        f"/quality/inspection-lots/INSP-{lot_code}", headers=context["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_plan_characteristic_sampling_and_gauge_are_governed(quality_context: dict) -> None:
    assert quality_context["plan"]["status"] == "draft"
    assert quality_context["approved_plan"]["status"] == "approved"
    assert quality_context["effective_plan"]["status"] == "effective"
    characteristic = quality_context["effective_plan"]["characteristics"][0]
    assert characteristic["uom_code"] == "P5-MM"
    assert characteristic["lower_spec_limit"] == 9.9
    assert characteristic["upper_spec_limit"] == 10.1
    assert characteristic["sample_size"] == 2
    assert characteristic["method"] == "digital-micrometer"
    assert quality_context["valid_gauge"]["calibration_status"] == "valid"
    assert quality_context["invalid_gauge"]["calibration_status"] == "expired"


def test_failed_measurement_places_hold_and_creates_nonconformance(
    quality_context: dict,
) -> None:
    inspection = _create_inspection(quality_context, "P5-FAIL")
    assert inspection["status"] == "open"
    assert inspection["quality_hold"]["status"] == "open"
    blocked = quality_context["client"].post(
        "/material-flow/movements",
        headers=quality_context["headers"],
        json={
            "movement_id": "P5-FAIL-BLOCKED",
            "movement_type": "transfer",
            "lot_code": "P5-FAIL",
            "quantity": 1,
            "from_location_code": "P5-RAW-01",
            "to_location_code": "P5-WIP-01",
            "source": "manual",
            "reason": "must stay held",
            "evidence_reference": "P5-HOLD-PROBE",
            "occurred_at": "2026-07-14T00:00:00+00:00",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "QUALITY_HOLD_ACTIVE"
    first = _measurement(quality_context, "P5-FAIL", "P5-FAIL-M1", 1, 10.0)
    repeated = _measurement(quality_context, "P5-FAIL", "P5-FAIL-M1", 1, 10.0)
    assert repeated["id"] == first["id"]
    changed = quality_context["client"].post(
        "/quality/inspection-lots/INSP-P5-FAIL/measurements",
        headers=quality_context["headers"],
        json={
            "measurement_id": "P5-FAIL-M1",
            "characteristic_code": "P5-DIAMETER",
            "sample_index": 1,
            "numeric_value": 9.8,
            "uom_code": "P5-MM",
            "method": "digital-micrometer",
            "gauge_code": "P5-GAUGE-VALID",
            "personnel_code": "P5-INSPECTOR",
            "occurred_at": "2026-07-14T00:00:00+00:00",
            "evidence_reference": "CHANGED",
        },
    )
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    failed = _measurement(quality_context, "P5-FAIL", "P5-FAIL-M2", 2, 10.3)
    assert failed["result"] == "fail"
    inspection_response = quality_context["client"].get(
        "/quality/inspection-lots/INSP-P5-FAIL", headers=quality_context["headers"]
    )
    state = inspection_response.json()
    assert state["status"] == "failed"
    assert state["quality_hold"]["status"] == "open"
    assert len(state["nonconformances"]) == 1
    assert state["nonconformances"][0]["status"] == "open"


def test_measurement_requires_matching_method_unit_gauge_and_qualification(
    quality_context: dict,
) -> None:
    _create_inspection(quality_context, "P5-METADATA")
    for suffix, overrides, code in (
        ("METHOD", {"method": "visual"}, "METHOD_MISMATCH"),
        ("UOM", {"uom_code": "P5-EA"}, "MEASUREMENT_UOM_MISMATCH"),
        ("GAUGE", {"gauge_code": "P5-GAUGE-EXPIRED"}, "GAUGE_CALIBRATION_INVALID"),
        (
            "PERSON",
            {"personnel_code": "P5-UNQUALIFIED"},
            "INSPECTOR_QUALIFICATION_MISSING",
        ),
    ):
        response = quality_context["client"].post(
            "/quality/inspection-lots/INSP-P5-METADATA/measurements",
            headers=quality_context["headers"],
            json={
                "measurement_id": f"P5-META-{suffix}",
                "characteristic_code": "P5-DIAMETER",
                "sample_index": 1,
                "numeric_value": 10,
                "uom_code": overrides.get("uom_code", "P5-MM"),
                "method": overrides.get("method", "digital-micrometer"),
                "gauge_code": overrides.get("gauge_code", "P5-GAUGE-VALID"),
                "personnel_code": overrides.get("personnel_code", "P5-INSPECTOR"),
                "occurred_at": "2026-07-14T00:00:00+00:00",
                "evidence_reference": f"P5-META-{suffix}-EVIDENCE",
            },
        )
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == code


def test_ai_cannot_release_and_failed_lot_requires_approved_disposition(
    quality_context: dict,
) -> None:
    failed_release = quality_context["client"].post(
        "/quality/inspection-lots/INSP-P5-FAIL/release",
        headers=quality_context["headers"],
        json={"authorization_reference": "P5-NO-DISPOSITION"},
    )
    assert failed_release.status_code == 409
    assert failed_release.json()["detail"]["code"] == "DISPOSITION_REQUIRED"
    ai_token = issue_access_token(
        {
            "username": "phase5-ai",
            "display_name": "Phase 5 AI",
            "roles": ["ai_service"],
            "permissions": ["ai:diagnose"],
        }
    )
    ai_release = quality_context["client"].post(
        "/quality/inspection-lots/INSP-P5-FAIL/release",
        headers={"Authorization": f"Bearer {ai_token}"},
        json={"authorization_reference": "AI-MUST-NOT-RELEASE"},
    )
    assert ai_release.status_code == 403
    nc_code = (
        quality_context["client"]
        .get("/quality/inspection-lots/INSP-P5-FAIL", headers=quality_context["headers"])
        .json()["nonconformances"][0]["nc_code"]
    )
    disposition = _post(
        quality_context,
        f"/quality/nonconformances/{nc_code}/dispositions",
        {
            "disposition_code": "P5-FAIL-UAI",
            "disposition_type": "use_as_is",
            "reason": "Engineering concession after documented review",
            "evidence_reference": "P5-CONCESSION-REQUEST",
        },
    )
    assert disposition["status"] == "proposed"
    still_blocked = quality_context["client"].post(
        "/quality/inspection-lots/INSP-P5-FAIL/release",
        headers=quality_context["headers"],
        json={"authorization_reference": "P5-NOT-APPROVED"},
    )
    assert still_blocked.status_code == 409
    assert still_blocked.json()["detail"]["code"] == "DISPOSITION_NOT_APPROVED"
    approved = _post(
        quality_context,
        "/quality/dispositions/P5-FAIL-UAI/approve",
        {"authorization_reference": "P5-CONCESSION-APPROVAL"},
        expected=200,
    )
    assert approved["status"] == "approved"
    released = _post(
        quality_context,
        "/quality/inspection-lots/INSP-P5-FAIL/release",
        {"authorization_reference": "P5-QUALITY-RELEASE"},
        expected=200,
    )
    assert released["status"] == "released"
    assert released["quality_hold"]["status"] == "released"
    moved = _movement(
        quality_context,
        "P5-FAIL-AFTER-RELEASE",
        "P5-FAIL",
        1,
        movement_type="transfer",
        from_location="P5-RAW-01",
        to_location="P5-WIP-01",
    )
    assert moved["movement_type"] == "transfer"


def test_passing_inspection_requires_explicit_authorized_release(
    quality_context: dict,
) -> None:
    _create_inspection(quality_context, "P5-PASS")
    _measurement(quality_context, "P5-PASS", "P5-PASS-M1", 1, 9.95)
    _measurement(quality_context, "P5-PASS", "P5-PASS-M2", 2, 10.05)
    before_release = (
        quality_context["client"]
        .get("/quality/inspection-lots/INSP-P5-PASS", headers=quality_context["headers"])
        .json()
    )
    assert before_release["status"] == "passed"
    assert before_release["quality_hold"]["status"] == "open"
    released = _post(
        quality_context,
        "/quality/inspection-lots/INSP-P5-PASS/release",
        {"authorization_reference": "P5-PASS-RELEASE"},
        expected=200,
    )
    assert released["status"] == "released"


def test_scrap_and_rework_dispositions_do_not_restore_normal_flow(
    quality_context: dict,
) -> None:
    scrap_state = _fail_inspection(quality_context, "P5-SCRAP")
    scrap_nc = scrap_state["nonconformances"][0]["nc_code"]
    _post(
        quality_context,
        f"/quality/nonconformances/{scrap_nc}/dispositions",
        {
            "disposition_code": "P5-SCRAP-DISP",
            "disposition_type": "scrap",
            "reason": "Dimension exceeds repair envelope",
            "evidence_reference": "P5-SCRAP-REVIEW",
        },
    )
    scrap = _post(
        quality_context,
        "/quality/dispositions/P5-SCRAP-DISP/approve",
        {"authorization_reference": "P5-SCRAP-APPROVAL"},
        expected=200,
    )
    assert scrap["inspection_status"] == "dispositioned"
    assert scrap["lot_status"] == "closed"

    rework_state = _fail_inspection(quality_context, "P5-REWORK")
    rework_nc = rework_state["nonconformances"][0]["nc_code"]
    _post(
        quality_context,
        f"/quality/nonconformances/{rework_nc}/dispositions",
        {
            "disposition_code": "P5-REWORK-DISP",
            "disposition_type": "rework",
            "reason": "Controlled diameter rework required",
            "evidence_reference": "P5-REWORK-REVIEW",
        },
    )
    rework = _post(
        quality_context,
        "/quality/dispositions/P5-REWORK-DISP/approve",
        {"authorization_reference": "P5-REWORK-APPROVAL"},
        expected=200,
    )
    assert rework["inspection_status"] == "rework_required"
    held_state = (
        quality_context["client"]
        .get("/quality/inspection-lots/INSP-P5-REWORK", headers=quality_context["headers"])
        .json()
    )
    assert held_state["quality_hold"]["status"] == "open"


def test_capa_records_root_cause_action_and_effectiveness(quality_context: dict) -> None:
    nc_code = (
        quality_context["client"]
        .get("/quality/inspection-lots/INSP-P5-SCRAP", headers=quality_context["headers"])
        .json()["nonconformances"][0]["nc_code"]
    )
    capa = _post(
        quality_context,
        f"/quality/nonconformances/{nc_code}/capas",
        {
            "capa_code": "P5-CAPA-001",
            "problem_statement": "Repeated diameter oversize",
            "root_cause": "Offset verification omitted after tool change",
            "action_plan": "Add independent offset verification to setup checklist",
            "due_at": "2026-08-01T00:00:00+00:00",
            "evidence_reference": "P5-CAPA-PLAN",
        },
    )
    assert capa["status"] == "open"
    completed = _post(
        quality_context,
        "/quality/capas/P5-CAPA-001/complete",
        {
            "verification_reference": "P5-CAPA-VERIFY",
            "effectiveness_result": "Two audited setups completed without recurrence",
        },
        expected=200,
    )
    assert completed["status"] == "completed"


def test_quality_evidence_is_append_only(quality_context: dict) -> None:
    with get_db() as db:
        measurement = db.execute("SELECT id FROM quality_measurements LIMIT 1").fetchone()
        history = db.execute("SELECT id FROM quality_status_history LIMIT 1").fetchone()
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                "UPDATE quality_measurements SET result='pass' WHERE id=?",
                (int(dict(measurement)["id"]),),
            )
    with pytest.raises(sqlite3.DatabaseError):
        with get_db() as db:
            db.execute(
                "DELETE FROM quality_status_history WHERE id=?",
                (int(dict(history)["id"]),),
            )


def test_measurement_rolls_back_when_outbox_enqueue_fails(
    quality_context: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_inspection(quality_context, "P5-ROLLBACK")
    monkeypatch.setattr(outbox_repository, "enqueue_in_transaction", lambda *_args: False)
    response = quality_context["client"].post(
        "/quality/inspection-lots/INSP-P5-ROLLBACK/measurements",
        headers=quality_context["headers"],
        json={
            "measurement_id": "P5-ROLLBACK-M1",
            "characteristic_code": "P5-DIAMETER",
            "sample_index": 1,
            "numeric_value": 10,
            "uom_code": "P5-MM",
            "method": "digital-micrometer",
            "gauge_code": "P5-GAUGE-VALID",
            "personnel_code": "P5-INSPECTOR",
            "occurred_at": "2026-07-14T00:00:00+00:00",
            "evidence_reference": "P5-ROLLBACK-EVIDENCE",
        },
    )
    assert response.status_code == 500
    with get_db() as db:
        row = db.execute(
            "SELECT COUNT(*) AS count FROM quality_measurements WHERE measurement_id=?",
            ("P5-ROLLBACK-M1",),
        ).fetchone()
    assert int(dict(row)["count"]) == 0
