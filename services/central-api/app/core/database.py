from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import settings

SQLITE_SCHEMA_SQL = """
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
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    result TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS part_queue_shadow (
    part_id TEXT PRIMARY KEY,
    parent_part_id TEXT NOT NULL DEFAULT '',
    order_id TEXT NOT NULL,
    product_code TEXT NOT NULL DEFAULT '',
    current_step TEXT NOT NULL,
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
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    claimed_by TEXT NOT NULL DEFAULT '',
    result_message TEXT NOT NULL DEFAULT '',
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

CREATE INDEX IF NOT EXISTS idx_heartbeat_shadow_node_received
    ON heartbeat_shadow(node_code, received_at);

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
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    result TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS part_queue_shadow (
    part_id TEXT PRIMARY KEY,
    parent_part_id TEXT NOT NULL DEFAULT '',
    order_id TEXT NOT NULL,
    product_code TEXT NOT NULL DEFAULT '',
    current_step TEXT NOT NULL,
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
    node_code TEXT NOT NULL,
    command_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    claimed_by TEXT NOT NULL DEFAULT '',
    result_message TEXT NOT NULL DEFAULT '',
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

CREATE INDEX IF NOT EXISTS idx_heartbeat_shadow_node_received
    ON heartbeat_shadow(node_code, received_at);

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
        raise RuntimeError("PostgreSQL persistence requires psycopg; install psycopg[binary]") from exc
    return PostgresConnection(psycopg.connect(settings.postgres_dsn, row_factory=dict_row))


def _schema_statements(schema_sql: str) -> list[str]:
    return [statement.strip() for statement in schema_sql.split(";") if statement.strip()]


def init_db() -> None:
    if persistence_backend() == "postgres":
        with _connect_postgres() as connection:
            for statement in _schema_statements(POSTGRES_SCHEMA_SQL):
                connection.execute(statement)
            connection.commit()
        return

    db_path = Path(settings.central_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SQLITE_SCHEMA_SQL)
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
