"""Health check — lightweight HTTP probe with retry."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class HealthError(Exception):
    """Service did not respond with healthy status."""


def check(port: int, *, timeout: float = 3.0) -> bool:
    """Return True if the service on *port* responds with ``{"status":"ok"}``."""
    if port <= 0:
        return True  # agent processes have no HTTP port
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/health", method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 300:
                return False
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") == "ok"
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        logger.debug("health check :%s → %s", port, exc)
        return False


def wait(port: int, *, timeout: float = 20.0, interval: float = 1.0) -> bool:
    """Block until *port* is healthy or *timeout* seconds elapse."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check(port, timeout=min(interval, timeout)):
            return True
        time.sleep(0.5)
    return False


def api_request(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    host: str = "http://127.0.0.1:8080",
    token: str = "mini-ogas-dev-token",
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Call the central-api REST endpoint and return parsed JSON."""
    url = f"{host}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-OGAS-Token": token,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.debug("api %s %s → %s", method, path, exc)
        return {}
