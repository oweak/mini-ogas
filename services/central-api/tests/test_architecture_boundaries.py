from __future__ import annotations

import ast
import tomllib
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
PROJECT_ROOT = APP_ROOT.parents[2]
ALLOWED_ROUTER_DEPENDENCIES = {
    ("ai", "demo"),
    ("compat", "ai"),
    ("compat", "audit"),
    ("compat", "demo"),
    ("demo", "compat"),
    ("ops", "control"),
    ("reports", "demo"),
}


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            found.append((node.lineno, prefix + (node.module or "")))
    return found


def test_core_and_persistence_layers_do_not_depend_on_http_routers() -> None:
    protected = list((APP_ROOT / "core").rglob("*.py"))
    protected.extend(
        [APP_ROOT / "models.py", APP_ROOT / "store.py", APP_ROOT / "persistence_repository.py"]
    )
    violations = []
    for path in protected:
        for line, imported in _imports(path):
            if "routers" in imported:
                violations.append(f"{path.relative_to(APP_ROOT)}:{line} -> {imported}")
    assert violations == []


def test_router_to_router_legacy_dependencies_are_frozen() -> None:
    observed: set[tuple[str, str]] = set()
    for path in (APP_ROOT / "routers").glob("*.py"):
        source = path.stem
        for _, imported in _imports(path):
            target = ""
            if imported.startswith(".") and not imported.startswith(".."):
                target = imported.lstrip(".").split(".")[0]
            elif imported.startswith("..routers."):
                target = imported.split(".")[-1]
            if target and target not in {"__future__"}:
                observed.add((source, target))
    assert observed == ALLOWED_ROUTER_DEPENDENCIES


def _asyncio_create_task_calls(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
        and node.func.attr == "create_task"
    ]


def test_periodic_business_tasks_are_owned_by_dedicated_worker() -> None:
    api_lifecycle = APP_ROOT / "core" / "lifecycle.py"
    background_worker = APP_ROOT / "worker.py"

    assert _asyncio_create_task_calls(api_lifecycle) == []
    assert len(_asyncio_create_task_calls(background_worker)) == 2


def test_supervisor_registers_one_background_worker() -> None:
    with (PROJECT_ROOT / "config" / "supervisor.toml").open("rb") as handle:
        supervisor = tomllib.load(handle)

    workers = [
        process
        for process in supervisor["process"]
        if process["name"] == "background-worker"
    ]

    assert len(workers) == 1
    assert workers[0]["args"][2] == "app.worker:app"
    assert workers[0]["env"]["DATABASE_AUTO_MIGRATE"] == "false"


def test_compose_environment_enables_worker_transport_adapters() -> None:
    values = {}
    for line in (PROJECT_ROOT / "deploy" / "env.central.example").read_text(
        encoding="utf-8"
    ).splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    assert values["NATS_ENABLED"] == "true"
    assert values["NATS_URL"] == "nats://nats:4222"
    assert values["REDIS_ENABLED"] == "true"
    assert values["REDIS_URL"] == "redis://redis:6379/0"
    assert "REDIS_ADDR" not in values
