from __future__ import annotations

import json
from datetime import UTC, datetime

from .core.config import settings
from .core.database import get_db, init_db, persistence_label


def migration_report() -> dict[str, object]:
    with get_db() as db:
        rows = db.execute(
            "SELECT version, description, applied_at FROM schema_migrations ORDER BY applied_at, version"
        ).fetchall()
    migrations = [
        {
            "version": str(row["version"]),
            "description": str(row["description"]),
            "applied_at": str(row["applied_at"]),
        }
        for row in rows
    ]
    return {
        "status": "migrated",
        "backend": persistence_label(),
        "migration_count": len(migrations),
        "latest_migration": migrations[-1]["version"] if migrations else "",
        "completed_at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    if not settings.persist_enabled:
        raise RuntimeError("PERSIST_ENABLED=true is required for the migration job")
    init_db()
    print(json.dumps(migration_report(), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
