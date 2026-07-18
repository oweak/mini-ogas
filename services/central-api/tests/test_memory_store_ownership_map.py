from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GENERATOR = PROJECT_ROOT / "tools" / "memory_store_ownership.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("memory_store_ownership", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_memory_store_inventory_is_complete_and_classified() -> None:
    module = _load_generator()
    document = module.build_document()
    field_inventory = document.split("## Field Inventory", 1)[1].split(
        "## Method Inventory", 1
    )[0]

    assert "Inventory: 28 instance fields and 143 methods." in document
    assert "unclassified" not in document
    assert "CommandRepository / CommandService" in document
    assert "NodeRepository / NodeService" in document
    assert "| `simulation_runtime` |" in field_inventory
    assert "| `incident_repository` |" in field_inventory
    legacy_simulation_fields = {
        "rng",
        "simulation_running",
        "simulation_tick",
        "simulation_speed",
        "simulation_anomaly_rate",
        "simulation_last_tick_at",
        "simulation_generated_orders",
        "simulation_generated_events",
    }
    assert all(
        f"| `{field}` |" not in field_inventory for field in legacy_simulation_fields
    )
    legacy_incident_fields = {
        "alerts",
        "audit_logs",
        "incident_events",
        "_incident_event_seq",
        "_node_event_sequences",
        "_shadow_event_count",
        "ai_diagnoses",
    }
    assert all(
        f"| `{field}` |" not in field_inventory for field in legacy_incident_fields
    )


def test_committed_memory_store_ownership_map_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
