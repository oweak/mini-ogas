from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..core.config import settings
from ..core.database import get_db, persistence_backend
from ..core.nats_contracts import build_audit_envelope
from ..core.outbox import outbox_repository
from ..domain.maintenance import (
    AssetIn,
    CalibrationIn,
    ChecklistIn,
    ChecklistResultIn,
    MaintenanceActionIn,
    MaintenanceCodeIn,
    MaintenanceError,
    MaintenanceOrderIn,
    MaintenanceRequestIn,
    MaintenanceVerifyIn,
    PreventiveGenerateIn,
    PreventivePlanIn,
    SpareUseIn,
    ToolAssignmentIn,
    ToolIn,
    ToolLifeEventIn,
    WorkCompleteIn,
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


class MaintenanceRepository:
    """Transactional authority for Phase 6 maintenance and tooling facts."""

    def _scope(self) -> tuple[str, str]:
        return settings.tenant_id, settings.site_id

    def _lock_suffix(self) -> str:
        return " FOR UPDATE" if persistence_backend() == "postgres" else ""

    def _insert_id(
        self,
        db: Any,
        sql: str,
        params: tuple[Any, ...],
        *,
        code: str = "DUPLICATE_MAINTENANCE_RESOURCE",
        message: str = "maintenance resource already exists",
    ) -> int:
        try:
            row = db.execute(f"{sql} RETURNING id", params).fetchone()
        except Exception as exc:
            lowered = str(exc).lower()
            if any(token in lowered for token in ("unique", "duplicate", "constraint failed")):
                raise MaintenanceError(409, code, message) from exc
            raise
        if row is None:
            raise RuntimeError("database insert did not return an identifier")
        return int(dict(row)["id"] if hasattr(row, "keys") else row[0])

    def _require_code(
        self,
        db: Any,
        table: str,
        column: str,
        code: str,
        resource: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        sql = f"SELECT * FROM {table} WHERE tenant_id=? AND site_id=? AND {column}=?"
        if lock:
            sql += self._lock_suffix()
        row = db.execute(sql, (*self._scope(), code)).fetchone()
        if row is None:
            raise MaintenanceError(
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
               ) VALUES (?, ?, 'maintenance', ?, ?, ?, ?, 'success', ?, ?)
               RETURNING id""",
            (*self._scope(), actor, action, resource_type, resource_id, detail_json, created_at),
        ).fetchone()
        audit_id = int(dict(row)["id"] if hasattr(row, "keys") else row[0])
        envelope = build_audit_envelope(
            {
                "id": audit_id,
                "run_id": "maintenance",
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "result": "success",
                "detail": detail_json,
                "created_at": created_at,
            },
            run_id="maintenance",
        )
        if not outbox_repository.enqueue_in_transaction(db, envelope):
            raise RuntimeError("failed to enqueue the maintenance audit envelope")

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
            """INSERT INTO maintenance_status_history (
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

    def _format_asset(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT asset.*, equipment.equipment_code,
                      parent.asset_code AS parent_asset_code
               FROM maintenance_assets asset
               JOIN equipment ON equipment.id=asset.equipment_id
               LEFT JOIN maintenance_assets parent ON parent.id=asset.parent_asset_id
               WHERE asset.tenant_id=? AND asset.site_id=? AND asset.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaintenanceError(404, "ASSET_NOT_FOUND", "maintenance asset was not found")
        return _row(row)

    def create_asset(self, payload: AssetIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            equipment = self._require_code(
                db, "equipment", "equipment_code", payload.equipment_code, "equipment"
            )
            parent_id = None
            if payload.parent_asset_code:
                parent = self._require_code(
                    db,
                    "maintenance_assets",
                    "asset_code",
                    payload.parent_asset_code,
                    "maintenance asset",
                )
                parent_id = int(parent["id"])
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_assets (
                       tenant_id, site_id, asset_code, equipment_id, parent_asset_id,
                       name, criticality, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.asset_code,
                    int(equipment["id"]),
                    parent_id,
                    payload.name,
                    payload.criticality,
                    actor,
                ),
                code="DUPLICATE_MAINTENANCE_ASSET",
                message="asset code or governed equipment is already registered",
            )
            self._history(
                db,
                "asset",
                payload.asset_code,
                None,
                "active",
                "create",
                "asset-registration",
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:asset-created",
                "maintenance_asset",
                payload.asset_code,
                payload.model_dump(mode="json"),
            )
            return self._format_asset(db, identifier)

    def create_code(self, payload: MaintenanceCodeIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_codes (
                       tenant_id, site_id, code, code_type, description, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.code, payload.code_type, payload.description, actor),
                code="DUPLICATE_MAINTENANCE_CODE",
                message="maintenance code already exists",
            )
            self._audit(
                db,
                actor,
                "maintenance:code-created",
                "maintenance_code",
                payload.code,
                payload.model_dump(mode="json"),
            )
            row = db.execute("SELECT * FROM maintenance_codes WHERE id=?", (identifier,)).fetchone()
            return _row(row)

    def _format_checklist(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM maintenance_checklists WHERE tenant_id=? AND site_id=? AND id=?",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaintenanceError(
                404, "CHECKLIST_NOT_FOUND", "maintenance checklist was not found"
            )
        result = _row(row)
        items = db.execute(
            """SELECT * FROM maintenance_checklist_items
               WHERE tenant_id=? AND site_id=? AND checklist_id=? ORDER BY sequence""",
            (*self._scope(), identifier),
        ).fetchall()
        result["items"] = [_row(item) for item in items]
        return result

    def create_checklist(self, payload: ChecklistIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_checklists (
                       tenant_id, site_id, checklist_code, revision, name, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.checklist_code, payload.revision, payload.name, actor),
                code="DUPLICATE_MAINTENANCE_CHECKLIST",
                message="maintenance checklist revision already exists",
            )
            for item in payload.items:
                db.execute(
                    """INSERT INTO maintenance_checklist_items (
                           tenant_id, site_id, checklist_id, sequence, instruction,
                           required, created_by
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        *self._scope(),
                        identifier,
                        item.sequence,
                        item.instruction,
                        int(item.required),
                        actor,
                    ),
                )
            self._history(
                db,
                "checklist",
                f"{payload.checklist_code}:{payload.revision}",
                None,
                "draft",
                "create",
                "checklist-registration",
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:checklist-created",
                "maintenance_checklist",
                f"{payload.checklist_code}:{payload.revision}",
                payload.model_dump(mode="json"),
            )
            return self._format_checklist(db, identifier)

    def transition_checklist(
        self,
        checklist_code: str,
        revision: int,
        target: str,
        payload: MaintenanceActionIn,
        actor: str,
    ) -> dict[str, Any]:
        with get_db() as db:
            sql = (
                "SELECT * FROM maintenance_checklists WHERE tenant_id=? AND site_id=? "
                "AND checklist_code=? AND revision=?" + self._lock_suffix()
            )
            row = db.execute(sql, (*self._scope(), checklist_code, revision)).fetchone()
            if row is None:
                raise MaintenanceError(
                    404, "CHECKLIST_NOT_FOUND", "maintenance checklist was not found"
                )
            checklist = _row(row)
            expected = "draft" if target == "approved" else "approved"
            if checklist["status"] != expected:
                raise MaintenanceError(
                    409,
                    "INVALID_CHECKLIST_TRANSITION",
                    f"checklist must be {expected} before transition to {target}",
                )
            now = _now()
            if target == "approved":
                db.execute(
                    """UPDATE maintenance_checklists
                       SET status='approved', approved_by=?,
                           approval_evidence_reference=?, approved_at=?
                       WHERE id=?""",
                    (actor, payload.evidence_reference, now, int(checklist["id"])),
                )
            else:
                db.execute(
                    """UPDATE maintenance_checklists SET status='superseded'
                       WHERE tenant_id=? AND site_id=? AND checklist_code=?
                         AND status='effective' AND id<>?""",
                    (*self._scope(), checklist_code, int(checklist["id"])),
                )
                db.execute(
                    """UPDATE maintenance_checklists
                       SET status='effective', effective_by=?,
                           effectivity_evidence_reference=?, effective_at=?
                       WHERE id=?""",
                    (actor, payload.evidence_reference, now, int(checklist["id"])),
                )
            self._history(
                db,
                "checklist",
                f"{checklist_code}:{revision}",
                expected,
                target,
                target,
                payload.evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                f"maintenance:checklist-{target}",
                "maintenance_checklist",
                f"{checklist_code}:{revision}",
                {"evidence_reference": payload.evidence_reference},
            )
            return self._format_checklist(db, int(checklist["id"]))

    def _format_request(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT request.*, asset.asset_code
               FROM maintenance_requests request
               JOIN maintenance_assets asset ON asset.id=request.asset_id
               WHERE request.tenant_id=? AND request.site_id=? AND request.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaintenanceError(404, "MAINTENANCE_REQUEST_NOT_FOUND", "request was not found")
        return _row(row)

    def create_request(self, payload: MaintenanceRequestIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            asset = self._require_code(
                db, "maintenance_assets", "asset_code", payload.asset_code, "maintenance asset"
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_requests (
                       tenant_id, site_id, request_code, asset_id, source_type,
                       source_reference, description, priority, observed_at, requested_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.request_code,
                    int(asset["id"]),
                    payload.source_type,
                    payload.source_reference,
                    payload.description,
                    payload.priority,
                    payload.observed_at.astimezone(UTC).isoformat(),
                    actor,
                ),
                code="DUPLICATE_MAINTENANCE_REQUEST",
                message="maintenance request code already exists",
            )
            self._history(
                db,
                "request",
                payload.request_code,
                None,
                "open",
                "create",
                payload.source_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:request-created",
                "maintenance_request",
                payload.request_code,
                payload.model_dump(mode="json"),
            )
            return self._format_request(db, identifier)

    def get_request(self, request_code: str) -> dict[str, Any]:
        with get_db() as db:
            request = self._require_code(
                db,
                "maintenance_requests",
                "request_code",
                request_code,
                "maintenance request",
            )
            return self._format_request(db, int(request["id"]))

    def _require_checklist_revision(
        self, db: Any, checklist_code: str, revision: int, *, effective: bool = True
    ) -> dict[str, Any]:
        row = db.execute(
            """SELECT * FROM maintenance_checklists
               WHERE tenant_id=? AND site_id=? AND checklist_code=? AND revision=?""",
            (*self._scope(), checklist_code, revision),
        ).fetchone()
        if row is None:
            raise MaintenanceError(409, "REFERENCE_NOT_FOUND", "checklist revision does not exist")
        result = _row(row)
        if effective and result["status"] != "effective":
            raise MaintenanceError(
                409, "CHECKLIST_NOT_EFFECTIVE", "maintenance checklist is not effective"
            )
        return result

    def _validate_task_binding(
        self,
        db: Any,
        asset: dict[str, Any],
        task_id: int | None,
        downtime_id: int | None,
    ) -> None:
        if task_id is None:
            return
        row = db.execute(
            """SELECT task.id, task.status, assignment.equipment_id
               FROM operation_tasks task
               JOIN operation_task_assignments assignment ON assignment.operation_task_id=task.id
               WHERE task.tenant_id=? AND task.site_id=? AND task.id=?""",
            (*self._scope(), task_id),
        ).fetchone()
        if row is None:
            raise MaintenanceError(409, "REFERENCE_NOT_FOUND", "operation task does not exist")
        task = _row(row)
        if int(task["equipment_id"]) != int(asset["equipment_id"]):
            raise MaintenanceError(
                409,
                "ASSET_TASK_MISMATCH",
                "maintenance asset is not the equipment assigned to the operation task",
            )
        if downtime_id is None:
            return
        downtime_row = db.execute(
            """SELECT * FROM operation_downtime
               WHERE tenant_id=? AND site_id=? AND id=?""",
            (*self._scope(), downtime_id),
        ).fetchone()
        if downtime_row is None:
            raise MaintenanceError(409, "REFERENCE_NOT_FOUND", "operation downtime does not exist")
        downtime = _row(downtime_row)
        if int(downtime["operation_task_id"]) != task_id or downtime["status"] != "open":
            raise MaintenanceError(
                409,
                "DOWNTIME_TASK_MISMATCH",
                "maintenance order must reference the open downtime for its operation task",
            )

    def _format_order(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT maintenance_order.*, request.request_code, asset.asset_code,
                      personnel.personnel_code AS assigned_personnel_code,
                      checklist.checklist_code, checklist.revision AS checklist_revision,
                      failure.code AS failure_code, cause.code AS cause_code,
                      remedy.code AS remedy_code
               FROM maintenance_orders maintenance_order
               JOIN maintenance_requests request ON request.id=maintenance_order.request_id
               JOIN maintenance_assets asset ON asset.id=maintenance_order.asset_id
               JOIN personnel ON personnel.id=maintenance_order.assigned_personnel_id
               JOIN maintenance_checklists checklist ON checklist.id=maintenance_order.checklist_id
               LEFT JOIN maintenance_codes failure ON failure.id=maintenance_order.failure_code_id
               LEFT JOIN maintenance_codes cause ON cause.id=maintenance_order.cause_code_id
               LEFT JOIN maintenance_codes remedy ON remedy.id=maintenance_order.remedy_code_id
               WHERE maintenance_order.tenant_id=? AND maintenance_order.site_id=?
                 AND maintenance_order.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaintenanceError(404, "MAINTENANCE_ORDER_NOT_FOUND", "order was not found")
        result = _row(row)
        checks = db.execute(
            """SELECT result.*, item.sequence AS item_sequence, item.instruction
               FROM maintenance_check_results result
               JOIN maintenance_checklist_items item ON item.id=result.checklist_item_id
               WHERE result.tenant_id=? AND result.site_id=?
                 AND result.maintenance_order_id=? ORDER BY item.sequence""",
            (*self._scope(), identifier),
        ).fetchall()
        result["checklist_results"] = [_row(item) for item in checks]
        return result

    def create_order(self, payload: MaintenanceOrderIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            request = self._require_code(
                db,
                "maintenance_requests",
                "request_code",
                payload.request_code,
                "maintenance request",
                lock=True,
            )
            if request["status"] != "open":
                raise MaintenanceError(
                    409, "REQUEST_NOT_OPEN", "only an open request can be converted"
                )
            asset = self._require_code(
                db, "maintenance_assets", "asset_code", payload.asset_code, "maintenance asset"
            )
            if int(request["asset_id"]) != int(asset["id"]):
                raise MaintenanceError(
                    409, "REQUEST_ASSET_MISMATCH", "request and order asset differ"
                )
            checklist = self._require_checklist_revision(
                db, payload.checklist_code, payload.checklist_revision
            )
            personnel = self._require_code(
                db, "personnel", "personnel_code", payload.assigned_personnel_code, "personnel"
            )
            if not int(personnel["active"]):
                raise MaintenanceError(409, "PERSONNEL_INACTIVE", "assigned personnel is inactive")
            self._validate_task_binding(
                db, asset, payload.operation_task_id, payload.operation_downtime_id
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_orders (
                       tenant_id, site_id, order_code, request_id, asset_id, order_type,
                       priority, assigned_personnel_id, checklist_id, operation_task_id,
                       operation_downtime_id, production_impact, planned_start_at,
                       planned_end_at, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.order_code,
                    int(request["id"]),
                    int(asset["id"]),
                    payload.order_type,
                    payload.priority,
                    int(personnel["id"]),
                    int(checklist["id"]),
                    payload.operation_task_id,
                    payload.operation_downtime_id,
                    payload.production_impact,
                    payload.planned_start_at.astimezone(UTC).isoformat(),
                    payload.planned_end_at.astimezone(UTC).isoformat(),
                    actor,
                ),
                code="DUPLICATE_MAINTENANCE_ORDER",
                message="maintenance order or downtime binding already exists",
            )
            now = _now()
            db.execute(
                """UPDATE maintenance_requests SET status='converted', converted_at=?
                   WHERE id=? AND status='open'""",
                (now, int(request["id"])),
            )
            self._history(
                db,
                "request",
                payload.request_code,
                "open",
                "converted",
                "convert-to-order",
                payload.order_code,
                actor,
            )
            self._history(
                db,
                "order",
                payload.order_code,
                None,
                "draft",
                "create",
                payload.request_code,
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:order-created",
                "maintenance_order",
                payload.order_code,
                payload.model_dump(mode="json"),
            )
            return self._format_order(db, identifier)

    def _require_order(self, db: Any, order_code: str, *, lock: bool = True) -> dict[str, Any]:
        sql = "SELECT * FROM maintenance_orders WHERE tenant_id=? AND site_id=? AND order_code=?"
        if lock:
            sql += self._lock_suffix()
        row = db.execute(sql, (*self._scope(), order_code)).fetchone()
        if row is None:
            raise MaintenanceError(404, "MAINTENANCE_ORDER_NOT_FOUND", "order was not found")
        return _row(row)

    def approve_order(
        self, order_code: str, payload: MaintenanceActionIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            order = self._require_order(db, order_code)
            if order["status"] != "draft":
                raise MaintenanceError(409, "ORDER_NOT_DRAFT", "only a draft order can be approved")
            db.execute(
                """UPDATE maintenance_orders
                   SET status='approved', approved_by=?,
                       approval_evidence_reference=?, approved_at=?
                   WHERE id=? AND status='draft'""",
                (actor, payload.evidence_reference, _now(), int(order["id"])),
            )
            self._history(
                db,
                "order",
                order_code,
                "draft",
                "approved",
                "approve",
                payload.evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:order-approved",
                "maintenance_order",
                order_code,
                payload.model_dump(),
            )
            return self._format_order(db, int(order["id"]))

    def start_order(
        self, order_code: str, payload: MaintenanceActionIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            order = self._require_order(db, order_code)
            if order["status"] != "approved":
                raise MaintenanceError(
                    409, "ORDER_NOT_APPROVED", "only an approved order can start"
                )
            if order["operation_task_id"] is not None:
                task = db.execute(
                    "SELECT status FROM operation_tasks WHERE id=?",
                    (int(order["operation_task_id"]),),
                ).fetchone()
                task_status = str(dict(task)["status"])
                if task_status == "running":
                    raise MaintenanceError(
                        409,
                        "DOWNTIME_REQUIRED",
                        "running production must enter governed downtime before maintenance starts",
                    )
                if task_status == "paused":
                    if order["operation_downtime_id"] is None:
                        raise MaintenanceError(
                            409,
                            "DOWNTIME_REQUIRED",
                            "paused production maintenance requires its open downtime binding",
                        )
                    downtime = db.execute(
                        "SELECT status, operation_task_id FROM operation_downtime WHERE id=?",
                        (int(order["operation_downtime_id"]),),
                    ).fetchone()
                    downtime_fact = _row(downtime)
                    if downtime_fact["status"] != "open" or int(
                        downtime_fact["operation_task_id"]
                    ) != int(order["operation_task_id"]):
                        raise MaintenanceError(
                            409,
                            "DOWNTIME_TASK_MISMATCH",
                            "maintenance order downtime is not open for its task",
                        )
            db.execute(
                """UPDATE maintenance_orders
                   SET status='in_progress', started_by=?, start_evidence_reference=?, started_at=?
                   WHERE id=? AND status='approved'""",
                (actor, payload.evidence_reference, _now(), int(order["id"])),
            )
            if order["production_impact"] == "equipment_unavailable":
                asset_status = "out_of_service"
            elif order["production_impact"] == "reduced_capacity":
                asset_status = "degraded"
            else:
                asset_status = None
            if asset_status:
                db.execute(
                    "UPDATE maintenance_assets SET status=? WHERE id=? AND status<>'retired'",
                    (asset_status, int(order["asset_id"])),
                )
            self._history(
                db,
                "order",
                order_code,
                "approved",
                "in_progress",
                "start",
                payload.evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:order-started",
                "maintenance_order",
                order_code,
                payload.model_dump(),
            )
            return self._format_order(db, int(order["id"]))

    def record_check_result(
        self, order_code: str, payload: ChecklistResultIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            order = self._require_order(db, order_code)
            if order["status"] != "in_progress":
                raise MaintenanceError(
                    409, "ORDER_NOT_IN_PROGRESS", "checklist evidence requires an in-progress order"
                )
            item_row = db.execute(
                """SELECT * FROM maintenance_checklist_items
                   WHERE tenant_id=? AND site_id=? AND checklist_id=? AND sequence=?""",
                (*self._scope(), int(order["checklist_id"]), payload.item_sequence),
            ).fetchone()
            if item_row is None:
                raise MaintenanceError(
                    409, "CHECKLIST_ITEM_NOT_FOUND", "checklist item was not found"
                )
            item = _row(item_row)
            if int(item["required"]) and payload.result == "not_applicable":
                raise MaintenanceError(
                    409,
                    "REQUIRED_CHECK_NOT_APPLICABLE",
                    "required checklist item cannot be skipped",
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_check_results (
                       tenant_id, site_id, maintenance_order_id, checklist_item_id,
                       result, evidence_reference, recorded_by, recorded_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(order["id"]),
                    int(item["id"]),
                    payload.result,
                    payload.evidence_reference,
                    actor,
                    _now(),
                ),
                code="CHECKLIST_RESULT_ALREADY_RECORDED",
                message="checklist item already has an immutable result",
            )
            self._audit(
                db,
                actor,
                "maintenance:check-result-recorded",
                "maintenance_order",
                order_code,
                payload.model_dump(),
            )
            row = db.execute(
                """SELECT result.*, item.sequence AS item_sequence, item.instruction
                   FROM maintenance_check_results result
                   JOIN maintenance_checklist_items item ON item.id=result.checklist_item_id
                   WHERE result.id=?""",
                (identifier,),
            ).fetchone()
            return _row(row)

    def _require_maintenance_code(self, db: Any, code: str, expected_type: str) -> dict[str, Any]:
        fact = self._require_code(db, "maintenance_codes", "code", code, "maintenance code")
        if fact["code_type"] != expected_type or not int(fact["active"]):
            raise MaintenanceError(
                409,
                "MAINTENANCE_CODE_TYPE_MISMATCH",
                f"{code} is not an active {expected_type} code",
            )
        return fact

    def complete_work(self, order_code: str, payload: WorkCompleteIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            order = self._require_order(db, order_code)
            if order["status"] != "in_progress":
                raise MaintenanceError(
                    409, "ORDER_NOT_IN_PROGRESS", "only in-progress maintenance work can complete"
                )
            incomplete = db.execute(
                """SELECT COUNT(*) AS count FROM maintenance_checklist_items item
                   WHERE item.checklist_id=? AND item.required=1 AND NOT EXISTS (
                       SELECT 1 FROM maintenance_check_results result
                       WHERE result.maintenance_order_id=? AND result.checklist_item_id=item.id
                         AND result.result='pass'
                   )""",
                (int(order["checklist_id"]), int(order["id"])),
            ).fetchone()
            if int(dict(incomplete)["count"]):
                raise MaintenanceError(
                    409,
                    "CHECKLIST_INCOMPLETE",
                    "all required maintenance checklist items must have immutable pass evidence",
                )
            failure = self._require_maintenance_code(db, payload.failure_code, "failure")
            cause = self._require_maintenance_code(db, payload.cause_code, "cause")
            remedy = self._require_maintenance_code(db, payload.remedy_code, "remedy")
            db.execute(
                """UPDATE maintenance_orders
                   SET status='work_completed', failure_code_id=?, cause_code_id=?,
                       remedy_code_id=?, work_evidence_reference=?, completed_by=?,
                       work_completed_at=?
                   WHERE id=? AND status='in_progress'""",
                (
                    int(failure["id"]),
                    int(cause["id"]),
                    int(remedy["id"]),
                    payload.work_evidence_reference,
                    actor,
                    _now(),
                    int(order["id"]),
                ),
            )
            self._history(
                db,
                "order",
                order_code,
                "in_progress",
                "work_completed",
                "work-complete",
                payload.work_evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:work-completed",
                "maintenance_order",
                order_code,
                payload.model_dump(),
            )
            return self._format_order(db, int(order["id"]))

    def verify_order(
        self, order_code: str, payload: MaintenanceVerifyIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            order = self._require_order(db, order_code)
            if order["status"] != "work_completed":
                raise MaintenanceError(
                    409,
                    "MAINTENANCE_NOT_READY_FOR_VERIFICATION",
                    "maintenance verification requires completed work and checklist evidence",
                )
            if actor == order["completed_by"]:
                raise MaintenanceError(
                    409,
                    "INDEPENDENT_VERIFIER_REQUIRED",
                    "work completer cannot verify the same maintenance order",
                )
            db.execute(
                """UPDATE maintenance_orders
                   SET status='verified', verification_result=?, verification_reference=?,
                       verified_by=?, verified_at=?
                   WHERE id=? AND status='work_completed'""",
                (
                    payload.verification_result,
                    payload.verification_reference,
                    actor,
                    _now(),
                    int(order["id"]),
                ),
            )
            asset_status = {
                "restored": "active",
                "degraded": "degraded",
                "not_restored": "out_of_service",
            }[payload.verification_result]
            db.execute(
                "UPDATE maintenance_assets SET status=? WHERE id=? AND status<>'retired'",
                (asset_status, int(order["asset_id"])),
            )
            self._history(
                db,
                "order",
                order_code,
                "work_completed",
                "verified",
                "verify",
                payload.verification_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:order-verified",
                "maintenance_order",
                order_code,
                payload.model_dump(),
            )
            return self._format_order(db, int(order["id"]))

    def _format_tool(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT tool.*, asset.asset_code
               FROM maintenance_tools tool
               JOIN maintenance_assets asset ON asset.id=tool.asset_id
               WHERE tool.tenant_id=? AND tool.site_id=? AND tool.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaintenanceError(404, "TOOL_NOT_FOUND", "maintenance tool was not found")
        return _row(row)

    def create_tool(self, payload: ToolIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            asset = self._require_code(
                db, "maintenance_assets", "asset_code", payload.asset_code, "maintenance asset"
            )
            status = "over_life" if payload.life_used >= payload.life_limit else "active"
            if (
                status == "active"
                and payload.calibration_required
                and payload.calibration_due_at is not None
                and payload.calibration_due_at <= datetime.now(UTC)
            ):
                status = "calibration_invalid"
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_tools (
                       tenant_id, site_id, tool_code, asset_id, name, tool_type,
                       life_limit, life_used, life_uom, calibration_required,
                       calibration_due_at, status, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.tool_code,
                    int(asset["id"]),
                    payload.name,
                    payload.tool_type,
                    payload.life_limit,
                    payload.life_used,
                    payload.life_uom,
                    int(payload.calibration_required),
                    payload.calibration_due_at.astimezone(UTC).isoformat()
                    if payload.calibration_due_at
                    else None,
                    status,
                    actor,
                ),
                code="DUPLICATE_MAINTENANCE_TOOL",
                message="maintenance tool code already exists",
            )
            self._history(
                db, "tool", payload.tool_code, None, status, "create", "tool-registration", actor
            )
            self._audit(
                db,
                actor,
                "maintenance:tool-created",
                "maintenance_tool",
                payload.tool_code,
                payload.model_dump(mode="json"),
            )
            return self._format_tool(db, identifier)

    def assign_tool(self, tool_code: str, payload: ToolAssignmentIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            tool = self._require_code(
                db, "maintenance_tools", "tool_code", tool_code, "maintenance tool"
            )
            row = db.execute(
                """SELECT task.id, assignment.equipment_id
                   FROM operation_tasks task
                   JOIN operation_task_assignments assignment
                     ON assignment.operation_task_id=task.id
                   WHERE task.tenant_id=? AND task.site_id=? AND task.id=?""",
                (*self._scope(), payload.operation_task_id),
            ).fetchone()
            if row is None:
                raise MaintenanceError(409, "REFERENCE_NOT_FOUND", "operation task does not exist")
            task = _row(row)
            asset = db.execute(
                "SELECT equipment_id FROM maintenance_assets WHERE id=?",
                (int(tool["asset_id"]),),
            ).fetchone()
            if int(dict(asset)["equipment_id"]) != int(task["equipment_id"]):
                raise MaintenanceError(
                    409,
                    "TOOL_TASK_ASSET_MISMATCH",
                    "tool asset is not the equipment assigned to the operation task",
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_tool_assignments (
                       tenant_id, site_id, tool_id, operation_task_id,
                       evidence_reference, assigned_by, assigned_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(tool["id"]),
                    payload.operation_task_id,
                    payload.evidence_reference,
                    actor,
                    _now(),
                ),
                code="TOOL_ALREADY_ASSIGNED",
                message="tool is already assigned to the operation task",
            )
            self._audit(
                db,
                actor,
                "maintenance:tool-assigned",
                "maintenance_tool",
                tool_code,
                payload.model_dump(),
            )
            assignment = db.execute(
                "SELECT * FROM maintenance_tool_assignments WHERE id=?", (identifier,)
            ).fetchone()
            result = _row(assignment)
            result["tool_code"] = tool_code
            return result

    def record_tool_life(
        self, tool_code: str, payload: ToolLifeEventIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            tool = self._require_code(
                db, "maintenance_tools", "tool_code", tool_code, "maintenance tool", lock=True
            )
            if tool["status"] == "retired":
                raise MaintenanceError(409, "TOOL_RETIRED", "retired tool cannot record usage")
            if payload.operation_task_id is not None:
                assigned = db.execute(
                    """SELECT id FROM maintenance_tool_assignments
                       WHERE tenant_id=? AND site_id=? AND tool_id=? AND operation_task_id=?""",
                    (*self._scope(), int(tool["id"]), payload.operation_task_id),
                ).fetchone()
                if assigned is None:
                    raise MaintenanceError(
                        409, "TOOL_NOT_ASSIGNED", "tool is not assigned to the operation task"
                    )
            identifier = self._insert_id(
                db,
                """INSERT INTO tool_life_events (
                       tenant_id, site_id, event_id, tool_id, usage_delta,
                       operation_task_id, occurred_at, evidence_reference, recorded_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.event_id,
                    int(tool["id"]),
                    payload.usage_delta,
                    payload.operation_task_id,
                    payload.occurred_at.astimezone(UTC).isoformat(),
                    payload.evidence_reference,
                    actor,
                ),
                code="DUPLICATE_TOOL_LIFE_EVENT",
                message="tool life event id already exists",
            )
            updated_tool = self._format_tool(db, int(tool["id"]))
            self._audit(
                db,
                actor,
                "maintenance:tool-life-recorded",
                "maintenance_tool",
                tool_code,
                payload.model_dump(mode="json"),
            )
            event = db.execute(
                "SELECT * FROM tool_life_events WHERE id=?", (identifier,)
            ).fetchone()
            result = _row(event)
            result["tool_code"] = tool_code
            result["life_used"] = updated_tool["life_used"]
            result["tool_status"] = updated_tool["status"]
            return result

    def record_calibration(
        self, tool_code: str, payload: CalibrationIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            tool = self._require_code(
                db, "maintenance_tools", "tool_code", tool_code, "maintenance tool", lock=True
            )
            personnel = self._require_code(
                db,
                "personnel",
                "personnel_code",
                payload.performed_by_personnel_code,
                "personnel",
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO calibration_events (
                       tenant_id, site_id, calibration_code, tool_id, result,
                       valid_from, valid_to, performed_by_personnel_id,
                       evidence_reference, recorded_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.calibration_code,
                    int(tool["id"]),
                    payload.result,
                    payload.valid_from.astimezone(UTC).isoformat(),
                    payload.valid_to.astimezone(UTC).isoformat(),
                    int(personnel["id"]),
                    payload.evidence_reference,
                    actor,
                ),
                code="DUPLICATE_CALIBRATION_EVENT",
                message="calibration event code already exists",
            )
            updated_tool = self._format_tool(db, int(tool["id"]))
            self._audit(
                db,
                actor,
                "maintenance:calibration-recorded",
                "maintenance_tool",
                tool_code,
                payload.model_dump(mode="json"),
            )
            event = db.execute(
                "SELECT * FROM calibration_events WHERE id=?", (identifier,)
            ).fetchone()
            result = _row(event)
            result["tool_code"] = tool_code
            result["tool_status"] = updated_tool["status"]
            return result

    def _format_plan(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT plan.*, asset.asset_code, checklist.checklist_code,
                      checklist.revision AS checklist_revision
               FROM preventive_maintenance_plans plan
               JOIN maintenance_assets asset ON asset.id=plan.asset_id
               JOIN maintenance_checklists checklist ON checklist.id=plan.checklist_id
               WHERE plan.tenant_id=? AND plan.site_id=? AND plan.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MaintenanceError(
                404, "PREVENTIVE_PLAN_NOT_FOUND", "preventive plan was not found"
            )
        return _row(row)

    def create_preventive_plan(self, payload: PreventivePlanIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            asset = self._require_code(
                db, "maintenance_assets", "asset_code", payload.asset_code, "maintenance asset"
            )
            checklist = self._require_checklist_revision(
                db, payload.checklist_code, payload.checklist_revision
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO preventive_maintenance_plans (
                       tenant_id, site_id, plan_code, asset_id, checklist_id,
                       interval_hours, next_due_at, production_impact, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.plan_code,
                    int(asset["id"]),
                    int(checklist["id"]),
                    payload.interval_hours,
                    payload.next_due_at.astimezone(UTC).isoformat(),
                    payload.production_impact,
                    actor,
                ),
                code="DUPLICATE_PREVENTIVE_PLAN",
                message="preventive maintenance plan code already exists",
            )
            self._history(
                db,
                "preventive_plan",
                payload.plan_code,
                None,
                "draft",
                "create",
                "preventive-plan-registration",
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:preventive-plan-created",
                "preventive_maintenance_plan",
                payload.plan_code,
                payload.model_dump(mode="json"),
            )
            return self._format_plan(db, identifier)

    def effective_preventive_plan(
        self, plan_code: str, payload: MaintenanceActionIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            plan = self._require_code(
                db,
                "preventive_maintenance_plans",
                "plan_code",
                plan_code,
                "preventive plan",
                lock=True,
            )
            if plan["status"] != "draft":
                raise MaintenanceError(
                    409, "PLAN_NOT_DRAFT", "only a draft plan can become effective"
                )
            db.execute(
                """UPDATE preventive_maintenance_plans
                   SET status='effective', effective_by=?,
                       effectivity_evidence_reference=?, effective_at=?
                   WHERE id=? AND status='draft'""",
                (actor, payload.evidence_reference, _now(), int(plan["id"])),
            )
            self._history(
                db,
                "preventive_plan",
                plan_code,
                "draft",
                "effective",
                "effective",
                payload.evidence_reference,
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:preventive-plan-effective",
                "preventive_maintenance_plan",
                plan_code,
                payload.model_dump(),
            )
            return self._format_plan(db, int(plan["id"]))

    def generate_preventive_work(
        self, plan_code: str, payload: PreventiveGenerateIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            plan = self._require_code(
                db,
                "preventive_maintenance_plans",
                "plan_code",
                plan_code,
                "preventive plan",
                lock=True,
            )
            if plan["status"] != "effective":
                raise MaintenanceError(
                    409, "PLAN_NOT_EFFECTIVE", "preventive plan is not effective"
                )
            now = datetime.now(UTC)
            due_at = _as_datetime(plan["next_due_at"])
            if due_at > now:
                raise MaintenanceError(409, "PREVENTIVE_PLAN_NOT_DUE", "preventive plan is not due")
            personnel = self._require_code(
                db, "personnel", "personnel_code", payload.assigned_personnel_code, "personnel"
            )
            asset = db.execute(
                "SELECT * FROM maintenance_assets WHERE id=?", (int(plan["asset_id"]),)
            ).fetchone()
            asset_fact = _row(asset)
            request_id = self._insert_id(
                db,
                """INSERT INTO maintenance_requests (
                       tenant_id, site_id, request_code, asset_id, source_type,
                       source_reference, description, priority, observed_at,
                       status, requested_by, converted_at
                   ) VALUES (?, ?, ?, ?, 'preventive', ?, ?, 'medium', ?,
                             'converted', ?, ?)""",
                (
                    *self._scope(),
                    payload.request_code,
                    int(plan["asset_id"]),
                    plan_code,
                    f"Preventive maintenance due for {asset_fact['asset_code']}",
                    now.isoformat(),
                    actor,
                    now.isoformat(),
                ),
                code="DUPLICATE_MAINTENANCE_REQUEST",
                message="preventive request code already exists",
            )
            order_id = self._insert_id(
                db,
                """INSERT INTO maintenance_orders (
                       tenant_id, site_id, order_code, request_id, asset_id, order_type,
                       priority, assigned_personnel_id, checklist_id, production_impact,
                       planned_start_at, planned_end_at, created_by
                   ) VALUES (?, ?, ?, ?, ?, 'preventive', 'medium', ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.order_code,
                    request_id,
                    int(plan["asset_id"]),
                    int(personnel["id"]),
                    int(plan["checklist_id"]),
                    plan["production_impact"],
                    payload.planned_start_at.astimezone(UTC).isoformat(),
                    payload.planned_end_at.astimezone(UTC).isoformat(),
                    actor,
                ),
                code="DUPLICATE_MAINTENANCE_ORDER",
                message="preventive order code already exists",
            )
            next_due = due_at
            interval = timedelta(hours=int(plan["interval_hours"]))
            while next_due <= now:
                next_due += interval
            db.execute(
                """UPDATE preventive_maintenance_plans
                   SET next_due_at=?, last_generated_at=? WHERE id=?""",
                (next_due.isoformat(), now.isoformat(), int(plan["id"])),
            )
            self._history(
                db,
                "request",
                payload.request_code,
                None,
                "converted",
                "preventive-generate",
                plan_code,
                actor,
            )
            self._history(
                db,
                "order",
                payload.order_code,
                None,
                "draft",
                "preventive-generate",
                plan_code,
                actor,
            )
            self._audit(
                db,
                actor,
                "maintenance:preventive-work-generated",
                "preventive_maintenance_plan",
                plan_code,
                payload.model_dump(mode="json"),
            )
            return {
                "request": self._format_request(db, request_id),
                "order": self._format_order(db, order_id),
                "plan": self._format_plan(db, int(plan["id"])),
            }

    def record_spare_use(self, order_code: str, payload: SpareUseIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            order = self._require_order(db, order_code)
            if order["status"] not in {"in_progress", "work_completed"}:
                raise MaintenanceError(
                    409,
                    "ORDER_NOT_ACTIVE",
                    "spare usage requires an in-progress or work-completed maintenance order",
                )
            movement_row = db.execute(
                """SELECT movement.*, lot.lot_code, material.material_code
                   FROM inventory_movements movement
                   JOIN material_lots lot ON lot.id=movement.lot_id
                   JOIN materials material ON material.id=movement.material_id
                   WHERE movement.tenant_id=? AND movement.site_id=? AND movement.movement_id=?""",
                (*self._scope(), payload.movement_id),
            ).fetchone()
            if movement_row is None:
                raise MaintenanceError(
                    409, "REFERENCE_NOT_FOUND", "inventory movement does not exist"
                )
            movement = _row(movement_row)
            if movement["movement_type"] != "consume":
                raise MaintenanceError(
                    409,
                    "SPARE_MOVEMENT_NOT_CONSUME",
                    "maintenance spare usage must reference a Phase 4 consume movement",
                )
            if movement.get("maintenance_order_id") != order["id"]:
                raise MaintenanceError(
                    409,
                    "SPARE_MOVEMENT_ORDER_MISMATCH",
                    "consume movement is not authorized by this maintenance order",
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO maintenance_spare_usages (
                       tenant_id, site_id, usage_id, maintenance_order_id,
                       inventory_movement_id, evidence_reference, recorded_by, recorded_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.usage_id,
                    int(order["id"]),
                    int(movement["id"]),
                    payload.evidence_reference,
                    actor,
                    _now(),
                ),
                code="DUPLICATE_SPARE_USAGE",
                message="spare usage or inventory movement is already linked",
            )
            self._audit(
                db,
                actor,
                "maintenance:spare-used",
                "maintenance_order",
                order_code,
                payload.model_dump(),
            )
            usage = db.execute(
                "SELECT * FROM maintenance_spare_usages WHERE id=?", (identifier,)
            ).fetchone()
            result = _row(usage)
            result.update(
                {
                    "order_code": order_code,
                    "movement_id": movement["movement_id"],
                    "movement_type": movement["movement_type"],
                    "lot_code": movement["lot_code"],
                    "material_code": movement["material_code"],
                    "quantity": movement["quantity"],
                }
            )
            return result


maintenance_repository = MaintenanceRepository()
