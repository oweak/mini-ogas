from __future__ import annotations

import json

import pytest

from app import migrate
from app.core.config import settings


def test_one_shot_migration_initializes_schema_and_reports_safely(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(tmp_path / "migration.db"))

    assert migrate.main() == 0
    report = json.loads(capsys.readouterr().out)

    assert report["status"] == "migrated"
    assert report["backend"] == "sqlite-local"
    assert report["migration_count"] > 0
    assert report["latest_migration"]
    assert "dsn" not in json.dumps(report).lower()


def test_one_shot_migration_rejects_disabled_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)

    with pytest.raises(RuntimeError, match="PERSIST_ENABLED=true"):
        migrate.main()
