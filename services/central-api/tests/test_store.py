import pytest

from app.models import Machine, MetricIn, NodeStatus, ProductionPlanIn, Severity
from app.store import MemoryStore


@pytest.fixture()
def store() -> MemoryStore:
    return MemoryStore()


def test_record_metric_creates_new_node(store: MemoryStore) -> None:
    store.record_metric(
        MetricIn(
            node_code="quality-cloud-01",
            workshop_type="cloud",
            cpu_usage=35,
            memory_usage=42,
            disk_usage=51,
            network_in=1_000_000,
            network_out=900_000,
            db_latency_ms=20,
            api_latency_ms=60,
        )
    )

    assert "quality-cloud-01" in store.nodes
    assert store.nodes["quality-cloud-01"].workshop_type == "cloud"


def test_record_metric_disk_90_generates_alert(store: MemoryStore) -> None:
    alerts = store.record_metric(
        MetricIn(
            node_code="turning-workshop-01",
            cpu_usage=40,
            memory_usage=50,
            disk_usage=90,
            network_in=1_000_000,
            network_out=900_000,
            db_latency_ms=20,
            api_latency_ms=60,
        )
    )

    assert any(alert.alert_type == "disk_pressure" for alert in alerts)
    assert any(command.command_type == "clean_temp_cache" for command in store.commands)


def test_record_metric_cpu_92_and_latency_800_triggers_ai_diagnosis(store: MemoryStore) -> None:
    alerts = store.record_metric(
        MetricIn(
            node_code="milling-workshop-01",
            cpu_usage=92,
            memory_usage=70,
            disk_usage=60,
            network_in=1_000_000,
            network_out=900_000,
            db_latency_ms=100,
            api_latency_ms=800,
        )
    )

    assert any(alert.alert_type == "cpu_latency_correlation" for alert in alerts)
    assert len(store.ai_diagnoses) >= 1
    assert store.nodes["milling-workshop-01"].status == NodeStatus.degraded


def test_record_metric_network_100m_isolates_node(store: MemoryStore) -> None:
    alerts = store.record_metric(
        MetricIn(
            node_code="grinding-workshop-01",
            cpu_usage=45,
            memory_usage=55,
            disk_usage=60,
            network_in=100_000_000,
            network_out=5_000_000,
            db_latency_ms=40,
            api_latency_ms=80,
        )
    )

    assert any(alert.severity == Severity.high for alert in alerts)
    assert store.nodes["grinding-workshop-01"].status == NodeStatus.isolated


def test_isolate_node_changes_topology_edges(store: MemoryStore) -> None:
    store.isolate_node("turning-workshop-01", "pytest")

    edge = next(edge for edge in store.topology_edges if edge.target == "turning-workshop-01")
    assert edge.status == "isolated"
    assert edge.latency_ms == 999


def test_restore_node_regenerates_plan(store: MemoryStore) -> None:
    store.isolate_node("turning-workshop-01", "pytest")
    store.production_plans.clear()

    node = store.restore_node("turning-workshop-01", "pytest")

    assert node.status == NodeStatus.online
    assert len(store.production_plans) > 0


def test_apply_scenario_normal_resets_data(store: MemoryStore) -> None:
    store.isolate_node("turning-workshop-01", "pytest")

    result = store.apply_scenario("normal")

    assert result["scenario"] == "normal"
    assert store.nodes["turning-workshop-01"].status == NodeStatus.online
    assert len(store.dispatch_tasks) > 0


def test_apply_scenario_unknown_raises_value_error(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        store.apply_scenario("unknown")


def test_rebuild_dispatch_creates_tasks(store: MemoryStore) -> None:
    store.production_plans = [
        ProductionPlanIn(
            product_code="P1",
            target_quantity=120,
            priority=1,
            route=["turning", "drilling", "inspection"],
            reason="pytest",
        )
    ]

    tasks = store.rebuild_dispatch()

    assert len(tasks) == 3
    assert all(task.status in {"scheduled", "queued"} for task in tasks)


def test_rebuild_dispatch_blocks_task_when_no_machine(store: MemoryStore) -> None:
    store.machines = [
        Machine(
            machine_code="MILL-OFFLINE",
            node_code="milling-workshop-01",
            machine_type="CNC Milling",
            status="maintenance",
            load_rate=10,
            tool_wear_level=10,
            today_output=0,
            defect_count=0,
        )
    ]
    store.production_plans = [
        ProductionPlanIn(
            product_code="P1",
            target_quantity=80,
            priority=1,
            route=["turning"],
            reason="pytest",
        )
    ]

    tasks = store.rebuild_dispatch()

    assert len(tasks) == 1
    assert tasks[0].status == "blocked"
    assert tasks[0].assigned_machine == "waiting-capacity"


def test_management_snapshot_includes_all_sections(store: MemoryStore) -> None:
    snapshot = store.management_snapshot()

    for key in (
        "summary",
        "hosts",
        "nodes",
        "metrics",
        "topology",
        "market_signals",
        "inventory",
        "plans",
        "dispatch_tasks",
        "resource_allocations",
        "machines",
        "alerts",
        "events",
        "commands",
        "ai_shortcuts",
        "simulation",
        "integrations",
    ):
        assert key in snapshot


def test_simulation_step_increments_tick(store: MemoryStore) -> None:
    before = store.simulation_tick

    state = store.simulation_step()

    assert state.tick == before + 1
    assert store.simulation_tick == before + 1
