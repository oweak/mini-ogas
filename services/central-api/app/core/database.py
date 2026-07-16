from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import settings
from .migrations import Migration, apply_migrations, ensure_migration_ledger
from .phase2_schema import PHASE2_MIGRATIONS
from .phase3_schema import PHASE3_MIGRATIONS
from .phase4_schema import PHASE4_MIGRATIONS
from .phase5_schema import PHASE5_MIGRATIONS
from .phase6_schema import PHASE6_MIGRATIONS
from .phase7_schema import PHASE7_MIGRATIONS
from .principal_schema import STAGE_C_PRINCIPAL_MIGRATIONS
from .stage_e_schema import STAGE_E_MIGRATIONS

SCHEMA_VERSION = "2026.07.13-v3.0.1-nats-shadow"
PHASE1_SCOPE_MIGRATION_VERSION = "2026.07.13-phase1-scope-outbox"

SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT NOT NULL,
    cpu_usage REAL NOT NULL,
    memory_usage REAL NOT NULL,
    disk_usage REAL NOT NULL,
    network_in INTEGER NOT NULL,
    network_out INTEGER NOT NULL,
    db_latency_ms INTEGER NOT NULL,
    api_latency_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL DEFAULT '',
    node_code TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    source TEXT NOT NULL,
    description TEXT NOT NULL,
    handled_by TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS ai_diagnosis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL DEFAULT '',
    alert_id INTEGER,
    severity TEXT NOT NULL DEFAULT 'medium',
    node_code TEXT,
    root_cause TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    need_isolation INTEGER NOT NULL DEFAULT 0,
    model_name TEXT NOT NULL DEFAULT 'deepseek',
    raw_response TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL DEFAULT '',
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    result TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_store (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_node TEXT NOT NULL,
    event_time TEXT NOT NULL,
    ingest_time TEXT NOT NULL,
    local_sequence INTEGER NOT NULL,
    global_sequence INTEGER NOT NULL UNIQUE,
    correlation_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_store_run_global ON event_store(run_id, global_sequence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_store_source_local
    ON event_store(source_node, run_id, local_sequence);

CREATE TABLE IF NOT EXISTS part_queue_shadow (
    part_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    scenario_id TEXT NOT NULL DEFAULT '',
    batch_id TEXT NOT NULL DEFAULT '',
    parent_part_id TEXT NOT NULL DEFAULT '',
    order_id TEXT NOT NULL,
    product_code TEXT NOT NULL DEFAULT '',
    current_step TEXT NOT NULL,
    current_operation TEXT NOT NULL DEFAULT '',
    next_operation TEXT NOT NULL DEFAULT '',
    quality_status TEXT NOT NULL DEFAULT 'pending',
    event_sequence INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    claimed_by TEXT NOT NULL DEFAULT '',
    claim_token TEXT NOT NULL DEFAULT '',
    claim_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS command_shadow (
    command_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    claimed_by TEXT NOT NULL DEFAULT '',
    result_message TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT,
    dispatched_at TEXT,
    received_at TEXT,
    applied_at TEXT,
    verified_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'not_started',
    verification_baseline_json TEXT NOT NULL DEFAULT '{}',
    verification_evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS production_plan_shadow (
    plan_key TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    plan_index INTEGER NOT NULL,
    product_code TEXT NOT NULL,
    target_quantity INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    route_json TEXT NOT NULL DEFAULT '[]',
    reason TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dispatch_task_shadow (
    task_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    route_json TEXT NOT NULL DEFAULT '[]',
    assigned_node TEXT NOT NULL DEFAULT '',
    assigned_machine TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'scheduled',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS allocation_order_shadow (
    order_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    source_unit TEXT NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    required_quantity INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    deadline_hours INTEGER NOT NULL,
    assigned_cloud_role TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'received',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS heartbeat_shadow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    scenario_id TEXT NOT NULL DEFAULT '',
    simulation_time TEXT,
    payload_json TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY,
    simulation_engine TEXT NOT NULL DEFAULT '',
    random_seed INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'normal',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    random_seed INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    last_event_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_shadow_node_received
    ON heartbeat_shadow(node_code, received_at);

CREATE TABLE IF NOT EXISTS node_record_receipts (
    node_code TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    local_id INTEGER NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_created_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (node_code, run_id, local_id)
);

CREATE TABLE IF NOT EXISTS nats_shadow_receipts (
    message_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    message_type TEXT NOT NULL,
    source_node TEXT NOT NULL,
    run_id TEXT NOT NULL,
    local_sequence INTEGER NOT NULL,
    correlation_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    delivery_count INTEGER NOT NULL DEFAULT 1,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    last_ingested_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_nats_shadow_source_run_sequence
    ON nats_shadow_receipts(source_node, run_id, local_sequence);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roles (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS permissions (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS user_roles (
    username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    role_name TEXT NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
    PRIMARY KEY (username, role_name)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_name TEXT NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
    permission_name TEXT NOT NULL REFERENCES permissions(name) ON DELETE CASCADE,
    PRIMARY KEY (role_name, permission_name)
);
"""

POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS metrics (
    id BIGSERIAL PRIMARY KEY,
    node_code TEXT NOT NULL,
    cpu_usage DOUBLE PRECISION NOT NULL,
    memory_usage DOUBLE PRECISION NOT NULL,
    disk_usage DOUBLE PRECISION NOT NULL,
    network_in BIGINT NOT NULL,
    network_out BIGINT NOT NULL,
    db_latency_ms INTEGER NOT NULL,
    api_latency_ms INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    node_code TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    source TEXT NOT NULL,
    description TEXT NOT NULL,
    handled_by TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ai_diagnosis (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    alert_id BIGINT,
    severity TEXT NOT NULL DEFAULT 'medium',
    node_code TEXT,
    root_cause TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    need_isolation BOOLEAN NOT NULL DEFAULT false,
    model_name TEXT NOT NULL DEFAULT 'deepseek',
    raw_response TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS commands (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    result TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_store (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_node TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    ingest_time TIMESTAMPTZ NOT NULL,
    local_sequence BIGINT NOT NULL,
    global_sequence BIGINT NOT NULL UNIQUE,
    correlation_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_store_run_global ON event_store(run_id, global_sequence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_store_source_local
    ON event_store(source_node, run_id, local_sequence);

CREATE TABLE IF NOT EXISTS part_queue_shadow (
    part_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    scenario_id TEXT NOT NULL DEFAULT '',
    batch_id TEXT NOT NULL DEFAULT '',
    parent_part_id TEXT NOT NULL DEFAULT '',
    order_id TEXT NOT NULL,
    product_code TEXT NOT NULL DEFAULT '',
    current_step TEXT NOT NULL,
    current_operation TEXT NOT NULL DEFAULT '',
    next_operation TEXT NOT NULL DEFAULT '',
    quality_status TEXT NOT NULL DEFAULT 'pending',
    event_sequence BIGINT NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    claimed_by TEXT NOT NULL DEFAULT '',
    claim_token TEXT NOT NULL DEFAULT '',
    claim_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS command_shadow (
    command_id BIGINT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    claimed_by TEXT NOT NULL DEFAULT '',
    result_message TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    expires_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'not_started',
    verification_baseline_json TEXT NOT NULL DEFAULT '{}',
    verification_evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS production_plan_shadow (
    plan_key TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    plan_index INTEGER NOT NULL,
    product_code TEXT NOT NULL,
    target_quantity INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    route_json TEXT NOT NULL DEFAULT '[]',
    reason TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dispatch_task_shadow (
    task_id BIGINT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    route_json TEXT NOT NULL DEFAULT '[]',
    assigned_node TEXT NOT NULL DEFAULT '',
    assigned_machine TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'scheduled',
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS allocation_order_shadow (
    order_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    source_unit TEXT NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    required_quantity INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    deadline_hours INTEGER NOT NULL,
    assigned_cloud_role TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'received',
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS heartbeat_shadow (
    id BIGSERIAL PRIMARY KEY,
    node_code TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    scenario_id TEXT NOT NULL DEFAULT '',
    simulation_time TIMESTAMPTZ,
    payload_json TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY,
    simulation_engine TEXT NOT NULL DEFAULT '',
    random_seed BIGINT NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'normal',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    random_seed BIGINT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL,
    last_event_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_shadow_node_received
    ON heartbeat_shadow(node_code, received_at);

CREATE TABLE IF NOT EXISTS node_record_receipts (
    node_code TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    local_id BIGINT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_created_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (node_code, run_id, local_id)
);

CREATE TABLE IF NOT EXISTS nats_shadow_receipts (
    message_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    message_type TEXT NOT NULL,
    source_node TEXT NOT NULL,
    run_id TEXT NOT NULL,
    local_sequence BIGINT NOT NULL,
    correlation_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    payload_json TEXT NOT NULL,
    delivery_count BIGINT NOT NULL DEFAULT 1,
    duplicate_count BIGINT NOT NULL DEFAULT 0,
    last_ingested_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_nats_shadow_source_run_sequence
    ON nats_shadow_receipts(source_node, run_id, local_sequence);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS permissions (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS user_roles (
    username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    role_name TEXT NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
    PRIMARY KEY (username, role_name)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_name TEXT NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
    permission_name TEXT NOT NULL REFERENCES permissions(name) ON DELETE CASCADE,
    PRIMARY KEY (role_name, permission_name)
);
"""


def persistence_backend() -> str:
    configured = (settings.persist_backend or "auto").strip().lower()
    if configured in {"postgres", "postgresql"}:
        return "postgres"
    if configured in {"sqlite", "sqlite-shadow", "local"}:
        return "sqlite"
    if settings.postgres_dsn:
        return "postgres"
    return "sqlite"


def persistence_label() -> str:
    if persistence_backend() == "postgres":
        return "postgresql"
    return "sqlite-local"


def _translate_qmark_placeholders(sql: str) -> str:
    return sql.replace("?", "%s")


class PostgresConnection:
    def __init__(self, connection: Any):
        self._connection = connection
        self._connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            (settings.tenant_id, settings.site_id),
        )

    def __enter__(self) -> PostgresConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is None:
            self.commit()
        self.close()

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        return self._connection.execute(_translate_qmark_placeholders(sql), params or ())

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


def _connect_postgres() -> PostgresConnection:
    if not settings.postgres_dsn:
        raise RuntimeError("PERSIST_BACKEND=postgres requires POSTGRES_DSN or DATABASE_URL")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depends on deployment package set
        raise RuntimeError(
            "PostgreSQL persistence requires psycopg; install psycopg[binary]"
        ) from exc
    return PostgresConnection(psycopg.connect(settings.postgres_dsn, row_factory=dict_row))


def _schema_statements(schema_sql: str) -> list[str]:
    return [statement.strip() for statement in schema_sql.split(";") if statement.strip()]


RUN_ID_TABLES = (
    "alerts",
    "ai_diagnosis",
    "commands",
    "audit_logs",
    "part_queue_shadow",
    "command_shadow",
    "production_plan_shadow",
    "dispatch_task_shadow",
    "allocation_order_shadow",
)

SCOPED_TABLES = (
    "metrics",
    "alerts",
    "ai_diagnosis",
    "commands",
    "audit_logs",
    "event_store",
    "part_queue_shadow",
    "command_shadow",
    "production_plan_shadow",
    "dispatch_task_shadow",
    "allocation_order_shadow",
    "heartbeat_shadow",
    "scenarios",
    "runs",
    "node_record_receipts",
    "nats_shadow_receipts",
    "users",
    "outbox_messages",
)

RUN_ID_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_alerts_run_created ON alerts(run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_ai_diagnosis_run_created ON ai_diagnosis(run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_commands_run_created ON commands(run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_run_created ON audit_logs(run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_part_queue_shadow_run_updated ON part_queue_shadow(run_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_command_shadow_run_updated ON command_shadow(run_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_production_plan_shadow_run_updated ON production_plan_shadow(run_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_dispatch_task_shadow_run_updated ON dispatch_task_shadow(run_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_allocation_order_shadow_run_updated ON allocation_order_shadow(run_id, updated_at)",
)


def _sqlite_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _ensure_sqlite_run_id_columns(connection: sqlite3.Connection) -> None:
    for table_name in RUN_ID_TABLES:
        if "run_id" not in _sqlite_table_columns(connection, table_name):
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN run_id TEXT NOT NULL DEFAULT ''"
            )


def _ensure_postgres_run_id_columns(connection: PostgresConnection) -> None:
    for table_name in RUN_ID_TABLES:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS run_id TEXT NOT NULL DEFAULT ''"
        )


def _ensure_sqlite_command_verification_columns(connection: sqlite3.Connection) -> None:
    definitions = {
        "version": "INTEGER NOT NULL DEFAULT 1",
        "expires_at": "TEXT",
        "dispatched_at": "TEXT",
        "received_at": "TEXT",
        "applied_at": "TEXT",
        "verified_at": "TEXT",
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "verification_status": "TEXT NOT NULL DEFAULT 'not_started'",
        "verification_baseline_json": "TEXT NOT NULL DEFAULT '{}'",
        "verification_evidence_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    existing = _sqlite_table_columns(connection, "command_shadow")
    for name, definition in definitions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE command_shadow ADD COLUMN {name} {definition}")


def _ensure_postgres_command_verification_columns(connection: PostgresConnection) -> None:
    definitions = {
        "version": "INTEGER NOT NULL DEFAULT 1",
        "expires_at": "TIMESTAMPTZ",
        "dispatched_at": "TIMESTAMPTZ",
        "received_at": "TIMESTAMPTZ",
        "applied_at": "TIMESTAMPTZ",
        "verified_at": "TIMESTAMPTZ",
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "verification_status": "TEXT NOT NULL DEFAULT 'not_started'",
        "verification_baseline_json": "TEXT NOT NULL DEFAULT '{}'",
        "verification_evidence_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for name, definition in definitions.items():
        connection.execute(
            f"ALTER TABLE command_shadow ADD COLUMN IF NOT EXISTS {name} {definition}"
        )


def _ensure_sqlite_part_identity_columns(connection: sqlite3.Connection) -> None:
    definitions = {
        "scenario_id": "TEXT NOT NULL DEFAULT ''",
        "batch_id": "TEXT NOT NULL DEFAULT ''",
        "current_operation": "TEXT NOT NULL DEFAULT ''",
        "next_operation": "TEXT NOT NULL DEFAULT ''",
        "quality_status": "TEXT NOT NULL DEFAULT 'pending'",
        "event_sequence": "INTEGER NOT NULL DEFAULT 1",
    }
    existing = _sqlite_table_columns(connection, "part_queue_shadow")
    for name, definition in definitions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE part_queue_shadow ADD COLUMN {name} {definition}")


def _ensure_postgres_part_identity_columns(connection: PostgresConnection) -> None:
    definitions = {
        "scenario_id": "TEXT NOT NULL DEFAULT ''",
        "batch_id": "TEXT NOT NULL DEFAULT ''",
        "current_operation": "TEXT NOT NULL DEFAULT ''",
        "next_operation": "TEXT NOT NULL DEFAULT ''",
        "quality_status": "TEXT NOT NULL DEFAULT 'pending'",
        "event_sequence": "BIGINT NOT NULL DEFAULT 1",
    }
    for name, definition in definitions.items():
        connection.execute(
            f"ALTER TABLE part_queue_shadow ADD COLUMN IF NOT EXISTS {name} {definition}"
        )


def _ensure_run_id_indexes(connection: Any) -> None:
    for statement in RUN_ID_INDEX_SQL:
        connection.execute(statement)


def _record_schema_version(connection: Any) -> None:
    connection.execute(
        """INSERT INTO schema_migrations (version, description)
           VALUES (?, ?)
           ON CONFLICT(version) DO NOTHING""",
        (SCHEMA_VERSION, "v3.0.1 NATS JetStream shadow transport receipts"),
    )


def _create_sqlite_outbox(connection: sqlite3.Connection) -> None:
    tenant = settings.tenant_id.replace("'", "''")
    site = settings.site_id.replace("'", "''")
    connection.execute(
        f"""CREATE TABLE IF NOT EXISTS outbox_messages (
                message_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{tenant}',
                site_id TEXT NOT NULL DEFAULT '{site}',
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                claimed_at TEXT,
                claim_token TEXT NOT NULL DEFAULT '',
                published_at TEXT,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
    )


def _phase1_sqlite_scope_outbox(connection: sqlite3.Connection) -> None:
    _create_sqlite_outbox(connection)
    tenant = settings.tenant_id.replace("'", "''")
    site = settings.site_id.replace("'", "''")
    for table_name in SCOPED_TABLES:
        columns = _sqlite_table_columns(connection, table_name)
        if "tenant_id" not in columns:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '{tenant}'"
            )
        if "site_id" not in columns:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN site_id TEXT NOT NULL DEFAULT '{site}'"
            )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_scope ON {table_name}(tenant_id, site_id)"
        )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_outbox_pending
           ON outbox_messages(tenant_id, site_id, status, available_at, created_at)"""
    )


def _phase1_postgres_scope_outbox(connection: PostgresConnection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS outbox_messages (
               message_id TEXT PRIMARY KEY,
               tenant_id TEXT NOT NULL DEFAULT current_setting('app.tenant_id', true),
               site_id TEXT NOT NULL DEFAULT current_setting('app.site_id', true),
               aggregate_type TEXT NOT NULL,
               aggregate_id TEXT NOT NULL,
               message_type TEXT NOT NULL,
               subject TEXT NOT NULL,
               schema_version TEXT NOT NULL,
               payload_json TEXT NOT NULL,
               status TEXT NOT NULL DEFAULT 'pending',
               attempts INTEGER NOT NULL DEFAULT 0,
               available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               claimed_at TIMESTAMPTZ,
               claim_token TEXT NOT NULL DEFAULT '',
               published_at TIMESTAMPTZ,
               last_error TEXT NOT NULL DEFAULT '',
               created_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )"""
    )
    for table_name in SCOPED_TABLES:
        connection.execute(
            f"""ALTER TABLE {table_name}
                ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL
                DEFAULT current_setting('app.tenant_id', true)"""
        )
        connection.execute(
            f"""ALTER TABLE {table_name}
                ADD COLUMN IF NOT EXISTS site_id TEXT NOT NULL
                DEFAULT current_setting('app.site_id', true)"""
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_scope ON {table_name}(tenant_id, site_id)"
        )
        connection.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        connection.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        connection.execute(f"DROP POLICY IF EXISTS miniogas_scope ON {table_name}")
        connection.execute(
            f"""CREATE POLICY miniogas_scope ON {table_name}
                USING (
                    tenant_id = current_setting('app.tenant_id', true)
                    AND site_id = current_setting('app.site_id', true)
                )
                WITH CHECK (
                    tenant_id = current_setting('app.tenant_id', true)
                    AND site_id = current_setting('app.site_id', true)
                )"""
        )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_outbox_pending
           ON outbox_messages(tenant_id, site_id, status, available_at, created_at)"""
    )


PHASE1_MIGRATIONS = [
    Migration(
        version=PHASE1_SCOPE_MIGRATION_VERSION,
        description="Phase 1 tenant/site data scope, PostgreSQL RLS and transactional outbox foundation",
        checksum_material=(
            "scope-columns-v1|postgres-force-rls-v1|outbox-v1|" + "|".join(SCOPED_TABLES)
        ),
        sqlite_action=_phase1_sqlite_scope_outbox,
        postgres_action=_phase1_postgres_scope_outbox,
    ),
]


def init_db() -> None:
    if persistence_backend() == "postgres":
        with _connect_postgres() as connection:
            for statement in _schema_statements(POSTGRES_SCHEMA_SQL):
                connection.execute(statement)
            _ensure_postgres_run_id_columns(connection)
            _ensure_postgres_command_verification_columns(connection)
            _ensure_postgres_part_identity_columns(connection)
            _ensure_run_id_indexes(connection)
            ensure_migration_ledger(connection, "postgres")
            _record_schema_version(connection)
            apply_migrations(
                connection,
                "postgres",
                PHASE1_MIGRATIONS
                + PHASE2_MIGRATIONS
                + PHASE3_MIGRATIONS
                + PHASE4_MIGRATIONS
                + PHASE5_MIGRATIONS
                + PHASE6_MIGRATIONS
                + PHASE7_MIGRATIONS
                + STAGE_C_PRINCIPAL_MIGRATIONS
                + STAGE_E_MIGRATIONS,
            )
            connection.commit()
        return

    db_path = Path(settings.central_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SQLITE_SCHEMA_SQL)
        _ensure_sqlite_run_id_columns(connection)
        _ensure_sqlite_command_verification_columns(connection)
        _ensure_sqlite_part_identity_columns(connection)
        _ensure_run_id_indexes(connection)
        ensure_migration_ledger(connection, "sqlite")
        _record_schema_version(connection)
        apply_migrations(
            connection,
            "sqlite",
            PHASE1_MIGRATIONS
            + PHASE2_MIGRATIONS
            + PHASE3_MIGRATIONS
            + PHASE4_MIGRATIONS
            + PHASE5_MIGRATIONS
            + PHASE6_MIGRATIONS
            + PHASE7_MIGRATIONS
            + STAGE_C_PRINCIPAL_MIGRATIONS
            + STAGE_E_MIGRATIONS,
        )
        connection.commit()


@contextmanager
def get_db() -> Iterator[Any]:
    if persistence_backend() == "postgres":
        connection = _connect_postgres()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()
        return

    db_path = Path(settings.central_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
