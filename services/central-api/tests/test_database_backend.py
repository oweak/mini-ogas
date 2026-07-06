from __future__ import annotations

import json
import sqlite3

import pytest

from app.core import database
from app.core.config import settings


def test_postgres_backend_is_selected_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "persist_backend", "postgres")
    monkeypatch.setattr(settings, "postgres_dsn", "postgresql://mini_ogas:test@localhost:5432/mini_ogas")

    assert database.persistence_backend() == "postgres"
    assert database.persistence_label() == "postgresql"


def test_auto_backend_uses_postgres_when_dsn_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "persist_backend", "auto")
    monkeypatch.setattr(settings, "postgres_dsn", "postgresql://mini_ogas:test@localhost:5432/mini_ogas")

    assert database.persistence_backend() == "postgres"


def test_sqlite_backend_remains_explicit_local_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "postgres_dsn", "postgresql://mini_ogas:test@localhost:5432/mini_ogas")

    assert database.persistence_backend() == "sqlite"
    assert database.persistence_label() == "sqlite-local"


def test_postgres_placeholder_translation_keeps_store_queries_compatible() -> None:
    sql = "INSERT INTO command_shadow (command_id, status) VALUES (?, ?)"

    assert database._translate_qmark_placeholders(sql) == (
        "INSERT INTO command_shadow (command_id, status) VALUES (%s, %s)"
    )


def test_database_datetime_accepts_sqlite_and_postgres_values() -> None:
    from datetime import datetime, timezone
    from app.store import _database_datetime

    timestamp = datetime(2026, 6, 22, 1, 2, 3, tzinfo=timezone.utc)

    assert _database_datetime(timestamp) is timestamp
    assert _database_datetime("2026-06-22T01:02:03+00:00") == timestamp


def test_sqlite_init_migrates_legacy_shadow_tables_with_run_id(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE command_shadow (
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
            )
            """
        )
        connection.commit()

    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))

    database.init_db()

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(command_shadow)").fetchall()}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(command_shadow)").fetchall()}

    assert "run_id" in columns
    assert "idx_command_shadow_run_updated" in indexes


def test_shadow_consistency_report_is_explicit_when_persistence_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import store

    monkeypatch.setattr(settings, "persist_enabled", False)

    assert store.shadow_consistency_report()["status"] == "disabled"


def test_heartbeat_shadow_restores_runtime_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))

    database.init_db()
    payload = {
        "node_code": "milling-workshop-01",
        "status": "running",
        "runtime": {
            "run_id": "RUN-PERSIST-RESTORE",
            "scenario_id": "SCN-PERSIST-RESTORE",
            "simulation_engine": "simpy",
            "runtime_source": "node-agent",
        },
        "metrics": {
            "cpu_usage": 31,
            "memory_usage": 44,
            "disk_usage": 55,
            "network_latency_ms": 19,
        },
        "production": {
            "machine_code": "MILL-PERSIST",
            "workshop_type": "milling",
            "active_order": "WO-PERSIST",
            "finished_quantity": 77,
            "defect_quantity": 1,
            "target_rate": 1.1,
            "actual_rate": 0.9,
            "utilization": 0.82,
            "wip_input": 8,
            "wip_output": 5,
        },
        "sync": {"pending_records": 2},
    }
    with database.get_db() as db:
        db.execute(
            """INSERT INTO heartbeat_shadow (
               node_code, run_id, scenario_id, simulation_time, payload_json, received_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "milling-workshop-01",
                "RUN-PERSIST-RESTORE",
                "SCN-PERSIST-RESTORE",
                None,
                json.dumps(payload),
                "2026-06-26T10:00:00+00:00",
            ),
        )

    restored = MemoryStore()
    heartbeat = restored.node_heartbeats_v2["milling-workshop-01"]

    assert heartbeat["_restored_from_persistence"] is True
    assert heartbeat["runtime"]["run_id"] == "RUN-PERSIST-RESTORE"
    assert heartbeat["production"]["machine_code"] == "MILL-PERSIST"
    assert restored.latest_metrics()["milling-workshop-01"].finished_quantity == 77
    assert restored.nodes["milling-workshop-01"].last_heartbeat.isoformat() == "2026-06-26T10:00:00+00:00"


def test_heartbeat_shadow_skips_ephemeral_workflow_nodes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))

    database.init_db()
    payload = {
        "node_code": "workflow-check-node-123",
        "status": "running",
        "runtime": {"run_id": "RUN-WORKFLOW", "scenario_id": "SCN-WORKFLOW"},
        "metrics": {"cpu_usage": 1, "memory_usage": 1, "disk_usage": 1},
        "production": {"workshop_type": "milling", "machine_code": "WF-1"},
    }
    with database.get_db() as db:
        db.execute(
            """INSERT INTO heartbeat_shadow (
               node_code, run_id, scenario_id, simulation_time, payload_json, received_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "workflow-check-node-123",
                "RUN-WORKFLOW",
                "SCN-WORKFLOW",
                None,
                json.dumps(payload),
                "2026-06-26T10:00:00+00:00",
            ),
        )

    restored = MemoryStore()

    assert "workflow-check-node-123" not in restored.node_heartbeats_v2
    assert "workflow-check-node-123" not in restored.nodes


def test_replay_readiness_survives_new_store_instance(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models import IncidentEvent, Severity
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))

    first = MemoryStore()
    first.record_node_heartbeat_v2({
        "node_code": "turning-workshop-01",
        "status": "running",
        "runtime": {
            "run_id": "RUN-REPLAY-001",
            "scenario_id": "SCN-REPLAY-001",
            "simulation_engine": "simpy",
            "runtime_source": "node-agent",
        },
        "metrics": {"cpu_usage": 20, "memory_usage": 30, "disk_usage": 40},
        "production": {
            "machine_code": "LATHE-REPLAY",
            "workshop_type": "turning",
            "active_order": "WO-REPLAY",
            "finished_quantity": 4,
            "target_rate": 1.0,
            "actual_rate": 0.9,
            "utilization": 0.7,
        },
    })
    part = first.create_ready_part("WO-REPLAY", "P3")
    command = first.add_command(
        "turning-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.92},
    )
    first.claim_pending_commands_for_node("turning-workshop-01", "pytest-agent")
    first.record_command_result("turning-workshop-01", command.id, "executed", "replay command executed")
    first.persist_event(IncidentEvent(
        id=9001,
        node_code="turning-workshop-01",
        severity=Severity.info,
        stage="replay-proof",
        message="replay proof event",
    ))

    first_report = first.replay_readiness_report()
    second = MemoryStore()
    second_report = second.replay_readiness_report()

    assert first_report["status"] == "ok"
    assert second_report["status"] == "ok"
    assert second_report["shadow"]["audit_events"] >= 1
    assert second_report["shadow"]["heartbeat_nodes"] >= 1
    assert "turning-workshop-01" in second_report["restored_cache"]["heartbeat_nodes"]
    assert command.id in second_report["restored_cache"]["commands"]
    assert part.part_id in second_report["restored_cache"]["part_queue_items"]
    assert second.node_heartbeats_v2["turning-workshop-01"]["runtime"]["run_id"] == "RUN-REPLAY-001"


def test_heartbeat_shadow_retention_keeps_latest_rows_per_node(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    monkeypatch.setattr(settings, "heartbeat_shadow_retention_per_node", 2)

    store = MemoryStore()
    for index in range(5):
        store.record_node_heartbeat_v2({
            "node_code": "turning-workshop-01",
            "status": "running",
            "runtime": {
                "run_id": f"RUN-RETENTION-{index}",
                "scenario_id": "SCN-RETENTION",
                "simulation_engine": "simpy",
                "runtime_source": "node-agent",
            },
            "metrics": {"cpu_usage": 10 + index, "memory_usage": 20, "disk_usage": 30},
            "production": {
                "machine_code": "LATHE-RETENTION",
                "workshop_type": "turning",
                "finished_quantity": index,
                "target_rate": 1.0,
                "actual_rate": 0.9,
                "utilization": 0.7,
            },
        })

    with database.get_db() as db:
        rows = db.execute(
            """SELECT run_id FROM heartbeat_shadow
               WHERE node_code = ?
               ORDER BY id ASC""",
            ("turning-workshop-01",),
        ).fetchall()

    status = store.persistence_status()
    run_ids = [row["run_id"] for row in rows]

    assert run_ids == ["RUN-RETENTION-3", "RUN-RETENTION-4"]
    assert status["retention"]["heartbeat_shadow_per_node"] == 2
    assert status["retention"]["heartbeat_shadow_policy"] == "keep_latest_per_node"
    assert status["replay_readiness"]["status"] == "ok"


def test_replay_api_rebuilds_run_timeline_from_persistence(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models import Severity
    from app.store import store

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    database.init_db()

    run_id = "RUN-REPLAY-API-001"
    node_code = "turning-workshop-01"
    first_heartbeat = {
        "node_code": node_code,
        "status": "running",
        "runtime": {
            "run_id": run_id,
            "scenario_id": "SCN-REPLAY-API",
            "simulation_engine": "simpy",
            "runtime_source": "node-agent",
        },
        "metrics": {"cpu_usage": 31, "memory_usage": 42, "disk_usage": 53},
        "production": {
            "machine_code": "LATHE-REPLAY-API",
            "workshop_type": "turning",
            "active_order": "WO-REPLAY-API",
            "finished_quantity": 8,
            "target_rate": 1.0,
            "actual_rate": 0.96,
            "utilization": 0.74,
            "defect_rate": 0.01,
        },
    }
    store.record_node_heartbeat_v2(first_heartbeat)
    part = store.create_ready_part("WO-REPLAY-API", "P3")
    command = store.add_command(
        node_code,
        "replay_api_adjust_feed_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.96},
    )
    store.claim_pending_commands_for_node(node_code, "pytest-agent")
    store.record_command_result(node_code, command.id, "executed", "replay api command executed")
    alert = store.create_alert(node_code, "replay_api_alarm", Severity.medium, "Replay API proof alert", "ai")
    store.add_ai_diagnosis(
        alert.id,
        node_code,
        "Replay test root cause",
        "Replay test recommended action",
        0.88,
        False,
        "pytest-rule",
    )
    store.record_node_heartbeat_v2({
        **first_heartbeat,
        "production": {
            **first_heartbeat["production"],
            "finished_quantity": 9,
            "actual_rate": 0.98,
            "utilization": 0.76,
        },
    })

    with TestClient(app) as client:
        runs = client.get("/api/replay/runs", headers={"X-OGAS-Token": "mini-ogas-dev-token"})
        detail = client.get(f"/api/replay/runs/{run_id}", headers={"X-OGAS-Token": "mini-ogas-dev-token"})
        missing = client.get("/api/replay/runs/RUN-DOES-NOT-EXIST", headers={"X-OGAS-Token": "mini-ogas-dev-token"})

    assert runs.status_code == 200
    assert detail.status_code == 200
    assert missing.status_code == 404
    assert run_id in {item["run_id"] for item in runs.json()["runs"]}

    payload = detail.json()
    assert payload["status"] == "ok"
    assert payload["run_id"] == run_id
    assert payload["counts"]["heartbeats"] == 2
    assert payload["counts"]["commands"] >= 1
    assert payload["counts"]["part_queue"] >= 1
    assert payload["counts"]["audit_events"] >= 1
    assert payload["counts"]["alerts"] >= 1
    assert payload["counts"]["ai_diagnoses"] >= 1
    assert part.part_id in {item["part_id"] for item in payload["part_queue"]}
    assert command.id in {item["command_id"] for item in payload["commands"]}
    assert {"heartbeat", "command", "part_queue", "audit", "alert", "ai_diagnosis"}.issubset(
        {item["kind"] for item in payload["timeline"]}
    )


def test_replay_run_uses_full_bounds_and_latest_heartbeat_sample(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    database.init_db()

    run_id = "RUN-BOUNDS-001"
    for index in range(4):
        payload = {
            "node_code": "turning-workshop-01",
            "status": "running",
            "runtime": {
                "run_id": run_id,
                "scenario_id": "SCN-BOUNDS",
                "simulation_engine": "simpy",
            },
            "production": {
                "machine_code": f"LATHE-{index}",
                "active_order": "P1",
                "utilization": 0.6 + index / 100,
            },
        }
        with database.get_db() as db:
            db.execute(
                """INSERT INTO heartbeat_shadow (
                   node_code, run_id, scenario_id, simulation_time, payload_json, received_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    "turning-workshop-01",
                    run_id,
                    "SCN-BOUNDS",
                    None,
                    json.dumps(payload),
                    f"2026-07-03T10:0{index}:00+00:00",
                ),
            )

    replay_store = MemoryStore()
    runs = replay_store.replay_runs()
    result = replay_store.replay_run(run_id, max_rows=2)
    run_summary = next(item for item in runs["runs"] if item["run_id"] == run_id)

    assert run_summary["started_at"] == "2026-07-03T10:00:00+00:00"
    assert run_summary["ended_at"] == "2026-07-03T10:03:00+00:00"
    assert run_summary["heartbeat_count"] == 4
    assert result["status"] == "ok"
    assert result["started_at"] == "2026-07-03T10:00:00+00:00"
    assert result["ended_at"] == "2026-07-03T10:03:00+00:00"
    assert result["counts"]["heartbeats"] == 4
    assert result["sampling"]["heartbeat_rows"] == 2
    assert result["sampling"]["heartbeats_truncated"] is True
    assert [item["machine_code"] for item in result["heartbeats"]] == ["LATHE-2", "LATHE-3"]


def test_replay_run_prefers_exact_run_id_for_operational_facts(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    database.init_db()

    run_id = "RUN-EXACT-FACTS-001"
    payload = {
        "node_code": "turning-workshop-01",
        "status": "running",
        "runtime": {"run_id": run_id, "scenario_id": "SCN-EXACT", "simulation_engine": "simpy"},
        "production": {"machine_code": "LATHE-EXACT", "active_order": "P1"},
    }
    with database.get_db() as db:
        for timestamp in ("2026-07-04T10:00:00+00:00", "2026-07-04T10:01:00+00:00"):
            db.execute(
                """INSERT INTO heartbeat_shadow (
                   node_code, run_id, scenario_id, simulation_time, payload_json, received_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                ("turning-workshop-01", run_id, "SCN-EXACT", None, json.dumps(payload), timestamp),
            )
        db.execute(
            """
            INSERT INTO command_shadow (
                command_id, run_id, node_code, command_type, risk_level, status, operator,
                parameters_json, claimed_by, result_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7788,
                run_id,
                "turning-workshop-01",
                "exact_run_id_command",
                "low",
                "executed",
                "pytest",
                "{}",
                "pytest-agent",
                "matched by run_id outside timestamp window",
                "2026-07-05T12:00:00+00:00",
                "2026-07-05T12:00:00+00:00",
            ),
        )

    result = MemoryStore().replay_run(run_id, max_rows=10)

    assert result["status"] == "ok"
    assert result["started_at"] == "2026-07-04T10:00:00+00:00"
    assert result["ended_at"] == "2026-07-04T10:01:00+00:00"
    assert 7788 in {item["command_id"] for item in result["commands"]}
    command = next(item for item in result["commands"] if item["command_id"] == 7788)
    assert command["run_id"] == run_id
    assert command["result_message"] == "matched by run_id outside timestamp window"
