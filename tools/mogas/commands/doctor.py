"""``mogas doctor`` — environment diagnosis."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

from ..core.health import check
from ..core.services import PROJ_ROOT


SENSITIVE_ENV_KEYS = {"DEEPSEEK_API_KEY", "API_ACCESS_TOKEN"}


def run() -> None:
    print()
    print(f"  OS          : {platform.system()} {platform.release()}")
    print(f"  Python      : {sys.version.split()[0]}  ({sys.executable})")

    for name, flag in [("pip", ["--version"]), ("node", ["--version"])]:
        print(f"  {name:12s}: {_run_cmd(name, flag)}")

    print()
    print("  Ports:")
    for p in [8080, 8081, 8082, 8083, 5173]:
        busy = "BUSY" if check(p, timeout=1) else "free"
        print(f"    :{p:<5} {busy}")

    print()
    print("  Environment:")
    for key in ["MINI_OGAS_ENV", "DEEPSEEK_API_KEY", "API_ACCESS_TOKEN", "AI_ENABLED"]:
        val = os.environ.get(key, "")
        if not val or val == "replace-with-your-key":
            print(f"    {key:26s} NOT SET")
        elif key in SENSITIVE_ENV_KEYS:
            print(f"    {key:26s} SET (redacted)")
        else:
            print(f"    {key:26s} {val}")

    env_file = PROJ_ROOT / ".env"
    if env_file.exists():
        print("\n    .env        OK")
    else:
        print("\n    .env        NOT FOUND  (run 'mogas setup')")

    deps = (
        ("psutil", "pip install psutil"),
        ("httpx", "pip install httpx"),
        ("uvicorn", "pip install uvicorn"),
    )
    print()
    for mod, fix in deps:
        try:
            __import__(mod)
            print(f"    {mod:12s} installed")
        except ImportError:
            print(f"    {mod:12s} MISSING  ({fix})")

    print()


def _run_cmd(name: str, args: list[str]) -> str:
    exe = shutil.which(name)
    if exe is None:
        return "NOT FOUND"
    try:
        result = subprocess.run([name] + args, capture_output=True, text=True, timeout=5)
        return (result.stdout or result.stderr).strip().split("\n")[0][:60]
    except Exception:
        return "ERROR"
