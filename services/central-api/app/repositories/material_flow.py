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
from ..domain.material_flow import (
    ContainerIn,
    ExternalSnapshotIn,
    LocationIn,
    LotIn,
    MaterialFlowError,
    MovementIn,
    ReconciliationAdjustmentIn,
    TransformationIn,
    WarehouseIn,
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


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_ready(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _row(value: Any) -> dict[str, Any]:
    return _json_ready(dict(value))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _same_quantity(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= 1e-9


class MaterialFlowRepository:
    """Transactional Phase 4 material, balance, lineage and reconciliation authority."""

    def _scope(self) -> tuple[str, str]:
        return settings.tenant_id, settings.site_id

    def _lock_suffix(self) -> str:
        return " FOR UPDATE" if persistence_backend() == "postgres" else ""

    def _hash(self, payload: Any) -> str:
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def _insert_id(
        self,
        db: Any,
        sql: str,
        params: tuple[Any, ...],
        *,
        code: str = "DUPLICATE_MATERIAL_RESOURCE",
        message: str = "material-flow resource already exists",
    ) -> int:
        try:
            row = db.execute(f"{sql} RETURNING id", params).fetchone()
        except Exception as exc:
            lowered = str(exc).lower()
            if any(token in lowered for token in ("unique", "duplicate", "constraint failed")):
                raise MaterialFlowError(409, code, message) from exc
            raise
        if row is None:
            raise RuntimeError("database insert did not return an identifier")
        return int(dict(row)["id"] if hasattr(row, "keys") else row[0])

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
               ) VALUES (?, ?, 'material-flow', ?, ?, ?, ?, 'success', ?, ?)
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
                "run_id": "material-flow",
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "result": "success",
                "detail": detail_json,
                "created_at": created_at,
            },
            run_id="material-flow",
        )
        if not outbox_repository.enqueue_in_transaction(db, envelope):
            raise RuntimeError("failed to enqueue the material-flow audit envelope")

    def _require_code(
        self, db: Any, table: str, code_column: str, code: str, resource: str
    ) -> dict[str, Any]:
        row = db.execute(
            f"SELECT * FROM {table} WHERE tenant_id=? AND site_id=? AND {code_column}=?",
            (*self._scope(), code),
        ).fetchone()
        if row is None:
            raise MaterialFlowError(
                409,
                "REFERENCE_NOT_FOUND",
                f"referenced {resource} does not exist in the active tenant/site",
                resource_type=resource,
                resource_code=code,
            )
        return _row(row)

    def _require_lot(self, db: Any, lot_code: str) -> dict[str, Any]:
        row = db.execute(
            """SELECT lot.*, material.material_code, uom.uom_code, uom.dimension, uom.scale
               FROM material_lots lot
               JOIN materials material ON material.id=lot.material_id
               JOIN uoms uom ON uom.id=lot.uom_id
               WHERE lot.tenant_id=? AND lot.site_id=? AND lot.lot_code=?""",
            (*self._scope(), lot_code),
        ).fetchone()
        if row is None:
            raise MaterialFlowError(
                409, "LOT_NOT_FOUND", "material lot or serial was not found", lot_code=lot_code
            )
        return _row(row)

    def _assert_no_quality_hold(self, db: Any, lot: dict[str, Any]) -> None:
        row = db.execute(
            """SELECT hold_code FROM quality_holds
               WHERE tenant_id=? AND site_id=? AND lot_id=? AND status='open'
               ORDER BY id LIMIT 1""",
            (*self._scope(), int(lot["id"])),
        ).fetchone()
        if row is not None:
            hold = _row(row)
            raise MaterialFlowError(
                409,
                "QUALITY_HOLD_ACTIVE",
                "material lot is blocked by an open quality hold",
                lot_code=lot["lot_code"],
                hold_code=hold["hold_code"],
            )

    def _require_location(self, db: Any, location_code: str) -> dict[str, Any]:
        row = db.execute(
            """SELECT location.*, warehouse.warehouse_code, warehouse.warehouse_type
               FROM inventory_locations location
               JOIN warehouses warehouse ON warehouse.id=location.warehouse_id
               WHERE location.tenant_id=? AND location.site_id=?
                 AND location.location_code=?""",
            (*self._scope(), location_code),
        ).fetchone()
        if row is None:
            raise MaterialFlowError(
                409,
                "LOCATION_NOT_FOUND",
                "inventory location was not found",
                location_code=location_code,
            )
        result = _row(row)
        if not bool(result["active"]):
            raise MaterialFlowError(
                409,
                "LOCATION_INACTIVE",
                "inventory location is inactive",
                location_code=location_code,
            )
        return result

    def _resolve_container(
        self,
        db: Any,
        container_code: str | None,
        location: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not container_code:
            return None
        container = self._require_code(
            db, "material_containers", "container_code", container_code, "container"
        )
        if container["status"] != "active":
            raise MaterialFlowError(
                409,
                "CONTAINER_NOT_ACTIVE",
                "material container is not active",
                container_code=container_code,
            )
        if location is None or int(container["location_id"]) != int(location["id"]):
            raise MaterialFlowError(
                409,
                "CONTAINER_LOCATION_MISMATCH",
                "container is not registered at the selected location",
                container_code=container_code,
            )
        return container

    def _format_warehouse(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM warehouses WHERE tenant_id=? AND site_id=? AND id=?",
            (*self._scope(), identifier),
        ).fetchone()
        return _row(row)

    def create_warehouse(self, payload: WarehouseIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            identifier = self._insert_id(
                db,
                """INSERT INTO warehouses (
                       tenant_id, site_id, warehouse_code, name, warehouse_type, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.warehouse_code,
                    payload.name,
                    payload.warehouse_type,
                    actor,
                ),
                message="warehouse code already exists",
            )
            self._audit(
                db,
                actor,
                "material-flow:warehouse-created",
                "warehouse",
                payload.warehouse_code,
                payload.model_dump(mode="json"),
            )
            return self._format_warehouse(db, identifier)

    def create_location(self, payload: LocationIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            warehouse = self._require_code(
                db, "warehouses", "warehouse_code", payload.warehouse_code, "warehouse"
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO inventory_locations (
                       tenant_id, site_id, location_code, warehouse_id, name,
                       location_type, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.location_code,
                    int(warehouse["id"]),
                    payload.name,
                    payload.location_type,
                    actor,
                ),
                message="inventory location code already exists",
            )
            row = db.execute(
                """SELECT location.*, warehouse.warehouse_code
                   FROM inventory_locations location
                   JOIN warehouses warehouse ON warehouse.id=location.warehouse_id
                   WHERE location.tenant_id=? AND location.site_id=? AND location.id=?""",
                (*self._scope(), identifier),
            ).fetchone()
            self._audit(
                db,
                actor,
                "material-flow:location-created",
                "inventory_location",
                payload.location_code,
                payload.model_dump(mode="json"),
            )
            return _row(row)

    def create_container(self, payload: ContainerIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            location = self._require_location(db, payload.location_code)
            identifier = self._insert_id(
                db,
                """INSERT INTO material_containers (
                       tenant_id, site_id, container_code, container_type,
                       location_id, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.container_code,
                    payload.container_type,
                    int(location["id"]),
                    actor,
                ),
                message="container code already exists",
            )
            row = db.execute(
                """SELECT container.*, location.location_code
                   FROM material_containers container
                   JOIN inventory_locations location ON location.id=container.location_id
                   WHERE container.tenant_id=? AND container.site_id=? AND container.id=?""",
                (*self._scope(), identifier),
            ).fetchone()
            self._audit(
                db,
                actor,
                "material-flow:container-created",
                "material_container",
                payload.container_code,
                payload.model_dump(mode="json"),
            )
            return _row(row)

    def create_lot(self, payload: LotIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            material = self._require_code(
                db, "materials", "material_code", payload.material_code, "material"
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO material_lots (
                       tenant_id, site_id, lot_code, material_id, uom_id,
                       tracking_kind, evidence_reference, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.lot_code,
                    int(material["id"]),
                    int(material["base_uom_id"]),
                    payload.tracking_kind,
                    payload.evidence_reference,
                    actor,
                ),
                message="lot or serial code already exists",
            )
            lot = self._require_lot(db, payload.lot_code)
            self._audit(
                db,
                actor,
                "material-flow:lot-created",
                "material_lot",
                payload.lot_code,
                payload.model_dump(mode="json"),
            )
            if int(lot["id"]) != identifier:
                raise RuntimeError("created lot identifier mismatch")
            return lot

    def _require_operation_task(self, db: Any, task_id: int, movement_type: str) -> dict[str, Any]:
        sql = (
            "SELECT * FROM operation_tasks WHERE tenant_id=? AND site_id=? AND id=?"
            + self._lock_suffix()
        )
        row = db.execute(sql, (*self._scope(), task_id)).fetchone()
        if row is None:
            raise MaterialFlowError(
                409,
                "OPERATION_TASK_NOT_FOUND",
                "material movement references an unknown operation task",
                operation_task_id=task_id,
            )
        task = _row(row)
        allowed = {
            "consume": {"running", "paused"},
            "rework": {"running", "paused"},
            "produce": {"completed", "closed"},
            "consume_produce": {"completed", "closed"},
        }.get(
            movement_type,
            {"dispatched", "setup", "ready", "running", "paused", "completed", "closed"},
        )
        if task["status"] not in allowed:
            raise MaterialFlowError(
                409,
                "EXECUTION_STATE_INCOMPATIBLE",
                "operation task state is incompatible with the material transaction",
                operation_task_id=task_id,
                operation_status=task["status"],
                material_action=movement_type,
                allowed_statuses=sorted(allowed),
            )
        return task

    def _balance_quantity(
        self,
        db: Any,
        lot_id: int,
        location_id: int,
        container_key: str,
    ) -> float:
        row = db.execute(
            """SELECT quantity FROM inventory_balances
               WHERE tenant_id=? AND site_id=? AND lot_id=? AND location_id=?
                 AND container_key=?""",
            (*self._scope(), lot_id, location_id, container_key),
        ).fetchone()
        return float(_row(row)["quantity"]) if row is not None else 0.0

    def _apply_balance_delta(
        self,
        db: Any,
        lot: dict[str, Any],
        location: dict[str, Any],
        container: dict[str, Any] | None,
        delta: float,
    ) -> float:
        container_key = str(container["container_code"]) if container else ""
        container_id = int(container["id"]) if container else None
        if delta > 0 and lot["tracking_kind"] == "serial":
            total_row = db.execute(
                """SELECT COALESCE(SUM(quantity), 0) AS total
                   FROM inventory_balances
                   WHERE tenant_id=? AND site_id=? AND lot_id=?""",
                (*self._scope(), int(lot["id"])),
            ).fetchone()
            if float(_row(total_row)["total"]) + delta > 1.000000001:
                raise MaterialFlowError(
                    409,
                    "SERIAL_QUANTITY_INVALID",
                    "a serial identity can represent at most one unit across all locations",
                    lot_code=lot["lot_code"],
                )
        db.execute(
            """INSERT INTO inventory_balances (
                   tenant_id, site_id, material_id, lot_id, uom_id, location_id,
                   container_id, container_key, quantity, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
               ON CONFLICT (tenant_id, site_id, lot_id, location_id, container_key)
               DO NOTHING""",
            (
                *self._scope(),
                int(lot["material_id"]),
                int(lot["id"]),
                int(lot["uom_id"]),
                int(location["id"]),
                container_id,
                container_key,
                _now(),
            ),
        )
        updated = db.execute(
            """UPDATE inventory_balances
               SET quantity=quantity+?, updated_at=?
               WHERE tenant_id=? AND site_id=? AND lot_id=? AND location_id=?
                 AND container_key=? AND quantity+?>=-0.000000001""",
            (
                delta,
                _now(),
                *self._scope(),
                int(lot["id"]),
                int(location["id"]),
                container_key,
                delta,
            ),
        )
        if int(getattr(updated, "rowcount", 0) or 0) != 1:
            available = self._balance_quantity(
                db, int(lot["id"]), int(location["id"]), container_key
            )
            raise MaterialFlowError(
                409,
                "NEGATIVE_INVENTORY",
                "material movement would make inventory or WIP negative",
                lot_code=lot["lot_code"],
                location_code=location["location_code"],
                container_code=container_key or None,
                available_quantity=available,
                requested_quantity=abs(delta),
            )
        quantity = self._balance_quantity(db, int(lot["id"]), int(location["id"]), container_key)
        if quantity < 0 and quantity >= -1e-9:
            db.execute(
                """UPDATE inventory_balances SET quantity=0, updated_at=?
                   WHERE tenant_id=? AND site_id=? AND lot_id=? AND location_id=?
                     AND container_key=?""",
                (
                    _now(),
                    *self._scope(),
                    int(lot["id"]),
                    int(location["id"]),
                    container_key,
                ),
            )
            return 0.0
        return quantity

    def _insert_movement(
        self,
        db: Any,
        *,
        movement_id: str,
        movement_type: str,
        lot: dict[str, Any],
        quantity: float,
        from_location: dict[str, Any] | None,
        to_location: dict[str, Any] | None,
        from_container: dict[str, Any] | None,
        to_container: dict[str, Any] | None,
        operation_task_id: int | None,
        transformation_id: str | None,
        reconciliation_case_id: int | None,
        source: str,
        reason: str,
        evidence_reference: str,
        request_hash: str,
        occurred_at: str,
        actor: str,
        maintenance_order_id: int | None = None,
    ) -> int:
        return self._insert_id(
            db,
            """INSERT INTO inventory_movements (
                   tenant_id, site_id, movement_id, movement_type, material_id,
                   lot_id, uom_id, quantity, from_location_id, to_location_id,
                   from_container_id, to_container_id, operation_task_id,
                   maintenance_order_id, transformation_id, reconciliation_case_id, source, reason,
                   evidence_reference, request_hash, occurred_at, recorded_by
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                *self._scope(),
                movement_id,
                movement_type,
                int(lot["material_id"]),
                int(lot["id"]),
                int(lot["uom_id"]),
                quantity,
                int(from_location["id"]) if from_location else None,
                int(to_location["id"]) if to_location else None,
                int(from_container["id"]) if from_container else None,
                int(to_container["id"]) if to_container else None,
                operation_task_id,
                maintenance_order_id,
                transformation_id,
                reconciliation_case_id,
                source,
                reason,
                evidence_reference,
                request_hash,
                occurred_at,
                actor,
            ),
            code="DUPLICATE_MOVEMENT",
            message="material movement identifier already exists",
        )

    def _format_movement(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT movement.*, lot.lot_code, material.material_code, uom.uom_code,
                      source_location.location_code AS from_location_code,
                      target_location.location_code AS to_location_code,
                      source_container.container_code AS from_container_code,
                      target_container.container_code AS to_container_code,
                      maintenance_order.order_code AS maintenance_order_code
               FROM inventory_movements movement
               JOIN material_lots lot ON lot.id=movement.lot_id
               JOIN materials material ON material.id=movement.material_id
               JOIN uoms uom ON uom.id=movement.uom_id
               LEFT JOIN inventory_locations source_location
                 ON source_location.id=movement.from_location_id
               LEFT JOIN inventory_locations target_location
                 ON target_location.id=movement.to_location_id
               LEFT JOIN material_containers source_container
                 ON source_container.id=movement.from_container_id
               LEFT JOIN material_containers target_container
                 ON target_container.id=movement.to_container_id
               LEFT JOIN maintenance_orders maintenance_order
                 ON maintenance_order.id=movement.maintenance_order_id
               WHERE movement.tenant_id=? AND movement.site_id=? AND movement.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaterialFlowError(404, "MOVEMENT_NOT_FOUND", "material movement was not found")
        return _row(row)

    def _validate_location_semantics(
        self,
        movement_type: str,
        from_location: dict[str, Any] | None,
        to_location: dict[str, Any] | None,
    ) -> None:
        if (
            movement_type == "issue"
            and to_location
            and to_location["location_type"] not in {"wip", "staging"}
        ):
            raise MaterialFlowError(
                409, "INVALID_ISSUE_DESTINATION", "issue destination must be WIP or staging"
            )
        if movement_type == "scrap" and to_location and to_location["location_type"] != "scrap":
            raise MaterialFlowError(
                409, "INVALID_SCRAP_DESTINATION", "scrap movement must enter a scrap location"
            )
        if movement_type == "rework" and to_location and to_location["location_type"] != "wip":
            raise MaterialFlowError(
                409, "INVALID_REWORK_DESTINATION", "rework movement must enter a WIP location"
            )

    def record_movement(self, payload: MovementIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        request_hash = self._hash(request)
        with get_db() as db:
            existing = db.execute(
                """SELECT id, request_hash FROM inventory_movements
                   WHERE tenant_id=? AND site_id=? AND movement_id=?""",
                (*self._scope(), payload.movement_id),
            ).fetchone()
            if existing is not None:
                data = _row(existing)
                if data["request_hash"] != request_hash:
                    raise MaterialFlowError(
                        409,
                        "IDEMPOTENCY_KEY_REUSED",
                        "movement_id was already used with a different request",
                        movement_id=payload.movement_id,
                    )
                return self._format_movement(db, int(data["id"]))
            lot = self._require_lot(db, payload.lot_code)
            if lot["status"] != "active":
                raise MaterialFlowError(
                    409, "LOT_NOT_ACTIVE", "material lot is not active", lot_code=payload.lot_code
                )
            self._assert_no_quality_hold(db, lot)
            if lot["tracking_kind"] == "serial" and not _same_quantity(payload.quantity, 1):
                raise MaterialFlowError(
                    409,
                    "SERIAL_QUANTITY_INVALID",
                    "every serial movement must have quantity one",
                    lot_code=payload.lot_code,
                )
            if payload.operation_task_id is not None:
                self._require_operation_task(db, payload.operation_task_id, payload.movement_type)
            elif payload.source == "execution":
                raise MaterialFlowError(
                    409,
                    "OPERATION_TASK_REQUIRED",
                    "execution-sourced movement requires operation_task_id",
                )
            maintenance_order_id = None
            if payload.maintenance_order_code is not None:
                maintenance_order_row = db.execute(
                    """SELECT id, status FROM maintenance_orders
                       WHERE tenant_id=? AND site_id=? AND order_code=?""",
                    (*self._scope(), payload.maintenance_order_code),
                ).fetchone()
                if maintenance_order_row is None:
                    raise MaterialFlowError(
                        409,
                        "MAINTENANCE_ORDER_NOT_FOUND",
                        "maintenance-bound movement requires an existing maintenance order",
                    )
                maintenance_order = _row(maintenance_order_row)
                if maintenance_order["status"] not in {"in_progress", "work_completed"}:
                    raise MaterialFlowError(
                        409,
                        "MAINTENANCE_ORDER_NOT_ACTIVE",
                        "maintenance-bound consume requires active maintenance work",
                    )
                maintenance_order_id = int(maintenance_order["id"])
            from_location = (
                self._require_location(db, payload.from_location_code)
                if payload.from_location_code
                else None
            )
            to_location = (
                self._require_location(db, payload.to_location_code)
                if payload.to_location_code
                else None
            )
            from_container = self._resolve_container(db, payload.from_container_code, from_location)
            to_container = self._resolve_container(db, payload.to_container_code, to_location)
            self._validate_location_semantics(payload.movement_type, from_location, to_location)
            if from_location:
                self._apply_balance_delta(db, lot, from_location, from_container, -payload.quantity)
            if to_location:
                self._apply_balance_delta(db, lot, to_location, to_container, payload.quantity)
            identifier = self._insert_movement(
                db,
                movement_id=payload.movement_id,
                movement_type=payload.movement_type,
                lot=lot,
                quantity=payload.quantity,
                from_location=from_location,
                to_location=to_location,
                from_container=from_container,
                to_container=to_container,
                operation_task_id=payload.operation_task_id,
                transformation_id=None,
                reconciliation_case_id=None,
                source=payload.source,
                reason=payload.reason,
                evidence_reference=payload.evidence_reference,
                request_hash=request_hash,
                occurred_at=payload.occurred_at.astimezone(UTC).isoformat(),
                actor=actor,
                maintenance_order_id=maintenance_order_id,
            )
            response = self._format_movement(db, identifier)
            self._audit(
                db,
                actor,
                "material-flow:movement-recorded",
                "inventory_movement",
                payload.movement_id,
                {
                    "movement_type": payload.movement_type,
                    "lot_code": payload.lot_code,
                    "quantity": payload.quantity,
                    "uom_code": lot["uom_code"],
                    "operation_task_id": payload.operation_task_id,
                    "maintenance_order_code": payload.maintenance_order_code,
                    "source": payload.source,
                },
            )
            return response

    def lot_balances(self, lot_code: str) -> list[dict[str, Any]]:
        with get_db() as db:
            lot = self._require_lot(db, lot_code)
            rows = db.execute(
                """SELECT balance.*, lot.lot_code, material.material_code, uom.uom_code,
                          location.location_code, container.container_code
                   FROM inventory_balances balance
                   JOIN material_lots lot ON lot.id=balance.lot_id
                   JOIN materials material ON material.id=balance.material_id
                   JOIN uoms uom ON uom.id=balance.uom_id
                   JOIN inventory_locations location ON location.id=balance.location_id
                   LEFT JOIN material_containers container ON container.id=balance.container_id
                   WHERE balance.tenant_id=? AND balance.site_id=? AND balance.lot_id=?
                     AND balance.quantity>0.000000001
                   ORDER BY location.location_code, balance.container_key""",
                (*self._scope(), int(lot["id"])),
            ).fetchall()
            return [_row(item) for item in rows]

    def _resolve_transformation_leg(self, db: Any, leg: Any) -> dict[str, Any]:
        lot = self._require_lot(db, leg.lot_code)
        location = self._require_location(db, leg.location_code)
        container = self._resolve_container(db, leg.container_code, location)
        if lot["status"] != "active":
            raise MaterialFlowError(
                409,
                "LOT_NOT_ACTIVE",
                "material transformation requires an active lot or serial",
                lot_code=leg.lot_code,
            )
        self._assert_no_quality_hold(db, lot)
        if lot["tracking_kind"] == "serial" and not _same_quantity(leg.quantity, 1):
            raise MaterialFlowError(
                409,
                "SERIAL_QUANTITY_INVALID",
                "every serial transformation leg must have quantity one",
                lot_code=leg.lot_code,
            )
        return {
            "lot": lot,
            "location": location,
            "container": container,
            "quantity": float(leg.quantity),
        }

    def _validate_transformation_semantics(
        self,
        payload: TransformationIn,
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
    ) -> None:
        input_total = sum(item["quantity"] for item in inputs)
        output_total = sum(item["quantity"] for item in outputs)
        input_materials = {
            (int(item["lot"]["material_id"]), int(item["lot"]["uom_id"])) for item in inputs
        }
        output_materials = {
            (int(item["lot"]["material_id"]), int(item["lot"]["uom_id"])) for item in outputs
        }
        if payload.transformation_type in {"split", "merge", "rework"}:
            if len(input_materials | output_materials) != 1:
                raise MaterialFlowError(
                    409,
                    "MATERIAL_CONSERVATION_VIOLATION",
                    "split, merge and rework must preserve material and unit of measure",
                )
            if not _same_quantity(input_total, output_total):
                raise MaterialFlowError(
                    409,
                    "QUANTITY_CONSERVATION_VIOLATION",
                    "split, merge and rework input and output quantities must match",
                    input_quantity=input_total,
                    output_quantity=output_total,
                )
        conversion_changed = input_materials != output_materials or not _same_quantity(
            input_total, output_total
        )
        if payload.transformation_type == "consume_produce" and conversion_changed:
            if not payload.conversion_evidence_reference:
                raise MaterialFlowError(
                    409,
                    "CONVERSION_EVIDENCE_REQUIRED",
                    "material or quantity conversion requires an evidence reference",
                )
        input_lot_ids = {int(item["lot"]["id"]) for item in inputs}
        output_lot_ids = {int(item["lot"]["id"]) for item in outputs}
        overlap = input_lot_ids & output_lot_ids
        if overlap:
            lot_codes = sorted(
                item["lot"]["lot_code"] for item in inputs if int(item["lot"]["id"]) in overlap
            )
            raise MaterialFlowError(
                409,
                "GENEALOGY_SELF_REFERENCE",
                "a transformation must produce a distinct output lot or serial",
                lot_codes=lot_codes,
            )

    def _assert_no_genealogy_cycle(self, db: Any, parent_lot_id: int, child_lot_id: int) -> None:
        row = db.execute(
            """WITH RECURSIVE descendants(lot_id) AS (
                   SELECT child_lot_id FROM genealogy_edges
                   WHERE tenant_id=? AND site_id=? AND parent_lot_id=?
                   UNION
                   SELECT edge.child_lot_id
                   FROM genealogy_edges edge
                   JOIN descendants item ON edge.parent_lot_id=item.lot_id
                   WHERE edge.tenant_id=? AND edge.site_id=?
               )
               SELECT 1 AS cycle FROM descendants WHERE lot_id=? LIMIT 1""",
            (*self._scope(), child_lot_id, *self._scope(), parent_lot_id),
        ).fetchone()
        if row is not None:
            raise MaterialFlowError(
                409,
                "GENEALOGY_CYCLE",
                "material transformation would create a genealogy cycle",
            )

    def _format_transformation(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT * FROM material_transformations
               WHERE tenant_id=? AND site_id=? AND id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaterialFlowError(
                404, "TRANSFORMATION_NOT_FOUND", "material transformation was not found"
            )
        result = _row(row)
        movements = db.execute(
            """SELECT movement.*, lot.lot_code
               FROM inventory_movements movement
               JOIN material_lots lot ON lot.id=movement.lot_id
               WHERE movement.tenant_id=? AND movement.site_id=?
                 AND movement.transformation_id=?
               ORDER BY movement.id""",
            (*self._scope(), result["transformation_id"]),
        ).fetchall()
        edges = db.execute(
            """SELECT edge.*, parent.lot_code AS parent_lot_code,
                      child.lot_code AS child_lot_code
               FROM genealogy_edges edge
               JOIN material_lots parent ON parent.id=edge.parent_lot_id
               JOIN material_lots child ON child.id=edge.child_lot_id
               WHERE edge.tenant_id=? AND edge.site_id=?
                 AND edge.transformation_id=?
               ORDER BY edge.id""",
            (*self._scope(), result["transformation_id"]),
        ).fetchall()
        result["movements"] = [_row(item) for item in movements]
        result["genealogy_edges"] = [_row(item) for item in edges]
        return result

    def record_transformation(self, payload: TransformationIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        request_hash = self._hash(request)
        with get_db() as db:
            existing = db.execute(
                """SELECT id, request_hash FROM material_transformations
                   WHERE tenant_id=? AND site_id=? AND transformation_id=?""",
                (*self._scope(), payload.transformation_id),
            ).fetchone()
            if existing is not None:
                data = _row(existing)
                if data["request_hash"] != request_hash:
                    raise MaterialFlowError(
                        409,
                        "IDEMPOTENCY_KEY_REUSED",
                        "transformation_id was already used with a different request",
                        transformation_id=payload.transformation_id,
                    )
                return self._format_transformation(db, int(data["id"]))
            if payload.operation_task_id is not None:
                self._require_operation_task(
                    db, payload.operation_task_id, payload.transformation_type
                )
            inputs = [self._resolve_transformation_leg(db, item) for item in payload.inputs]
            outputs = [self._resolve_transformation_leg(db, item) for item in payload.outputs]
            self._validate_transformation_semantics(payload, inputs, outputs)
            for parent in inputs:
                for child in outputs:
                    self._assert_no_genealogy_cycle(
                        db, int(parent["lot"]["id"]), int(child["lot"]["id"])
                    )
            identifier = self._insert_id(
                db,
                """INSERT INTO material_transformations (
                       tenant_id, site_id, transformation_id, transformation_type,
                       operation_task_id, reason, evidence_reference,
                       conversion_evidence_reference, request_hash, occurred_at,
                       recorded_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.transformation_id,
                    payload.transformation_type,
                    payload.operation_task_id,
                    payload.reason,
                    payload.evidence_reference,
                    payload.conversion_evidence_reference,
                    request_hash,
                    payload.occurred_at.astimezone(UTC).isoformat(),
                    actor,
                ),
                code="DUPLICATE_TRANSFORMATION",
                message="material transformation identifier already exists",
            )
            movement_types = {
                "split": ("split_input", "split_output"),
                "merge": ("merge_input", "merge_output"),
                "consume_produce": ("transform_input", "transform_output"),
                "rework": ("transform_input", "transform_output"),
            }
            source = "execution" if payload.operation_task_id is not None else "manual"
            input_type, output_type = movement_types[payload.transformation_type]
            for direction, movement_type, legs in (
                ("IN", input_type, inputs),
                ("OUT", output_type, outputs),
            ):
                for index, leg in enumerate(legs, start=1):
                    delta = -leg["quantity"] if direction == "IN" else leg["quantity"]
                    self._apply_balance_delta(
                        db, leg["lot"], leg["location"], leg["container"], delta
                    )
                    self._insert_movement(
                        db,
                        movement_id=f"{payload.transformation_id}-{direction}-{index}",
                        movement_type=movement_type,
                        lot=leg["lot"],
                        quantity=leg["quantity"],
                        from_location=leg["location"] if direction == "IN" else None,
                        to_location=leg["location"] if direction == "OUT" else None,
                        from_container=leg["container"] if direction == "IN" else None,
                        to_container=leg["container"] if direction == "OUT" else None,
                        operation_task_id=payload.operation_task_id,
                        transformation_id=payload.transformation_id,
                        reconciliation_case_id=None,
                        source=source,
                        reason=payload.reason,
                        evidence_reference=payload.evidence_reference,
                        request_hash=self._hash(
                            {
                                "transformation_request_hash": request_hash,
                                "direction": direction,
                                "index": index,
                            }
                        ),
                        occurred_at=payload.occurred_at.astimezone(UTC).isoformat(),
                        actor=actor,
                    )
            for parent in inputs:
                for child in outputs:
                    self._insert_id(
                        db,
                        """INSERT INTO genealogy_edges (
                               tenant_id, site_id, transformation_id, parent_lot_id,
                               child_lot_id, parent_quantity, child_quantity,
                               relation_type, evidence_reference
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            *self._scope(),
                            payload.transformation_id,
                            int(parent["lot"]["id"]),
                            int(child["lot"]["id"]),
                            parent["quantity"],
                            child["quantity"],
                            payload.transformation_type,
                            payload.evidence_reference,
                        ),
                        code="DUPLICATE_GENEALOGY_EDGE",
                        message="material genealogy edge already exists",
                    )
            self._audit(
                db,
                actor,
                "material-flow:transformation-recorded",
                "material_transformation",
                payload.transformation_id,
                {
                    "transformation_type": payload.transformation_type,
                    "input_lots": [item["lot"]["lot_code"] for item in inputs],
                    "output_lots": [item["lot"]["lot_code"] for item in outputs],
                    "operation_task_id": payload.operation_task_id,
                },
            )
            return self._format_transformation(db, identifier)

    def genealogy(self, lot_code: str) -> dict[str, Any]:
        with get_db() as db:
            lot = self._require_lot(db, lot_code)
            query_columns = (
                "lot.lot_code, lot.tracking_kind, lot.status, material.material_code, uom.uom_code"
            )
            ancestors = db.execute(
                f"""WITH RECURSIVE lineage(lot_id) AS (
                        SELECT parent_lot_id FROM genealogy_edges
                        WHERE tenant_id=? AND site_id=? AND child_lot_id=?
                        UNION
                        SELECT edge.parent_lot_id FROM genealogy_edges edge
                        JOIN lineage item ON edge.child_lot_id=item.lot_id
                        WHERE edge.tenant_id=? AND edge.site_id=?
                    )
                    SELECT {query_columns} FROM lineage
                    JOIN material_lots lot ON lot.id=lineage.lot_id
                    JOIN materials material ON material.id=lot.material_id
                    JOIN uoms uom ON uom.id=lot.uom_id
                    ORDER BY lot.lot_code""",
                (*self._scope(), int(lot["id"]), *self._scope()),
            ).fetchall()
            descendants = db.execute(
                f"""WITH RECURSIVE lineage(lot_id) AS (
                        SELECT child_lot_id FROM genealogy_edges
                        WHERE tenant_id=? AND site_id=? AND parent_lot_id=?
                        UNION
                        SELECT edge.child_lot_id FROM genealogy_edges edge
                        JOIN lineage item ON edge.parent_lot_id=item.lot_id
                        WHERE edge.tenant_id=? AND edge.site_id=?
                    )
                    SELECT {query_columns} FROM lineage
                    JOIN material_lots lot ON lot.id=lineage.lot_id
                    JOIN materials material ON material.id=lot.material_id
                    JOIN uoms uom ON uom.id=lot.uom_id
                    ORDER BY lot.lot_code""",
                (*self._scope(), int(lot["id"]), *self._scope()),
            ).fetchall()
            return {
                "lot": lot,
                "ancestors": [_row(item) for item in ancestors],
                "descendants": [_row(item) for item in descendants],
            }

    def _format_reconciliation_case(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT reconciliation.*, lot.lot_code, material.material_code,
                      uom.uom_code, location.location_code, container.container_code,
                      external.import_id, external.provider, external.source AS external_source
               FROM inventory_reconciliation_cases reconciliation
               JOIN material_lots lot ON lot.id=reconciliation.lot_id
               JOIN materials material ON material.id=reconciliation.material_id
               JOIN uoms uom ON uom.id=reconciliation.uom_id
               JOIN inventory_locations location ON location.id=reconciliation.location_id
               LEFT JOIN material_containers container
                 ON container.id=reconciliation.container_id
               JOIN external_inventory_imports external
                 ON external.id=reconciliation.external_import_id
               WHERE reconciliation.tenant_id=? AND reconciliation.site_id=?
                 AND reconciliation.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaterialFlowError(
                404,
                "RECONCILIATION_NOT_FOUND",
                "inventory reconciliation case was not found",
                reconciliation_id=identifier,
            )
        return _row(row)

    def _format_external_import(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT * FROM external_inventory_imports
               WHERE tenant_id=? AND site_id=? AND id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaterialFlowError(
                404, "EXTERNAL_IMPORT_NOT_FOUND", "external inventory import was not found"
            )
        result = _row(row)
        cases = db.execute(
            """SELECT id FROM inventory_reconciliation_cases
               WHERE tenant_id=? AND site_id=? AND external_import_id=? ORDER BY id""",
            (*self._scope(), identifier),
        ).fetchall()
        result["reconciliation_cases"] = [
            self._format_reconciliation_case(db, int(_row(item)["id"])) for item in cases
        ]
        return result

    def import_external_snapshot(self, payload: ExternalSnapshotIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        payload_json = _canonical_json(request)
        payload_hash = self._hash(request)
        with get_db() as db:
            existing = db.execute(
                """SELECT id, payload_hash FROM external_inventory_imports
                   WHERE tenant_id=? AND site_id=? AND import_id=?""",
                (*self._scope(), payload.import_id),
            ).fetchone()
            if existing is not None:
                data = _row(existing)
                if data["payload_hash"] != payload_hash:
                    raise MaterialFlowError(
                        409,
                        "IDEMPOTENCY_KEY_REUSED",
                        "import_id was already used with a different snapshot",
                        import_id=payload.import_id,
                    )
                return self._format_external_import(db, int(data["id"]))
            import_identifier = self._insert_id(
                db,
                """INSERT INTO external_inventory_imports (
                       tenant_id, site_id, import_id, provider, contract_version,
                       source, observed_at, evidence_reference, payload_json,
                       payload_hash, created_by
                   ) VALUES (?, ?, ?, ?, ?, 'simulated', ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.import_id,
                    payload.provider,
                    payload.contract_version,
                    payload.observed_at.astimezone(UTC).isoformat(),
                    payload.evidence_reference,
                    payload_json,
                    payload_hash,
                    actor,
                ),
                code="DUPLICATE_EXTERNAL_IMPORT",
                message="external inventory import identifier already exists",
            )
            discrepancy_count = 0
            for index, item in enumerate(payload.items, start=1):
                lot = self._require_lot(db, item.lot_code)
                location = self._require_location(db, item.location_code)
                container = self._resolve_container(db, item.container_code, location)
                container_key = str(container["container_code"]) if container else ""
                expected = self._balance_quantity(
                    db, int(lot["id"]), int(location["id"]), container_key
                )
                observed = float(item.observed_quantity)
                if _same_quantity(expected, observed):
                    continue
                discrepancy_count += 1
                self._insert_id(
                    db,
                    """INSERT INTO inventory_reconciliation_cases (
                           tenant_id, site_id, case_code, external_import_id,
                           material_id, lot_id, uom_id, location_id, container_id,
                           container_key, expected_quantity, observed_quantity,
                           variance, evidence_reference
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        *self._scope(),
                        f"{payload.import_id}-{index:04d}",
                        import_identifier,
                        int(lot["material_id"]),
                        int(lot["id"]),
                        int(lot["uom_id"]),
                        int(location["id"]),
                        int(container["id"]) if container else None,
                        container_key,
                        expected,
                        observed,
                        observed - expected,
                        payload.evidence_reference,
                    ),
                    code="DUPLICATE_RECONCILIATION_CASE",
                    message="external snapshot reconciliation case already exists",
                )
            self._audit(
                db,
                actor,
                "material-flow:external-snapshot-imported",
                "external_inventory_import",
                payload.import_id,
                {
                    "provider": payload.provider,
                    "contract_version": payload.contract_version,
                    "source": "simulated",
                    "item_count": len(payload.items),
                    "discrepancy_count": discrepancy_count,
                    "payload_hash": payload_hash,
                },
            )
            return self._format_external_import(db, import_identifier)

    def adjust_reconciliation(
        self,
        reconciliation_id: int,
        payload: ReconciliationAdjustmentIn,
        actor: str,
    ) -> dict[str, Any]:
        request_hash = self._hash(
            {"reconciliation_id": reconciliation_id, **payload.model_dump(mode="json")}
        )
        with get_db() as db:
            sql = """SELECT reconciliation.*, lot.lot_code, location.location_code,
                          container.container_code
                   FROM inventory_reconciliation_cases reconciliation
                   JOIN material_lots lot ON lot.id=reconciliation.lot_id
                   JOIN inventory_locations location ON location.id=reconciliation.location_id
                   LEFT JOIN material_containers container
                     ON container.id=reconciliation.container_id
                   WHERE reconciliation.tenant_id=? AND reconciliation.site_id=?
                     AND reconciliation.id=?""" + (
                " FOR UPDATE OF reconciliation" if persistence_backend() == "postgres" else ""
            )
            row = db.execute(sql, (*self._scope(), reconciliation_id)).fetchone()
            if row is None:
                raise MaterialFlowError(
                    404,
                    "RECONCILIATION_NOT_FOUND",
                    "inventory reconciliation case was not found",
                    reconciliation_id=reconciliation_id,
                )
            case = _row(row)
            if case["status"] != "open":
                if case["adjustment_movement_id"] == payload.movement_id:
                    movement = db.execute(
                        """SELECT request_hash FROM inventory_movements
                           WHERE tenant_id=? AND site_id=? AND movement_id=?""",
                        (*self._scope(), payload.movement_id),
                    ).fetchone()
                    if movement is not None and _row(movement)["request_hash"] == request_hash:
                        return self._format_reconciliation_case(db, reconciliation_id)
                raise MaterialFlowError(
                    409,
                    "RECONCILIATION_ALREADY_RESOLVED",
                    "inventory reconciliation case is no longer open",
                    reconciliation_id=reconciliation_id,
                    status=case["status"],
                )
            lot = self._require_lot(db, case["lot_code"])
            location = self._require_location(db, case["location_code"])
            container = self._resolve_container(db, case.get("container_code"), location)
            current = self._balance_quantity(
                db, int(lot["id"]), int(location["id"]), case["container_key"]
            )
            expected = float(case["expected_quantity"])
            observed = float(case["observed_quantity"])
            if not _same_quantity(current, expected):
                raise MaterialFlowError(
                    409,
                    "RECONCILIATION_STALE",
                    "inventory changed after the external snapshot; a new snapshot is required",
                    expected_quantity=expected,
                    current_quantity=current,
                )
            delta = observed - expected
            if _same_quantity(delta, 0):
                raise MaterialFlowError(
                    409,
                    "RECONCILIATION_HAS_NO_VARIANCE",
                    "reconciliation case no longer contains an actionable variance",
                )
            self._apply_balance_delta(db, lot, location, container, delta)
            self._insert_movement(
                db,
                movement_id=payload.movement_id,
                movement_type="adjustment",
                lot=lot,
                quantity=abs(delta),
                from_location=location if delta < 0 else None,
                to_location=location if delta > 0 else None,
                from_container=container if delta < 0 else None,
                to_container=container if delta > 0 else None,
                operation_task_id=None,
                transformation_id=None,
                reconciliation_case_id=reconciliation_id,
                source="reconciliation",
                reason=payload.reason,
                evidence_reference=payload.evidence_reference,
                request_hash=request_hash,
                occurred_at=_now(),
                actor=actor,
            )
            updated = db.execute(
                """UPDATE inventory_reconciliation_cases
                   SET status='adjusted', adjustment_movement_id=?, adjustment_reason=?,
                       adjustment_evidence_reference=?, adjusted_by=?, adjusted_at=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='open'""",
                (
                    payload.movement_id,
                    payload.reason,
                    payload.evidence_reference,
                    actor,
                    _now(),
                    *self._scope(),
                    reconciliation_id,
                ),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise MaterialFlowError(
                    409,
                    "RECONCILIATION_CONFLICT",
                    "reconciliation case changed during adjustment",
                )
            self._audit(
                db,
                actor,
                "material-flow:reconciliation-adjusted",
                "inventory_reconciliation_case",
                str(reconciliation_id),
                {
                    "movement_id": payload.movement_id,
                    "lot_code": case["lot_code"],
                    "location_code": case["location_code"],
                    "previous_quantity": expected,
                    "adjusted_quantity": observed,
                    "variance": delta,
                    "evidence_reference": payload.evidence_reference,
                },
            )
            return self._format_reconciliation_case(db, reconciliation_id)


material_flow_repository = MaterialFlowRepository()
