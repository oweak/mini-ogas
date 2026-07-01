"""Process management — lifecycle, state tracking, cross-platform kill."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from .services import PROJ_ROOT, Service

logger = logging.getLogger(__name__)

PID_DIR = PROJ_ROOT / ".runtime" / "pids"
PID_DIR.mkdir(parents=True, exist_ok=True)

SESSION_TOKEN = os.environ.get(
    "OGAS_SESSION_TOKEN",
    f"mogas-{os.getpid():x}-{int(time.monotonic()):x}",
)
os.environ["OGAS_SESSION_TOKEN"] = SESSION_TOKEN


def _runtime_token() -> str:
    for key in ("OGAS_API_TOKEN", "API_ACCESS_TOKEN", "CENTRAL_API_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    token_path = PROJ_ROOT.parent.parent / "MiniOGAS-VMs" / "miniogas-token.txt"
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()
    return ""


class ProcessError(Exception):
    """Raised when a process fails to start or respond to health checks."""


class ProcessTimeout(ProcessError):
    """Service did not become healthy within the allotted time."""


@dataclass
class ProcessState:
    service: Service
    process: subprocess.Popen | None = None
    started_at: float = 0.0
    restarts: int = 0
    status: str = "stopped"  # stopped | starting | running | failed

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None


class ProcessManager:
    """Owns the lifecycle of all services.

    Usage as context manager::

        with ProcessManager() as pm:
            pm.start(core_service)
            pm.wait_healthy(core_service, timeout=20)
            # ... work ...
        # all processes terminated on __exit__
    """

    def __init__(self) -> None:
        self._states: dict[str, ProcessState] = {}

    # -- context manager --

    def __enter__(self) -> "ProcessManager":
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop_all()

    # -- start / stop --

    def start(self, svc: Service) -> ProcessState:
        if svc.name in self._states and self._states[svc.name].status == "running":
            logger.info("%s is already running (pid=%s)", svc.name, self._states[svc.name].pid)
            return self._states[svc.name]

        state = ProcessState(service=svc, started_at=time.monotonic(), status="starting")
        self._states[svc.name] = state

        env = os.environ.copy()
        env.setdefault("OGAS_SESSION_TOKEN", SESSION_TOKEN)
        token = _runtime_token()
        if token:
            env.setdefault("API_ACCESS_TOKEN", token)
            env.setdefault("OGAS_API_TOKEN", token)
            env.setdefault("CENTRAL_API_TOKEN", token)

        logger.info("starting %s  cwd=%s", svc.name, svc.workdir)
        try:
            proc = subprocess.Popen(
                svc.command,
                cwd=svc.workdir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            state.process = proc
            state.status = "running"
            logger.info("%s started (pid=%s)", svc.name, proc.pid)
            self._write_pid_file(svc.name, proc.pid)
        except FileNotFoundError as exc:
            state.status = "failed"
            raise ProcessError(f"{svc.name}: {exc.filename} not found") from exc
        except Exception as exc:
            state.status = "failed"
            raise ProcessError(f"{svc.name}: {exc}") from exc

        return state

    def stop(self, name: str, *, graceful: bool = True) -> None:
        state = self._states.get(name)
        if state is None:
            return
        state.status = "stopped"
        if state.process is None:
            return

        logger.info("stopping %s (pid=%s)", name, state.process.pid)
        try:
            if graceful and sys.platform != "win32":
                state.process.terminate()
                try:
                    state.process.wait(timeout=5)
                    return
                except subprocess.TimeoutExpired:
                    pass
            state.process.kill()
            state.process.wait(timeout=2)
        except Exception:
            pass

    def stop_all(self) -> None:
        names = list(self._states)
        for name in reversed(names):
            self.stop(name)
        self._clean_pid_files()

    # -- restart --

    def restart(self, name: str) -> ProcessState:
        svc = self._states[name].service
        self.stop(name)
        return self.start(svc)

    # -- status --

    def is_running(self, name: str) -> bool:
        st = self._states.get(name)
        if st is None or st.process is None:
            return False
        return st.process.poll() is None and st.status == "running"

    def states(self) -> dict[str, ProcessState]:
        return dict(self._states)

    # -- helpers --

    def _write_pid_file(self, name: str, pid: int) -> None:
        try:
            (PID_DIR / f"{name}.pid").write_text(str(pid))
        except OSError:
            pass

    def _clean_pid_files(self) -> None:
        for f in PID_DIR.glob("*.pid"):
            try:
                f.unlink()
            except OSError:
                pass


def kill_port(port: int) -> None:
    """Cross-platform port cleanup."""
    if port <= 0:
        return
    if sys.platform == "win32":
        _kill_port_windows(port)
    else:
        _kill_port_unix(port)


def _kill_port_windows(port: int) -> None:
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{port}" not in line or "LISTENING" not in line.upper():
                continue
            pid = line.strip().split()[-1]
            if pid.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    except Exception:
        pass


def _kill_port_unix(port: int) -> None:
    sig = getattr(signal, "SIGKILL", signal.SIGTERM)
    try:
        subprocess.run(["fuser", "-k", "-9", f"{port}/tcp"], capture_output=True)
    except Exception:
        try:
            subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True)
        except Exception:
            pass
