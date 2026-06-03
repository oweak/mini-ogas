from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .config import settings

SCHEMA_SQL = """
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
"""


def init_db() -> None:
    db_path = Path(settings.central_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.commit()


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    db_path = Path(settings.central_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
