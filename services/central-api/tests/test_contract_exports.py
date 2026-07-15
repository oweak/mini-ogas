from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_contract_exports_are_current_and_truthfully_scoped() -> None:
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "export_contracts.py"), "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    asyncapi = json.loads(
        (PROJECT_ROOT / "contracts" / "asyncapi" / "mini-ogas-shadow-v3.json").read_text(
            encoding="utf-8"
        )
    )
    assert asyncapi["asyncapi"] == "3.0.0"
    assert asyncapi["channels"]["heartbeats"]["address"] == "ogas.heartbeats.{node_code}"
    assert asyncapi["components"]["messages"]["Heartbeat"][
        "x-mini-ogas-implementation-status"
    ] == "wired-shadow"
    assert asyncapi["components"]["messages"]["Command"][
        "x-mini-ogas-implementation-status"
    ] == "contract-defined-not-transactionally-wired"
    assert asyncapi["x-mini-ogas-boundary"]["physicalDeviceWrite"] is False
    assert set(asyncapi["operations"]) == {"publishHeartbeat", "projectHeartbeat"}


def test_openapi_contract_contains_current_runtime_and_audit_paths() -> None:
    openapi = json.loads(
        (PROJECT_ROOT / "contracts" / "openapi" / "mini-ogas-openapi-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert openapi["info"]["title"] == "Mini-OGAS Central API"
    assert "/health" in openapi["paths"]
    assert "/dashboard/snapshot" in openapi["paths"]
    assert "/audit-logs" in openapi["paths"]
