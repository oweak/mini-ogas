"""``mogas up`` delegates to the one supported strict launcher."""

from __future__ import annotations

import logging
import subprocess
import sys

from ..core.health import check, probe
from ..core.process import ProcessError, SESSION_TOKEN
from ..core.services import PROJ_ROOT

logger = logging.getLogger(__name__)


def run(*, all: bool = False) -> None:
    """Start the strict runtime and require its session-bound health proof."""
    if sys.platform != "win32":
        raise ProcessError("mogas up requires scripts/start-system.ps1 on Windows")
    launcher = PROJ_ROOT / "scripts" / "start-system.ps1"
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(launcher), "-SessionToken", SESSION_TOKEN,
    ]
    if all:
        logger.info("--all is implicit: the strict launcher always starts microservices and dashboard")
    result = subprocess.run(command, cwd=PROJ_ROOT, check=False)
    if result.returncode != 0:
        raise ProcessError(f"strict launcher failed with exit code {result.returncode}")

    proof = probe(8080, timeout=8)
    if proof is None or not check(8080, timeout=8, expected_session_token=SESSION_TOKEN):
        raise ProcessError("central-api health proof is missing or belongs to another launch session")
    print(f"  central-api OK  pid={proof.process_id} started={proof.process_started_at}")
    print("  Dashboard:  http://127.0.0.1:5173")
