from __future__ import annotations

from datetime import timedelta

import pytest
from app.core.config import settings
from app.models import NodeStatus, utc_now
from app.store import MemoryStore

NODE_FIELDS = {
    "nodes",
    "metrics",
    "runtime_metrics",
    "machines",
    "node_db_size_bytes",
    "node_db_size_sources",
    "node_heartbeats_v2",
    "node_record_sync_ids",
}


def _heartbeat() -> dict[str, object]:
    return {
        "node_code": "turning-workshop-01",
        "status": "running",
        "runtime": {
            "run_id": "RUN-NODE-REPOSITORY",
            "scenario_id": "SCN-NODE-REPOSITORY",
            "simulation_engine": "simpy",
            "simulation_mode": "normal",
            "random_seed": 260715,
        },
        "metrics": {
            "cpu_usage": 21,
            "memory_usage": 32,
            "disk_usage": 43,
            "api_latency_ms": 12,
        },
        "production": {
            "machine_code": "LATHE-NODE-REPOSITORY",
            "workshop_type": "turning",
            "target_rate": 1.0,
            "actual_rate": 0.94,
            "utilization": 0.72,
            "finished_quantity": 4,
            "defect_quantity": 0,
        },
    }


def test_memory_store_exposes_node_repository_without_duplicate_projection_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    state = MemoryStore()

    assert NODE_FIELDS.isdisjoint(state.__dict__)
    assert state.nodes is state.node_repository.nodes
    assert state.metrics is state.node_repository.metrics
    assert state.runtime_metrics is state.node_repository.runtime_metrics
    assert state.machines is state.node_repository.machines
    assert state.node_heartbeats_v2 is state.node_repository.heartbeats_v2


def test_node_repository_rebuilds_heartbeat_projection_after_restart(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "node-repository-restart.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    monkeypatch.setattr(settings, "demo_seed_enabled", False)

    first = MemoryStore()
    first.record_node_heartbeat_v2(_heartbeat())

    restarted = MemoryStore()

    assert NODE_FIELDS.isdisjoint(restarted.__dict__)
    assert "turning-workshop-01" in restarted.node_repository.nodes
    assert "turning-workshop-01" in restarted.node_repository.heartbeats_v2
    assert "turning-workshop-01" in restarted.node_repository.runtime_metrics
    machine = next(
        item
        for item in restarted.node_repository.machines
        if item.machine_code == "LATHE-NODE-REPOSITORY"
    )
    assert machine.node_code == "turning-workshop-01"
    assert machine.status == "running"
    assert restarted.node_repository.runtime_metrics["turning-workshop-01"].cpu_usage == 21


def test_restored_stale_heartbeat_cannot_make_node_look_online(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    state = MemoryStore()
    stale_at = utc_now() - timedelta(seconds=settings.heartbeat_timeout_seconds + 1)

    with state._lock:
        state._restore_heartbeat_shadow_locked(
            "turning-workshop-01",
            _heartbeat(),
            stale_at,
        )

    node = state.nodes["turning-workshop-01"]
    machine = next(item for item in state.machines if item.machine_code == "LATHE-NODE-REPOSITORY")
    readiness = state.production_node_readiness()

    assert node.status == NodeStatus.offline
    assert machine.status == "offline"
    assert readiness["healthy"] == []
    assert readiness["stale"] == ["turning-workshop-01"]
