from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

Backend = Literal["sqlite", "postgres"]
MigrationAction = Callable[[Any], None]


@dataclass(frozen=True)
class Migration:
    version: str
    description: str
    checksum_material: str
    sqlite_action: MigrationAction
    postgres_action: MigrationAction

    @property
    def checksum(self) -> str:
        content = "\n".join((self.version, self.description, self.checksum_material))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def apply(self, connection: Any, backend: Backend) -> None:
        action = self.postgres_action if backend == "postgres" else self.sqlite_action
        action(connection)


def _sqlite_columns(connection: Any, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _upgrade_integer_sqlite_ledger(connection: Any) -> None:
    table_info = connection.execute("PRAGMA table_info(schema_migrations)").fetchall()
    version_column = next((row for row in table_info if str(row[1]) == "version"), None)
    if version_column is None or "INT" not in str(version_column[2]).upper():
        return

    legacy_table = "schema_migrations_legacy_integer"
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (legacy_table,),
    ).fetchone():
        raise RuntimeError(
            "cannot upgrade integer migration ledger: interrupted legacy table already exists"
        )

    cursor = connection.execute("SELECT * FROM schema_migrations ORDER BY version")
    column_names = [str(item[0]) for item in cursor.description]
    legacy_rows = [dict(zip(column_names, row)) for row in cursor.fetchall()]
    connection.execute(f"ALTER TABLE schema_migrations RENAME TO {legacy_table}")
    connection.execute(
        """CREATE TABLE schema_migrations (
               version TEXT PRIMARY KEY,
               description TEXT NOT NULL,
               checksum TEXT NOT NULL DEFAULT '',
               applied_by TEXT NOT NULL DEFAULT 'mini-ogas',
               execution_ms INTEGER NOT NULL DEFAULT 0,
               applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    for row in legacy_rows:
        legacy_version = str(row.get("version", ""))
        legacy_name = str(row.get("name") or row.get("description") or "legacy migration")
        version = f"legacy-{legacy_version}:{legacy_name}"
        connection.execute(
            """INSERT INTO schema_migrations (
                   version, description, checksum, applied_by, execution_ms, applied_at
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                version,
                legacy_name,
                str(row.get("checksum") or ""),
                str(row.get("applied_by") or "legacy-mini-ogas"),
                int(row.get("execution_ms") or 0),
                str(row.get("applied_at") or ""),
            ),
        )
    connection.execute(f"DROP TABLE {legacy_table}")


def ensure_migration_ledger(connection: Any, backend: Backend) -> None:
    if backend == "postgres":
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   description TEXT NOT NULL,
                   checksum TEXT NOT NULL DEFAULT '',
                   applied_by TEXT NOT NULL DEFAULT 'mini-ogas',
                   execution_ms BIGINT NOT NULL DEFAULT 0,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
               )"""
        )
        connection.execute(
            "ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''"
        )
        connection.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT NOT NULL DEFAULT ''")
        connection.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS applied_by TEXT NOT NULL DEFAULT 'mini-ogas'")
        connection.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS execution_ms BIGINT NOT NULL DEFAULT 0")
        return

    connection.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version TEXT PRIMARY KEY,
               description TEXT NOT NULL,
               checksum TEXT NOT NULL DEFAULT '',
               applied_by TEXT NOT NULL DEFAULT 'mini-ogas',
               execution_ms INTEGER NOT NULL DEFAULT 0,
               applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    _upgrade_integer_sqlite_ledger(connection)
    columns = _sqlite_columns(connection, "schema_migrations")
    additions = {
        "description": "TEXT NOT NULL DEFAULT ''",
        "checksum": "TEXT NOT NULL DEFAULT ''",
        "applied_by": "TEXT NOT NULL DEFAULT 'mini-ogas'",
        "execution_ms": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE schema_migrations ADD COLUMN {name} {definition}")


def apply_migrations(connection: Any, backend: Backend, migrations: list[Migration]) -> list[str]:
    ensure_migration_ledger(connection, backend)
    applied: list[str] = []
    for migration in migrations:
        row = connection.execute(
            "SELECT version, checksum FROM schema_migrations WHERE version = ?",
            (migration.version,),
        ).fetchone()
        if row is not None:
            if hasattr(row, "keys"):
                recorded = str(dict(row).get("checksum") or "")
            else:
                recorded = str(row[1] or "")
            if recorded and recorded != migration.checksum:
                raise RuntimeError(
                    f"migration checksum mismatch for {migration.version}: "
                    f"database={recorded} code={migration.checksum}"
                )
            continue

        started = time.perf_counter()
        migration.apply(connection, backend)
        execution_ms = max(0, round((time.perf_counter() - started) * 1000))
        connection.execute(
            """INSERT INTO schema_migrations (
                   version, description, checksum, applied_by, execution_ms
               ) VALUES (?, ?, ?, ?, ?)""",
            (
                migration.version,
                migration.description,
                migration.checksum,
                "mini-ogas-migration-runner",
                execution_ms,
            ),
        )
        applied.append(migration.version)
    return applied
