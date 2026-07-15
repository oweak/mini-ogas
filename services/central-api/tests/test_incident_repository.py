from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.core.config import settings
from app.models import Severity
from app.repositories.incidents import IncidentRepository
from app.store import MemoryStore

INCIDENT_FIELDS = {
    "alerts",
    "audit_logs",
    "incident_events",
    "_incident_event_seq",
    "_node_event_sequences",
    "_shadow_event_count",
    "ai_diagnoses",
}
APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_memory_store_exposes_one_incident_repository_without_duplicate_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    state = MemoryStore()

    assert INCIDENT_FIELDS.isdisjoint(state.__dict__)
    assert isinstance(state.incident_repository, IncidentRepository)
    assert state.alerts is state.incident_repository.alerts
    assert state.audit_logs is state.incident_repository.audit_logs
    assert state.incident_events is state.incident_repository.events
    assert state.ai_diagnoses is state.incident_repository.ai_diagnoses


def test_incident_repository_owns_global_and_per_run_event_sequences() -> None:
    repository = IncidentRepository()
    occurred_at = datetime(2026, 7, 15, tzinfo=UTC)

    first = repository.append_event(
        node_code="turning-workshop-01",
        stage="observed",
        severity=Severity.info,
        message="first",
        run_id="RUN-INCIDENT-1",
        scenario_id="SCN-INCIDENT-1",
        occurred_at=occurred_at,
    )
    second = repository.append_event(
        node_code="turning-workshop-01",
        stage="verified",
        severity=Severity.info,
        message="second",
        run_id="RUN-INCIDENT-1",
        scenario_id="SCN-INCIDENT-1",
        occurred_at=occurred_at,
    )
    other_run = repository.append_event(
        node_code="turning-workshop-01",
        stage="observed",
        severity=Severity.info,
        message="new run",
        run_id="RUN-INCIDENT-2",
        scenario_id="SCN-INCIDENT-2",
        occurred_at=occurred_at,
    )

    assert (first.global_sequence, second.global_sequence, other_run.global_sequence) == (
        1,
        2,
        3,
    )
    assert (first.local_sequence, second.local_sequence, other_run.local_sequence) == (
        1,
        2,
        1,
    )
    assert second.correlation_id == "RUN-INCIDENT-1:turning-workshop-01:2"


def test_incident_mutation_and_restore_sql_is_not_owned_by_memory_store() -> None:
    store_source = (APP_ROOT / "store.py").read_text(encoding="utf-8")
    repository_source = (APP_ROOT / "repositories" / "incidents.py").read_text(
        encoding="utf-8"
    )

    for sql in (
        "INSERT INTO alerts",
        "UPDATE alerts",
        "INSERT INTO ai_diagnosis",
    ):
        assert sql not in store_source
        assert sql in repository_source
    assert "load_audits_and_events" in repository_source
    assert "central_fact_repository.persist_event" in repository_source
    assert "central_fact_repository.persist_audit" in repository_source
