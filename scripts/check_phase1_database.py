from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CENTRAL_API_ROOT = PROJECT_ROOT / "services" / "central-api"


def read_env_value(path: Path, name: str) -> str:
    if not path.exists():
        return ""
    prefix = f"{name}="
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith(prefix):
            return raw_line[len(prefix):].strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the live Phase 1 PostgreSQL gate")
    parser.add_argument("--runtime-root", default=r"D:\MiniOGAS-VMs")
    parser.add_argument("--tenant-id", default="tenant-local")
    parser.add_argument("--site-id", default="site-digital-twin")
    args = parser.parse_args()

    dsn = read_env_value(Path(args.runtime_root) / "postgres.env", "POSTGRES_DSN")
    if not dsn:
        print(json.dumps({"ok": False, "failures": ["POSTGRES_DSN is not configured"]}))
        return 1

    os.environ.update(
        {
            "APP_ENV": "digital_twin",
            "DATA_SOURCE": "simulated",
            "CONTROL_MODE": "read_only",
            "DEMO_SEED_ENABLED": "false",
            "TENANT_ID": args.tenant_id,
            "SITE_ID": args.site_id,
            "PERSIST_ENABLED": "true",
            "PERSIST_BACKEND": "postgres",
            "POSTGRES_DSN": dsn,
        }
    )
    sys.path.insert(0, str(CENTRAL_API_ROOT))
    from app.core.database import PHASE1_SCOPE_MIGRATION_VERSION, SCOPED_TABLES

    import psycopg
    from psycopg.rows import dict_row

    failures: list[str] = []
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        role = connection.execute(
            """SELECT current_user AS role_name, rolsuper, rolbypassrls
               FROM pg_roles WHERE rolname = current_user"""
        ).fetchone()
        if role is None:
            failures.append("current database role metadata is unavailable")
            role = {"role_name": "unknown", "rolsuper": True, "rolbypassrls": True}
        if role["rolsuper"] or role["rolbypassrls"]:
            failures.append("application database role bypasses PostgreSQL RLS")

        migration = connection.execute(
            """SELECT version, checksum, applied_by
               FROM schema_migrations WHERE version = %s""",
            (PHASE1_SCOPE_MIGRATION_VERSION,),
        ).fetchone()
        if migration is None or not migration.get("checksum"):
            failures.append("Phase 1 checksum migration record is missing")

        columns = connection.execute(
            """SELECT table_name, column_name
               FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = ANY(%s)
                 AND column_name IN ('tenant_id', 'site_id')""",
            (list(SCOPED_TABLES),),
        ).fetchall()
        columns_by_table: dict[str, set[str]] = {name: set() for name in SCOPED_TABLES}
        for row in columns:
            columns_by_table[row["table_name"]].add(row["column_name"])
        missing_columns = sorted(
            table for table, names in columns_by_table.items()
            if names != {"tenant_id", "site_id"}
        )
        if missing_columns:
            failures.append("scope columns missing: " + ", ".join(missing_columns))

        rls_rows = connection.execute(
            """SELECT c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity,
                      COUNT(p.policyname) AS policy_count
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
               LEFT JOIN pg_policies p
                 ON p.schemaname = n.nspname AND p.tablename = c.relname
                    AND p.policyname = 'miniogas_scope'
               WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
               GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity""",
            (list(SCOPED_TABLES),),
        ).fetchall()
        rls_by_table = {row["table_name"]: row for row in rls_rows}
        missing_rls = sorted(
            table for table in SCOPED_TABLES
            if table not in rls_by_table
            or not rls_by_table[table]["relrowsecurity"]
            or not rls_by_table[table]["relforcerowsecurity"]
            or int(rls_by_table[table]["policy_count"]) != 1
        )
        if missing_rls:
            failures.append("forced RLS policy missing: " + ", ".join(missing_rls))

        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            (args.tenant_id, args.site_id),
        )
        audit_count = int(connection.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()["count"])
        outbox_rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM outbox_messages GROUP BY status ORDER BY status"
        ).fetchall()
        outbox_counts = {row["status"]: int(row["count"]) for row in outbox_rows}
        if audit_count <= 0:
            failures.append("scoped audit log is empty")
        if outbox_counts.get("published", 0) <= 0:
            failures.append("no heartbeat Outbox message has reached published state")

        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            ("tenant-phase1-negative", "site-phase1-negative"),
        )
        negative_audit_count = int(
            connection.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()["count"]
        )
        negative_outbox_count = int(
            connection.execute("SELECT COUNT(*) AS count FROM outbox_messages").fetchone()["count"]
        )
        if negative_audit_count != 0 or negative_outbox_count != 0:
            failures.append("cross-scope negative query returned rows")

    result = {
        "ok": not failures,
        "database_role": {
            "name": role["role_name"],
            "superuser": bool(role["rolsuper"]),
            "bypass_rls": bool(role["rolbypassrls"]),
        },
        "migration": PHASE1_SCOPE_MIGRATION_VERSION if migration else "missing",
        "scoped_tables": len(SCOPED_TABLES),
        "forced_rls_tables": len(SCOPED_TABLES) - len(missing_rls),
        "audit_rows_in_scope": audit_count,
        "outbox_by_status": outbox_counts,
        "negative_scope": {
            "audit_rows": negative_audit_count,
            "outbox_rows": negative_outbox_count,
        },
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
