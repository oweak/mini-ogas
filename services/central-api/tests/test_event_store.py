from app.core import database
from app.core.config import settings
from app.models import Severity
from app.store import MemoryStore


def test_event_envelope_is_ordered_idempotent_and_restart_restorable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(tmp_path / "events.db"))
    monkeypatch.setattr(settings, "central_fact_source", "memory")

    first = MemoryStore()
    first.record_node_heartbeat_v2({
        "node_code": "turning-workshop-01",
        "status": "running",
        "runtime": {
            "simulation_engine": "simpy",
            "run_id": "RUN-EVENT-001",
            "scenario_id": "SCN-EVENT-001",
            "random_seed": 7,
        },
        "metrics": {},
        "production": {
            "machine_code": "LATHE-01",
            "workshop_type": "turning",
            "target_rate": 1.333,
            "actual_rate": 1.1,
            "wip_input": 8,
            "wip_output": 5,
        },
    })
    event = first.add_event(
        "turning-workshop-01",
        "capacity-observed",
        Severity.info,
        "physical capacity observation",
    )
    first.persist_event(event)

    assert event.event_type == "capacity-observed"
    assert event.schema_version == "2.5"
    assert event.source_node == "turning-workshop-01"
    assert event.run_id == "RUN-EVENT-001"
    assert event.scenario_id == "SCN-EVENT-001"
    assert event.local_sequence > 0
    assert event.global_sequence > 0
    assert event.correlation_id
    assert event.payload["message"] == "physical capacity observation"

    with database.get_db() as db:
        count = int(db.execute(
            "SELECT COUNT(*) AS count FROM event_store WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()["count"])
    assert count == 1

    second = MemoryStore()
    restored = next(item for item in second.incident_events if item.event_id == event.event_id)
    assert restored.global_sequence == event.global_sequence
    assert restored.local_sequence == event.local_sequence
    assert restored.run_id == event.run_id
    assert restored.payload == event.payload
