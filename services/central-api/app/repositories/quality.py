from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..core.config import settings
from ..core.database import get_db, persistence_backend
from ..core.nats_contracts import build_audit_envelope
from ..core.outbox import outbox_repository
from ..domain.quality import (
    AuthorizationIn,
    CapaCompleteIn,
    CapaIn,
    DispositionIn,
    GaugeIn,
    InspectionLotIn,
    InspectionPlanIn,
    MeasurementIn,
    QualityActionIn,
    QualityError,
)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _row(value: Any) -> dict[str, Any]:
    return _json_ready(dict(value))


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class QualityRepository:
    """Transactional Phase 5 inspection, hold and disposition authority."""

    def _scope(self) -> tuple[str, str]:
        return settings.tenant_id, settings.site_id

    def _lock_suffix(self, alias: str = "") -> str:
        if persistence_backend() != "postgres":
            return ""
        return f" FOR UPDATE OF {alias}" if alias else " FOR UPDATE"

    def _hash(self, payload: Any) -> str:
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def _insert_id(
        self,
        db: Any,
        sql: str,
        params: tuple[Any, ...],
        *,
        code: str = "DUPLICATE_QUALITY_RESOURCE",
        message: str = "quality resource already exists",
    ) -> int:
        try:
            row = db.execute(f"{sql} RETURNING id", params).fetchone()
        except Exception as exc:
            lowered = str(exc).lower()
            if any(token in lowered for token in ("unique", "duplicate", "constraint failed")):
                raise QualityError(409, code, message) from exc
            raise
        if row is None:
            raise RuntimeError("database insert did not return an identifier")
        return int(dict(row)["id"] if hasattr(row, "keys") else row[0])

    def _require_code(
        self, db: Any, table: str, code_column: str, code: str, resource: str
    ) -> dict[str, Any]:
        row = db.execute(
            f"SELECT * FROM {table} WHERE tenant_id=? AND site_id=? AND {code_column}=?",
            (*self._scope(), code),
        ).fetchone()
        if row is None:
            raise QualityError(
                409,
                "REFERENCE_NOT_FOUND",
                f"referenced {resource} does not exist in the active tenant/site",
                resource_type=resource,
                resource_code=code,
            )
        return _row(row)

    def _audit(
        self,
        db: Any,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        detail: dict[str, Any],
    ) -> None:
        created_at = _now()
        detail_json = _canonical_json(detail)
        row = db.execute(
            """INSERT INTO audit_logs (
                   tenant_id, site_id, run_id, actor, action, resource_type,
                   resource_id, result, detail, created_at
               ) VALUES (?, ?, 'quality', ?, ?, ?, ?, 'success', ?, ?)
               RETURNING id""",
            (
                *self._scope(),
                actor,
                action,
                resource_type,
                resource_id,
                detail_json,
                created_at,
            ),
        ).fetchone()
        audit_id = int(dict(row)["id"] if hasattr(row, "keys") else row[0])
        envelope = build_audit_envelope(
            {
                "id": audit_id,
                "run_id": "quality",
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "result": "success",
                "detail": detail_json,
                "created_at": created_at,
            },
            run_id="quality",
        )
        if not outbox_repository.enqueue_in_transaction(db, envelope):
            raise RuntimeError("failed to enqueue the quality audit envelope")

    def _history(
        self,
        db: Any,
        resource_type: str,
        resource_id: str,
        from_status: str | None,
        to_status: str,
        action: str,
        evidence_reference: str,
        actor: str,
    ) -> None:
        db.execute(
            """INSERT INTO quality_status_history (
                   tenant_id, site_id, resource_type, resource_id, from_status,
                   to_status, action, evidence_reference, actor, occurred_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                *self._scope(),
                resource_type,
                resource_id,
                from_status,
                to_status,
                action,
                evidence_reference,
                actor,
                _now(),
            ),
        )

    def _format_gauge(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM gauges WHERE tenant_id=? AND site_id=? AND id=?",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise QualityError(404, "GAUGE_NOT_FOUND", "gauge was not found")
        return _row(row)

    def create_gauge(self, payload: GaugeIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            identifier = self._insert_id(
                db,
                """INSERT INTO gauges (
                       tenant_id, site_id, gauge_code, name, gauge_type,
                       calibration_status, valid_from, valid_to,
                       evidence_reference, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.gauge_code,
                    payload.name,
                    payload.gauge_type,
                    payload.calibration_status,
                    payload.valid_from.astimezone(UTC).isoformat(),
                    payload.valid_to.astimezone(UTC).isoformat(),
                    payload.evidence_reference,
                    actor,
                ),
                code="DUPLICATE_GAUGE",
                message="gauge code already exists",
            )
            self._audit(
                db,
                actor,
                "quality:gauge-created",
                "gauge",
                payload.gauge_code,
                payload.model_dump(mode="json"),
            )
            return self._format_gauge(db, identifier)

    def _format_plan(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT plan.*, material.material_code
               FROM inspection_plans plan
               JOIN materials material ON material.id=plan.material_id
               WHERE plan.tenant_id=? AND plan.site_id=? AND plan.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise QualityError(404, "INSPECTION_PLAN_NOT_FOUND", "inspection plan was not found")
        result = _row(row)
        characteristics = db.execute(
            """SELECT characteristic.*, uom.uom_code, skill.skill_code
               FROM quality_characteristics characteristic
               LEFT JOIN uoms uom ON uom.id=characteristic.uom_id
               JOIN skills skill ON skill.id=characteristic.required_skill_id
               WHERE characteristic.tenant_id=? AND characteristic.site_id=?
                 AND characteristic.inspection_plan_id=?
               ORDER BY characteristic.id""",
            (*self._scope(), identifier),
        ).fetchall()
        result["characteristics"] = [_row(item) for item in characteristics]
        return result

    def create_plan(self, payload: InspectionPlanIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            material = self._require_code(
                db, "materials", "material_code", payload.material_code, "material"
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO inspection_plans (
                       tenant_id, site_id, plan_code, revision, name, material_id,
                       stage, operation_code, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.plan_code,
                    payload.revision,
                    payload.name,
                    int(material["id"]),
                    payload.stage,
                    payload.operation_code,
                    actor,
                ),
                code="DUPLICATE_INSPECTION_PLAN",
                message="inspection plan revision already exists",
            )
            for item in payload.characteristics:
                uom = (
                    self._require_code(db, "uoms", "uom_code", item.uom_code, "uom")
                    if item.uom_code
                    else None
                )
                skill = self._require_code(
                    db, "skills", "skill_code", item.required_skill_code, "skill"
                )
                self._insert_id(
                    db,
                    """INSERT INTO quality_characteristics (
                           tenant_id, site_id, inspection_plan_id,
                           characteristic_code, name, value_type, uom_id,
                           target_value, lower_spec_limit, upper_spec_limit,
                           expected_boolean, expected_text, method, sample_size,
                           gauge_type, required_skill_id, required_skill_level,
                           created_by
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        *self._scope(),
                        identifier,
                        item.characteristic_code,
                        item.name,
                        item.value_type,
                        int(uom["id"]) if uom else None,
                        item.target_value,
                        item.lower_spec_limit,
                        item.upper_spec_limit,
                        item.expected_boolean,
                        item.expected_text,
                        item.method,
                        item.sample_size,
                        item.gauge_type,
                        int(skill["id"]),
                        item.required_skill_level,
                        actor,
                    ),
                    code="DUPLICATE_CHARACTERISTIC",
                    message="inspection characteristic code is duplicated",
                )
            self._history(
                db,
                "inspection_plan",
                f"{payload.plan_code}:{payload.revision}",
                None,
                "draft",
                "create",
                "plan-definition",
                actor,
            )
            self._audit(
                db,
                actor,
                "quality:inspection-plan-created",
                "inspection_plan",
                f"{payload.plan_code}:{payload.revision}",
                payload.model_dump(mode="json"),
            )
            return self._format_plan(db, identifier)

    def _require_plan(
        self, db: Any, plan_code: str, revision: int, *, lock: bool = False
    ) -> dict[str, Any]:
        sql = """SELECT * FROM inspection_plans
               WHERE tenant_id=? AND site_id=? AND plan_code=? AND revision=?""" + (
            self._lock_suffix() if lock else ""
        )
        row = db.execute(sql, (*self._scope(), plan_code, revision)).fetchone()
        if row is None:
            raise QualityError(
                404,
                "INSPECTION_PLAN_NOT_FOUND",
                "inspection plan revision was not found",
                plan_code=plan_code,
                revision=revision,
            )
        return _row(row)

    def transition_plan(
        self,
        plan_code: str,
        revision: int,
        target: str,
        payload: QualityActionIn,
        actor: str,
    ) -> dict[str, Any]:
        with get_db() as db:
            plan = self._require_plan(db, plan_code, revision, lock=True)
            if plan["status"] == target:
                return self._format_plan(db, int(plan["id"]))
            expected = "draft" if target == "approved" else "approved"
            if plan["status"] != expected:
                raise QualityError(
                    409,
                    "INVALID_QUALITY_TRANSITION",
                    "inspection plan cannot enter the requested state",
                    current_status=plan["status"],
                    target_status=target,
                )
            now = _now()
            if target == "approved":
                db.execute(
                    """UPDATE inspection_plans
                       SET status='approved', approved_by=?,
                           approval_evidence_reference=?, approved_at=?
                       WHERE tenant_id=? AND site_id=? AND id=?""",
                    (
                        actor,
                        payload.evidence_reference,
                        now,
                        *self._scope(),
                        int(plan["id"]),
                    ),
                )
            else:
                effective = db.execute(
                    """SELECT id, revision FROM inspection_plans
                       WHERE tenant_id=? AND site_id=? AND plan_code=?
                         AND status='effective'""",
                    (*self._scope(), plan_code),
                ).fetchone()
                if effective is not None:
                    previous = _row(effective)
                    db.execute(
                        """UPDATE inspection_plans SET status='superseded'
                           WHERE tenant_id=? AND site_id=? AND id=?""",
                        (*self._scope(), int(previous["id"])),
                    )
                    self._history(
                        db,
                        "inspection_plan",
                        f"{plan_code}:{previous['revision']}",
                        "effective",
                        "superseded",
                        "supersede",
                        payload.evidence_reference,
                        actor,
                    )
                db.execute(
                    """UPDATE inspection_plans
                       SET status='effective', effective_by=?,
                           effectivity_evidence_reference=?, effective_at=?
                       WHERE tenant_id=? AND site_id=? AND id=?""",
                    (
                        actor,
                        payload.evidence_reference,
                        now,
                        *self._scope(),
                        int(plan["id"]),
                    ),
                )
            self._history(
                db,
                "inspection_plan",
                f"{plan_code}:{revision}",
                plan["status"],
                target,
                target,
                payload.evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                f"quality:inspection-plan-{target}",
                "inspection_plan",
                f"{plan_code}:{revision}",
                {"from_status": plan["status"], "to_status": target},
            )
            return self._format_plan(db, int(plan["id"]))

    def _format_measurement(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT measurement.*, characteristic.characteristic_code,
                      characteristic.name AS characteristic_name,
                      uom.uom_code, gauge.gauge_code, personnel.personnel_code
               FROM quality_measurements measurement
               JOIN quality_characteristics characteristic
                 ON characteristic.id=measurement.characteristic_id
               LEFT JOIN uoms uom ON uom.id=measurement.uom_id
               JOIN gauges gauge ON gauge.id=measurement.gauge_id
               JOIN personnel personnel ON personnel.id=measurement.personnel_id
               WHERE measurement.tenant_id=? AND measurement.site_id=?
                 AND measurement.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise QualityError(404, "MEASUREMENT_NOT_FOUND", "measurement was not found")
        return _row(row)

    def _format_disposition(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT disposition.*, nc.nc_code,
                      inspection.inspection_lot_code,
                      inspection.status AS inspection_status,
                      lot.lot_code, lot.status AS lot_status
               FROM quality_dispositions disposition
               JOIN nonconformances nc ON nc.id=disposition.nonconformance_id
               JOIN inspection_lots inspection ON inspection.id=nc.inspection_lot_id
               JOIN material_lots lot ON lot.id=nc.lot_id
               WHERE disposition.tenant_id=? AND disposition.site_id=?
                 AND disposition.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise QualityError(404, "DISPOSITION_NOT_FOUND", "quality disposition was not found")
        return _row(row)

    def _format_capa(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT capa.*, nc.nc_code
               FROM capa_records capa
               JOIN nonconformances nc ON nc.id=capa.nonconformance_id
               WHERE capa.tenant_id=? AND capa.site_id=? AND capa.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise QualityError(404, "CAPA_NOT_FOUND", "CAPA record was not found")
        return _row(row)

    def _format_nonconformance(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT nc.*, inspection.inspection_lot_code, lot.lot_code
               FROM nonconformances nc
               JOIN inspection_lots inspection ON inspection.id=nc.inspection_lot_id
               JOIN material_lots lot ON lot.id=nc.lot_id
               WHERE nc.tenant_id=? AND nc.site_id=? AND nc.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise QualityError(404, "NONCONFORMANCE_NOT_FOUND", "nonconformance was not found")
        result = _row(row)
        dispositions = db.execute(
            """SELECT id FROM quality_dispositions
               WHERE tenant_id=? AND site_id=? AND nonconformance_id=? ORDER BY id""",
            (*self._scope(), identifier),
        ).fetchall()
        capas = db.execute(
            """SELECT id FROM capa_records
               WHERE tenant_id=? AND site_id=? AND nonconformance_id=? ORDER BY id""",
            (*self._scope(), identifier),
        ).fetchall()
        result["dispositions"] = [
            self._format_disposition(db, int(_row(item)["id"])) for item in dispositions
        ]
        result["capas"] = [self._format_capa(db, int(_row(item)["id"])) for item in capas]
        return result

    def _format_inspection(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT inspection.*, plan.plan_code, plan.revision AS plan_revision,
                      plan.stage, lot.lot_code, location.location_code,
                      material.material_code
               FROM inspection_lots inspection
               JOIN inspection_plans plan ON plan.id=inspection.inspection_plan_id
               JOIN material_lots lot ON lot.id=inspection.lot_id
               JOIN materials material ON material.id=lot.material_id
               JOIN inventory_locations location ON location.id=inspection.location_id
               WHERE inspection.tenant_id=? AND inspection.site_id=?
                 AND inspection.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise QualityError(404, "INSPECTION_LOT_NOT_FOUND", "inspection lot was not found")
        result = _row(row)
        hold = db.execute(
            """SELECT * FROM quality_holds
               WHERE tenant_id=? AND site_id=? AND inspection_lot_id=?
               ORDER BY id DESC LIMIT 1""",
            (*self._scope(), identifier),
        ).fetchone()
        measurements = db.execute(
            """SELECT id FROM quality_measurements
               WHERE tenant_id=? AND site_id=? AND inspection_lot_id=?
               ORDER BY characteristic_id, sample_index""",
            (*self._scope(), identifier),
        ).fetchall()
        nonconformances = db.execute(
            """SELECT id FROM nonconformances
               WHERE tenant_id=? AND site_id=? AND inspection_lot_id=? ORDER BY id""",
            (*self._scope(), identifier),
        ).fetchall()
        result["quality_hold"] = _row(hold) if hold is not None else None
        result["measurements"] = [
            self._format_measurement(db, int(_row(item)["id"])) for item in measurements
        ]
        result["nonconformances"] = [
            self._format_nonconformance(db, int(_row(item)["id"])) for item in nonconformances
        ]
        return result

    def _require_inspection(
        self, db: Any, inspection_lot_code: str, *, lock: bool = False
    ) -> dict[str, Any]:
        sql = """SELECT * FROM inspection_lots
               WHERE tenant_id=? AND site_id=? AND inspection_lot_code=?""" + (
            self._lock_suffix() if lock else ""
        )
        row = db.execute(sql, (*self._scope(), inspection_lot_code)).fetchone()
        if row is None:
            raise QualityError(
                404,
                "INSPECTION_LOT_NOT_FOUND",
                "inspection lot was not found",
                inspection_lot_code=inspection_lot_code,
            )
        return _row(row)

    def get_inspection(self, inspection_lot_code: str) -> dict[str, Any]:
        with get_db() as db:
            inspection = self._require_inspection(db, inspection_lot_code)
            return self._format_inspection(db, int(inspection["id"]))

    def create_inspection(self, payload: InspectionLotIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            plan = self._require_plan(db, payload.plan_code, payload.plan_revision)
            if plan["status"] != "effective":
                raise QualityError(
                    409,
                    "INSPECTION_PLAN_NOT_EFFECTIVE",
                    "inspection lot requires an effective inspection plan revision",
                )
            lot = self._require_code(
                db, "material_lots", "lot_code", payload.lot_code, "material lot"
            )
            if lot["status"] != "active":
                raise QualityError(
                    409,
                    "LOT_NOT_ACTIVE",
                    "inspection requires an active material lot or serial",
                    lot_code=payload.lot_code,
                )
            if int(lot["material_id"]) != int(plan["material_id"]):
                raise QualityError(
                    409,
                    "INSPECTION_PLAN_MATERIAL_MISMATCH",
                    "inspection plan material does not match the selected lot",
                )
            location = self._require_code(
                db,
                "inventory_locations",
                "location_code",
                payload.location_code,
                "inventory location",
            )
            balance = db.execute(
                """SELECT COALESCE(SUM(quantity), 0) AS quantity
                   FROM inventory_balances
                   WHERE tenant_id=? AND site_id=? AND lot_id=? AND location_id=?""",
                (*self._scope(), int(lot["id"]), int(location["id"])),
            ).fetchone()
            available = float(_row(balance)["quantity"])
            if payload.quantity > available + 1e-9:
                raise QualityError(
                    409,
                    "INSPECTION_QUANTITY_UNAVAILABLE",
                    "inspection quantity exceeds material at the selected location",
                    available_quantity=available,
                )
            existing_hold = db.execute(
                """SELECT hold_code FROM quality_holds
                   WHERE tenant_id=? AND site_id=? AND lot_id=? AND status='open'""",
                (*self._scope(), int(lot["id"])),
            ).fetchone()
            if existing_hold is not None:
                raise QualityError(
                    409,
                    "QUALITY_HOLD_ALREADY_ACTIVE",
                    "material lot already has an open quality hold",
                    hold_code=_row(existing_hold)["hold_code"],
                )
            if payload.operation_task_id is not None:
                task = db.execute(
                    """SELECT id FROM operation_tasks
                       WHERE tenant_id=? AND site_id=? AND id=?""",
                    (*self._scope(), payload.operation_task_id),
                ).fetchone()
                if task is None:
                    raise QualityError(
                        409,
                        "OPERATION_TASK_NOT_FOUND",
                        "inspection references an unknown operation task",
                    )
            now = _now()
            identifier = self._insert_id(
                db,
                """INSERT INTO inspection_lots (
                       tenant_id, site_id, inspection_lot_code,
                       inspection_plan_id, lot_id, location_id, operation_task_id,
                       quantity, evidence_reference, opened_by, opened_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.inspection_lot_code,
                    int(plan["id"]),
                    int(lot["id"]),
                    int(location["id"]),
                    payload.operation_task_id,
                    payload.quantity,
                    payload.evidence_reference,
                    actor,
                    now,
                ),
                code="DUPLICATE_INSPECTION_LOT",
                message="inspection lot code already exists",
            )
            self._insert_id(
                db,
                """INSERT INTO quality_holds (
                       tenant_id, site_id, hold_code, inspection_lot_id, lot_id,
                       reason, placed_by, placed_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    f"{payload.inspection_lot_code}-HOLD",
                    identifier,
                    int(lot["id"]),
                    "inspection pending authorized quality decision",
                    actor,
                    now,
                ),
                code="QUALITY_HOLD_ALREADY_ACTIVE",
                message="material lot already has an open quality hold",
            )
            self._history(
                db,
                "inspection_lot",
                payload.inspection_lot_code,
                None,
                "open",
                "open",
                payload.evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "quality:inspection-opened",
                "inspection_lot",
                payload.inspection_lot_code,
                payload.model_dump(mode="json"),
            )
            return self._format_inspection(db, identifier)

    def _require_characteristic(
        self, db: Any, inspection_plan_id: int, characteristic_code: str
    ) -> dict[str, Any]:
        row = db.execute(
            """SELECT characteristic.*, uom.uom_code, skill.skill_code
               FROM quality_characteristics characteristic
               LEFT JOIN uoms uom ON uom.id=characteristic.uom_id
               JOIN skills skill ON skill.id=characteristic.required_skill_id
               WHERE characteristic.tenant_id=? AND characteristic.site_id=?
                 AND characteristic.inspection_plan_id=?
                 AND characteristic.characteristic_code=?""",
            (*self._scope(), inspection_plan_id, characteristic_code),
        ).fetchone()
        if row is None:
            raise QualityError(
                409,
                "CHARACTERISTIC_NOT_IN_PLAN",
                "measurement characteristic is not part of the inspection plan",
                characteristic_code=characteristic_code,
            )
        return _row(row)

    def _validate_measurement_context(
        self,
        db: Any,
        characteristic: dict[str, Any],
        payload: MeasurementIn,
    ) -> tuple[dict[str, Any], dict[str, Any], int | None, str]:
        if payload.sample_index > int(characteristic["sample_size"]):
            raise QualityError(
                409,
                "SAMPLE_INDEX_OUT_OF_RANGE",
                "sample index exceeds the inspection plan sample size",
                sample_size=int(characteristic["sample_size"]),
            )
        if payload.method != characteristic["method"]:
            raise QualityError(
                409,
                "METHOD_MISMATCH",
                "measurement method does not match the effective inspection plan",
                required_method=characteristic["method"],
            )
        expected_uom = characteristic.get("uom_code")
        if payload.uom_code != expected_uom:
            raise QualityError(
                409,
                "MEASUREMENT_UOM_MISMATCH",
                "measurement UOM does not match the characteristic specification",
                required_uom=expected_uom,
            )
        if characteristic["value_type"] == "numeric":
            if payload.numeric_value is None:
                raise QualityError(
                    409, "MEASUREMENT_VALUE_TYPE_MISMATCH", "numeric value is required"
                )
            lower = characteristic.get("lower_spec_limit")
            upper = characteristic.get("upper_spec_limit")
            passed = (lower is None or payload.numeric_value >= float(lower)) and (
                upper is None or payload.numeric_value <= float(upper)
            )
        elif characteristic["value_type"] == "boolean":
            if payload.boolean_value is None:
                raise QualityError(
                    409, "MEASUREMENT_VALUE_TYPE_MISMATCH", "boolean value is required"
                )
            passed = bool(payload.boolean_value) == bool(characteristic["expected_boolean"])
        else:
            if payload.text_value is None:
                raise QualityError(409, "MEASUREMENT_VALUE_TYPE_MISMATCH", "text value is required")
            passed = payload.text_value == characteristic["expected_text"]
        gauge = self._require_code(db, "gauges", "gauge_code", payload.gauge_code, "gauge")
        if gauge["gauge_type"] != characteristic["gauge_type"]:
            raise QualityError(
                409,
                "GAUGE_TYPE_MISMATCH",
                "gauge type does not match the characteristic requirement",
                required_gauge_type=characteristic["gauge_type"],
            )
        occurred_at = payload.occurred_at.astimezone(UTC)
        if (
            gauge["calibration_status"] != "valid"
            or occurred_at < _as_datetime(gauge["valid_from"])
            or occurred_at > _as_datetime(gauge["valid_to"])
        ):
            raise QualityError(
                409,
                "GAUGE_CALIBRATION_INVALID",
                "gauge calibration is not valid at measurement time",
                gauge_code=payload.gauge_code,
                calibration_status=gauge["calibration_status"],
            )
        personnel = self._require_code(
            db, "personnel", "personnel_code", payload.personnel_code, "personnel"
        )
        if not bool(personnel["active"]):
            raise QualityError(
                409,
                "INSPECTOR_INACTIVE",
                "measurement personnel is inactive",
                personnel_code=payload.personnel_code,
            )
        qualification = db.execute(
            """SELECT qualification.id FROM personnel_qualifications qualification
               WHERE qualification.tenant_id=? AND qualification.site_id=?
                 AND qualification.personnel_id=? AND qualification.skill_id=?
                 AND qualification.level>=? AND qualification.valid_from<=?
                 AND qualification.valid_to>=?
               ORDER BY qualification.level DESC LIMIT 1""",
            (
                *self._scope(),
                int(personnel["id"]),
                int(characteristic["required_skill_id"]),
                int(characteristic["required_skill_level"]),
                occurred_at.isoformat(),
                occurred_at.isoformat(),
            ),
        ).fetchone()
        if qualification is None:
            raise QualityError(
                409,
                "INSPECTOR_QUALIFICATION_MISSING",
                "measurement personnel lacks a current required qualification",
                personnel_code=payload.personnel_code,
                skill_code=characteristic["skill_code"],
            )
        return gauge, personnel, characteristic.get("uom_id"), "pass" if passed else "fail"

    def _evaluate_inspection(
        self, db: Any, inspection: dict[str, Any], actor: str, evidence_reference: str
    ) -> None:
        required_row = db.execute(
            """SELECT COALESCE(SUM(sample_size), 0) AS required
               FROM quality_characteristics
               WHERE tenant_id=? AND site_id=? AND inspection_plan_id=?""",
            (*self._scope(), int(inspection["inspection_plan_id"])),
        ).fetchone()
        measured_row = db.execute(
            """SELECT COUNT(*) AS measured,
                      SUM(CASE WHEN result='fail' THEN 1 ELSE 0 END) AS failed
               FROM quality_measurements
               WHERE tenant_id=? AND site_id=? AND inspection_lot_id=?""",
            (*self._scope(), int(inspection["id"])),
        ).fetchone()
        required = int(_row(required_row)["required"])
        measured_data = _row(measured_row)
        measured = int(measured_data["measured"])
        failed = int(measured_data["failed"] or 0)
        if measured < required:
            return
        target = "failed" if failed else "passed"
        db.execute(
            """UPDATE inspection_lots SET status=?, result_evaluated_at=?
               WHERE tenant_id=? AND site_id=? AND id=? AND status='open'""",
            (target, _now(), *self._scope(), int(inspection["id"])),
        )
        self._history(
            db,
            "inspection_lot",
            inspection["inspection_lot_code"],
            "open",
            target,
            "evaluate",
            evidence_reference,
            actor,
        )
        if failed:
            failed_codes = db.execute(
                """SELECT DISTINCT characteristic.characteristic_code
                   FROM quality_measurements measurement
                   JOIN quality_characteristics characteristic
                     ON characteristic.id=measurement.characteristic_id
                   WHERE measurement.tenant_id=? AND measurement.site_id=?
                     AND measurement.inspection_lot_id=? AND measurement.result='fail'
                   ORDER BY characteristic.characteristic_code""",
                (*self._scope(), int(inspection["id"])),
            ).fetchall()
            codes = [str(_row(item)["characteristic_code"]) for item in failed_codes]
            self._insert_id(
                db,
                """INSERT INTO nonconformances (
                       tenant_id, site_id, nc_code, inspection_lot_id, lot_id,
                       severity, description, affected_quantity, opened_by, opened_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    f"{inspection['inspection_lot_code']}-NC",
                    int(inspection["id"]),
                    int(inspection["lot_id"]),
                    "major",
                    "Failed characteristics: " + ", ".join(codes),
                    float(inspection["quantity"]),
                    actor,
                    _now(),
                ),
                code="DUPLICATE_NONCONFORMANCE",
                message="inspection lot already has a nonconformance",
            )
            self._history(
                db,
                "nonconformance",
                f"{inspection['inspection_lot_code']}-NC",
                None,
                "open",
                "open",
                evidence_reference,
                actor,
            )

    def record_measurement(
        self, inspection_lot_code: str, payload: MeasurementIn, actor: str
    ) -> dict[str, Any]:
        request_hash = self._hash(payload.model_dump(mode="json"))
        with get_db() as db:
            existing = db.execute(
                """SELECT id, request_hash FROM quality_measurements
                   WHERE tenant_id=? AND site_id=? AND measurement_id=?""",
                (*self._scope(), payload.measurement_id),
            ).fetchone()
            if existing is not None:
                data = _row(existing)
                if data["request_hash"] != request_hash:
                    raise QualityError(
                        409,
                        "IDEMPOTENCY_KEY_REUSED",
                        "measurement_id was already used with a different request",
                        measurement_id=payload.measurement_id,
                    )
                return self._format_measurement(db, int(data["id"]))
            inspection = self._require_inspection(db, inspection_lot_code, lock=True)
            if inspection["status"] != "open":
                raise QualityError(
                    409,
                    "INSPECTION_NOT_OPEN",
                    "measurements can be recorded only while inspection is open",
                    status=inspection["status"],
                )
            characteristic = self._require_characteristic(
                db,
                int(inspection["inspection_plan_id"]),
                payload.characteristic_code,
            )
            gauge, personnel, uom_id, result = self._validate_measurement_context(
                db, characteristic, payload
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO quality_measurements (
                       tenant_id, site_id, measurement_id, inspection_lot_id,
                       characteristic_id, sample_index, numeric_value,
                       boolean_value, text_value, uom_id, method, gauge_id,
                       personnel_id, occurred_at, evidence_reference, result,
                       request_hash, recorded_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.measurement_id,
                    int(inspection["id"]),
                    int(characteristic["id"]),
                    payload.sample_index,
                    payload.numeric_value,
                    payload.boolean_value,
                    payload.text_value,
                    int(uom_id) if uom_id is not None else None,
                    payload.method,
                    int(gauge["id"]),
                    int(personnel["id"]),
                    payload.occurred_at.astimezone(UTC).isoformat(),
                    payload.evidence_reference,
                    result,
                    request_hash,
                    actor,
                ),
                code="DUPLICATE_MEASUREMENT_SAMPLE",
                message="measurement ID or characteristic sample already exists",
            )
            self._evaluate_inspection(db, inspection, actor, payload.evidence_reference)
            self._audit(
                db,
                actor,
                "quality:measurement-recorded",
                "quality_measurement",
                payload.measurement_id,
                {
                    "inspection_lot_code": inspection_lot_code,
                    "characteristic_code": payload.characteristic_code,
                    "sample_index": payload.sample_index,
                    "gauge_code": payload.gauge_code,
                    "personnel_code": payload.personnel_code,
                    "result": result,
                },
            )
            return self._format_measurement(db, identifier)

    def _require_nonconformance(
        self, db: Any, nc_code: str, *, lock: bool = False
    ) -> dict[str, Any]:
        sql = """SELECT * FROM nonconformances
               WHERE tenant_id=? AND site_id=? AND nc_code=?""" + (
            self._lock_suffix() if lock else ""
        )
        row = db.execute(sql, (*self._scope(), nc_code)).fetchone()
        if row is None:
            raise QualityError(
                404,
                "NONCONFORMANCE_NOT_FOUND",
                "nonconformance was not found",
                nc_code=nc_code,
            )
        return _row(row)

    def create_disposition(
        self, nc_code: str, payload: DispositionIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            nc = self._require_nonconformance(db, nc_code, lock=True)
            if nc["status"] not in {"open", "dispositioned"}:
                raise QualityError(
                    409,
                    "NONCONFORMANCE_NOT_OPEN",
                    "disposition requires an open nonconformance",
                    status=nc["status"],
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO quality_dispositions (
                       tenant_id, site_id, disposition_code, nonconformance_id,
                       disposition_type, reason, evidence_reference,
                       proposed_by, proposed_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.disposition_code,
                    int(nc["id"]),
                    payload.disposition_type,
                    payload.reason,
                    payload.evidence_reference,
                    actor,
                    _now(),
                ),
                code="DUPLICATE_DISPOSITION",
                message="quality disposition code already exists",
            )
            self._history(
                db,
                "quality_disposition",
                payload.disposition_code,
                None,
                "proposed",
                "propose",
                payload.evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "quality:disposition-proposed",
                "quality_disposition",
                payload.disposition_code,
                {"nc_code": nc_code, **payload.model_dump(mode="json")},
            )
            return self._format_disposition(db, identifier)

    def _require_disposition(
        self, db: Any, disposition_code: str, *, lock: bool = False
    ) -> dict[str, Any]:
        sql = """SELECT * FROM quality_dispositions disposition
               WHERE disposition.tenant_id=? AND disposition.site_id=?
                 AND disposition.disposition_code=?""" + (
            self._lock_suffix("disposition") if lock else ""
        )
        row = db.execute(sql, (*self._scope(), disposition_code)).fetchone()
        if row is None:
            raise QualityError(
                404,
                "DISPOSITION_NOT_FOUND",
                "quality disposition was not found",
                disposition_code=disposition_code,
            )
        return _row(row)

    def approve_disposition(
        self,
        disposition_code: str,
        payload: AuthorizationIn,
        actor: str,
    ) -> dict[str, Any]:
        with get_db() as db:
            disposition = self._require_disposition(db, disposition_code, lock=True)
            if disposition["status"] == "approved":
                return self._format_disposition(db, int(disposition["id"]))
            if disposition["status"] != "proposed":
                raise QualityError(
                    409,
                    "INVALID_QUALITY_TRANSITION",
                    "only a proposed disposition can be approved",
                    status=disposition["status"],
                )
            nc = db.execute(
                """SELECT * FROM nonconformances
                   WHERE tenant_id=? AND site_id=? AND id=?""",
                (*self._scope(), int(disposition["nonconformance_id"])),
            ).fetchone()
            nc_data = _row(nc)
            inspection = db.execute(
                """SELECT * FROM inspection_lots
                   WHERE tenant_id=? AND site_id=? AND id=?""",
                (*self._scope(), int(nc_data["inspection_lot_id"])),
            ).fetchone()
            inspection_data = _row(inspection)
            now = _now()
            db.execute(
                """UPDATE quality_dispositions
                   SET status='approved', approved_by=?,
                       authorization_reference=?, approved_at=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='proposed'""",
                (
                    actor,
                    payload.authorization_reference,
                    now,
                    *self._scope(),
                    int(disposition["id"]),
                ),
            )
            db.execute(
                """UPDATE nonconformances SET status='dispositioned'
                   WHERE tenant_id=? AND site_id=? AND id=?""",
                (*self._scope(), int(nc_data["id"])),
            )
            disposition_type = disposition["disposition_type"]
            if disposition_type in {"scrap", "return_to_supplier"}:
                db.execute(
                    """UPDATE inspection_lots SET status='dispositioned'
                       WHERE tenant_id=? AND site_id=? AND id=?""",
                    (*self._scope(), int(inspection_data["id"])),
                )
                db.execute(
                    """UPDATE quality_holds
                       SET status='disposed', resolved_by=?,
                           resolution_evidence_reference=?, resolved_at=?
                       WHERE tenant_id=? AND site_id=? AND inspection_lot_id=?
                         AND status='open'""",
                    (
                        actor,
                        payload.authorization_reference,
                        now,
                        *self._scope(),
                        int(inspection_data["id"]),
                    ),
                )
                db.execute(
                    """UPDATE material_lots SET status='closed'
                       WHERE tenant_id=? AND site_id=? AND id=?""",
                    (*self._scope(), int(nc_data["lot_id"])),
                )
                self._history(
                    db,
                    "inspection_lot",
                    inspection_data["inspection_lot_code"],
                    inspection_data["status"],
                    "dispositioned",
                    disposition_type,
                    payload.authorization_reference,
                    actor,
                )
            elif disposition_type == "rework":
                db.execute(
                    """UPDATE inspection_lots SET status='rework_required'
                       WHERE tenant_id=? AND site_id=? AND id=?""",
                    (*self._scope(), int(inspection_data["id"])),
                )
                self._history(
                    db,
                    "inspection_lot",
                    inspection_data["inspection_lot_code"],
                    inspection_data["status"],
                    "rework_required",
                    "rework-disposition",
                    payload.authorization_reference,
                    actor,
                )
            self._history(
                db,
                "quality_disposition",
                disposition_code,
                "proposed",
                "approved",
                "approve",
                payload.authorization_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "quality:disposition-approved",
                "quality_disposition",
                disposition_code,
                {
                    "disposition_type": disposition_type,
                    "nc_code": nc_data["nc_code"],
                    "authorization_reference": payload.authorization_reference,
                },
            )
            return self._format_disposition(db, int(disposition["id"]))

    def release_inspection(
        self,
        inspection_lot_code: str,
        payload: AuthorizationIn,
        actor: str,
    ) -> dict[str, Any]:
        with get_db() as db:
            inspection = self._require_inspection(db, inspection_lot_code, lock=True)
            if inspection["status"] == "released":
                return self._format_inspection(db, int(inspection["id"]))
            if inspection["status"] == "failed":
                dispositions = db.execute(
                    """SELECT disposition.status FROM nonconformances nc
                       JOIN quality_dispositions disposition
                         ON disposition.nonconformance_id=nc.id
                       WHERE nc.tenant_id=? AND nc.site_id=?
                         AND nc.inspection_lot_id=?
                         AND disposition.disposition_type='use_as_is'
                       ORDER BY disposition.id DESC""",
                    (*self._scope(), int(inspection["id"])),
                ).fetchall()
                if not dispositions:
                    raise QualityError(
                        409,
                        "DISPOSITION_REQUIRED",
                        "failed inspection requires a quality disposition before release",
                    )
                if not any(_row(item)["status"] == "approved" for item in dispositions):
                    raise QualityError(
                        409,
                        "DISPOSITION_NOT_APPROVED",
                        "use-as-is disposition requires separate approval before release",
                    )
            elif inspection["status"] != "passed":
                raise QualityError(
                    409,
                    "INSPECTION_NOT_RELEASABLE",
                    "inspection is not in a releasable state",
                    status=inspection["status"],
                )
            now = _now()
            db.execute(
                """UPDATE inspection_lots
                   SET status='released', released_by=?,
                       release_authorization_reference=?, released_at=?
                   WHERE tenant_id=? AND site_id=? AND id=?""",
                (
                    actor,
                    payload.authorization_reference,
                    now,
                    *self._scope(),
                    int(inspection["id"]),
                ),
            )
            updated = db.execute(
                """UPDATE quality_holds
                   SET status='released', resolved_by=?,
                       resolution_evidence_reference=?, resolved_at=?
                   WHERE tenant_id=? AND site_id=? AND inspection_lot_id=?
                     AND status='open'""",
                (
                    actor,
                    payload.authorization_reference,
                    now,
                    *self._scope(),
                    int(inspection["id"]),
                ),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise QualityError(
                    409,
                    "QUALITY_HOLD_NOT_OPEN",
                    "inspection release requires one open quality hold",
                )
            self._history(
                db,
                "inspection_lot",
                inspection_lot_code,
                inspection["status"],
                "released",
                "release",
                payload.authorization_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "quality:inspection-released",
                "inspection_lot",
                inspection_lot_code,
                {
                    "from_status": inspection["status"],
                    "authorization_reference": payload.authorization_reference,
                },
            )
            return self._format_inspection(db, int(inspection["id"]))

    def create_capa(self, nc_code: str, payload: CapaIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            nc = self._require_nonconformance(db, nc_code)
            identifier = self._insert_id(
                db,
                """INSERT INTO capa_records (
                       tenant_id, site_id, capa_code, nonconformance_id,
                       problem_statement, root_cause, action_plan, due_at,
                       evidence_reference, created_by, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.capa_code,
                    int(nc["id"]),
                    payload.problem_statement,
                    payload.root_cause,
                    payload.action_plan,
                    payload.due_at.astimezone(UTC).isoformat(),
                    payload.evidence_reference,
                    actor,
                    _now(),
                ),
                code="DUPLICATE_CAPA",
                message="CAPA code already exists",
            )
            self._history(
                db,
                "capa",
                payload.capa_code,
                None,
                "open",
                "open",
                payload.evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "quality:capa-opened",
                "capa",
                payload.capa_code,
                {"nc_code": nc_code, **payload.model_dump(mode="json")},
            )
            return self._format_capa(db, identifier)

    def complete_capa(self, capa_code: str, payload: CapaCompleteIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            sql = """SELECT * FROM capa_records
                   WHERE tenant_id=? AND site_id=? AND capa_code=?""" + self._lock_suffix()
            row = db.execute(sql, (*self._scope(), capa_code)).fetchone()
            if row is None:
                raise QualityError(404, "CAPA_NOT_FOUND", "CAPA record was not found")
            capa = _row(row)
            if capa["status"] == "completed":
                return self._format_capa(db, int(capa["id"]))
            if capa["status"] != "open":
                raise QualityError(
                    409,
                    "INVALID_QUALITY_TRANSITION",
                    "only an open CAPA can be completed",
                )
            db.execute(
                """UPDATE capa_records
                   SET status='completed', verification_reference=?,
                       effectiveness_result=?, completed_by=?, completed_at=?
                   WHERE tenant_id=? AND site_id=? AND id=?""",
                (
                    payload.verification_reference,
                    payload.effectiveness_result,
                    actor,
                    _now(),
                    *self._scope(),
                    int(capa["id"]),
                ),
            )
            self._history(
                db,
                "capa",
                capa_code,
                "open",
                "completed",
                "complete",
                payload.verification_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "quality:capa-completed",
                "capa",
                capa_code,
                payload.model_dump(mode="json"),
            )
            return self._format_capa(db, int(capa["id"]))


quality_repository = QualityRepository()
