from __future__ import annotations

import pytest
from app.core.config import settings
from app.store import MemoryStore


def test_memory_store_exposes_command_repository_projection_without_duplicate_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    state = MemoryStore()

    assert "commands" not in state.__dict__
    assert state.commands is state.command_repository.commands


def test_command_repository_recovers_command_state_after_restart(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "command-repository-restart.db"
    monkeypatch.setattr(settings, "persist_enabled", True)
    monkeypatch.setattr(settings, "persist_backend", "sqlite")
    monkeypatch.setattr(settings, "central_db_path", str(db_path))
    monkeypatch.setattr(settings, "demo_seed_enabled", False)

    first = MemoryStore()
    command = first.add_command(
        "milling-workshop-01",
        "set_target_rate",
        "low",
        "pending",
        "user:pytest",
        parameters={"target_rate": 0.73, "idempotency_key": "repository-restart"},
    )
    first.claim_pending_commands_for_node("milling-workshop-01", "node:milling-workshop-01")
    first.record_command_result(
        "milling-workshop-01",
        command.id,
        "executed",
        "applied by test agent",
    )

    restarted = MemoryStore()
    restored = next(item for item in restarted.commands if item.id == command.id)

    assert "commands" not in restarted.__dict__
    assert restored.status == "applied"
    assert restored.claimed_by == "node:milling-workshop-01"
    assert restored.parameters["idempotency_key"] == "repository-restart"
    assert restored.result_message == "applied by test agent"
