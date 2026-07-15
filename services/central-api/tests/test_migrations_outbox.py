import sqlite3
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.core.database import (
    PHASE1_SCOPE_MIGRATION_VERSION,
    SCOPED_TABLES,
    get_db,
    init_db,
)
from app.core.migrations import Migration, apply_migrations
from app.core.nats_contracts import build_heartbeat_envelope
from app.core.outbox import outbox_repository
from app.persistence_repository import central_fact_repository


def heartbeat_payload() -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "node_code": "turning-workshop-01",
        "status": "running",
        "timestamp": timestamp,
        "agent_version": "0.3.0",
        "uptime_sec": 30,
        "metrics": {
            "cpu_usage": 20.0,
            "memory_usage": 30.0,
            "disk_usage": 40.0,
            "db_latency_ms": 5,
            "network_latency_ms": 6,
        },
        "production": {
            "workshop_type": "turning",
            "machine_code": "LATHE-01",
            "finished_quantity": 3,
            "defect_quantity": 0,
            "target_rate": 0.8,
            "actual_rate": 0.7,
            "rate_unit": "parts_per_minute",
            "utilization": 0.7,
            "defect_rate": 0.0,
            "wip_input": 4,
            "wip_output": 3,
        },
        "alarms": [],
        "sync": {"last_sync_id": 1, "pending_records": 0},
        "runtime": {
            "run_id": "RUN-MIGRATION-OUTBOX",
            "scenario_id": "SCN-MIGRATION-OUTBOX",
            "simulation_engine": "simpy",
            "simulation_mode": "normal",
            "simulation_speed": 1,
            "random_seed": 42,
            "simulation_time": timestamp,
            "wall_clock_time": timestamp,
            "deployment_mode": "process",
            "runtime_source": "simulated",
            "clock_offset_ms": 0,
            "clock_synchronized": True,
        },
        "_received_at": timestamp,
    }


@pytest.fixture
def scoped_sqlite(monkeypatch, tmp_path):
    db_path = tmp_path / "phase1.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    monkeypatch.setattr(settings, "tenant_id", "tenant-test")
    monkeypatch.setattr(settings, "site_id", "site-test")
    monkeypatch.setattr(settings, "nats_enabled", True)
    init_db()
    return db_path


def test_phase1_migration_is_repeatable_and_scopes_every_fact_table(scoped_sqlite) -> None:
    init_db()

    with sqlite3.connect(scoped_sqlite) as db:
        rows = db.execute(
            "SELECT version, checksum FROM schema_migrations WHERE version = ?",
            (PHASE1_SCOPE_MIGRATION_VERSION,),
        ).fetchall()
        assert len(rows) == 1
        assert len(rows[0][1]) == 64
        for table_name in SCOPED_TABLES:
            columns = {row[1] for row in db.execute(f"PRAGMA table_info({table_name})")}
            assert {"tenant_id", "site_id"}.issubset(columns), table_name


def test_migration_checksum_drift_fails_closed(scoped_sqlite) -> None:
    noop = lambda _connection: None
    changed = Migration(
        version=PHASE1_SCOPE_MIGRATION_VERSION,
        description="changed migration",
        checksum_material="tampered",
        sqlite_action=noop,
        postgres_action=noop,
    )
    with sqlite3.connect(scoped_sqlite) as db:
        db.row_factory = sqlite3.Row
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            apply_migrations(db, "sqlite", [changed])


def test_heartbeat_and_outbox_enqueue_commit_in_one_transaction(scoped_sqlite) -> None:
    payload = heartbeat_payload()
    expected_id = build_heartbeat_envelope(payload).message_id

    central_fact_repository.persist_heartbeat(payload, retention_per_node=10)

    with sqlite3.connect(scoped_sqlite) as db:
        heartbeat_count = db.execute("SELECT COUNT(*) FROM heartbeat_shadow").fetchone()[0]
        outbox_row = db.execute(
            "SELECT message_id, tenant_id, site_id, status FROM outbox_messages"
        ).fetchone()
    assert heartbeat_count == 1
    assert outbox_row == (expected_id, "tenant-test", "site-test", "pending")


def test_outbox_claim_publish_and_scope_filter_are_operational(scoped_sqlite) -> None:
    envelope = build_heartbeat_envelope(heartbeat_payload())
    with get_db() as db:
        assert outbox_repository.enqueue_in_transaction(db, envelope) is True
        db.execute(
            """INSERT INTO outbox_messages (
                   message_id, tenant_id, site_id, aggregate_type, aggregate_id,
                   message_type, subject, schema_version, payload_json, status
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                "other-scope-message",
                "tenant-other",
                "site-other",
                "heartbeat",
                "other-node",
                "heartbeat",
                "ogas.heartbeats.other-node",
                "3.0",
                "{}",
            ),
        )

    claimed = outbox_repository.claim_pending(limit=10)
    assert [item["message_id"] for item in claimed] == [envelope.message_id]
    assert outbox_repository.mark_published(envelope.message_id) is True
    status = outbox_repository.status()
    assert status["pending"] == 0
    assert status["counts"]["published"] == 1
