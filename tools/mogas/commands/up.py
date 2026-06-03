"""``mogas up`` — start services in dependency order."""

from __future__ import annotations

import logging
import time
from typing import Sequence

from ..core.health import check, wait
from ..core.process import ProcessManager, ProcessError, kill_port
from ..core.services import CORE, AGENTS, DASHBOARD, MICROSERVICES, Service

logger = logging.getLogger(__name__)


def run(*, all: bool = False) -> None:
    """Start the system stack.

    Phase 0: kill stale port holders.
    Phase 1: core (central-api).
    Phase 2: microservices (if --all).
    Phase 3: dashboard (if available).
    Phase 4: node agents.
    Phase 5: final verification.
    """
    with ProcessManager() as pm:
        # Phase 0 — clean
        logger.info("=== phase 0: cleaning ports ===")
        for svc in (CORE + MICROSERVICES + DASHBOARD):
            kill_port(svc.port)
        time.sleep(0.5)

        # Phase 1 — core
        logger.info("=== phase 1: core ===")
        for svc in CORE:
            pm.start(svc)
            if not wait(svc.port, timeout=svc.health_timeout):
                raise ProcessError(f"{svc.name} did not become healthy")
            print(f"  {svc.name:25s} OK  (http://127.0.0.1:{svc.port})")

        # Phase 2 — microservices
        ms = MICROSERVICES if all else []
        if ms:
            logger.info("=== phase 2: microservices ===")
            for svc in ms:
                pm.start(svc)
                healthy = wait(svc.port, timeout=svc.health_timeout)
                status = "OK" if healthy else "FAIL"
                print(f"  {svc.name:25s} {status}  (port {svc.port})")

        # Phase 3 — dashboard
        dash_svcs = DASHBOARD if all else []
        if dash_svcs:
            logger.info("=== phase 3: dashboard ===")
            for svc in dash_svcs:
                try:
                    pm.start(svc)
                except ProcessError as exc:
                    print(f"  {svc.name:25s} SKIP ({exc})")
                else:
                    print(f"  {svc.name:25s} ...  (http://127.0.0.1:{svc.port})")

        # Phase 4 — agents
        logger.info("=== phase 4: agents ===")
        for svc in AGENTS:
            pm.start(svc)
            time.sleep(0.3)
            print(f"  {svc.name:25s} started")

        # Phase 5 — verify
        logger.info("=== phase 5: verify ===")
        time.sleep(2.5)
        from .status import _print_api_status
        _print_api_status()

    print()
    print("  Dashboard:  http://127.0.0.1:8080")
    if any(svcs for svcs in (dash_svcs,)):
        print("  Dev server: http://127.0.0.1:5173")
    print("  Stop:       mogas down")
    print()
