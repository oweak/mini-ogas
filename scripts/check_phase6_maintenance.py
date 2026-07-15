from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from check_phase1_database import read_env_value
from check_phase3_execution import (
    ApiClient,
    GateFailure,
    _expect_problem,
    _read_env_file,
    _seed_master_data,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CENTRAL_API_ROOT = PROJECT_ROOT / "services" / "central-api"


def _ready_task(client: ApiClient, prefix: str, master: dict[str, Any], suffix: str) -> int:
    work_order = f"{prefix}-WO-{suffix}"
    production_order = f"{prefix}-PO-{suffix}"
    client.post(
        "/master-data/work-orders",
        {
            "work_order_code": work_order,
            "product_code": master["product"],
            "quantity": 2,
            "bom_revision_id": master["bom_revision_id"],
            "routing_revision_id": master["routing_revision_id"],
            "document_revision_ids": [master["document_revision_id"]],
            "calendar_code": master["calendar"],
            "shift_code": master["shift"],
            "operation_assignments": [
                {
                    "sequence": 10,
                    "equipment_code": master["equipment"],
                    "personnel_code": master["personnel"],
                }
            ],
        },
        expected=(201,),
    )
    client.post(f"/master-data/work-orders/{work_order}/release", expected=(200,))
    client.post(
        "/execution/production-orders",
        {
            "production_order_code": production_order,
            "product_code": master["product"],
            "quantity": 2,
            "priority": 5,
            "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
        expected=(201,),
    )
    client.post(
        f"/execution/production-orders/{production_order}/work-orders/{work_order}/attach",
        {"idempotency_key": f"{prefix}-ATTACH-{suffix}"},
        expected=(200,),
    )
    client.post(
        f"/execution/production-orders/{production_order}/release",
        {"idempotency_key": f"{prefix}-RELEASE-{suffix}"},
        expected=(200,),
    )
    dispatched = client.post(
        f"/execution/work-orders/{work_order}/dispatch",
        {"idempotency_key": f"{prefix}-DISPATCH-{suffix}"},
        expected=(200,),
    )
    task_id = int(dispatched["tasks"][0]["id"])
    client.post(
        f"/execution/tasks/{task_id}/setup/start",
        {"idempotency_key": f"{prefix}-SETUP-START-{suffix}"},
        expected=(200,),
    )
    client.post(
        f"/execution/tasks/{task_id}/setup/complete",
        {
            "idempotency_key": f"{prefix}-SETUP-COMPLETE-{suffix}",
            "evidence_reference": f"{prefix}-SETUP-EVIDENCE-{suffix}",
            "parameters": {"fixture_verified": True},
        },
        expected=(200,),
    )
    return task_id


def _seed_authority(client: ApiClient, prefix: str, master: dict[str, Any]) -> dict[str, str]:
    codes = {
        "asset": f"{prefix}-ASSET",
        "checklist": f"{prefix}-CHECK",
        "failure": f"{prefix}-F-BEARING",
        "cause": f"{prefix}-C-LUBE",
        "remedy": f"{prefix}-R-REPLACE",
        "spare": f"{prefix}-SPARE",
        "warehouse": f"{prefix}-MRO-WH",
        "location": f"{prefix}-MRO-LOC",
        "lot": f"{prefix}-SPARE-LOT",
    }
    client.post(
        "/maintenance/assets",
        {
            "asset_code": codes["asset"],
            "equipment_code": master["equipment"],
            "name": "Phase 6 governed machine asset",
            "criticality": "critical",
        },
        expected=(201,),
    )
    for code_type in ("failure", "cause", "remedy"):
        client.post(
            "/maintenance/codes",
            {
                "code": codes[code_type],
                "code_type": code_type,
                "description": f"Phase 6 governed {code_type}",
            },
            expected=(201,),
        )
    client.post(
        "/maintenance/checklists",
        {
            "checklist_code": codes["checklist"],
            "revision": 1,
            "name": "Phase 6 bearing replacement",
            "items": [
                {"sequence": 10, "instruction": "Lockout verified", "required": True},
                {"sequence": 20, "instruction": "Guard restored", "required": True},
            ],
        },
        expected=(201,),
    )
    client.post(
        f"/maintenance/checklists/{codes['checklist']}/revisions/1/approve",
        {"evidence_reference": f"{prefix}-CHECK-APPROVAL"},
        expected=(200,),
    )
    client.post(
        f"/maintenance/checklists/{codes['checklist']}/revisions/1/effective",
        {"evidence_reference": f"{prefix}-CHECK-EFFECTIVE"},
        expected=(200,),
    )
    client.post(
        "/master-data/materials",
        {
            "material_code": codes["spare"],
            "name": "Phase 6 replacement bearing",
            "material_type": "consumable",
            "base_uom_code": master["each_uom"],
        },
        expected=(201,),
    )
    client.post(
        "/material-flow/warehouses",
        {
            "warehouse_code": codes["warehouse"],
            "name": "Phase 6 MRO warehouse",
            "warehouse_type": "raw",
        },
        expected=(201,),
    )
    client.post(
        "/material-flow/locations",
        {
            "location_code": codes["location"],
            "warehouse_code": codes["warehouse"],
            "name": "Phase 6 MRO storage",
            "location_type": "storage",
        },
        expected=(201,),
    )
    client.post(
        "/material-flow/lots",
        {
            "lot_code": codes["lot"],
            "material_code": codes["spare"],
            "tracking_kind": "lot",
            "evidence_reference": f"{prefix}-SPARE-CERT",
        },
        expected=(201,),
    )
    client.post(
        "/material-flow/movements",
        {
            "movement_id": f"{prefix}-SPARE-RECEIPT",
            "movement_type": "receipt",
            "lot_code": codes["lot"],
            "quantity": 5,
            "to_location_code": codes["location"],
            "source": "manual",
            "reason": "Phase 6 gate spare receipt",
            "evidence_reference": f"{prefix}-SPARE-RECEIPT-EVIDENCE",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        expected=(201,),
    )
    return codes


def _request_order(
    client: ApiClient,
    prefix: str,
    codes: dict[str, str],
    suffix: str,
    task_id: int | None = None,
    downtime_id: int | None = None,
) -> str:
    request_code = f"{prefix}-REQ-{suffix}"
    order_code = f"{prefix}-MO-{suffix}"
    client.post(
        "/maintenance/requests",
        {
            "request_code": request_code,
            "asset_code": codes["asset"],
            "source_type": "alarm",
            "source_reference": f"{prefix}-ALARM-{suffix}",
            "description": "Bearing condition requires governed inspection",
            "priority": "high",
            "observed_at": datetime.now(UTC).isoformat(),
        },
        expected=(201,),
    )
    client.post(
        "/maintenance/orders",
        {
            "order_code": order_code,
            "request_code": request_code,
            "asset_code": codes["asset"],
            "order_type": "corrective",
            "priority": "high",
            "assigned_personnel_code": master_personnel(codes),
            "checklist_code": codes["checklist"],
            "checklist_revision": 1,
            "operation_task_id": task_id,
            "operation_downtime_id": downtime_id,
            "production_impact": "equipment_unavailable",
            "planned_start_at": datetime.now(UTC).isoformat(),
            "planned_end_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        },
        expected=(201,),
    )
    client.post(
        f"/maintenance/orders/{order_code}/approve",
        {"evidence_reference": f"{prefix}-APPROVE-{suffix}"},
        expected=(200,),
    )
    return order_code


def master_personnel(codes: dict[str, str]) -> str:
    return codes["personnel"]


def _complete_work(client: ApiClient, prefix: str, codes: dict[str, str], order: str) -> None:
    for sequence in (10, 20):
        client.post(
            f"/maintenance/orders/{order}/checklist-results",
            {
                "item_sequence": sequence,
                "result": "pass",
                "evidence_reference": f"{order}-CHECK-{sequence}",
            },
            expected=(201,),
        )
    client.post(
        f"/maintenance/orders/{order}/work-complete",
        {
            "failure_code": codes["failure"],
            "cause_code": codes["cause"],
            "remedy_code": codes["remedy"],
            "work_evidence_reference": f"{order}-WORK-EVIDENCE",
        },
        expected=(200,),
    )


def _verify_order(verifier: ApiClient, order: str, prefix: str) -> dict[str, Any]:
    return verifier.post(
        f"/maintenance/orders/{order}/verify",
        {
            "verification_reference": f"{order}-INDEPENDENT-VERIFY",
            "verification_result": "restored",
        },
        expected=(200,),
    )


def _verify_postgres(
    dsn: str,
    tenant_id: str,
    site_id: str,
    prefix: str,
    active_order: str,
    active_task_id: int,
    verified_order: str,
) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    sys.path.insert(0, str(CENTRAL_API_ROOT))
    from app.core.phase6_schema import PHASE6_MIGRATIONS, PHASE6_SCOPED_TABLES

    versions = [migration.version for migration in PHASE6_MIGRATIONS]
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        migrations = connection.execute(
            "SELECT version FROM schema_migrations WHERE version=ANY(%s)", (versions,)
        ).fetchall()
        if {item["version"] for item in migrations} != set(versions):
            raise GateFailure("Phase 6 PostgreSQL migration records are incomplete")
        rls_rows = connection.execute(
            """SELECT c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity,
                      COUNT(p.policyname) AS policy_count
               FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               LEFT JOIN pg_policies p ON p.schemaname=n.nspname
                 AND p.tablename=c.relname AND p.policyname='miniogas_scope'
               WHERE n.nspname=current_schema() AND c.relname=ANY(%s)
               GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity""",
            (list(PHASE6_SCOPED_TABLES),),
        ).fetchall()
        valid_rls = {
            item["table_name"]
            for item in rls_rows
            if item["relrowsecurity"]
            and item["relforcerowsecurity"]
            and int(item["policy_count"]) == 1
        }
        if valid_rls != set(PHASE6_SCOPED_TABLES):
            raise GateFailure("Phase 6 forced-RLS policies are incomplete")
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            (tenant_id, site_id),
        )
        order_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM maintenance_orders WHERE order_code LIKE %s",
                (f"{prefix}%",),
            ).fetchone()["count"]
        )
        audit_count = int(
            connection.execute(
                """SELECT COUNT(*) AS count FROM audit_logs
                   WHERE run_id='maintenance' AND resource_id LIKE %s""",
                (f"{prefix}%",),
            ).fetchone()["count"]
        )
        if order_count < 4 or audit_count < 25:
            raise GateFailure("Phase 6 live maintenance facts are incomplete in PostgreSQL")

        check = connection.execute(
            """SELECT result.id FROM maintenance_check_results result
               JOIN maintenance_orders maintenance_order
                 ON maintenance_order.id=result.maintenance_order_id
               WHERE maintenance_order.order_code=%s ORDER BY result.id LIMIT 1""",
            (verified_order,),
        ).fetchone()
        append_only_guard = False
        try:
            connection.execute(
                "UPDATE maintenance_check_results SET result=result WHERE id=%s",
                (check["id"],),
            )
        except psycopg.Error as exc:
            append_only_guard = "append-only" in str(exc)
        if not append_only_guard:
            raise GateFailure("maintenance checklist evidence rewrite was accepted")

        independent_guard = False
        try:
            connection.execute(
                """UPDATE maintenance_orders
                   SET status='verified', verification_result='restored',
                       verification_reference='DIRECT-SAME-ACTOR-BYPASS',
                       verified_by=completed_by, verified_at=now()
                   WHERE order_code=%s""",
                (active_order,),
            )
        except psycopg.Error as exc:
            independent_guard = "independent evidence" in str(exc)
        if not independent_guard:
            raise GateFailure("database accepted non-independent maintenance verification")

        verified_evidence_guard = False
        try:
            connection.execute(
                """UPDATE maintenance_orders SET verified_by=completed_by
                   WHERE order_code=%s""",
                (verified_order,),
            )
        except psycopg.Error as exc:
            verified_evidence_guard = "lifecycle or evidence is immutable" in str(exc)
        if not verified_evidence_guard:
            raise GateFailure("database accepted a rewrite of verified maintenance evidence")

        task_interlock = False
        try:
            connection.execute(
                "UPDATE operation_tasks SET status='running' WHERE id=%s",
                (active_task_id,),
            )
        except psycopg.Error as exc:
            task_interlock = "active maintenance" in str(exc)
        if not task_interlock:
            raise GateFailure("database bypassed active-maintenance task interlock")

        receipt = connection.execute(
            """SELECT movement.* FROM inventory_movements movement
               WHERE movement.movement_id=%s""",
            (f"{prefix}-SPARE-RECEIPT",),
        ).fetchone()
        consume_authority_guard = False
        try:
            connection.execute(
                """INSERT INTO inventory_movements (
                       tenant_id, site_id, movement_id, movement_type, material_id,
                       lot_id, uom_id, quantity, from_location_id, to_location_id,
                       from_container_id, to_container_id, operation_task_id,
                       maintenance_order_id, transformation_id, reconciliation_case_id,
                       source, reason, evidence_reference, request_hash, occurred_at, recorded_by
                   ) VALUES (
                       %s, %s, %s, 'consume', %s, %s, %s, 0.1, %s, NULL,
                       NULL, NULL, NULL, NULL, NULL, NULL, 'manual', %s, %s, %s, now(), %s
                   )""",
                (
                    tenant_id,
                    site_id,
                    f"{prefix}-UNBOUND-CONSUME",
                    receipt["material_id"],
                    receipt["lot_id"],
                    receipt["uom_id"],
                    receipt["to_location_id"],
                    "unbound consume bypass probe",
                    f"{prefix}-UNBOUND-EVIDENCE",
                    f"{prefix}-UNBOUND-HASH",
                    "phase6-gate",
                ),
            )
        except psycopg.Error as exc:
            consume_authority_guard = (
                "requires exactly one operation or maintenance authority" in str(exc)
            )
        if not consume_authority_guard:
            raise GateFailure("database accepted an unbound consume movement")

        operator_verify_permissions = int(
            connection.execute(
                """SELECT COUNT(*) AS count FROM role_permissions
                   WHERE role_name='operator' AND permission_name='maintenance:verify'"""
            ).fetchone()["count"]
        )
        if operator_verify_permissions:
            raise GateFailure("operator role unexpectedly owns maintenance verification")

        active = connection.execute(
            "SELECT status FROM maintenance_orders WHERE order_code=%s", (active_order,)
        ).fetchone()
        if active is None or active["status"] != "work_completed":
            raise GateFailure("maintenance probe order is not awaiting independent verification")
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            ("tenant-phase6-negative", "site-phase6-negative"),
        )
        cross_scope = sum(
            int(connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
            for table in PHASE6_SCOPED_TABLES
        )
        if cross_scope:
            raise GateFailure("Phase 6 cross-scope query returned maintenance facts")
    return {
        "migrations": versions,
        "forced_rls_tables": len(valid_rls),
        "maintenance_orders": order_count,
        "maintenance_audit_records": audit_count,
        "append_only_guard": append_only_guard,
        "independent_verification_guard": independent_guard,
        "verified_evidence_guard": verified_evidence_guard,
        "task_interlock": task_interlock,
        "consume_authority_guard": consume_authority_guard,
        "operator_verify_permissions": operator_verify_permissions,
        "cross_scope_rows": cross_scope,
    }


def run_gate(
    api_url: str,
    runtime_root: Path,
    tenant_id: str,
    site_id: str,
) -> dict[str, Any]:
    auth = _read_env_file(runtime_root / "auth.env")
    password = auth.get("AUTH_BOOTSTRAP_PASSWORD", "")
    jwt_secret = auth.get("JWT_SECRET", "")
    dsn = read_env_value(runtime_root / "postgres.env", "POSTGRES_DSN")
    if not password or not jwt_secret or not dsn:
        raise GateFailure("runtime authentication or PostgreSQL configuration is missing")
    client = ApiClient(api_url)
    login = client.post("/auth/login", {"operator": "admin", "password": password}, expected=(200,))
    client.token = str(login.get("access_token") or "")
    if not client.token:
        raise GateFailure("administrator login did not return a bearer token")

    os.environ["JWT_SECRET"] = jwt_secret
    sys.path.insert(0, str(CENTRAL_API_ROOT))
    from app.core.auth import issue_access_token

    verifier = ApiClient(api_url)
    verifier.token = issue_access_token(
        {
            "username": "phase6-independent-verifier",
            "display_name": "Phase 6 Independent Verifier",
            "roles": ["maintenance_verifier"],
            "permissions": ["maintenance:verify"],
        }
    )

    prefix = f"P6G{datetime.now(UTC):%m%d%H%M%S}{uuid4().hex[:4].upper()}"
    master = _seed_master_data(client, prefix)
    codes = _seed_authority(client, prefix, master)
    codes["personnel"] = str(master["personnel"])

    task_id = _ready_task(client, prefix, master, "VERIFY")
    order = _request_order(client, prefix, codes, "VERIFY", task_id)
    client.post(
        f"/maintenance/orders/{order}/start",
        {"evidence_reference": f"{prefix}-MAINT-START"},
        expected=(200,),
    )
    _expect_problem(
        client,
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": f"{prefix}-BLOCKED-BY-MAINTENANCE"},
        "ACTIVE_MAINTENANCE_BLOCKS_TASK",
    )
    _expect_problem(
        client,
        f"/maintenance/orders/{order}/work-complete",
        {
            "failure_code": codes["failure"],
            "cause_code": codes["cause"],
            "remedy_code": codes["remedy"],
            "work_evidence_reference": f"{prefix}-INCOMPLETE-WORK",
        },
        "CHECKLIST_INCOMPLETE",
    )
    _complete_work(client, prefix, codes, order)
    verified = _verify_order(verifier, order, prefix)
    started = client.post(
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": f"{prefix}-START-AFTER-VERIFY"},
        expected=(200,),
    )

    downtime = client.post(
        f"/execution/tasks/{task_id}/downtime",
        {
            "downtime_code": f"{prefix}-DOWN-001",
            "idempotency_key": f"{prefix}-DOWN-OPEN",
            "reason": "Phase 6 bearing replacement",
            "evidence_reference": f"{prefix}-DOWN-EVIDENCE",
        },
        expected=(201,),
    )
    downtime_order = _request_order(client, prefix, codes, "DOWN", task_id, int(downtime["id"]))
    client.post(
        f"/maintenance/orders/{downtime_order}/start",
        {"evidence_reference": f"{prefix}-DOWN-MAINT-START"},
        expected=(200,),
    )
    movement = client.post(
        "/material-flow/movements",
        {
            "movement_id": f"{prefix}-SPARE-CONSUME",
            "movement_type": "consume",
            "lot_code": codes["lot"],
            "quantity": 1,
            "from_location_code": codes["location"],
            "maintenance_order_code": downtime_order,
            "source": "manual",
            "reason": "Phase 6 governed spare use",
            "evidence_reference": f"{prefix}-SPARE-CONSUME-EVIDENCE",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        expected=(201,),
    )
    client.post(
        f"/maintenance/orders/{downtime_order}/spares",
        {
            "usage_id": f"{prefix}-SPARE-USE",
            "movement_id": movement["movement_id"],
            "evidence_reference": f"{prefix}-SPARE-LINK",
        },
        expected=(201,),
    )
    _complete_work(client, prefix, codes, downtime_order)
    _verify_order(verifier, downtime_order, prefix)
    closed_downtime = client.post(
        f"/execution/downtime/{downtime['id']}/end",
        {
            "idempotency_key": f"{prefix}-DOWN-CLOSE",
            "evidence_reference": f"{prefix}-DOWN-CLOSE-EVIDENCE",
        },
        expected=(200,),
    )

    tool_task = _ready_task(client, prefix, master, "TOOL")
    tool_code = f"{prefix}-TOOL"
    client.post(
        "/maintenance/tools",
        {
            "tool_code": tool_code,
            "asset_code": codes["asset"],
            "name": "Phase 6 turning insert",
            "tool_type": "turning_insert",
            "life_limit": 100,
            "life_used": 90,
            "life_uom": "cycles",
            "calibration_required": True,
            "calibration_due_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
        expected=(201,),
    )
    client.post(
        f"/maintenance/tools/{tool_code}/assignments",
        {
            "operation_task_id": tool_task,
            "evidence_reference": f"{prefix}-TOOL-ASSIGN",
        },
        expected=(201,),
    )
    tool_event = client.post(
        f"/maintenance/tools/{tool_code}/life-events",
        {
            "event_id": f"{prefix}-TOOL-LIFE",
            "usage_delta": 15,
            "operation_task_id": tool_task,
            "occurred_at": datetime.now(UTC).isoformat(),
            "evidence_reference": f"{prefix}-TOOL-COUNTER",
        },
        expected=(201,),
    )
    _expect_problem(
        client,
        f"/execution/tasks/{tool_task}/start",
        {"idempotency_key": f"{prefix}-TOOL-BLOCK"},
        "TOOL_LIFE_EXCEEDED",
    )

    plan_code = f"{prefix}-PM-PLAN"
    client.post(
        "/maintenance/preventive-plans",
        {
            "plan_code": plan_code,
            "asset_code": codes["asset"],
            "checklist_code": codes["checklist"],
            "checklist_revision": 1,
            "interval_hours": 168,
            "next_due_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "production_impact": "equipment_unavailable",
        },
        expected=(201,),
    )
    client.post(
        f"/maintenance/preventive-plans/{plan_code}/effective",
        {"evidence_reference": f"{prefix}-PM-EFFECTIVE"},
        expected=(200,),
    )
    preventive = client.post(
        f"/maintenance/preventive-plans/{plan_code}/generate",
        {
            "request_code": f"{prefix}-PM-REQ",
            "order_code": f"{prefix}-PM-MO",
            "assigned_personnel_code": master["personnel"],
            "planned_start_at": datetime.now(UTC).isoformat(),
            "planned_end_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
        expected=(200,),
    )

    guard_task = _ready_task(client, prefix, master, "DB-GUARD")
    guard_order = _request_order(client, prefix, codes, "DB-GUARD", guard_task)
    client.post(
        f"/maintenance/orders/{guard_order}/start",
        {"evidence_reference": f"{prefix}-DB-GUARD-START"},
        expected=(200,),
    )
    _complete_work(client, prefix, codes, guard_order)
    database = _verify_postgres(
        dsn,
        tenant_id,
        site_id,
        prefix,
        guard_order,
        guard_task,
        order,
    )
    _verify_order(verifier, guard_order, prefix)
    return {
        "status": "PASS",
        "validation_prefix": prefix,
        "verified_order_status": verified["status"],
        "task_status_after_verification": started["status"],
        "downtime_status": closed_downtime["status"],
        "spare_movement_authority": movement["maintenance_order_code"],
        "tool_status": tool_event["tool_status"],
        "preventive_order_status": preventive["order"]["status"],
        "database": database,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Phase 6 maintenance gate")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--runtime-root", type=Path, default=Path(r"D:\MiniOGAS-VMs"))
    parser.add_argument("--tenant-id", default="tenant-local")
    parser.add_argument("--site-id", default="site-digital-twin")
    args = parser.parse_args()
    try:
        result = run_gate(args.api_url, args.runtime_root, args.tenant_id, args.site_id)
    except GateFailure as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
