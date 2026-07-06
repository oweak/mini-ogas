from __future__ import annotations

from .config import settings
from .service_client import get_json


def supervisor_health(session_token: str) -> dict[str, object]:
    ok, payload = get_json(
        f"{settings.supervisor_url.rstrip('/')}/supervisor/status",
        timeout=min(settings.service_probe_timeout_seconds, 2),
    )
    expected = list(settings.expected_supervisor_processes)
    base: dict[str, object] = {
        "url": settings.supervisor_url,
        "status": "offline",
        "session_match": False,
        "expected_processes": expected,
        "healthy_processes": 0,
        "missing_processes": expected,
        "unhealthy_processes": [],
    }
    if not ok or not isinstance(payload, dict):
        base["detail"] = payload if isinstance(payload, dict) else {"error": "unavailable"}
        return base

    processes = payload.get("processes")
    if not isinstance(processes, list):
        base["status"] = "degraded"
        base["detail"] = {"error": "missing_process_list"}
        return base

    process_by_name = {
        str(item.get("name")): item
        for item in processes
        if isinstance(item, dict) and item.get("name")
    }
    missing = [name for name in expected if name not in process_by_name]
    unhealthy = [
        {
            "name": name,
            "state": str(item.get("state") or "unknown"),
            "pid": item.get("pid"),
            "crash_count": item.get("crash_count", 0),
        }
        for name, item in process_by_name.items()
        if name in expected and str(item.get("state") or "").lower() != "healthy"
    ]
    supervisor_session = str(payload.get("session_id") or "")
    session_match = bool(supervisor_session) and supervisor_session == session_token
    status = "ok"
    if not session_match:
        status = "session_mismatch"
    if missing or unhealthy:
        status = "degraded"

    return {
        **base,
        "status": status,
        "session_id": supervisor_session,
        "session_match": session_match,
        "healthy_processes": sum(
            1
            for name in expected
            if name in process_by_name and str(process_by_name[name].get("state") or "").lower() == "healthy"
        ),
        "missing_processes": missing,
        "unhealthy_processes": unhealthy,
        "total_processes": len(process_by_name),
    }
