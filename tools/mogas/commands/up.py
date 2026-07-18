"""``mogas up`` delegates to the supported Supervisor launcher."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from ..core.health import check, probe
from ..core.process import ProcessError
from ..core.services import PROJ_ROOT

logger = logging.getLogger(__name__)
RUNTIME_ROOT = Path(os.environ.get("MINIOGAS_RUNTIME_ROOT", r"D:\MiniOGAS-VMs"))


def run(*, all: bool = False) -> None:
    """Start the full supervised runtime and require its session-bound health proof."""
    if sys.platform != "win32":
        raise ProcessError("mogas up requires scripts/start-miniogas.ps1 on Windows")
    launcher = PROJ_ROOT / "scripts" / "start-miniogas.ps1"
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(launcher), "-RuntimeRoot", str(RUNTIME_ROOT),
    ]
    if all:
        logger.info("--all is implicit: Supervisor always starts the complete component set")
    result = subprocess.run(command, cwd=PROJ_ROOT, check=False)
    if result.returncode != 0:
        raise ProcessError(f"Supervisor launcher failed with exit code {result.returncode}")

    session_path = RUNTIME_ROOT / "miniogas-session-token.txt"
    try:
        session_token = session_path.read_text(encoding="ascii").strip()
    except OSError as exc:
        raise ProcessError(f"Supervisor session proof is missing: {session_path}") from exc
    if not session_token:
        raise ProcessError(f"Supervisor session proof is empty: {session_path}")
    proof = probe(8080, timeout=8)
    if proof is None or not check(8080, timeout=8, expected_session_token=session_token):
        raise ProcessError("central-api health proof is missing or belongs to another launch session")
    print(f"  central-api OK  pid={proof.process_id} started={proof.process_started_at}")
    print("  Dashboard:  http://127.0.0.1:5173")
