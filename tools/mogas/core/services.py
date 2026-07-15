"""Service definitions — declarative, no logic.

All service configurations live here.  Changing ports, commands, or
adding/removing services only touches this file.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parents[3]


def _python() -> str:
    return sys.executable


def _find_npx() -> str:
    """Resolve npx/vite path. Returns '' if Node toolchain is unavailable."""
    candidates = [
        "npx",
        str(PROJ_ROOT / "services" / "dashboard" / "node_modules" / ".bin" / "vite.cmd"),
        str(PROJ_ROOT / "services" / "dashboard" / "node_modules" / ".bin" / "vite"),
    ]
    import shutil
    for c in candidates:
        if shutil.which(c) or Path(c).exists():
            return c
    return ""


@dataclass(frozen=True)
class Service:
    name: str
    role: str  # core | microservice | agent | dashboard
    port: int = 0
    workdir: Path = PROJ_ROOT
    command: list[str] = field(default_factory=list)
    depends_on: tuple[str, ...] = ()
    health_timeout: int = 20  # seconds to wait for healthy


def _core_api() -> list[str]:
    return [_python(), "-u", "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", "8080", "--log-level", "warning"]


def _background_worker() -> list[str]:
    return [_python(), "-u", "-m", "uvicorn", "app.worker:app",
            "--host", "127.0.0.1", "--port", "8084", "--log-level", "warning"]


def _microservice(port: int) -> list[str]:
    return [_python(), "-u", "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", f"--port={port}", "--log-level", "warning"]


def _agent(node_code: str, workshop: str) -> list[str]:
    script = PROJ_ROOT / "services" / "node-agent" / "agent.py"
    return [_python(), "-u", str(script),
            "--node-code", node_code, "--workshop-type", workshop,
            "--interval", "3", "--api-url", "http://127.0.0.1:8080"]


# ---------------------------------------------------------------------------
# Service registry
# ---------------------------------------------------------------------------

_CENTRAL_API = Service(
    name="central-api", role="core", port=8080,
    workdir=PROJ_ROOT / "services" / "central-api",
    command=_core_api(),
)

_BACKGROUND_WORKER = Service(
    name="background-worker", role="core", port=8084,
    workdir=PROJ_ROOT / "services" / "central-api",
    command=_background_worker(),
    depends_on=("central-api",),
)

_AI_DISPATCHER = Service(
    name="ai-dispatcher", role="microservice", port=8081,
    workdir=PROJ_ROOT / "services" / "ai-dispatcher",
    command=_microservice(8081),
    depends_on=("central-api",), health_timeout=10,
)

_MARKET = Service(
    name="market-simulator", role="microservice", port=8082,
    workdir=PROJ_ROOT / "services" / "market-simulator",
    command=_microservice(8082),
    depends_on=("central-api",), health_timeout=10,
)

_PLANNER = Service(
    name="production-planner", role="microservice", port=8083,
    workdir=PROJ_ROOT / "services" / "production-planner",
    command=_microservice(8083),
    depends_on=("central-api",), health_timeout=10,
)

_DASHBOARD = Service(
    name="dashboard", role="dashboard", port=5173,
    workdir=PROJ_ROOT / "services" / "dashboard",
    command=[_find_npx(), "vite", "--host", "0.0.0.0", "--port", "5173"],
    depends_on=("central-api",), health_timeout=15,
)

_TURNING = Service(
    name="turning-agent", role="agent",
    command=_agent("turning-workshop-01", "turning"),
    depends_on=("central-api",),
)

_MILLING = Service(
    name="milling-agent", role="agent",
    command=_agent("milling-workshop-01", "milling"),
    depends_on=("central-api",),
)

_GRINDING = Service(
    name="grinding-agent", role="agent",
    command=_agent("grinding-workshop-01", "grinding"),
    depends_on=("central-api",),
)

_CLOUD = Service(
    name="cloud-agent", role="agent",
    command=_agent("cloud-workshop-01", "cloud"),
    depends_on=("central-api",),
)

_CLOUD_DB = Service(
    name="cloud-db-agent", role="agent",
    command=_agent("cloud-db-01", "database"),
    depends_on=("central-api",),
)

ALL: tuple[Service, ...] = (
    _CENTRAL_API,
    _BACKGROUND_WORKER,
    _AI_DISPATCHER,
    _MARKET,
    _PLANNER,
    _DASHBOARD,
    _TURNING,
    _MILLING,
    _GRINDING,
    _CLOUD,
    _CLOUD_DB,
)


def by_role(*roles: str) -> list[Service]:
    return [s for s in ALL if s.role in roles]


def get(name: str) -> Service:
    for s in ALL:
        if s.name == name:
            return s
    raise KeyError(name)


CORE = by_role("core")
MICROSERVICES = by_role("microservice")
AGENTS = by_role("agent")
DASHBOARD = by_role("dashboard")
