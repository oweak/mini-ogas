"""Health probes with launch-session and process-freshness verification."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class HealthError(Exception):
    """Service did not respond with a valid health proof."""


@dataclass(frozen=True)
class HealthProof:
    status: str
    service: str
    session_token: str
    process_id: int
    process_started_at: str


def probe(port: int, *, timeout: float = 3.0) -> HealthProof | None:
    if port <= 0:
        return None
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status >= 300:
                return None
            data = json.loads(response.read().decode("utf-8"))
        started_at = str(data.get("process_started_at") or "")
        if data.get("status") != "ok" or not str(data.get("session_token") or ""):
            return None
        if int(data.get("process_id") or 0) <= 0 or not started_at:
            return None
        datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        return HealthProof(
            status="ok",
            service=str(data.get("service") or ""),
            session_token=str(data["session_token"]),
            process_id=int(data["process_id"]),
            process_started_at=started_at,
        )
    except (urllib.error.URLError, OSError, ValueError, TypeError, TimeoutError) as exc:
        logger.debug("health probe :%s failed: %s", port, exc)
        return None


def check(port: int, *, timeout: float = 3.0, expected_session_token: str | None = None) -> bool:
    if port <= 0:
        return True
    proof = probe(port, timeout=timeout)
    return bool(proof and (expected_session_token is None or proof.session_token == expected_session_token))


def wait(
    port: int,
    *,
    timeout: float = 20.0,
    interval: float = 1.0,
    expected_session_token: str | None = None,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check(port, timeout=min(interval, timeout), expected_session_token=expected_session_token):
            return True
        time.sleep(0.5)
    return False


def api_request(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    host: str = "http://127.0.0.1:8080",
    token: str = "",
    timeout: float = 5.0,
) -> dict[str, Any]:
    url = f"{host}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-OGAS-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.debug("api %s %s failed: %s", method, path, exc)
        return {}
