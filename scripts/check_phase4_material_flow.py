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


def _movement(
    client: ApiClient,
    *,
    movement_id: str,
    movement_type: str,
    lot_code: str,
    quantity: float,
    occurred_at: str,
    from_location: str | None = None,
    to_location: str | None = None,
    from_container: str | None = None,
    to_container: str | None = None,
    operation_task_id: int | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    return {
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
        "reason": "Phase 4 live PostgreSQL gate",
        "evidence_reference": f"{movement_id}-EVIDENCE",
        "occurred_at": occurred_at,
    }


def _balance_quantity(client: ApiClient, lot_code: str) -> float:
    rows = client.get(f"/material-flow/lots/{lot_code}/balances")
    if not isinstance(rows, list):
        raise GateFailure(f"balance response for {lot_code} is not a list")
    return sum(float(item["quantity"]) for item in rows)


def _create_running_task(
    client: ApiClient, prefix: str, master: dict[str, Any]
) -> tuple[str, str, int]:
    work_order = f"{prefix}-WO"
    production_order = f"{prefix}-PO"
    client.post(
        "/master-data/work-orders",
        {
            "work_order_code": work_order,
            "product_code": master["product"],
            "quantity": 4,
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
            "quantity": 4,
            "priority": 4,
            "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
        expected=(201,),
    )
    client.post(
        f"/execution/production-orders/{production_order}/work-orders/{work_order}/attach",
        {"idempotency_key": f"{prefix}-ATTACH"},
    )
    client.post(
        f"/execution/production-orders/{production_order}/release",
        {"idempotency_key": f"{prefix}-RELEASE", "reason": "Phase 4 live gate"},
    )
    dispatch = client.post(
        f"/execution/work-orders/{work_order}/dispatch",
        {"idempotency_key": f"{prefix}-DISPATCH"},
    )
    task_id = int(dispatch["tasks"][0]["id"])
    client.post(
        f"/execution/tasks/{task_id}/setup/start",
        {"idempotency_key": f"{prefix}-SETUP-START"},
    )
    client.post(
        f"/execution/tasks/{task_id}/setup/complete",
        {
            "idempotency_key": f"{prefix}-SETUP-COMPLETE",
            "evidence_reference": f"{prefix}-SETUP-EVIDENCE",
            "parameters": {"fixture_verified": True},
        },
    )
    client.post(
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": f"{prefix}-START"},
    )
    return work_order, production_order, task_id


def _seed_material_authority(
    client: ApiClient, prefix: str, master: dict[str, Any]
) -> dict[str, str]:
    codes = {
        "raw_warehouse": f"{prefix}-RAWW",
        "wip_warehouse": f"{prefix}-WIPW",
        "raw_location": f"{prefix}-RAWL",
        "wip_location": f"{prefix}-WIPL",
        "raw_container": f"{prefix}-RAWC",
        "wip_container": f"{prefix}-WIPC",
        "raw_lot": f"{prefix}-RAWLOT",
        "product_lot": f"{prefix}-PRODLOT",
        "split_a": f"{prefix}-SPLITA",
        "split_b": f"{prefix}-SPLITB",
        "serial": f"{prefix}-SER001",
    }
    client.post(
        "/material-flow/warehouses",
        {
            "warehouse_code": codes["raw_warehouse"],
            "name": "Phase 4 raw warehouse",
            "warehouse_type": "raw",
        },
        expected=(201,),
    )
    client.post(
        "/material-flow/warehouses",
        {
            "warehouse_code": codes["wip_warehouse"],
            "name": "Phase 4 WIP warehouse",
            "warehouse_type": "wip",
        },
        expected=(201,),
    )
    for key, warehouse, location_type in (
        ("raw_location", "raw_warehouse", "storage"),
        ("wip_location", "wip_warehouse", "wip"),
    ):
        client.post(
            "/material-flow/locations",
            {
                "location_code": codes[key],
                "warehouse_code": codes[warehouse],
                "name": f"Phase 4 {location_type} location",
                "location_type": location_type,
            },
            expected=(201,),
        )
    for key, location in (
        ("raw_container", "raw_location"),
        ("wip_container", "wip_location"),
    ):
        client.post(
            "/material-flow/containers",
            {
                "container_code": codes[key],
                "container_type": "validation-tote",
                "location_code": codes[location],
            },
            expected=(201,),
        )
    for key, material, tracking_kind in (
        ("raw_lot", master["raw_material"], "lot"),
        ("product_lot", master["product"], "lot"),
        ("split_a", master["product"], "lot"),
        ("split_b", master["product"], "lot"),
        ("serial", master["product"], "serial"),
    ):
        client.post(
            "/material-flow/lots",
            {
                "lot_code": codes[key],
                "material_code": material,
                "tracking_kind": tracking_kind,
                "evidence_reference": f"{codes[key]}-CERT",
            },
            expected=(201,),
        )
    return codes


def _verify_postgres(
    dsn: str,
    tenant_id: str,
    site_id: str,
    prefix: str,
    codes: dict[str, str],
) -> dict[str, Any]:
    os.environ.update(
        {
            "TENANT_ID": tenant_id,
            "SITE_ID": site_id,
            "PERSIST_BACKEND": "postgres",
            "POSTGRES_DSN": dsn,
        }
    )
    sys.path.insert(0, str(CENTRAL_API_ROOT))
    import psycopg
    from app.core.phase4_schema import PHASE4_MIGRATIONS, PHASE4_SCOPED_TABLES
    from psycopg.rows import dict_row

    migration_versions = [item.version for item in PHASE4_MIGRATIONS]
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        migrations = connection.execute(
            "SELECT version FROM schema_migrations WHERE version = ANY(%s)",
            (migration_versions,),
        ).fetchall()
        if {item["version"] for item in migrations} != set(migration_versions):
            raise GateFailure("Phase 4 PostgreSQL migration records are incomplete")
        rls_rows = connection.execute(
            """SELECT c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity,
                      COUNT(p.policyname) AS policy_count
               FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               LEFT JOIN pg_policies p ON p.schemaname=n.nspname
                 AND p.tablename=c.relname AND p.policyname='miniogas_scope'
               WHERE n.nspname=current_schema() AND c.relname=ANY(%s)
               GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity""",
            (list(PHASE4_SCOPED_TABLES),),
        ).fetchall()
        valid_rls = {
            item["table_name"]
            for item in rls_rows
            if item["relrowsecurity"]
            and item["relforcerowsecurity"]
            and int(item["policy_count"]) == 1
        }
        if valid_rls != set(PHASE4_SCOPED_TABLES):
            raise GateFailure("Phase 4 forced-RLS policies are incomplete")
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            (tenant_id, site_id),
        )
        lot_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM material_lots WHERE lot_code LIKE %s",
                (f"{prefix}%",),
            ).fetchone()["count"]
        )
        movement = connection.execute(
            "SELECT id FROM inventory_movements WHERE movement_id LIKE %s ORDER BY id LIMIT 1",
            (f"{prefix}%",),
        ).fetchone()
        if lot_count < 5 or movement is None:
            raise GateFailure("Phase 4 live facts were not persisted in PostgreSQL")
        append_only_guard = False
        try:
            connection.execute(
                "UPDATE inventory_movements SET reason='tamper' WHERE id=%s",
                (movement["id"],),
            )
        except psycopg.Error:
            append_only_guard = True
        if not append_only_guard:
            raise GateFailure("inventory movement append-only guard did not reject rewrite")
        balance = connection.execute(
            """SELECT balance.id FROM inventory_balances balance
               JOIN material_lots lot ON lot.id=balance.lot_id
               WHERE lot.lot_code=%s AND balance.quantity>0 LIMIT 1""",
            (codes["split_b"],),
        ).fetchone()
        negative_guard = False
        try:
            connection.execute(
                "UPDATE inventory_balances SET quantity=-1 WHERE id=%s",
                (balance["id"],),
            )
        except psycopg.Error:
            negative_guard = True
        if not negative_guard:
            raise GateFailure("database accepted a negative inventory balance")
        serial = connection.execute(
            """SELECT lot.id, lot.material_id, lot.uom_id FROM material_lots lot
               WHERE lot.lot_code=%s""",
            (codes["serial"],),
        ).fetchone()
        wip_location = connection.execute(
            "SELECT id FROM inventory_locations WHERE location_code=%s",
            (codes["wip_location"],),
        ).fetchone()
        serial_guard = False
        try:
            connection.execute(
                """INSERT INTO inventory_balances (
                       tenant_id, site_id, material_id, lot_id, uom_id,
                       location_id, container_key, quantity
                   ) VALUES (%s, %s, %s, %s, %s, %s, '', 1)""",
                (
                    tenant_id,
                    site_id,
                    serial["material_id"],
                    serial["id"],
                    serial["uom_id"],
                    wip_location["id"],
                ),
            )
        except psycopg.Error:
            serial_guard = True
        if not serial_guard:
            raise GateFailure("database accepted duplicate inventory for one serial identity")
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            ("tenant-phase4-negative", "site-phase4-negative"),
        )
        cross_scope = int(
            connection.execute("SELECT COUNT(*) AS count FROM material_lots").fetchone()[
                "count"
            ]
        )
        if cross_scope != 0:
            raise GateFailure("Phase 4 cross-scope query returned material facts")
    return {
        "migrations": migration_versions,
        "forced_rls_tables": len(valid_rls),
        "persisted_lots": lot_count,
        "append_only_guard": append_only_guard,
        "negative_balance_guard": negative_guard,
        "serial_global_guard": serial_guard,
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
    dsn = read_env_value(runtime_root / "postgres.env", "POSTGRES_DSN")
    if not password or not dsn:
        raise GateFailure("runtime auth or PostgreSQL configuration is missing")
    client = ApiClient(api_url)
    login = client.post(
        "/auth/login", {"operator": "admin", "password": password}, expected=(200,)
    )
    client.token = str(login.get("access_token") or "")
    if not client.token:
        raise GateFailure("administrator login did not return a bearer token")
    prefix = f"P4G{datetime.now(UTC):%m%d%H%M%S}{uuid4().hex[:4].upper()}"
    master = _seed_master_data(client, prefix)
    work_order, production_order, task_id = _create_running_task(client, prefix, master)
    codes = _seed_material_authority(client, prefix, master)
    occurred_at = datetime.now(UTC).isoformat()
    receipt = _movement(
        client,
        movement_id=f"{prefix}-RECEIPT",
        movement_type="receipt",
        lot_code=codes["raw_lot"],
        quantity=10,
        occurred_at=occurred_at,
        to_location=codes["raw_location"],
        to_container=codes["raw_container"],
    )
    first_receipt = client.post("/material-flow/movements", receipt, expected=(201,))
    repeated_receipt = client.post("/material-flow/movements", receipt, expected=(201,))
    if first_receipt["id"] != repeated_receipt["id"]:
        raise GateFailure("movement retry created duplicate inventory")
    for (
        suffix,
        movement_type,
        quantity,
        source_location,
        target_location,
        source_container,
        target_container,
    ) in (
        (
            "ISSUE",
            "issue",
            10,
            codes["raw_location"],
            codes["wip_location"],
            codes["raw_container"],
            codes["wip_container"],
        ),
        (
            "RETURN",
            "return",
            1,
            codes["wip_location"],
            codes["raw_location"],
            codes["wip_container"],
            codes["raw_container"],
        ),
        (
            "REISSUE",
            "issue",
            1,
            codes["raw_location"],
            codes["wip_location"],
            codes["raw_container"],
            codes["wip_container"],
        ),
    ):
        client.post(
            "/material-flow/movements",
            _movement(
                client,
                movement_id=f"{prefix}-{suffix}",
                movement_type=movement_type,
                lot_code=codes["raw_lot"],
                quantity=quantity,
                occurred_at=occurred_at,
                from_location=source_location,
                to_location=target_location,
                from_container=source_container,
                to_container=target_container,
            ),
            expected=(201,),
        )
    client.post(
        "/material-flow/movements",
        _movement(
            client,
            movement_id=f"{prefix}-CONSUME",
            movement_type="consume",
            lot_code=codes["raw_lot"],
            quantity=10,
            occurred_at=occurred_at,
            from_location=codes["wip_location"],
            from_container=codes["wip_container"],
            operation_task_id=task_id,
            source="execution",
        ),
        expected=(201,),
    )
    premature_produce = _movement(
        client,
        movement_id=f"{prefix}-PREMATURE-PRODUCE",
        movement_type="produce",
        lot_code=codes["product_lot"],
        quantity=4,
        occurred_at=occurred_at,
        to_location=codes["wip_location"],
        operation_task_id=task_id,
        source="execution",
    )
    _expect_problem(
        client,
        "/material-flow/movements",
        premature_produce,
        "EXECUTION_STATE_INCOMPATIBLE",
    )
    client.post(
        f"/execution/tasks/{task_id}/quantity-reports",
        {
            "report_id": f"{prefix}-REPORT",
            "good_quantity": 4,
            "scrap_quantity": 0,
            "rework_quantity": 0,
            "evidence_reference": f"{prefix}-COUNTER",
            "occurred_at": occurred_at,
        },
        expected=(201,),
    )
    client.post(
        f"/execution/tasks/{task_id}/complete",
        {
            "idempotency_key": f"{prefix}-COMPLETE",
            "evidence_reference": f"{prefix}-INSPECTION",
        },
    )
    client.post(
        "/material-flow/movements",
        _movement(
            client,
            movement_id=f"{prefix}-PRODUCE",
            movement_type="produce",
            lot_code=codes["product_lot"],
            quantity=4,
            occurred_at=occurred_at,
            to_location=codes["wip_location"],
            operation_task_id=task_id,
            source="execution",
        ),
        expected=(201,),
    )
    split = {
        "transformation_id": f"{prefix}-SPLIT",
        "transformation_type": "split",
        "inputs": [
            {
                "lot_code": codes["product_lot"],
                "quantity": 4,
                "location_code": codes["wip_location"],
            }
        ],
        "outputs": [
            {
                "lot_code": codes["split_a"],
                "quantity": 1,
                "location_code": codes["wip_location"],
            },
            {
                "lot_code": codes["split_b"],
                "quantity": 3,
                "location_code": codes["wip_location"],
            },
        ],
        "reason": "Phase 4 governed lot split",
        "evidence_reference": f"{prefix}-SPLIT-EVIDENCE",
        "occurred_at": occurred_at,
    }
    first_split = client.post("/material-flow/transformations", split, expected=(201,))
    repeated_split = client.post("/material-flow/transformations", split, expected=(201,))
    if first_split["id"] != repeated_split["id"]:
        raise GateFailure("transformation retry created duplicate genealogy")
    forward = client.get(f"/material-flow/genealogy/{codes['product_lot']}")
    reverse = client.get(f"/material-flow/genealogy/{codes['split_a']}")
    descendants = {item["lot_code"] for item in forward["descendants"]}
    ancestors = {item["lot_code"] for item in reverse["ancestors"]}
    if descendants != {codes["split_a"], codes["split_b"]}:
        raise GateFailure("forward genealogy is incomplete")
    if ancestors != {codes["product_lot"]}:
        raise GateFailure("reverse genealogy is incomplete")
    serial_invalid = _movement(
        client,
        movement_id=f"{prefix}-SERIAL-BAD",
        movement_type="receipt",
        lot_code=codes["serial"],
        quantity=2,
        occurred_at=occurred_at,
        to_location=codes["raw_location"],
    )
    _expect_problem(
        client,
        "/material-flow/movements",
        serial_invalid,
        "SERIAL_QUANTITY_INVALID",
    )
    client.post(
        "/material-flow/movements",
        _movement(
            client,
            movement_id=f"{prefix}-SERIAL-OK",
            movement_type="receipt",
            lot_code=codes["serial"],
            quantity=1,
            occurred_at=occurred_at,
            to_location=codes["raw_location"],
        ),
        expected=(201,),
    )
    _expect_problem(
        client,
        "/material-flow/movements",
        _movement(
            client,
            movement_id=f"{prefix}-NEGATIVE",
            movement_type="transfer",
            lot_code=codes["split_a"],
            quantity=2,
            occurred_at=occurred_at,
            from_location=codes["wip_location"],
            to_location=codes["raw_location"],
        ),
        "NEGATIVE_INVENTORY",
    )
    snapshot = {
        "import_id": f"{prefix}-WMS",
        "provider": "wms_simulator",
        "contract_version": "1.0",
        "observed_at": occurred_at,
        "evidence_reference": f"{prefix}-WMS-EVIDENCE",
        "items": [
            {
                "lot_code": codes["split_b"],
                "location_code": codes["wip_location"],
                "container_code": None,
                "observed_quantity": 2,
            }
        ],
    }
    imported = client.post("/material-flow/external-snapshots", snapshot, expected=(201,))
    repeated_import = client.post(
        "/material-flow/external-snapshots", snapshot, expected=(201,)
    )
    if imported["id"] != repeated_import["id"]:
        raise GateFailure("external snapshot retry created a duplicate import")
    if _balance_quantity(client, codes["split_b"]) != 3:
        raise GateFailure("external snapshot silently overwrote authoritative inventory")
    cases = imported["reconciliation_cases"]
    if len(cases) != 1 or cases[0]["status"] != "open":
        raise GateFailure("external discrepancy did not create one open reconciliation case")
    adjusted = client.post(
        f"/material-flow/reconciliations/{cases[0]['id']}/adjust",
        {
            "movement_id": f"{prefix}-ADJUST",
            "reason": "approved Phase 4 cycle-count correction",
            "evidence_reference": f"{prefix}-ADJUST-APPROVAL",
        },
    )
    if adjusted["status"] != "adjusted" or _balance_quantity(
        client, codes["split_b"]
    ) != 2:
        raise GateFailure("approved reconciliation did not produce the expected adjustment")
    client.post(
        f"/execution/tasks/{task_id}/close",
        {"idempotency_key": f"{prefix}-TASK-CLOSE"},
    )
    client.post(
        f"/execution/work-orders/{work_order}/close",
        {"idempotency_key": f"{prefix}-WO-CLOSE"},
    )
    client.post(
        f"/execution/production-orders/{production_order}/close",
        {"idempotency_key": f"{prefix}-PO-CLOSE"},
    )
    database = _verify_postgres(dsn, tenant_id, site_id, prefix, codes)
    return {
        "status": "PASS",
        "validation_prefix": prefix,
        "task_id": task_id,
        "movement_retry_id": first_receipt["id"],
        "transformation_retry_id": first_split["id"],
        "forward_descendants": sorted(descendants),
        "reverse_ancestors": sorted(ancestors),
        "reconciliation_status": adjusted["status"],
        "reconciled_quantity": _balance_quantity(client, codes["split_b"]),
        "database": database,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Phase 4 material-flow gate")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--runtime-root", type=Path, default=Path(r"D:\MiniOGAS-VMs"))
    parser.add_argument("--tenant-id", default="tenant-local")
    parser.add_argument("--site-id", default="site-digital-twin")
    args = parser.parse_args()
    try:
        result = run_gate(
            args.api_url, args.runtime_root, args.tenant_id, args.site_id
        )
    except GateFailure as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
