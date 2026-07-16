from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import yaml

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


def test_schema_migration_is_owned_by_one_shot_entrypoint() -> None:
    callers: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if path.name == "database.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "init_db"
            for node in ast.walk(tree)
        ):
            callers.append(str(path.relative_to(APP_ROOT)))

    assert callers == ["migrate.py"]


def test_nats_publish_is_owned_only_by_dedicated_worker() -> None:
    api_lifecycle = (APP_ROOT / "core" / "lifecycle.py").read_text(encoding="utf-8")
    node_routes = (APP_ROOT / "routers" / "nodes.py").read_text(encoding="utf-8")
    background_worker = (APP_ROOT / "worker.py").read_text(encoding="utf-8")

    assert "nats_runtime" not in api_lifecycle
    assert "nats_runtime" not in node_routes
    assert "publish_heartbeat" not in node_routes
    assert "mark_published" not in node_routes
    assert background_worker.count("nats_runtime.publish_envelope") == 1


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

    dashboards = [
        process for process in supervisor["process"] if process["name"] == "dashboard"
    ]
    assert len(dashboards) == 1
    assert dashboards[0]["args"][1] == "preview"
    assert dashboards[0]["health"]["type"] == "http-status"


def test_supervisor_and_compose_use_the_same_runtime_service_names() -> None:
    with (PROJECT_ROOT / "config" / "supervisor.toml").open("rb") as handle:
        supervisor = tomllib.load(handle)
    supervisor_names = {process["name"] for process in supervisor["process"]}
    compose = (PROJECT_ROOT / "deploy" / "docker-compose.central.yml").read_text(
        encoding="utf-8"
    )
    node_compose = (PROJECT_ROOT / "deploy" / "docker-compose.node.yml").read_text(
        encoding="utf-8"
    )

    shared = {
        "central-api",
        "background-worker",
        "ai-dispatcher",
        "market-simulator",
        "production-planner",
        "dashboard",
    }
    assert shared <= supervisor_names
    assert all(f"  {name}:" in compose for name in shared)
    node_names = {
        "turning-simpy-node",
        "milling-simpy-node",
        "grinding-simpy-node",
    }
    assert node_names <= supervisor_names
    assert all(f"  {name}:" in node_compose for name in node_names)


def test_compose_uses_one_shot_migration_and_production_dashboard() -> None:
    compose_path = PROJECT_ROOT / "deploy" / "docker-compose.central.yml"
    compose = compose_path.read_text(encoding="utf-8")
    compose_config = yaml.safe_load(compose)
    dashboard_dockerfile = (PROJECT_ROOT / "services" / "dashboard" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert 'command: ["python", "-m", "app.migrate"]' in compose
    assert "condition: service_completed_successfully" in compose
    assert 'DATABASE_AUTO_MIGRATE: "false"' in compose
    assert "mini_ogas_dev" not in compose
    assert ":-replace_" not in compose
    assert compose_config["services"]["background-worker"]["ports"] == ["8084:8084"]
    assert "RUN npm run build" in dashboard_dockerfile
    assert "FROM nginx:" in dashboard_dockerfile


def test_legacy_script_controller_is_retired() -> None:
    start_system = (PROJECT_ROOT / "scripts" / "start-system.ps1").read_text(
        encoding="utf-8"
    )
    start_all = (PROJECT_ROOT / "scripts" / "start-all.ps1").read_text(encoding="utf-8")
    start_miniogas = (PROJECT_ROOT / "scripts" / "start-miniogas.ps1").read_text(
        encoding="utf-8"
    )

    assert 'if (-not $CheckOnly)' in start_system
    assert "script-managed runtime was retired in Stage F" in start_system
    assert "npm.cmd run dev" not in start_system
    assert 'Join-Path $PSScriptRoot "start-miniogas.ps1"' in start_all
    assert "UseScriptLauncher was retired in Stage F" in start_miniogas


def test_compose_environment_enables_worker_transport_adapters() -> None:
    values = {}
    for line in (PROJECT_ROOT / "deploy" / "env.central.example").read_text(
        encoding="utf-8"
    ).splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    assert values["DATABASE_AUTO_MIGRATE"] == "false"
    assert values["NATS_ENABLED"] == "true"
    assert values["NATS_URL"] == "nats://nats:4222"
    assert values["NATS_AUTH_TOKEN"] == "replace_nats_token"
    assert values["REDIS_ENABLED"] == "true"
    assert values["REDIS_URL"] == "redis://:replace_redis_password@redis:6379/0"
    assert values["OBJECT_STORAGE_ENABLED"] == "true"
    assert values["OBJECT_STORAGE_ENDPOINT"] == "minio:9000"
    assert "REDIS_ADDR" not in values
