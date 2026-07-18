"""``mogas down`` delegates to the supported Supervisor shutdown path."""

from __future__ import annotations

import subprocess
import sys

from ..core.process import ProcessError
from ..core.services import PROJ_ROOT


def run() -> None:
    """Stop the supervised runtime and verify the shutdown script succeeds."""
    if sys.platform != "win32":
        raise ProcessError("mogas down requires scripts/stop-all.ps1 on Windows")
    launcher = PROJ_ROOT / "scripts" / "stop-all.ps1"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(launcher),
    ]
    result = subprocess.run(command, cwd=PROJ_ROOT, check=False)
    if result.returncode != 0:
        raise ProcessError(f"Supervisor shutdown failed with exit code {result.returncode}")
    print("\n  Mini-OGAS supervised runtime stopped.")
