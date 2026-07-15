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
    movement_id: str,
    lot_code: str,
    quantity: float,
    occurred_at: str,
    *,
    movement_type: str = "receipt",
    from_location: str | None = None,
    to_location: str | None = None,
) -> dict[str, Any]:
    return {
        "movement_id": movement_id,
        "movement_type": movement_type,
        "lot_code": lot_code,
        "quantity": quantity,
        "from_location_code": from_location,
        "to_location_code": to_location,
        "source": "manual",
        "reason": "Phase 5 live PostgreSQL quality gate",
        "evidence_reference": f"{movement_id}-EVIDENCE",
        "occurred_at": occurred_at,
    }


def _seed_quality_authority(
    client: ApiClient,
    prefix: str,
    master: dict[str, Any],
    now: datetime,
) -> dict[str, str]:
    codes = {
        "millimetre": f"{prefix}-MM",
        "raw_warehouse": f"{prefix}-RAWW",
        "wip_warehouse": f"{prefix}-WIPW",
        "raw_location": f"{prefix}-RAWL",
        "wip_location": f"{prefix}-WIPL",
        "release_lot": f"{prefix}-RELEASELOT",
        "held_lot": f"{prefix}-HELDLOT",
        "gauge": f"{prefix}-GAUGE",
        "plan": f"{prefix}-PLAN",
        "characteristic": f"{prefix}-DIAMETER",
        "skill": f"{prefix}-SKILL",
        "release_inspection": f"{prefix}-RELEASE-INSP",
        "held_inspection": f"{prefix}-HELD-INSP",
    }
    client.post(
        "/master-data/uoms",
        {
            "uom_code": codes["millimetre"],
            "name": "Millimetre",
            "dimension": "length",
            "scale": 1,
        },
        expected=(201,),
    )
    for key, name, warehouse_type in (
        ("raw_warehouse", "Quality hold warehouse", "raw"),
        ("wip_warehouse", "Quality released warehouse", "wip"),
    ):
        client.post(
            "/material-flow/warehouses",
            {
                "warehouse_code": codes[key],
                "name": name,
                "warehouse_type": warehouse_type,
            },
            expected=(201,),
        )
    for key, warehouse_key, location_type in (
        ("raw_location", "raw_warehouse", "storage"),
        ("wip_location", "wip_warehouse", "wip"),
    ):
        client.post(
            "/material-flow/locations",
            {
                "location_code": codes[key],
                "warehouse_code": codes[warehouse_key],
                "name": codes[key],
                "location_type": location_type,
            },
            expected=(201,),
        )
    occurred_at = now.isoformat()
    for lot_key in ("release_lot", "held_lot"):
        client.post(
            "/material-flow/lots",
            {
                "lot_code": codes[lot_key],
                "material_code": master["product"],
                "tracking_kind": "lot",
                "evidence_reference": f"{codes[lot_key]}-CERT",
            },
            expected=(201,),
        )
        client.post(
            "/material-flow/movements",
            _movement(
                f"{prefix}-{lot_key.upper()}-RECEIPT",
                codes[lot_key],
                5,
                occurred_at,
                to_location=codes["raw_location"],
            ),
            expected=(201,),
        )
    client.post(
        "/quality/gauges",
        {
            "gauge_code": codes["gauge"],
            "name": "Phase 5 calibrated micrometer",
            "gauge_type": "micrometer",
            "calibration_status": "valid",
            "valid_from": (now - timedelta(days=1)).isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "evidence_reference": f"{prefix}-GAUGE-CERT",
        },
        expected=(201,),
    )
    client.post(
        "/quality/inspection-plans",
        {
            "plan_code": codes["plan"],
            "revision": 1,
            "name": "Phase 5 governed final inspection",
            "material_code": master["product"],
            "stage": "final",
            "characteristics": [
                {
                    "characteristic_code": codes["characteristic"],
                    "name": "Outside diameter",
                    "value_type": "numeric",
                    "uom_code": codes["millimetre"],
                    "target_value": 10,
                    "lower_spec_limit": 9.9,
                    "upper_spec_limit": 10.1,
                    "method": "digital-micrometer",
                    "sample_size": 2,
                    "gauge_type": "micrometer",
                    "required_skill_code": codes["skill"],
                    "required_skill_level": 2,
                }
            ],
        },
        expected=(201,),
    )
    client.post(
        f"/quality/inspection-plans/{codes['plan']}/revisions/1/approve",
        {"evidence_reference": f"{prefix}-PLAN-APPROVAL"},
        expected=(200,),
    )
    client.post(
        f"/quality/inspection-plans/{codes['plan']}/revisions/1/effective",
        {"evidence_reference": f"{prefix}-PLAN-EFFECTIVITY"},
        expected=(200,),
    )
    for lot_key, inspection_key in (
        ("release_lot", "release_inspection"),
        ("held_lot", "held_inspection"),
    ):
        client.post(
            "/quality/inspection-lots",
            {
                "inspection_lot_code": codes[inspection_key],
                "plan_code": codes["plan"],
                "plan_revision": 1,
                "lot_code": codes[lot_key],
                "location_code": codes["raw_location"],
                "quantity": 5,
                "evidence_reference": f"{codes[inspection_key]}-OPEN",
            },
            expected=(201,),
        )
    return codes


def _measurement(
    prefix: str,
    codes: dict[str, str],
    sample_index: int,
    value: float,
    occurred_at: str,
) -> dict[str, Any]:
    measurement_id = f"{prefix}-M{sample_index}"
    return {
        "measurement_id": measurement_id,
        "characteristic_code": codes["characteristic"],
        "sample_index": sample_index,
        "numeric_value": value,
        "uom_code": codes["millimetre"],
        "method": "digital-micrometer",
        "gauge_code": codes["gauge"],
        "personnel_code": f"{prefix}-OP",
        "occurred_at": occurred_at,
        "evidence_reference": f"{measurement_id}-EVIDENCE",
    }


def _verify_postgres(
    dsn: str,
    tenant_id: str,
    site_id: str,
    prefix: str,
    codes: dict[str, str],
) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    sys.path.insert(0, str(CENTRAL_API_ROOT))
    from app.core.phase5_schema import PHASE5_MIGRATIONS, PHASE5_SCOPED_TABLES

    migration_versions = [item.version for item in PHASE5_MIGRATIONS]
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        migrations = connection.execute(
            "SELECT version FROM schema_migrations WHERE version = ANY(%s)",
            (migration_versions,),
        ).fetchall()
        if {item["version"] for item in migrations} != set(migration_versions):
            raise GateFailure("Phase 5 PostgreSQL migration records are incomplete")
        rls_rows = connection.execute(
            """SELECT c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity,
                      COUNT(p.policyname) AS policy_count
               FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               LEFT JOIN pg_policies p ON p.schemaname=n.nspname
                 AND p.tablename=c.relname AND p.policyname='miniogas_scope'
               WHERE n.nspname=current_schema() AND c.relname=ANY(%s)
               GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity""",
            (list(PHASE5_SCOPED_TABLES),),
        ).fetchall()
        valid_rls = {
            item["table_name"]
            for item in rls_rows
            if item["relrowsecurity"]
            and item["relforcerowsecurity"]
            and int(item["policy_count"]) == 1
        }
        if valid_rls != set(PHASE5_SCOPED_TABLES):
            raise GateFailure("Phase 5 forced-RLS policies are incomplete")
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            (tenant_id, site_id),
        )
        inspection_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM inspection_lots WHERE inspection_lot_code LIKE %s",
                (f"{prefix}%",),
            ).fetchone()["count"]
        )
        measurement_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM quality_measurements WHERE measurement_id LIKE %s",
                (f"{prefix}%",),
            ).fetchone()["count"]
        )
        audit_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM audit_logs "
                "WHERE run_id='quality' AND resource_id LIKE %s",
                (f"{prefix}%",),
            ).fetchone()["count"]
        )
        if inspection_count != 2 or measurement_count != 2 or audit_count < 10:
            raise GateFailure("Phase 5 live quality facts are incomplete in PostgreSQL")

        measurement = connection.execute(
            "SELECT id FROM quality_measurements WHERE measurement_id=%s",
            (f"{prefix}-M1",),
        ).fetchone()
        append_only_guard = False
        try:
            connection.execute(
                "UPDATE quality_measurements SET result=result WHERE id=%s",
                (measurement["id"],),
            )
        except psycopg.Error as exc:
            append_only_guard = "append-only" in str(exc)
        if not append_only_guard:
            raise GateFailure("quality measurement append-only guard did not reject rewrite")

        held = connection.execute(
            """SELECT inspection.id AS inspection_id, lot.id AS lot_id
               FROM inspection_lots inspection
               JOIN material_lots lot ON lot.id=inspection.lot_id
               WHERE inspection.inspection_lot_code=%s""",
            (codes["held_inspection"],),
        ).fetchone()
        receipt = connection.execute(
            """SELECT movement.* FROM inventory_movements movement
               WHERE movement.lot_id=%s ORDER BY movement.id LIMIT 1""",
            (held["lot_id"],),
        ).fetchone()
        database_hold_guard = False
        try:
            connection.execute(
                """INSERT INTO inventory_movements (
                       tenant_id, site_id, movement_id, movement_type, material_id,
                       lot_id, uom_id, quantity, from_location_id, to_location_id,
                       from_container_id, to_container_id, operation_task_id,
                       transformation_id, reconciliation_case_id, source, reason,
                       evidence_reference, request_hash, occurred_at, recorded_by
                   ) VALUES (
                       %s, %s, %s, 'transfer', %s, %s, %s, 1, %s, %s,
                       NULL, NULL, NULL, NULL, NULL, 'manual', %s, %s, %s, %s, %s
                   )""",
                (
                    tenant_id,
                    site_id,
                    f"{prefix}-DIRECT-MOVE",
                    receipt["material_id"],
                    receipt["lot_id"],
                    receipt["uom_id"],
                    receipt["to_location_id"],
                    receipt["to_location_id"],
                    "direct hold bypass probe",
                    f"{prefix}-DIRECT-MOVE-EVIDENCE",
                    f"{prefix}-DIRECT-MOVE-HASH",
                    datetime.now(UTC).isoformat(),
                    "phase5-gate",
                ),
            )
        except psycopg.Error as exc:
            database_hold_guard = "open quality hold" in str(exc)
        if not database_hold_guard:
            raise GateFailure("database accepted movement for a quality-held lot")

        context = connection.execute(
            """SELECT characteristic.id AS characteristic_id,
                      characteristic.uom_id, characteristic.method,
                      gauge.id AS gauge_id, personnel.id AS personnel_id
               FROM quality_characteristics characteristic
               JOIN inspection_plans plan ON plan.id=characteristic.inspection_plan_id
               JOIN gauges gauge ON gauge.gauge_code=%s
               JOIN personnel personnel ON personnel.personnel_code=%s
               WHERE plan.plan_code=%s AND plan.revision=1""",
            (codes["gauge"], f"{prefix}-OP", codes["plan"]),
        ).fetchone()
        deterministic_result_guard = False
        try:
            connection.execute(
                """INSERT INTO quality_measurements (
                       tenant_id, site_id, measurement_id, inspection_lot_id,
                       characteristic_id, sample_index, numeric_value, boolean_value,
                       text_value, uom_id, method, gauge_id, personnel_id, occurred_at,
                       evidence_reference, result, request_hash, recorded_by
                   ) VALUES (
                       %s, %s, %s, %s, %s, 1, 10.0, NULL, NULL, %s, %s, %s, %s,
                       %s, %s, 'fail', %s, %s
                   )""",
                (
                    tenant_id,
                    site_id,
                    f"{prefix}-FORGED-MEASUREMENT",
                    held["inspection_id"],
                    context["characteristic_id"],
                    context["uom_id"],
                    context["method"],
                    context["gauge_id"],
                    context["personnel_id"],
                    datetime.now(UTC).isoformat(),
                    f"{prefix}-FORGED-EVIDENCE",
                    f"{prefix}-FORGED-HASH",
                    "phase5-gate",
                ),
            )
        except psycopg.Error as exc:
            deterministic_result_guard = "contradicts specification" in str(exc)
        if not deterministic_result_guard:
            raise GateFailure("database accepted a forged measurement result")

        release_guard = False
        try:
            connection.execute(
                """UPDATE inspection_lots
                   SET status='released', released_by='phase5-gate',
                       release_authorization_reference='DIRECT-BYPASS', released_at=now()
                   WHERE id=%s""",
                (held["inspection_id"],),
            )
        except psycopg.Error as exc:
            release_guard = "quality release requires" in str(exc)
        if not release_guard:
            raise GateFailure("database accepted an unauthorized inspection release")

        operator_release_permissions = int(
            connection.execute(
                """SELECT COUNT(*) AS count FROM role_permissions
                   WHERE role_name='operator' AND permission_name='quality:release'"""
            ).fetchone()["count"]
        )
        if operator_release_permissions != 0:
            raise GateFailure("operator role unexpectedly owns quality release permission")

        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            ("tenant-phase5-negative", "site-phase5-negative"),
        )
        cross_scope = 0
        for table_name in PHASE5_SCOPED_TABLES:
            cross_scope += int(
                connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()[
                    "count"
                ]
            )
        if cross_scope != 0:
            raise GateFailure("Phase 5 cross-scope query returned quality facts")
    return {
        "migrations": migration_versions,
        "forced_rls_tables": len(valid_rls),
        "inspection_lots": inspection_count,
        "measurements": measurement_count,
        "quality_audit_records": audit_count,
        "append_only_guard": append_only_guard,
        "quality_hold_database_guard": database_hold_guard,
        "deterministic_result_guard": deterministic_result_guard,
        "release_database_guard": release_guard,
        "operator_release_permissions": operator_release_permissions,
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

    prefix = f"P5G{datetime.now(UTC):%m%d%H%M%S}{uuid4().hex[:4].upper()}"
    now = datetime.now(UTC)
    master = _seed_master_data(client, prefix)
    codes = _seed_quality_authority(client, prefix, master, now)
    occurred_at = now.isoformat()
    blocked_movement = _movement(
        f"{prefix}-BLOCKED-MOVE",
        codes["release_lot"],
        1,
        occurred_at,
        movement_type="transfer",
        from_location=codes["raw_location"],
        to_location=codes["wip_location"],
    )
    _expect_problem(
        client,
        "/material-flow/movements",
        blocked_movement,
        "QUALITY_HOLD_ACTIVE",
    )
    first = client.post(
        f"/quality/inspection-lots/{codes['release_inspection']}/measurements",
        _measurement(prefix, codes, 1, 10.0, occurred_at),
        expected=(201,),
    )
    repeated = client.post(
        f"/quality/inspection-lots/{codes['release_inspection']}/measurements",
        _measurement(prefix, codes, 1, 10.0, occurred_at),
        expected=(201,),
    )
    if first["id"] != repeated["id"]:
        raise GateFailure("measurement retry created duplicate quality evidence")
    failed_measurement = client.post(
        f"/quality/inspection-lots/{codes['release_inspection']}/measurements",
        _measurement(prefix, codes, 2, 10.3, occurred_at),
        expected=(201,),
    )
    if failed_measurement.get("result") != "fail":
        raise GateFailure("out-of-specification measurement was not evaluated as fail")
    inspection = client.get(f"/quality/inspection-lots/{codes['release_inspection']}")
    if inspection.get("status") != "failed" or len(inspection["nonconformances"]) != 1:
        raise GateFailure("failed inspection did not create one nonconformance")
    _expect_problem(
        client,
        f"/quality/inspection-lots/{codes['release_inspection']}/release",
        {"authorization_reference": f"{prefix}-NO-DISPOSITION"},
        "DISPOSITION_REQUIRED",
    )

    os.environ["JWT_SECRET"] = jwt_secret
    sys.path.insert(0, str(CENTRAL_API_ROOT))
    from app.core.auth import issue_access_token

    ai_client = ApiClient(api_url)
    ai_client.token = issue_access_token(
        {
            "username": f"{prefix}-AI",
            "display_name": "Phase 5 AI authority probe",
            "roles": ["ai_service"],
            "permissions": ["ai:diagnose"],
        }
    )
    ai_problem = ai_client.post(
        f"/quality/inspection-lots/{codes['release_inspection']}/release",
        {"authorization_reference": f"{prefix}-AI-BYPASS"},
        expected=(403,),
    )
    if int(ai_problem.get("status") or 0) != 403:
        raise GateFailure("AI credential was not forbidden from quality release")

    nc_code = str(inspection["nonconformances"][0]["nc_code"])
    disposition_code = f"{prefix}-USE-AS-IS"
    disposition = client.post(
        f"/quality/nonconformances/{nc_code}/dispositions",
        {
            "disposition_code": disposition_code,
            "disposition_type": "use_as_is",
            "reason": "Documented engineering concession for the Phase 5 live gate",
            "evidence_reference": f"{prefix}-CONCESSION-PROPOSAL",
        },
        expected=(201,),
    )
    if disposition.get("status") != "proposed":
        raise GateFailure("quality disposition was not created as a proposal")
    _expect_problem(
        client,
        f"/quality/inspection-lots/{codes['release_inspection']}/release",
        {"authorization_reference": f"{prefix}-UNAPPROVED"},
        "DISPOSITION_NOT_APPROVED",
    )
    approved = client.post(
        f"/quality/dispositions/{disposition_code}/approve",
        {"authorization_reference": f"{prefix}-CONCESSION-APPROVAL"},
        expected=(200,),
    )
    if approved.get("status") != "approved":
        raise GateFailure("quality disposition approval was not persisted")
    released = client.post(
        f"/quality/inspection-lots/{codes['release_inspection']}/release",
        {"authorization_reference": f"{prefix}-QUALITY-RELEASE"},
        expected=(200,),
    )
    if released.get("status") != "released":
        raise GateFailure("authorized quality release did not resolve the inspection")
    moved = client.post(
        "/material-flow/movements",
        _movement(
            f"{prefix}-AFTER-RELEASE",
            codes["release_lot"],
            1,
            occurred_at,
            movement_type="transfer",
            from_location=codes["raw_location"],
            to_location=codes["wip_location"],
        ),
        expected=(201,),
    )
    capa_code = f"{prefix}-CAPA"
    client.post(
        f"/quality/nonconformances/{nc_code}/capas",
        {
            "capa_code": capa_code,
            "problem_statement": "Out-of-specification diameter reached final inspection",
            "root_cause": "Tool-offset verification was omitted",
            "action_plan": "Require independent offset verification after every tool change",
            "due_at": (now + timedelta(days=30)).isoformat(),
            "evidence_reference": f"{prefix}-CAPA-PLAN",
        },
        expected=(201,),
    )
    capa = client.post(
        f"/quality/capas/{capa_code}/complete",
        {
            "verification_reference": f"{prefix}-CAPA-VERIFY",
            "effectiveness_result": "Two controlled setup checks completed without recurrence",
        },
        expected=(200,),
    )
    if capa.get("status") != "completed":
        raise GateFailure("CAPA effectiveness record was not completed")
    database = _verify_postgres(dsn, tenant_id, site_id, prefix, codes)
    return {
        "status": "PASS",
        "validation_prefix": prefix,
        "inspection_status": released["status"],
        "nonconformance_code": nc_code,
        "disposition_status": approved["status"],
        "capa_status": capa["status"],
        "movement_after_release_id": moved["id"],
        "measurement_retry_id": first["id"],
        "ai_release_forbidden": True,
        "held_probe_inspection": codes["held_inspection"],
        "database": database,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Phase 5 quality gate")
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
