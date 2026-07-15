from __future__ import annotations

import asyncio

from fastapi import FastAPI


def test_api_lifespan_never_creates_periodic_tasks(monkeypatch) -> None:
    from app.core import lifecycle

    events: list[str] = []

    async def start_publisher() -> bool:
        events.append("publisher-started")
        return True

    async def stop_publisher() -> None:
        events.append("publisher-stopped")

    def reject_task_creation(*_args, **_kwargs):
        raise AssertionError("API request workers must not create background tasks")

    monkeypatch.setattr(lifecycle, "initialize_auth_store", lambda: None)
    monkeypatch.setattr(lifecycle.nats_runtime.publisher, "start", start_publisher)
    monkeypatch.setattr(lifecycle.nats_runtime.publisher, "stop", stop_publisher)
    monkeypatch.setattr(lifecycle.asyncio, "create_task", reject_task_creation)

    async def exercise() -> None:
        async with lifecycle.lifespan(FastAPI()):
            events.append("serving")

    asyncio.run(exercise())

    assert events == ["publisher-started", "serving", "publisher-stopped"]


def test_background_worker_lifespan_owns_exactly_two_periodic_tasks(monkeypatch) -> None:
    from app import worker

    events: list[str] = []

    async def idle_loop() -> None:
        await asyncio.Event().wait()

    async def start_nats() -> None:
        events.append("nats-started")

    async def stop_nats() -> None:
        events.append("nats-stopped")

    monkeypatch.setattr(worker.settings, "telemetry_bootstrap_catalog_enabled", False)
    monkeypatch.setattr(worker, "simulation_loop", idle_loop)
    monkeypatch.setattr(worker, "outbox_publish_loop", idle_loop)
    monkeypatch.setattr(worker.nats_runtime, "start", start_nats)
    monkeypatch.setattr(worker.nats_runtime, "stop", stop_nats)

    async def exercise() -> None:
        async with worker.worker_lifespan(FastAPI()):
            assert set(worker._tasks) == {"simulation", "outbox"}
            assert all(not task.done() for task in worker._tasks.values())

    asyncio.run(exercise())

    assert worker._tasks == {}
    assert events == ["nats-started", "nats-stopped"]


def test_worker_health_exposes_task_and_transport_ownership(monkeypatch) -> None:
    from app import worker

    class RunningTask:
        @staticmethod
        def done() -> bool:
            return False

    monkeypatch.setattr(worker, "_tasks", {"simulation": RunningTask(), "outbox": RunningTask()})
    monkeypatch.setattr(
        worker.nats_runtime,
        "health",
        lambda: {"enabled": True, "status": "live", "mode": "shadow"},
    )

    payload = worker.health()

    assert payload["overall_status"] == "ready"
    assert payload["task_owner"] == "dedicated-process"
    assert payload["tasks"] == {"simulation": "running", "outbox": "running"}
    assert payload["nats"]["status"] == "live"


def test_simulation_api_proxies_state_and_control_to_worker(monkeypatch) -> None:
    from app.models import SimulationControl
    from app.routers import simulation

    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        simulation,
        "get_json",
        lambda url: (True, {"running": True, "owner": url}),
    )
    monkeypatch.setattr(
        simulation,
        "post_json",
        lambda url, payload: calls.append((url, payload)) or (True, {"running": True}),
    )
    monkeypatch.setattr(simulation.settings, "data_source", "simulated")
    monkeypatch.setattr(simulation.settings, "control_mode", "operator_assisted")
    monkeypatch.setattr(simulation.settings, "app_env", "digital_twin")

    state = simulation.get_simulation_state()
    result = simulation.control_simulation(
        SimulationControl(running=True, speed=2.0, anomaly_rate=0.05),
        actor=None,
    )

    assert state["running"] is True
    assert state["owner"].endswith("/simulation/state")
    assert result == {"running": True}
    assert calls[0][0].endswith("/simulation/configure")
    assert calls[0][1] == {"running": True, "speed": 2.0, "anomaly_rate": 0.05}
