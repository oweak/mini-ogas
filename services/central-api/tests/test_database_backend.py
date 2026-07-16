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
        migration_versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }

    assert "run_id" in columns
    assert "idx_command_shadow_run_updated" in indexes
    assert database.SCHEMA_VERSION in migration_versions


def test_shadow_consistency_report_is_explicit_when_persistence_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import store

    monkeypatch.setattr(settings, "persist_enabled", False)

    assert store.shadow_consistency_report()["status"] == "disabled"


def test_primary_projection_refreshes_all_durable_read_models(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import store as store_module
    from app.store import store

    calls: list[str] = []
    store._persistence_write_failures.clear()

    class _Cursor:
        def fetchone(self):
            return {"ok": 1}

    class _Db:
        def execute(self, _sql, _params=()):
            return _Cursor()

    class _DbContext:
        def __enter__(self):
            return _Db()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "central_fact_source", "postgresql")
    monkeypatch.setattr(store_module, "persistence_backend", lambda: "postgres")
    monkeypatch.setattr(store_module, "get_db", lambda: _DbContext())
    for name in (
        "load_heartbeat_shadow",
        "load_command_shadow",
        "load_part_queue_shadow",
        "load_alert_shadow",
        "load_ai_diagnosis_shadow",
        "load_audit_log_shadow",
        "load_allocation_order_shadow",
        "load_production_plan_shadow",
        "load_dispatch_task_shadow",
    ):
        monkeypatch.setattr(store, name, lambda *args, _name=name, **kwargs: calls.append(_name) or 1)

    result = store.refresh_primary_projection(force=True)

    assert result["status"] == "ok"
    assert result["fact_source"] == "postgresql"
    assert result["read_model"] == "database_projection"
    assert calls == [
        "load_heartbeat_shadow",
        "load_command_shadow",
        "load_part_queue_shadow",
        "load_alert_shadow",
        "load_ai_diagnosis_shadow",
        "load_audit_log_shadow",
        "load_allocation_order_shadow",
        "load_production_plan_shadow",
        "load_dispatch_task_shadow",
    ]


def test_primary_projection_reports_loader_failure_as_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import store as store_module
    from app.store import store

    class _Cursor:
        def fetchone(self):
            return {"ok": 1}

    class _Db:
        def execute(self, _sql, _params=()):
            return _Cursor()

    class _DbContext:
        def __enter__(self):
            return _Db()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "central_fact_source", "postgresql")
    monkeypatch.setattr(store_module, "persistence_backend", lambda: "postgres")
    monkeypatch.setattr(store_module, "get_db", lambda: _DbContext())
    monkeypatch.setattr(store, "load_heartbeat_shadow", lambda **_kwargs: 1)
    monkeypatch.setattr(store, "load_command_shadow", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("query failed")))

    result = store.refresh_primary_projection(force=True)

    assert result["status"] == "degraded"
    assert result["fact_source"] == "memory-cache"
    assert result["read_model"] == "stale_cache"
    assert "query failed" in result["last_error"]


def test_unreconciled_write_failure_degrades_primary_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import store as store_module
    from app.store import store

    class _Cursor:
        def fetchone(self):
            return {"ok": 1}

    class _Db:
        def execute(self, _sql, _params=()):
            return _Cursor()

    class _DbContext:
        def __enter__(self):
            return _Db()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "central_fact_source", "postgresql")
    monkeypatch.setattr(store_module, "persistence_backend", lambda: "postgres")
    monkeypatch.setattr(store_module, "get_db", lambda: _DbContext())
    for name in (
        "load_heartbeat_shadow",
        "load_command_shadow",
        "load_part_queue_shadow",
        "load_alert_shadow",
        "load_ai_diagnosis_shadow",
        "load_audit_log_shadow",
        "load_allocation_order_shadow",
        "load_production_plan_shadow",
        "load_dispatch_task_shadow",
    ):
        monkeypatch.setattr(store, name, lambda **_kwargs: 1)

    store._persistence_write_failures.clear()
    store._record_persistence_write_failure("command_shadow", RuntimeError("database unavailable"))
    try:
        result = store.refresh_primary_projection(force=True)
    finally:
        store._persistence_write_failures.clear()

    assert result["status"] == "degraded"
    assert result["fact_source"] == "postgresql"
    assert result["write_failures"][0]["operation"] == "command_shadow"


def test_command_and_audit_event_transaction_rolls_back_together(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.persistence_repository import central_fact_repository
    from app.store import MemoryStore

    db_path = tmp_path / "command-event-transaction.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    database.init_db()
    transactional_store = MemoryStore()

    def fail_event_insert(*_args, **_kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(central_fact_repository, "_insert_event", fail_event_insert)
    command = transactional_store.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "pytest",
        parameters={"target_rate": 0.73},
    )

    with database.get_db() as db:
        base_count = int(db.execute("SELECT COUNT(*) AS count FROM commands").fetchone()["count"])
        shadow_count = int(db.execute(
            "SELECT COUNT(*) AS count FROM command_shadow WHERE command_id = ?",
            (command.id,),
        ).fetchone()["count"])
        event_count = int(db.execute(
            "SELECT COUNT(*) AS count FROM audit_logs WHERE resource_type = ? AND resource_id = ?",
            ("incident_event", str(transactional_store.incident_events[-1].id)),
        ).fetchone()["count"])

    assert base_count == 0
    assert shadow_count == 0
    assert event_count == 0
    assert transactional_store._persistence_write_failures["command_event_transaction"]["count"] == 1


def test_event_sequences_rebase_when_store_instances_overlap(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import Severity
    from app.store import MemoryStore

    db_path = tmp_path / "overlapping-event-writers.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    database.init_db()

    first = MemoryStore()
    stale_second = MemoryStore()
    first_event = first.add_event("milling-workshop-01", "writer-one", Severity.info, "first")
    second_event = stale_second.add_event(
        "milling-workshop-01",
        "writer-two",
        Severity.info,
        "second",
    )

    with database.get_db() as db:
        rows = db.execute(
            """SELECT local_sequence, global_sequence, event_type
               FROM event_store
               WHERE source_node = ? AND run_id = ?
               ORDER BY local_sequence""",
            ("milling-workshop-01", ""),
        ).fetchall()

    assert [dict(row)["local_sequence"] for row in rows] == [1, 2]
    assert [dict(row)["global_sequence"] for row in rows] == [1, 2]
    assert [dict(row)["event_type"] for row in rows] == ["writer-one", "writer-two"]
    assert first_event.local_sequence == 1
    assert second_event.local_sequence == 2
    assert second_event.id == 2
    assert stale_second._persistence_write_failures == {}


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
    database.init_db()

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


def test_alert_ai_and_audit_shadows_survive_new_store_instance(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models import Severity
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    database.init_db()

    first = MemoryStore()
    first.record_node_heartbeat_v2({
        "node_code": "milling-workshop-01",
        "status": "running",
        "runtime": {
            "run_id": "RUN-ALERT-AI-AUDIT",
            "scenario_id": "SCN-ALERT-AI-AUDIT",
            "simulation_engine": "simpy",
            "runtime_source": "node-agent",
        },
        "metrics": {"cpu_usage": 21, "memory_usage": 32, "disk_usage": 43},
        "production": {
            "machine_code": "MILL-AUDIT",
            "workshop_type": "milling",
            "active_order": "WO-AUDIT",
            "finished_quantity": 12,
            "target_rate": 1.0,
            "actual_rate": 0.97,
            "utilization": 0.78,
        },
    })
    alert = first.create_alert(
        "milling-workshop-01",
        "pytest_spindle_vibration",
        Severity.high,
        "pytest spindle vibration",
        "ai",
    )
    diagnosis = first.add_ai_diagnosis(
        alert.id,
        "milling-workshop-01",
        "bearing vibration exceeds learned baseline",
        "reduce spindle speed and request operator inspection",
        0.86,
        True,
        "pytest-provider",
        raw_response='{"provider":"pytest","risk":"high"}',
    )
    alert.status = "closed"
    alert.handled_by = "pytest-operator"
    first.persist_alert_state(alert)
    first.add_audit_log(
        "pytest-operator",
        "issue:close",
        "issue",
        f"{alert.node_code}-{alert.alert_type}",
        "closed",
        "operator accepted AI recommendation",
    )

    second = MemoryStore()
    restored_alert = next(item for item in second.alerts if item.id == alert.id)
    restored_diagnosis = next(item for item in second.ai_diagnoses if item.id == diagnosis.id)
    readiness = second.replay_readiness_report()
    consistency = second.shadow_consistency_report()

    assert restored_alert.status == "closed"
    assert restored_alert.handled_by == "pytest-operator"
    assert restored_diagnosis.raw_response == '{"provider":"pytest","risk":"high"}'
    assert any(item.action == "issue:close" for item in second.audit_logs)
    assert readiness["status"] == "ok"
    assert consistency["status"] == "ok"
    assert alert.id in readiness["restored_cache"]["alerts"]
    assert diagnosis.id in readiness["restored_cache"]["ai_diagnoses"]
    assert readiness["shadow"]["audit_events"] >= readiness["live"]["audit_logs"]


def test_alert_state_write_updates_current_projection_after_stale_reference(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import Severity
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    database.init_db()

    store = MemoryStore()
    stale_alert = store.create_alert(
        "milling-workshop-01",
        "pytest_projection_race",
        Severity.high,
        "projection refresh race",
        "human-required",
    )
    current_alert = stale_alert.model_copy(update={"status": "confirmed"})
    store.alerts = [
        current_alert if item.id == stale_alert.id else item
        for item in store.alerts
    ]

    stale_alert.status = "diagnosed"
    store.persist_alert_state(stale_alert)

    assert next(item for item in store.alerts if item.id == stale_alert.id).status == "diagnosed"
    with database.get_db() as db:
        row = db.execute("SELECT status FROM alerts WHERE id=?", (stale_alert.id,)).fetchone()
    assert dict(row)["status"] == "diagnosed"


def test_planning_and_dispatch_shadows_survive_new_store_instance(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models import AllocationOrderIn
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    monkeypatch.setattr(settings, "microservices_enabled", False)
    database.init_db()

    first = MemoryStore()
    order = first.submit_allocation_order(AllocationOrderIn(
        product_code="P4",
        required_quantity=41,
        priority=1,
        deadline_hours=8,
        assigned_cloud_role="pytest-dispatch",
        source_unit="pytest-suite",
        reason="persist planning layer",
    ))

    first_report = first.replay_readiness_report()
    second = MemoryStore()
    second_report = second.replay_readiness_report()

    assert first_report["status"] == "ok"
    assert second_report["status"] == "ok"
    assert order.order_id in {item.order_id for item in second.allocation_orders}
    assert any(plan.product_code == "P4" for plan in second.production_plans)
    assert len(second.dispatch_tasks) > 0
    assert second_report["shadow"]["production_plans"] >= len(second.production_plans)
    assert second_report["shadow"]["dispatch_tasks"] >= len(second.dispatch_tasks)
    assert second_report["shadow"]["allocation_orders"] >= len(second.allocation_orders)
    assert order.order_id in second_report["restored_cache"]["allocation_orders"]


def test_heartbeat_shadow_retention_keeps_latest_rows_per_node(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    monkeypatch.setattr(settings, "heartbeat_shadow_retention_per_node", 2)
    database.init_db()

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


def test_heartbeat_upserts_scenario_and_run_entities(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.store import MemoryStore

    db_path = tmp_path / "central.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    database.init_db()

    store = MemoryStore()
    store.record_node_heartbeat_v2({
        "node_code": "turning-workshop-01",
        "status": "running",
        "runtime": {
            "run_id": "RUN-ENTITY-001",
            "scenario_id": "SCN-ENTITY-001",
            "simulation_engine": "simpy",
            "simulation_mode": "normal",
            "random_seed": 260713,
        },
        "metrics": {"cpu_usage": 20, "memory_usage": 30, "disk_usage": 40},
        "production": {"machine_code": "LATHE-01", "workshop_type": "turning"},
    })

    with database.get_db() as db:
        scenario = dict(db.execute(
            "SELECT * FROM scenarios WHERE scenario_id = ?",
            ("SCN-ENTITY-001",),
        ).fetchone())
        run = dict(db.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            ("RUN-ENTITY-001",),
        ).fetchone())

    assert scenario["simulation_engine"] == "simpy"
    assert scenario["random_seed"] == 260713
    assert run["scenario_id"] == "SCN-ENTITY-001"
    assert run["status"] == "running"
    assert run["random_seed"] == 260713


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

    state_before_replay = {
        "heartbeats": json.dumps(store.node_heartbeats_v2, sort_keys=True, default=str),
        "commands": [(item.id, item.status, item.updated_at) for item in store.commands],
        "parts": [(item.part_id, item.status, item.updated_at) for item in store.part_queue],
        "alerts": [(item.id, item.status) for item in store.alerts],
    }
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
    assert payload["data_source"] == "replay"
    assert payload["read_only"] is True
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
    assert state_before_replay == {
        "heartbeats": json.dumps(store.node_heartbeats_v2, sort_keys=True, default=str),
        "commands": [(item.id, item.status, item.updated_at) for item in store.commands],
        "parts": [(item.part_id, item.status, item.updated_at) for item in store.part_queue],
        "alerts": [(item.id, item.status) for item in store.alerts],
    }


def test_offline_node_records_are_durable_deduplicated_and_do_not_regress_live_projection(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.store import MemoryStore

    db_path = tmp_path / "offline-sync.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    database.init_db()

    node_code = "turning-workshop-01"
    live = {
        "node_code": node_code,
        "timestamp": "2026-07-13T03:00:00+00:00",
        "status": "running",
        "runtime": {
            "run_id": "RUN-OFFLINE-SYNC",
            "scenario_id": "SCN-OFFLINE-SYNC",
            "simulation_engine": "simpy",
            "random_seed": 42,
            "simulation_time": "2026-07-13T03:00:00+00:00",
        },
        "metrics": {"cpu_usage": 20, "memory_usage": 30, "disk_usage": 40},
        "production": {
            "machine_code": "LATHE-SYNC",
            "workshop_type": "turning",
            "finished_quantity": 20,
            "target_rate": 1.0,
            "actual_rate": 0.9,
            "utilization": 0.75,
        },
    }
    store = MemoryStore()
    store.record_node_heartbeat_v2(live)
    projection_before = json.dumps(store.node_heartbeats_v2[node_code], sort_keys=True, default=str)
    records = [
        {
            "local_id": 2,
            "created_at": "2026-07-13T02:00:00+00:00",
            "payload": {
                **live,
                "timestamp": "2026-07-13T02:00:00+00:00",
                "production": {**live["production"], "finished_quantity": 12},
            },
        },
        {
            "local_id": 1,
            "created_at": "2026-07-13T01:00:00+00:00",
            "payload": {
                **live,
                "timestamp": "2026-07-13T01:00:00+00:00",
                "production": {**live["production"], "finished_quantity": 5},
            },
        },
    ]

    first = store.record_node_records(node_code, records)
    duplicate = store.record_node_records(node_code, list(reversed(records)))
    projection_after = json.dumps(store.node_heartbeats_v2[node_code], sort_keys=True, default=str)
    restored = MemoryStore()

    with database.get_db() as db:
        receipt_count = int(db.execute("SELECT COUNT(*) AS count FROM node_record_receipts").fetchone()["count"])
        heartbeat_count = int(db.execute("SELECT COUNT(*) AS count FROM heartbeat_shadow").fetchone()["count"])

    assert first["records_accepted"] == 2
    assert first["records_duplicate"] == 0
    assert duplicate["records_accepted"] == 0
    assert duplicate["records_duplicate"] == 2
    assert receipt_count == 2
    assert heartbeat_count == 3
    assert projection_after == projection_before
    assert restored.node_heartbeats_v2[node_code]["production"]["finished_quantity"] == 20

    conflicting = [{**records[0], "payload": {**records[0]["payload"], "status": "fault"}}]
    with pytest.raises(ValueError, match="identity conflict"):
        store.record_node_records(node_code, conflicting)


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
