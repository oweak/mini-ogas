from __future__ import annotations

import pytest
from app.core.config import settings
from app.domain.simulation import RuntimeSimulationState
from app.store import MemoryStore

SIMULATION_FIELDS = {
    "rng",
    "simulation_running",
    "simulation_tick",
    "simulation_speed",
    "simulation_anomaly_rate",
    "simulation_last_tick_at",
    "simulation_generated_orders",
    "simulation_generated_events",
}


def test_memory_store_has_no_duplicate_simulation_state_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    state = MemoryStore()

    assert SIMULATION_FIELDS.isdisjoint(state.__dict__)
    assert isinstance(state.simulation_runtime, RuntimeSimulationState)
    assert state.rng is state.simulation_runtime.rng


def test_simulation_runtime_configuration_and_step_use_one_state_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    state = MemoryStore()

    configured = state.configure_simulation(running=True, speed=2.0, anomaly_rate=0.0)
    stepped = state.simulation_step()

    assert configured.running is True
    assert configured.speed == 2.0
    assert stepped.tick == 1
    assert stepped.last_tick_at is not None
    assert state.simulation_tick == state.simulation_runtime.tick == 1


def test_simulation_compatibility_access_cannot_bypass_runtime_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    state = MemoryStore()

    with pytest.raises(ValueError, match="anomaly_rate"):
        state.simulation_anomaly_rate = 1.1
    with pytest.raises(AttributeError):
        state.simulation_tick = 9

    assert state.simulation_state().anomaly_rate == 0.12
    assert state.simulation_state().tick == 0


def test_simulation_runtime_is_volatile_and_does_not_resume_after_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    first = MemoryStore()
    first.configure_simulation(running=True, speed=3.0, anomaly_rate=0.0)
    first.simulation_step()

    restarted = MemoryStore()

    assert first.simulation_state().tick == 1
    assert restarted.simulation_state().tick == 0
    assert restarted.simulation_state().running is False
    assert restarted.simulation_state().last_tick_at is None
