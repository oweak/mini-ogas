from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.database import get_db, init_db
from app.core.nats_contracts import build_heartbeat_envelope, subject_for_envelope
from app.core.nats_reconciliation import nats_shadow_reconciler
from app.core.outbox import outbox_repository
from app.core.stage_e_schema import (
    STAGE_E_OUTBOX_ORDERING_VERSION,
    STAGE_E_SHADOW_METRICS_VERSION,
)
from app.persistence_repository import central_fact_repository


@pytest.fixture
def shadow_db(monkeypatch, tmp_path):
    db_path = tmp_path / "stage-e-shadow.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    monkeypatch.setattr(settings, "tenant_id", "tenant-test")
    monkeypatch.setattr(settings, "site_id", "site-test")
    monkeypatch.setattr(settings, "nats_enabled", True)
    monkeypatch.setattr(settings, "nats_reconciliation_grace_seconds", 10)
    monkeypatch.setattr(settings, "nats_reconciliation_window_messages", 100)
    monkeypatch.setattr(settings, "nats_reconciliation_min_samples", 1)
    monkeypatch.setattr(settings, "nats_min_receive_rate", 0.999)
    monkeypatch.setattr(settings, "nats_max_duplicate_rate", 0.01)
    monkeypatch.setattr(settings, "nats_max_p95_latency_ms", 5000)
    init_db()
    return db_path


def _payload(*, sequence: int, timestamp: datetime) -> dict[str, object]:
    iso_timestamp = timestamp.isoformat()
    return {
        "node_code": "turning-workshop-01",
        "status": "running",
        "timestamp": iso_timestamp,
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
            "finished_quantity": sequence,
            "defect_quantity": 0,
            "target_rate": 0.8,
            "actual_rate": 0.7,
            "rate_unit": "parts_per_minute",
            "utilization": 0.7,
            "defect_rate": 0.0,
            "wip_input": sequence + 1,
            "wip_output": sequence,
        },
        "alarms": [],
        "sync": {"last_sync_id": sequence, "pending_records": 0},
        "runtime": {
            "run_id": "RUN-STAGE-E",
            "scenario_id": "SCN-STAGE-E",
            "simulation_engine": "simpy",
            "simulation_mode": "normal",
            "simulation_speed": 1,
            "random_seed": 42,
            "simulation_time": iso_timestamp,
            "wall_clock_time": iso_timestamp,
            "deployment_mode": "process",
            "runtime_source": "simulated",
            "clock_offset_ms": 0,
            "clock_synchronized": True,
        },
    }


def _baseline() -> datetime:
    with get_db() as db:
        row = db.execute(
            "SELECT applied_at FROM schema_migrations WHERE version = ?",
            (STAGE_E_OUTBOX_ORDERING_VERSION,),
        ).fetchone()
    value = dict(row)["applied_at"]
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def _enqueue(sequence: int, created_at: datetime):
    envelope = build_heartbeat_envelope(
        _payload(sequence=sequence, timestamp=created_at),
        published_at=created_at,
    )
    with get_db() as db:
        assert outbox_repository.enqueue_in_transaction(db, envelope)
        db.execute(
            "UPDATE outbox_messages SET created_at=?, available_at=? WHERE message_id=?",
            (created_at.isoformat(), created_at.isoformat(), envelope.message_id),
        )
    return envelope


def _publish_and_receive(envelope, *, published_at: datetime, ingested_at: datetime) -> None:
    assert outbox_repository.mark_published(envelope.message_id)
    assert central_fact_repository.persist_nats_receipt(
        envelope.model_dump(mode="json"),
        subject_for_envelope(envelope),
    )
    with get_db() as db:
        db.execute(
            "UPDATE outbox_messages SET published_at=? WHERE message_id=?",
            (published_at.isoformat(), envelope.message_id),
        )
        db.execute(
            """UPDATE nats_shadow_receipts
               SET ingested_at=?, last_ingested_at=? WHERE message_id=?""",
            (ingested_at.isoformat(), ingested_at.isoformat(), envelope.message_id),
        )


def test_stage_e_migration_adds_durable_delivery_counters(shadow_db) -> None:
    with sqlite3.connect(shadow_db) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(nats_shadow_receipts)")}
        migration = db.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (STAGE_E_SHADOW_METRICS_VERSION,),
        ).fetchone()
        ordering_migration = db.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (STAGE_E_OUTBOX_ORDERING_VERSION,),
        ).fetchone()

    assert {"delivery_count", "duplicate_count", "last_ingested_at"}.issubset(columns)
    assert migration is not None and len(migration[0]) == 64
    assert ordering_migration is not None and len(ordering_migration[0]) == 64


def test_outbox_claim_blocks_newer_stream_message_behind_retry(shadow_db) -> None:
    baseline = _baseline()
    older = _enqueue(1, baseline + timedelta(seconds=1))
    newer = _enqueue(2, baseline + timedelta(seconds=2))
    with get_db() as db:
        db.execute(
            "UPDATE outbox_messages SET available_at=? WHERE message_id=?",
            ((baseline + timedelta(hours=1)).isoformat(), older.message_id),
        )
        db.execute(
            "UPDATE outbox_messages SET available_at=? WHERE message_id=?",
            (baseline.isoformat(), newer.message_id),
        )

    assert outbox_repository.claim_pending(limit=10) == []

    with get_db() as db:
        db.execute(
            "UPDATE outbox_messages SET available_at=? WHERE message_id=?",
            (baseline.isoformat(), older.message_id),
        )
    first = outbox_repository.claim_pending(limit=10)
    assert [item["message_id"] for item in first] == [older.message_id]
    assert outbox_repository.mark_published(older.message_id)

    second = outbox_repository.claim_pending(limit=10)
    assert [item["message_id"] for item in second] == [newer.message_id]


def test_duplicate_delivery_is_persisted_and_remains_idempotent(shadow_db) -> None:
    envelope = _enqueue(1, _baseline() + timedelta(seconds=1))
    payload = envelope.model_dump(mode="json")
    subject = subject_for_envelope(envelope)

    assert central_fact_repository.persist_nats_receipt(payload, subject) is True
    assert central_fact_repository.persist_nats_receipt(payload, subject) is False

    with get_db() as db:
        row = db.execute(
            """SELECT delivery_count, duplicate_count
               FROM nats_shadow_receipts WHERE message_id=?""",
            (envelope.message_id,),
        ).fetchone()
    assert dict(row) == {"delivery_count": 2, "duplicate_count": 1}


def test_reconciliation_reports_matched_rate_latency_and_no_auto_cutover(shadow_db) -> None:
    baseline = _baseline()
    envelope = _enqueue(1, baseline + timedelta(seconds=1))
    _publish_and_receive(
        envelope,
        published_at=baseline + timedelta(seconds=2),
        ingested_at=baseline + timedelta(seconds=3),
    )

    report = nats_shadow_reconciler.report(now=baseline + timedelta(seconds=4))

    assert report["status"] == "ready"
    assert report["counts"]["matched_receipts"] == 1
    assert report["rates"] == {"receive_rate": 1.0, "duplicate_rate": 0.0}
    assert report["latency_ms"]["p95"] == 2000.0
    assert report["postgresql_reconciliation"]["status"] == "matched"
    assert report["thresholds_met"] is True
    assert report["cutover_eligible"] is False


def test_latency_violation_does_not_mislabel_postgresql_reconciliation(
    shadow_db, monkeypatch
) -> None:
    baseline = _baseline()
    envelope = _enqueue(1, baseline + timedelta(seconds=1))
    _publish_and_receive(
        envelope,
        published_at=baseline + timedelta(seconds=2),
        ingested_at=baseline + timedelta(seconds=3),
    )
    monkeypatch.setattr(settings, "nats_max_p95_latency_ms", 100)

    report = nats_shadow_reconciler.report(now=baseline + timedelta(seconds=4))

    assert report["status"] == "degraded"
    assert "latency_above_threshold" in report["violations"]
    assert report["postgresql_reconciliation"]["status"] == "matched"


def test_reconciliation_distinguishes_fresh_catchup_from_stale_outage(shadow_db) -> None:
    baseline = _baseline()
    _enqueue(1, baseline + timedelta(seconds=1))

    fresh = nats_shadow_reconciler.report(now=baseline + timedelta(seconds=5))
    stale = nats_shadow_reconciler.report(now=baseline + timedelta(seconds=20))

    assert fresh["status"] == "catching_up"
    assert fresh["counts"]["fresh_pending"] == 1
    assert stale["status"] == "degraded"
    assert stale["counts"]["stale_pending"] == 1
    assert "stale_outbox_pending" in stale["violations"]


def test_reconciliation_detects_receipt_order_divergence(shadow_db) -> None:
    baseline = _baseline()
    sequence_two = _enqueue(2, baseline + timedelta(seconds=1))
    sequence_one = _enqueue(1, baseline + timedelta(seconds=2))
    _publish_and_receive(
        sequence_two,
        published_at=baseline + timedelta(seconds=2),
        ingested_at=baseline + timedelta(seconds=3),
    )
    _publish_and_receive(
        sequence_one,
        published_at=baseline + timedelta(seconds=3),
        ingested_at=baseline + timedelta(seconds=4),
    )

    report = nats_shadow_reconciler.report(now=baseline + timedelta(seconds=5))

    assert report["status"] == "degraded"
    assert report["ordering"]["comparisons"] == 1
    assert report["ordering"]["divergences"] == 1
    assert "order_divergence_detected" in report["violations"]


def test_outbox_batch_preserves_fact_for_retry_when_nats_is_down(shadow_db, monkeypatch) -> None:
    from app import worker

    envelope = _enqueue(1, _baseline() + timedelta(seconds=1))
    with get_db() as db:
        db.execute(
            "UPDATE outbox_messages SET available_at=? WHERE message_id=?",
            (_baseline().isoformat(), envelope.message_id),
        )

    async def degraded_publish(_envelope):
        return SimpleNamespace(status="degraded", error_category="connection")

    monkeypatch.setattr(worker.nats_runtime, "publish_envelope", degraded_publish)
    result = asyncio.run(worker.publish_outbox_batch(limit=10))

    with get_db() as db:
        row = db.execute(
            "SELECT status, attempts, last_error FROM outbox_messages WHERE message_id=?",
            (envelope.message_id,),
        ).fetchone()
    assert result == {"claimed": 1, "published": 0, "retried": 1, "dead_lettered": 0}
    assert dict(row) == {"status": "pending", "attempts": 1, "last_error": "connection"}


def test_outbox_batch_marks_success_only_after_transport_publish(shadow_db, monkeypatch) -> None:
    from app import worker

    envelope = _enqueue(1, _baseline() + timedelta(seconds=1))
    with get_db() as db:
        db.execute(
            "UPDATE outbox_messages SET available_at=? WHERE message_id=?",
            (_baseline().isoformat(), envelope.message_id),
        )

    async def successful_publish(_envelope):
        return SimpleNamespace(status="published", error_category="")

    monkeypatch.setattr(worker.nats_runtime, "publish_envelope", successful_publish)
    result = asyncio.run(worker.publish_outbox_batch(limit=10))

    with get_db() as db:
        row = db.execute(
            "SELECT status, attempts FROM outbox_messages WHERE message_id=?",
            (envelope.message_id,),
        ).fetchone()
    assert result == {"claimed": 1, "published": 1, "retried": 0, "dead_lettered": 0}
    assert dict(row) == {"status": "published", "attempts": 1}
