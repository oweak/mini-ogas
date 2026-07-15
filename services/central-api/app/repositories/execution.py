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
from ..domain.execution import (
    CompleteTaskIn,
    DowntimeEndIn,
    DowntimeStartIn,
    ExecutionActionIn,
    ExecutionError,
    HoldActionIn,
    ProductionOrderIn,
    QuantityReportIn,
    SetupCompleteIn,
)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
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


def _decode_json(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _row(row: Any) -> dict[str, Any]:
    return _json_ready(dict(row))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _same_quantity(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= 1e-9


class ExecutionRepository:
    """PostgreSQL/SQLite authority for Phase 3 production execution facts."""

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
        code: str = "DUPLICATE_EXECUTION_RESOURCE",
        message: str = "execution resource already exists",
    ) -> int:
        try:
            row = db.execute(f"{sql} RETURNING id", params).fetchone()
        except Exception as exc:
            lowered = str(exc).lower()
            if any(token in lowered for token in ("unique", "duplicate", "constraint failed")):
                raise ExecutionError(409, code, message) from exc
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
               ) VALUES (?, ?, 'execution', ?, ?, ?, ?, 'success', ?, ?)
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
                "run_id": "execution",
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "result": "success",
                "detail": detail_json,
                "created_at": created_at,
            },
            run_id="execution",
        )
        if not outbox_repository.enqueue_in_transaction(db, envelope):
            raise RuntimeError("failed to enqueue the execution audit envelope")

    def _request_hash(self, payload: Any) -> str:
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def _idempotent_get(
        self,
        db: Any,
        resource_type: str,
        resource_id: str,
        action: str,
        key: str,
        payload: Any,
    ) -> dict[str, Any] | None:
        row = db.execute(
            """SELECT request_hash, response_json FROM execution_idempotency
               WHERE tenant_id=? AND site_id=? AND resource_type=? AND resource_id=?
                 AND action=? AND idempotency_key=?""",
            (*self._scope(), resource_type, resource_id, action, key),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        if str(data["request_hash"]) != self._request_hash(payload):
            raise ExecutionError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "the idempotency key was already used with a different request",
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
            )
        return _decode_json(data["response_json"], {})

    def _idempotent_store(
        self,
        db: Any,
        resource_type: str,
        resource_id: str,
        action: str,
        key: str,
        payload: Any,
        response: dict[str, Any],
    ) -> None:
        db.execute(
            """INSERT INTO execution_idempotency (
                   tenant_id, site_id, resource_type, resource_id, action,
                   idempotency_key, request_hash, response_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                *self._scope(),
                resource_type,
                resource_id,
                action,
                key,
                self._request_hash(payload),
                _canonical_json(response),
            ),
        )

    def _require_product(self, db: Any, product_code: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM products WHERE tenant_id=? AND site_id=? AND product_code=?",
            (*self._scope(), product_code),
        ).fetchone()
        if row is None:
            raise ExecutionError(
                409,
                "REFERENCE_NOT_FOUND",
                "production order product does not exist in the active tenant/site",
                product_code=product_code,
            )
        return _row(row)

    def _require_production_order(
        self, db: Any, production_order_code: str, *, lock: bool = False
    ) -> dict[str, Any]:
        sql = (
            "SELECT * FROM production_orders "
            "WHERE tenant_id=? AND site_id=? AND production_order_code=?"
        )
        if lock:
            sql += self._lock_suffix()
        row = db.execute(sql, (*self._scope(), production_order_code)).fetchone()
        if row is None:
            raise ExecutionError(
                404,
                "PRODUCTION_ORDER_NOT_FOUND",
                "production order was not found",
                production_order_code=production_order_code,
            )
        return _row(row)

    def _require_work_order(
        self, db: Any, work_order_code: str, *, lock: bool = False
    ) -> dict[str, Any]:
        sql = "SELECT * FROM work_orders WHERE tenant_id=? AND site_id=? AND work_order_code=?"
        if lock:
            sql += self._lock_suffix()
        row = db.execute(sql, (*self._scope(), work_order_code)).fetchone()
        if row is None:
            raise ExecutionError(
                404,
                "WORK_ORDER_NOT_FOUND",
                "work order was not found",
                work_order_code=work_order_code,
            )
        return _row(row)

    def _require_task(self, db: Any, task_id: int, *, lock: bool = False) -> dict[str, Any]:
        sql = "SELECT * FROM operation_tasks WHERE tenant_id=? AND site_id=? AND id=?"
        if lock:
            sql += self._lock_suffix()
        row = db.execute(sql, (*self._scope(), task_id)).fetchone()
        if row is None:
            raise ExecutionError(404, "OPERATION_TASK_NOT_FOUND", "operation task was not found")
        return _row(row)

    def _format_production_order(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT po.*, p.product_code
               FROM production_orders po JOIN products p ON p.id=po.product_id
               WHERE po.tenant_id=? AND po.site_id=? AND po.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise ExecutionError(
                404, "PRODUCTION_ORDER_NOT_FOUND", "production order was not found"
            )
        return _row(row)

    def create_production_order(self, payload: ProductionOrderIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            product = self._require_product(db, payload.product_code)
            identifier = self._insert_id(
                db,
                """INSERT INTO production_orders (
                       tenant_id, site_id, production_order_code, product_id, quantity,
                       priority, due_at, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.production_order_code,
                    int(product["id"]),
                    payload.quantity,
                    payload.priority,
                    payload.due_at.astimezone(UTC).isoformat(),
                    actor,
                ),
                message="production order code already exists",
            )
            self._audit(
                db,
                actor,
                "execution:production-order-created",
                "production_order",
                payload.production_order_code,
                payload.model_dump(mode="json"),
            )
            return self._format_production_order(db, identifier)

    def attach_work_order(
        self,
        production_order_code: str,
        work_order_code: str,
        payload: ExecutionActionIn,
        actor: str,
    ) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        resource_id = f"{production_order_code}:{work_order_code}"
        with get_db() as db:
            replay = self._idempotent_get(
                db,
                "production_order_work_order",
                resource_id,
                "attach",
                payload.idempotency_key,
                request,
            )
            if replay is not None:
                return replay
            production_order = self._require_production_order(db, production_order_code, lock=True)
            work_order = self._require_work_order(db, work_order_code, lock=True)
            if production_order["status"] != "draft":
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_NOT_EDITABLE",
                    "work orders can only be attached while the production order is draft",
                    status=production_order["status"],
                )
            if work_order["status"] != "released":
                raise ExecutionError(
                    409,
                    "WORK_ORDER_NOT_RELEASED",
                    "only a validated and released work order can be attached",
                    work_order_code=work_order_code,
                    status=work_order["status"],
                )
            if int(work_order["product_id"]) != int(production_order["product_id"]):
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_PRODUCT_MISMATCH",
                    "attached work order must use the production-order product",
                )
            existing = db.execute(
                """SELECT production_order_id FROM production_order_work_orders
                   WHERE tenant_id=? AND site_id=? AND work_order_id=?""",
                (*self._scope(), int(work_order["id"])),
            ).fetchone()
            if existing is not None:
                raise ExecutionError(
                    409,
                    "WORK_ORDER_ALREADY_ATTACHED",
                    "work order is already attached to a production order",
                    work_order_code=work_order_code,
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO production_order_work_orders (
                       tenant_id, site_id, production_order_id, work_order_id, attached_by
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(production_order["id"]),
                    int(work_order["id"]),
                    actor,
                ),
                code="WORK_ORDER_ALREADY_ATTACHED",
                message="work order is already attached to a production order",
            )
            response = {
                "id": identifier,
                "production_order_code": production_order_code,
                "work_order_code": work_order_code,
                "status": "attached",
            }
            self._audit(
                db,
                actor,
                "execution:work-order-attached",
                "production_order",
                production_order_code,
                {"work_order_code": work_order_code},
            )
            self._idempotent_store(
                db,
                "production_order_work_order",
                resource_id,
                "attach",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def release_production_order(
        self, production_order_code: str, payload: ExecutionActionIn, actor: str
    ) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db,
                "production_order",
                production_order_code,
                "release",
                payload.idempotency_key,
                request,
            )
            if replay is not None:
                return replay
            production_order = self._require_production_order(db, production_order_code, lock=True)
            if production_order["status"] != "draft":
                raise ExecutionError(
                    409,
                    "INVALID_PRODUCTION_ORDER_TRANSITION",
                    "production order can only be released from draft",
                    status=production_order["status"],
                )
            rows = db.execute(
                """SELECT wo.id, wo.work_order_code, wo.product_id, wo.quantity, wo.status
                   FROM production_order_work_orders link
                   JOIN work_orders wo ON wo.id=link.work_order_id
                   WHERE link.tenant_id=? AND link.site_id=? AND link.production_order_id=?
                   ORDER BY wo.id""",
                (*self._scope(), int(production_order["id"])),
            ).fetchall()
            work_orders = [_row(row) for row in rows]
            if not work_orders:
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_EMPTY",
                    "production order must contain at least one released work order",
                )
            if any(item["status"] != "released" for item in work_orders):
                raise ExecutionError(
                    409,
                    "WORK_ORDER_NOT_RELEASED",
                    "every attached work order must be released before production-order release",
                )
            if any(
                int(item["product_id"]) != int(production_order["product_id"])
                for item in work_orders
            ):
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_PRODUCT_MISMATCH",
                    "all attached work orders must use the production-order product",
                )
            planned = sum(float(item["quantity"]) for item in work_orders)
            if not _same_quantity(planned, float(production_order["quantity"])):
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_QUANTITY_MISMATCH",
                    "attached work-order quantity must exactly equal production-order quantity",
                    production_order_quantity=production_order["quantity"],
                    work_order_quantity=planned,
                )
            now = _now()
            updated = db.execute(
                """UPDATE production_orders SET status='released', released_by=?, released_at=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='draft'""",
                (actor, now, *self._scope(), int(production_order["id"])),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_RELEASE_CONFLICT",
                    "production order changed during release validation",
                )
            response = self._format_production_order(db, int(production_order["id"]))
            self._audit(
                db,
                actor,
                "execution:production-order-released",
                "production_order",
                production_order_code,
                {
                    "reason": payload.reason,
                    "work_order_codes": [item["work_order_code"] for item in work_orders],
                    "quantity": planned,
                },
            )
            self._idempotent_store(
                db,
                "production_order",
                production_order_code,
                "release",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def _require_code(
        self, db: Any, table: str, code_column: str, code: str, resource: str
    ) -> dict[str, Any]:
        row = db.execute(
            f"SELECT * FROM {table} WHERE tenant_id=? AND site_id=? AND {code_column}=?",
            (*self._scope(), code),
        ).fetchone()
        if row is None:
            raise ExecutionError(
                409,
                "REFERENCE_NOT_FOUND",
                f"assigned {resource} was not found",
                resource_type=resource,
                resource_code=code,
            )
        return _row(row)

    def _record_history(
        self,
        db: Any,
        task_id: int,
        from_status: str | None,
        to_status: str,
        action: str,
        actor: str,
        idempotency_key: str,
        *,
        reason: str = "",
        evidence_reference: str = "",
    ) -> None:
        db.execute(
            """INSERT INTO operation_status_history (
                   tenant_id, site_id, operation_task_id, from_status, to_status,
                   action, reason, evidence_reference, actor, occurred_at, idempotency_key
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                *self._scope(),
                task_id,
                from_status,
                to_status,
                action,
                reason,
                evidence_reference,
                actor,
                _now(),
                idempotency_key,
            ),
        )

    def _change_task_status(
        self,
        db: Any,
        task: dict[str, Any],
        to_status: str,
        action: str,
        actor: str,
        idempotency_key: str,
        *,
        reason: str = "",
        evidence_reference: str = "",
        set_started: bool = False,
        set_completed: bool = False,
        set_closed: bool = False,
        hold_return_status: str | None = None,
        clear_hold_return: bool = False,
    ) -> dict[str, Any]:
        assignments = ["status=?"]
        params: list[Any] = [to_status]
        if set_started:
            assignments.append("started_at=COALESCE(started_at, ?)")
            params.append(_now())
        if set_completed:
            assignments.extend(["completed_at=?", "completion_evidence_reference=?"])
            params.extend([_now(), evidence_reference])
        if set_closed:
            assignments.append("closed_at=?")
            params.append(_now())
        if hold_return_status is not None:
            assignments.append("hold_return_status=?")
            params.append(hold_return_status)
        if clear_hold_return:
            assignments.append("hold_return_status=NULL")
        params.extend([*self._scope(), int(task["id"]), task["status"]])
        updated = db.execute(
            f"""UPDATE operation_tasks SET {", ".join(assignments)}
                WHERE tenant_id=? AND site_id=? AND id=? AND status=?""",
            tuple(params),
        )
        if int(getattr(updated, "rowcount", 0) or 0) != 1:
            raise ExecutionError(
                409,
                "OPERATION_TRANSITION_CONFLICT",
                "operation task changed while the transition was being applied",
                task_id=task["id"],
            )
        self._record_history(
            db,
            int(task["id"]),
            str(task["status"]),
            to_status,
            action,
            actor,
            idempotency_key,
            reason=reason,
            evidence_reference=evidence_reference,
        )
        return self._require_task(db, int(task["id"]))

    def _format_task(self, db: Any, task_id: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT task.*, e.equipment_code, p.personnel_code
               FROM operation_tasks task
               LEFT JOIN operation_task_assignments assignment
                 ON assignment.operation_task_id=task.id
                AND assignment.tenant_id=task.tenant_id AND assignment.site_id=task.site_id
               LEFT JOIN equipment e ON e.id=assignment.equipment_id
               LEFT JOIN personnel p ON p.id=assignment.personnel_id
               WHERE task.tenant_id=? AND task.site_id=? AND task.id=?""",
            (*self._scope(), task_id),
        ).fetchone()
        if row is None:
            raise ExecutionError(404, "OPERATION_TASK_NOT_FOUND", "operation task was not found")
        result = _row(row)
        totals = db.execute(
            """SELECT COALESCE(SUM(good_quantity), 0) AS good_quantity,
                      COALESCE(SUM(scrap_quantity), 0) AS scrap_quantity,
                      COALESCE(SUM(rework_quantity), 0) AS rework_quantity
               FROM operation_quantity_reports
               WHERE tenant_id=? AND site_id=? AND operation_task_id=?""",
            (*self._scope(), task_id),
        ).fetchone()
        quantities = _row(totals)
        quantities["accounted_quantity"] = sum(float(value) for value in quantities.values())
        result["quantities"] = quantities
        return result

    def _format_work_order_execution(self, db: Any, work_order_code: str) -> dict[str, Any]:
        row = db.execute(
            """SELECT execution.id, execution.status AS execution_status,
                      wo.work_order_code, wo.quantity, po.production_order_code,
                      po.status AS production_order_status
               FROM work_order_execution execution
               JOIN work_orders wo ON wo.id=execution.work_order_id
               JOIN production_orders po ON po.id=execution.production_order_id
               WHERE execution.tenant_id=? AND execution.site_id=? AND wo.work_order_code=?""",
            (*self._scope(), work_order_code),
        ).fetchone()
        if row is None:
            raise ExecutionError(
                404,
                "WORK_ORDER_EXECUTION_NOT_FOUND",
                "work order has not been dispatched",
                work_order_code=work_order_code,
            )
        result = _row(row)
        task_rows = db.execute(
            """SELECT id FROM operation_tasks
               WHERE tenant_id=? AND site_id=? AND work_order_execution_id=?
               ORDER BY sequence""",
            (*self._scope(), int(result["id"])),
        ).fetchall()
        result["tasks"] = [self._format_task(db, int(dict(item)["id"])) for item in task_rows]
        return result

    def _validate_predecessors(self, db: Any, task: dict[str, Any]) -> None:
        blocked = db.execute(
            """SELECT id, sequence, status FROM operation_tasks
               WHERE tenant_id=? AND site_id=? AND work_order_execution_id=?
                 AND sequence<? AND status NOT IN ('completed','closed')
               ORDER BY sequence LIMIT 1""",
            (
                *self._scope(),
                int(task["work_order_execution_id"]),
                int(task["sequence"]),
            ),
        ).fetchone()
        if blocked is not None:
            data = _row(blocked)
            raise ExecutionError(
                409,
                "PREDECESSOR_OPERATION_INCOMPLETE",
                "the preceding routing operation must complete before setup starts",
                predecessor_task_id=data["id"],
                predecessor_sequence=data["sequence"],
                predecessor_status=data["status"],
            )

    def dispatch_work_order(
        self, work_order_code: str, payload: ExecutionActionIn, actor: str
    ) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "work_order", work_order_code, "dispatch", payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            work_order = self._require_work_order(db, work_order_code, lock=True)
            if work_order["status"] != "released":
                raise ExecutionError(
                    409,
                    "WORK_ORDER_NOT_RELEASED",
                    "only a released work order can be dispatched",
                    status=work_order["status"],
                )
            link_row = db.execute(
                """SELECT link.production_order_id, po.status AS production_order_status
                   FROM production_order_work_orders link
                   JOIN production_orders po ON po.id=link.production_order_id
                   WHERE link.tenant_id=? AND link.site_id=? AND link.work_order_id=?""",
                (*self._scope(), int(work_order["id"])),
            ).fetchone()
            if link_row is None:
                raise ExecutionError(
                    409,
                    "WORK_ORDER_NOT_ATTACHED",
                    "work order must belong to a production order before dispatch",
                )
            link = _row(link_row)
            if link["production_order_status"] not in {"released", "in_progress"}:
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_NOT_RELEASED",
                    "production order must be released before work-order dispatch",
                    status=link["production_order_status"],
                )
            existing = db.execute(
                """SELECT id FROM work_order_execution
                   WHERE tenant_id=? AND site_id=? AND work_order_id=?""",
                (*self._scope(), int(work_order["id"])),
            ).fetchone()
            if existing is not None:
                raise ExecutionError(
                    409,
                    "WORK_ORDER_ALREADY_DISPATCHED",
                    "work order already has an execution record",
                    work_order_code=work_order_code,
                )
            execution_id = self._insert_id(
                db,
                """INSERT INTO work_order_execution (
                       tenant_id, site_id, production_order_id, work_order_id, status,
                       dispatched_by, dispatched_at
                   ) VALUES (?, ?, ?, ?, 'dispatched', ?, ?)""",
                (
                    *self._scope(),
                    int(link["production_order_id"]),
                    int(work_order["id"]),
                    actor,
                    _now(),
                ),
                code="WORK_ORDER_ALREADY_DISPATCHED",
                message="work order already has an execution record",
            )
            routing_row = db.execute(
                """SELECT content_json FROM routing_revisions
                   WHERE tenant_id=? AND site_id=? AND id=?""",
                (*self._scope(), int(work_order["routing_revision_id"])),
            ).fetchone()
            routing = _decode_json(dict(routing_row)["content_json"], {}) if routing_row else {}
            operations = list(routing.get("operations") or [])
            assignments = _decode_json(work_order["operation_assignments_json"], [])
            assignment_by_sequence = {int(item["sequence"]): item for item in assignments}
            if not operations:
                raise ExecutionError(
                    409,
                    "ROUTING_OPERATIONS_MISSING",
                    "released work order has no bound routing operations",
                )
            task_ids: list[int] = []
            for operation in sorted(operations, key=lambda item: int(item["sequence"])):
                sequence = int(operation["sequence"])
                assignment = assignment_by_sequence.get(sequence)
                if assignment is None:
                    raise ExecutionError(
                        409,
                        "OPERATION_ASSIGNMENT_INCOMPLETE",
                        "released work order is missing an operation assignment",
                        sequence=sequence,
                    )
                equipment = self._require_code(
                    db,
                    "equipment",
                    "equipment_code",
                    str(assignment["equipment_code"]),
                    "equipment",
                )
                personnel = self._require_code(
                    db,
                    "personnel",
                    "personnel_code",
                    str(assignment["personnel_code"]),
                    "personnel",
                )
                task_id = self._insert_id(
                    db,
                    """INSERT INTO operation_tasks (
                           tenant_id, site_id, work_order_execution_id, work_order_id,
                           routing_revision_id, sequence, operation_code, name,
                           planned_quantity, status
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'dispatched')""",
                    (
                        *self._scope(),
                        execution_id,
                        int(work_order["id"]),
                        int(work_order["routing_revision_id"]),
                        sequence,
                        str(operation["operation_code"]),
                        str(operation["name"]),
                        float(work_order["quantity"]),
                    ),
                    code="DUPLICATE_OPERATION_TASK",
                    message="routing operation was already materialized for this work order",
                )
                db.execute(
                    """INSERT INTO operation_task_assignments (
                           tenant_id, site_id, operation_task_id, equipment_id,
                           personnel_id, assigned_by
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        *self._scope(),
                        task_id,
                        int(equipment["id"]),
                        int(personnel["id"]),
                        actor,
                    ),
                )
                self._record_history(
                    db,
                    task_id,
                    None,
                    "dispatched",
                    "dispatch",
                    actor,
                    payload.idempotency_key,
                    reason=payload.reason,
                )
                task_ids.append(task_id)
            db.execute(
                """UPDATE production_orders SET status='in_progress'
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='released'""",
                (*self._scope(), int(link["production_order_id"])),
            )
            response = {
                "work_order_code": work_order_code,
                "execution_status": "dispatched",
                "tasks": [self._format_task(db, task_id) for task_id in task_ids],
            }
            self._audit(
                db,
                actor,
                "execution:work-order-dispatched",
                "work_order",
                work_order_code,
                {"task_ids": task_ids, "routing_revision_id": work_order["routing_revision_id"]},
            )
            self._idempotent_store(
                db,
                "work_order",
                work_order_code,
                "dispatch",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def get_task(self, task_id: int) -> dict[str, Any]:
        with get_db() as db:
            return self._format_task(db, task_id)

    def get_task_history(self, task_id: int) -> list[dict[str, Any]]:
        with get_db() as db:
            self._require_task(db, task_id)
            rows = db.execute(
                """SELECT * FROM operation_status_history
                   WHERE tenant_id=? AND site_id=? AND operation_task_id=?
                   ORDER BY occurred_at, id""",
                (*self._scope(), task_id),
            ).fetchall()
            return [_row(item) for item in rows]

    def get_work_order_execution(self, work_order_code: str) -> dict[str, Any]:
        with get_db() as db:
            return self._format_work_order_execution(db, work_order_code)

    def _require_transition(self, task: dict[str, Any], allowed: set[str], action: str) -> None:
        if str(task["status"]) not in allowed:
            raise ExecutionError(
                409,
                "INVALID_OPERATION_TRANSITION",
                f"operation task cannot {action} from status {task['status']}",
                task_id=task["id"],
                current_status=task["status"],
                allowed_statuses=sorted(allowed),
            )

    def _require_maintenance_readiness(self, db: Any, task_id: int) -> None:
        blocker = db.execute(
            """SELECT maintenance_order.order_code
               FROM operation_task_assignments assignment
               JOIN maintenance_assets asset ON asset.equipment_id=assignment.equipment_id
               JOIN maintenance_orders maintenance_order ON maintenance_order.asset_id=asset.id
               WHERE assignment.tenant_id=? AND assignment.site_id=?
                 AND assignment.operation_task_id=?
                 AND maintenance_order.status IN ('in_progress','work_completed')
                 AND maintenance_order.production_impact='equipment_unavailable'
               ORDER BY maintenance_order.id LIMIT 1""",
            (*self._scope(), task_id),
        ).fetchone()
        if blocker is not None:
            raise ExecutionError(
                409,
                "ACTIVE_MAINTENANCE_BLOCKS_TASK",
                (
                    "equipment-unavailable maintenance must be independently verified "
                    "before task execution"
                ),
                task_id=task_id,
                maintenance_order_code=str(dict(blocker)["order_code"]),
            )
        over_life = db.execute(
            """SELECT tool.tool_code FROM maintenance_tool_assignments assignment
               JOIN maintenance_tools tool ON tool.id=assignment.tool_id
               WHERE assignment.tenant_id=? AND assignment.site_id=?
                 AND assignment.operation_task_id=? AND tool.status='over_life'
               ORDER BY tool.id LIMIT 1""",
            (*self._scope(), task_id),
        ).fetchone()
        if over_life is not None:
            raise ExecutionError(
                409,
                "TOOL_LIFE_EXCEEDED",
                "assigned tool has reached or exceeded its governed life limit",
                task_id=task_id,
                tool_code=str(dict(over_life)["tool_code"]),
            )
        calibration = db.execute(
            """SELECT tool.tool_code FROM maintenance_tool_assignments assignment
               JOIN maintenance_tools tool ON tool.id=assignment.tool_id
               WHERE assignment.tenant_id=? AND assignment.site_id=?
                 AND assignment.operation_task_id=?
                 AND (tool.status='calibration_invalid'
                      OR (tool.calibration_required=1 AND tool.calibration_due_at<=?))
               ORDER BY tool.id LIMIT 1""",
            (*self._scope(), task_id, _now()),
        ).fetchone()
        if calibration is not None:
            raise ExecutionError(
                409,
                "TOOL_CALIBRATION_INVALID",
                "assigned tool has failed or expired calibration evidence",
                task_id=task_id,
                tool_code=str(dict(calibration)["tool_code"]),
            )

    def start_setup(self, task_id: int, payload: ExecutionActionIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "operation_task", str(task_id), "setup-start", payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"dispatched"}, "start setup")
            self._validate_predecessors(db, task)
            db.execute(
                """INSERT INTO operation_setups (
                       tenant_id, site_id, operation_task_id, status, started_by, started_at
                   ) VALUES (?, ?, ?, 'in_progress', ?, ?)""",
                (*self._scope(), task_id, actor, _now()),
            )
            self._change_task_status(
                db,
                task,
                "setup",
                "setup-start",
                actor,
                payload.idempotency_key,
                reason=payload.reason,
            )
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                "execution:setup-started",
                "operation_task",
                str(task_id),
                {"work_order_id": task["work_order_id"], "sequence": task["sequence"]},
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "setup-start",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def complete_setup(self, task_id: int, payload: SetupCompleteIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db,
                "operation_task",
                str(task_id),
                "setup-complete",
                payload.idempotency_key,
                request,
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"setup"}, "complete setup")
            updated = db.execute(
                """UPDATE operation_setups
                   SET status='completed', parameters_json=?, evidence_reference=?,
                       completed_by=?, completed_at=?
                   WHERE tenant_id=? AND site_id=? AND operation_task_id=?
                     AND status='in_progress'""",
                (
                    _canonical_json(payload.parameters),
                    payload.evidence_reference,
                    actor,
                    _now(),
                    *self._scope(),
                    task_id,
                ),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise ExecutionError(
                    409,
                    "SETUP_RECORD_NOT_ACTIVE",
                    "operation task has no active setup record",
                    task_id=task_id,
                )
            self._change_task_status(
                db,
                task,
                "ready",
                "setup-complete",
                actor,
                payload.idempotency_key,
                evidence_reference=payload.evidence_reference,
            )
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                "execution:setup-completed",
                "operation_task",
                str(task_id),
                {
                    "evidence_reference": payload.evidence_reference,
                    "parameters": payload.parameters,
                },
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "setup-complete",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def start_task(self, task_id: int, payload: ExecutionActionIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "operation_task", str(task_id), "start", payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"ready"}, "start")
            self._require_maintenance_readiness(db, task_id)
            self._change_task_status(
                db,
                task,
                "running",
                "start",
                actor,
                payload.idempotency_key,
                reason=payload.reason,
                set_started=True,
            )
            db.execute(
                """UPDATE work_order_execution SET status='in_progress'
                   WHERE tenant_id=? AND site_id=? AND id=?
                     AND status IN ('released','dispatched')""",
                (*self._scope(), int(task["work_order_execution_id"])),
            )
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                "execution:operation-started",
                "operation_task",
                str(task_id),
                {"work_order_id": task["work_order_id"], "sequence": task["sequence"]},
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "start",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def pause_task(self, task_id: int, payload: ExecutionActionIn, actor: str) -> dict[str, Any]:
        return self._simple_task_transition(
            task_id,
            payload,
            actor,
            action="pause",
            allowed={"running"},
            target="paused",
            audit_action="execution:operation-paused",
        )

    def resume_task(self, task_id: int, payload: ExecutionActionIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "operation_task", str(task_id), "resume", payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"paused"}, "resume")
            downtime = db.execute(
                """SELECT id FROM operation_downtime
                   WHERE tenant_id=? AND site_id=? AND operation_task_id=? AND status='open'""",
                (*self._scope(), task_id),
            ).fetchone()
            if downtime is not None:
                raise ExecutionError(
                    409,
                    "OPEN_DOWNTIME_BLOCKS_RESUME",
                    "operation cannot resume until its open downtime record is closed",
                    task_id=task_id,
                )
            self._require_maintenance_readiness(db, task_id)
            self._change_task_status(
                db,
                task,
                "running",
                "resume",
                actor,
                payload.idempotency_key,
                reason=payload.reason,
            )
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                "execution:operation-resumed",
                "operation_task",
                str(task_id),
                {"reason": payload.reason},
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "resume",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def _simple_task_transition(
        self,
        task_id: int,
        payload: ExecutionActionIn,
        actor: str,
        *,
        action: str,
        allowed: set[str],
        target: str,
        audit_action: str,
    ) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "operation_task", str(task_id), action, payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, allowed, action)
            self._change_task_status(
                db,
                task,
                target,
                action,
                actor,
                payload.idempotency_key,
                reason=payload.reason,
            )
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                audit_action,
                "operation_task",
                str(task_id),
                {"from_status": task["status"], "to_status": target, "reason": payload.reason},
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                action,
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def hold_task(self, task_id: int, payload: HoldActionIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "operation_task", str(task_id), "hold", payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(
                task, {"dispatched", "setup", "ready", "running", "paused"}, "hold"
            )
            db.execute(
                """INSERT INTO operation_holds (
                       tenant_id, site_id, operation_task_id, prior_status, status,
                       reason, held_by, held_at
                   ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?)""",
                (*self._scope(), task_id, task["status"], payload.reason, actor, _now()),
            )
            self._change_task_status(
                db,
                task,
                "held",
                "hold",
                actor,
                payload.idempotency_key,
                reason=payload.reason,
                hold_return_status=str(task["status"]),
            )
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                "execution:operation-held",
                "operation_task",
                str(task_id),
                {"prior_status": task["status"], "reason": payload.reason},
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "hold",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def release_hold(self, task_id: int, payload: HoldActionIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db,
                "operation_task",
                str(task_id),
                "release-hold",
                payload.idempotency_key,
                request,
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"held"}, "release hold")
            hold_row = db.execute(
                """SELECT * FROM operation_holds
                   WHERE tenant_id=? AND site_id=? AND operation_task_id=? AND status='open'
                   ORDER BY id DESC LIMIT 1""",
                (*self._scope(), task_id),
            ).fetchone()
            if hold_row is None:
                raise ExecutionError(
                    409,
                    "OPEN_HOLD_NOT_FOUND",
                    "held task has no durable open hold record",
                    task_id=task_id,
                )
            hold = _row(hold_row)
            restore_status = str(hold["prior_status"])
            db.execute(
                """UPDATE operation_holds
                   SET status='released', released_by=?, released_at=?, release_reason=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='open'""",
                (actor, _now(), payload.reason, *self._scope(), int(hold["id"])),
            )
            self._change_task_status(
                db,
                task,
                restore_status,
                "release-hold",
                actor,
                payload.idempotency_key,
                reason=payload.reason,
                clear_hold_return=True,
            )
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                "execution:operation-hold-released",
                "operation_task",
                str(task_id),
                {"restored_status": restore_status, "reason": payload.reason},
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "release-hold",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def report_quantity(
        self, task_id: int, payload: QuantityReportIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            task = self._require_task(db, task_id, lock=True)
            existing_row = db.execute(
                """SELECT * FROM operation_quantity_reports
                   WHERE tenant_id=? AND site_id=? AND report_id=?""",
                (*self._scope(), payload.report_id),
            ).fetchone()
            if existing_row is not None:
                existing = _row(existing_row)
                same = (
                    int(existing["operation_task_id"]) == task_id
                    and _same_quantity(existing["good_quantity"], payload.good_quantity)
                    and _same_quantity(existing["scrap_quantity"], payload.scrap_quantity)
                    and _same_quantity(existing["rework_quantity"], payload.rework_quantity)
                    and existing["evidence_reference"] == payload.evidence_reference
                    and _timestamp(existing["occurred_at"])
                    == payload.occurred_at.astimezone(UTC).isoformat()
                )
                if not same:
                    raise ExecutionError(
                        409,
                        "IDEMPOTENCY_KEY_REUSED",
                        "report_id already identifies a different quantity report",
                        report_id=payload.report_id,
                    )
                return existing
            self._require_transition(task, {"running", "paused"}, "report quantity")
            totals_row = db.execute(
                """SELECT COALESCE(SUM(good_quantity + scrap_quantity + rework_quantity), 0)
                          AS accounted_quantity
                   FROM operation_quantity_reports
                   WHERE tenant_id=? AND site_id=? AND operation_task_id=?""",
                (*self._scope(), task_id),
            ).fetchone()
            current = float(_row(totals_row)["accounted_quantity"])
            reported = payload.good_quantity + payload.scrap_quantity + payload.rework_quantity
            if current + reported > float(task["planned_quantity"]) + 1e-9:
                raise ExecutionError(
                    409,
                    "QUANTITY_EXCEEDS_PLAN",
                    "accepted quantity reports cannot exceed the operation plan",
                    planned_quantity=task["planned_quantity"],
                    already_accounted=current,
                    attempted_quantity=reported,
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO operation_quantity_reports (
                       tenant_id, site_id, operation_task_id, report_id, good_quantity,
                       scrap_quantity, rework_quantity, evidence_reference, occurred_at,
                       reported_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    task_id,
                    payload.report_id,
                    payload.good_quantity,
                    payload.scrap_quantity,
                    payload.rework_quantity,
                    payload.evidence_reference,
                    payload.occurred_at.astimezone(UTC).isoformat(),
                    actor,
                ),
                code="DUPLICATE_QUANTITY_REPORT",
                message="quantity report identifier already exists",
            )
            row = db.execute(
                """SELECT * FROM operation_quantity_reports
                   WHERE tenant_id=? AND site_id=? AND id=?""",
                (*self._scope(), identifier),
            ).fetchone()
            response = _row(row)
            self._audit(
                db,
                actor,
                "execution:quantity-reported",
                "operation_task",
                str(task_id),
                {
                    "report_id": payload.report_id,
                    "good_quantity": payload.good_quantity,
                    "scrap_quantity": payload.scrap_quantity,
                    "rework_quantity": payload.rework_quantity,
                    "evidence_reference": payload.evidence_reference,
                },
            )
            return response

    def _update_completion_aggregates(self, db: Any, task: dict[str, Any]) -> None:
        remaining_row = db.execute(
            """SELECT COUNT(*) AS remaining FROM operation_tasks
               WHERE tenant_id=? AND site_id=? AND work_order_execution_id=?
                 AND status NOT IN ('completed','closed')""",
            (*self._scope(), int(task["work_order_execution_id"])),
        ).fetchone()
        if int(_row(remaining_row)["remaining"]) != 0:
            return
        completed_at = _now()
        db.execute(
            """UPDATE work_order_execution SET status='completed', completed_at=?
               WHERE tenant_id=? AND site_id=? AND id=?
                 AND status IN ('released','dispatched','in_progress')""",
            (completed_at, *self._scope(), int(task["work_order_execution_id"])),
        )
        execution_row = db.execute(
            """SELECT production_order_id FROM work_order_execution
               WHERE tenant_id=? AND site_id=? AND id=?""",
            (*self._scope(), int(task["work_order_execution_id"])),
        ).fetchone()
        production_order_id = int(_row(execution_row)["production_order_id"])
        aggregate = db.execute(
            """SELECT COUNT(*) AS attached_count,
                      SUM(CASE WHEN execution.status IN ('completed','closed') THEN 1 ELSE 0 END)
                          AS completed_count
               FROM production_order_work_orders link
               LEFT JOIN work_order_execution execution
                 ON execution.work_order_id=link.work_order_id
                AND execution.tenant_id=link.tenant_id AND execution.site_id=link.site_id
               WHERE link.tenant_id=? AND link.site_id=? AND link.production_order_id=?""",
            (*self._scope(), production_order_id),
        ).fetchone()
        counts = _row(aggregate)
        if int(counts["attached_count"] or 0) == int(counts["completed_count"] or 0):
            db.execute(
                """UPDATE production_orders SET status='completed', completed_at=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='in_progress'""",
                (completed_at, *self._scope(), production_order_id),
            )

    def complete_task(self, task_id: int, payload: CompleteTaskIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "operation_task", str(task_id), "complete", payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"running"}, "complete")
            totals_row = db.execute(
                """SELECT COALESCE(SUM(good_quantity + scrap_quantity + rework_quantity), 0)
                          AS accounted_quantity
                   FROM operation_quantity_reports
                   WHERE tenant_id=? AND site_id=? AND operation_task_id=?""",
                (*self._scope(), task_id),
            ).fetchone()
            accounted = float(_row(totals_row)["accounted_quantity"])
            if not _same_quantity(accounted, float(task["planned_quantity"])):
                raise ExecutionError(
                    409,
                    "QUANTITY_NOT_CONSERVED",
                    "operation cannot complete until accepted reports exactly conserve "
                    "planned quantity",
                    planned_quantity=task["planned_quantity"],
                    accounted_quantity=accounted,
                )
            evidence = payload.evidence_reference.strip()
            if not evidence:
                raise ExecutionError(
                    409,
                    "COMPLETION_EVIDENCE_REQUIRED",
                    "operation completion requires a durable evidence reference",
                    task_id=task_id,
                )
            changed = self._change_task_status(
                db,
                task,
                "completed",
                "complete",
                actor,
                payload.idempotency_key,
                evidence_reference=evidence,
                set_completed=True,
            )
            self._update_completion_aggregates(db, changed)
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                "execution:operation-completed",
                "operation_task",
                str(task_id),
                {"accounted_quantity": accounted, "evidence_reference": evidence},
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "complete",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def _format_downtime(self, db: Any, downtime_id: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT * FROM operation_downtime
               WHERE tenant_id=? AND site_id=? AND id=?""",
            (*self._scope(), downtime_id),
        ).fetchone()
        if row is None:
            raise ExecutionError(404, "DOWNTIME_NOT_FOUND", "downtime record was not found")
        return _row(row)

    def start_downtime(self, task_id: int, payload: DowntimeStartIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db,
                "operation_task",
                str(task_id),
                "downtime-start",
                payload.idempotency_key,
                request,
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"running"}, "start downtime")
            identifier = self._insert_id(
                db,
                """INSERT INTO operation_downtime (
                       tenant_id, site_id, operation_task_id, downtime_code, status,
                       reason, start_evidence_reference, started_by, started_at
                   ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    task_id,
                    payload.downtime_code,
                    payload.reason,
                    payload.evidence_reference,
                    actor,
                    _now(),
                ),
                code="DOWNTIME_ALREADY_OPEN",
                message="task already has open downtime or the downtime code already exists",
            )
            self._change_task_status(
                db,
                task,
                "paused",
                "downtime-start",
                actor,
                payload.idempotency_key,
                reason=payload.reason,
                evidence_reference=payload.evidence_reference,
            )
            response = self._format_downtime(db, identifier)
            self._audit(
                db,
                actor,
                "execution:downtime-started",
                "operation_task",
                str(task_id),
                {
                    "downtime_id": identifier,
                    "downtime_code": payload.downtime_code,
                    "reason": payload.reason,
                    "evidence_reference": payload.evidence_reference,
                },
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "downtime-start",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def end_downtime(self, downtime_id: int, payload: DowntimeEndIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db,
                "downtime",
                str(downtime_id),
                "end",
                payload.idempotency_key,
                request,
            )
            if replay is not None:
                return replay
            sql = (
                "SELECT * FROM operation_downtime "
                "WHERE tenant_id=? AND site_id=? AND id=?" + self._lock_suffix()
            )
            row = db.execute(sql, (*self._scope(), downtime_id)).fetchone()
            if row is None:
                raise ExecutionError(404, "DOWNTIME_NOT_FOUND", "downtime record was not found")
            downtime = _row(row)
            if downtime["status"] != "open":
                raise ExecutionError(
                    409,
                    "DOWNTIME_NOT_OPEN",
                    "only open downtime can be ended",
                    downtime_id=downtime_id,
                )
            task_id = int(downtime["operation_task_id"])
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"paused"}, "end downtime")
            self._require_maintenance_readiness(db, task_id)
            updated = db.execute(
                """UPDATE operation_downtime
                   SET status='closed', end_evidence_reference=?, ended_by=?, ended_at=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='open'""",
                (
                    payload.evidence_reference,
                    actor,
                    _now(),
                    *self._scope(),
                    downtime_id,
                ),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise ExecutionError(
                    409,
                    "DOWNTIME_CLOSE_CONFLICT",
                    "downtime changed while it was being closed",
                )
            self._change_task_status(
                db,
                task,
                "running",
                "downtime-end",
                actor,
                payload.idempotency_key,
                evidence_reference=payload.evidence_reference,
            )
            response = self._format_downtime(db, downtime_id)
            self._audit(
                db,
                actor,
                "execution:downtime-ended",
                "operation_task",
                str(task_id),
                {"downtime_id": downtime_id, "evidence_reference": payload.evidence_reference},
            )
            self._idempotent_store(
                db,
                "downtime",
                str(downtime_id),
                "end",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def close_task(self, task_id: int, payload: ExecutionActionIn, actor: str) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "operation_task", str(task_id), "close", payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            task = self._require_task(db, task_id, lock=True)
            self._require_transition(task, {"completed"}, "close")
            self._change_task_status(
                db,
                task,
                "closed",
                "close",
                actor,
                payload.idempotency_key,
                reason=payload.reason,
                set_closed=True,
            )
            response = self._format_task(db, task_id)
            self._audit(
                db,
                actor,
                "execution:operation-closed",
                "operation_task",
                str(task_id),
                {"reason": payload.reason},
            )
            self._idempotent_store(
                db,
                "operation_task",
                str(task_id),
                "close",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def close_work_order(
        self, work_order_code: str, payload: ExecutionActionIn, actor: str
    ) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db, "work_order", work_order_code, "close", payload.idempotency_key, request
            )
            if replay is not None:
                return replay
            work_order = self._require_work_order(db, work_order_code, lock=True)
            execution_row = db.execute(
                """SELECT * FROM work_order_execution
                   WHERE tenant_id=? AND site_id=? AND work_order_id=?"""
                + self._lock_suffix(),
                (*self._scope(), int(work_order["id"])),
            ).fetchone()
            if execution_row is None:
                raise ExecutionError(
                    409,
                    "WORK_ORDER_NOT_COMPLETE",
                    "work order cannot close before execution is completed",
                    work_order_code=work_order_code,
                )
            execution = _row(execution_row)
            if execution["status"] != "completed":
                raise ExecutionError(
                    409,
                    "WORK_ORDER_NOT_COMPLETE",
                    "work order cannot close before every operation is completed",
                    work_order_code=work_order_code,
                    execution_status=execution["status"],
                )
            open_tasks = db.execute(
                """SELECT COUNT(*) AS open_count FROM operation_tasks
                   WHERE tenant_id=? AND site_id=? AND work_order_execution_id=?
                     AND status!='closed'""",
                (*self._scope(), int(execution["id"])),
            ).fetchone()
            if int(_row(open_tasks)["open_count"]) != 0:
                raise ExecutionError(
                    409,
                    "WORK_ORDER_TASKS_NOT_CLOSED",
                    "every completed operation task must be explicitly closed first",
                    work_order_code=work_order_code,
                )
            updated = db.execute(
                """UPDATE work_order_execution
                   SET status='closed', closed_by=?, closed_at=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='completed'""",
                (actor, _now(), *self._scope(), int(execution["id"])),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise ExecutionError(
                    409,
                    "WORK_ORDER_CLOSE_CONFLICT",
                    "work-order execution changed while closing",
                )
            response = self._format_work_order_execution(db, work_order_code)
            self._audit(
                db,
                actor,
                "execution:work-order-closed",
                "work_order",
                work_order_code,
                {"reason": payload.reason},
            )
            self._idempotent_store(
                db,
                "work_order",
                work_order_code,
                "close",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def close_production_order(
        self, production_order_code: str, payload: ExecutionActionIn, actor: str
    ) -> dict[str, Any]:
        request = payload.model_dump(mode="json")
        with get_db() as db:
            replay = self._idempotent_get(
                db,
                "production_order",
                production_order_code,
                "close",
                payload.idempotency_key,
                request,
            )
            if replay is not None:
                return replay
            production_order = self._require_production_order(db, production_order_code, lock=True)
            if production_order["status"] != "completed":
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_NOT_COMPLETE",
                    "production order cannot close before all work orders complete",
                    production_order_code=production_order_code,
                    status=production_order["status"],
                )
            aggregate = db.execute(
                """SELECT COUNT(*) AS attached_count,
                          SUM(CASE WHEN execution.status='closed' THEN 1 ELSE 0 END) AS closed_count
                   FROM production_order_work_orders link
                   LEFT JOIN work_order_execution execution
                     ON execution.work_order_id=link.work_order_id
                    AND execution.tenant_id=link.tenant_id AND execution.site_id=link.site_id
                   WHERE link.tenant_id=? AND link.site_id=? AND link.production_order_id=?""",
                (*self._scope(), int(production_order["id"])),
            ).fetchone()
            counts = _row(aggregate)
            if not counts["attached_count"] or int(counts["attached_count"]) != int(
                counts["closed_count"] or 0
            ):
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_WORK_ORDERS_NOT_CLOSED",
                    "all attached work orders must be explicitly closed",
                    production_order_code=production_order_code,
                )
            updated = db.execute(
                """UPDATE production_orders
                   SET status='closed', closed_by=?, closed_at=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='completed'""",
                (actor, _now(), *self._scope(), int(production_order["id"])),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise ExecutionError(
                    409,
                    "PRODUCTION_ORDER_CLOSE_CONFLICT",
                    "production order changed while closing",
                )
            response = self._format_production_order(db, int(production_order["id"]))
            self._audit(
                db,
                actor,
                "execution:production-order-closed",
                "production_order",
                production_order_code,
                {"reason": payload.reason},
            )
            self._idempotent_store(
                db,
                "production_order",
                production_order_code,
                "close",
                payload.idempotency_key,
                request,
                response,
            )
            return response

    def replay_work_order(self, work_order_code: str) -> dict[str, Any]:
        with get_db() as db:
            execution = self._format_work_order_execution(db, work_order_code)
            execution_id = int(execution["id"])
            task_ids = [int(task["id"]) for task in execution["tasks"]]
            result: dict[str, Any] = {
                "production_order_code": execution["production_order_code"],
                "production_order_status": execution["production_order_status"],
                "work_order_code": work_order_code,
                "execution_status": execution["execution_status"],
                "tasks": execution["tasks"],
            }
            collections = {
                "assignments": (
                    "operation_task_assignments",
                    "assigned_at, id",
                ),
                "setups": ("operation_setups", "started_at, id"),
                "quantity_reports": ("operation_quantity_reports", "occurred_at, id"),
                "downtimes": ("operation_downtime", "started_at, id"),
                "holds": ("operation_holds", "held_at, id"),
                "status_history": ("operation_status_history", "occurred_at, id"),
            }
            if not task_ids:
                for key in collections:
                    result[key] = []
                return result
            placeholders = ",".join("?" for _ in task_ids)
            for key, (table, order_by) in collections.items():
                rows = db.execute(
                    f"""SELECT * FROM {table}
                        WHERE tenant_id=? AND site_id=?
                          AND operation_task_id IN ({placeholders})
                        ORDER BY {order_by}""",
                    (*self._scope(), *task_ids),
                ).fetchall()
                items = [_row(item) for item in rows]
                if key == "setups":
                    for item in items:
                        item["parameters"] = _decode_json(item.pop("parameters_json", "{}"), {})
                result[key] = items
            result["work_order_execution_id"] = execution_id
            return result


execution_repository = ExecutionRepository()
