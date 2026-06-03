from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .config import settings

PUBLIC_PATHS = {"/health", "/preflight", "/auth/verify", "/auth/status", "/auth/login", "/system/preflight", "/api/health", "/api/preflight", "/api/auth/verify", "/api/auth/status", "/api/auth/login", "/api/system/preflight"}
RATE_HISTORY: dict[str, deque[float]] = defaultdict(deque)
_RATE_CHECK_COUNT = 0

# ---------------------------------------------------------------------------
# Permission constants
# ---------------------------------------------------------------------------
PERM_NODE_VIEW = "node:view"
PERM_NODE_ISOLATE = "node:isolate"
PERM_NODE_RESTORE = "node:restore"
PERM_COMMAND_APPROVE = "command:approve"
PERM_COMMAND_REJECT = "command:reject"
PERM_COMMAND_ISSUE = "command:issue"
PERM_AI_DIAGNOSE = "ai:diagnose"
PERM_METRIC_INGEST = "metric:ingest"
PERM_SIMULATION_CONTROL = "simulation:control"

# Role → permission set mapping.
# system_admin has every permission; node_agent is scoped to data ingestion.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "system_admin": {
        PERM_NODE_VIEW, PERM_NODE_ISOLATE, PERM_NODE_RESTORE,
        PERM_COMMAND_APPROVE, PERM_COMMAND_REJECT, PERM_COMMAND_ISSUE,
        PERM_AI_DIAGNOSE, PERM_METRIC_INGEST, PERM_SIMULATION_CONTROL,
    },
    "node_agent": {
        PERM_NODE_VIEW, PERM_METRIC_INGEST,
    },
}


class ActorInfo(BaseModel):
    """Server-derived identity — never trust client-provided actor strings."""
    role: str
    permissions: set[str]


def _is_node_ingest_path(path: str) -> bool:
    return path == "/metrics" or path.startswith("/nodes/")


async def security_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    # Normalize: strip /api prefix (embedded dashboard uses /api/* to reach backend routes)
    path = request.url.path
    if path.startswith("/api/"):
        path = path[4:]
        request.scope["path"] = path
        request.scope["raw_path"] = path.encode()

    if request.method == "OPTIONS" or path in PUBLIC_PATHS:
        return await call_next(request)

    # Static assets served by the embedded dashboard — no auth required
    if path in ("/", "/index.html") or path.startswith("/assets/"):
        return await call_next(request)

    token = request.headers.get("x-ogas-token", "")
    expected = settings.node_ingest_token if _is_node_ingest_path(path) else settings.api_access_token
    if not secrets.compare_digest(token, expected):
        return JSONResponse(status_code=401, content={"detail": "missing or invalid X-OGAS-Token"})

    client = request.client.host if request.client else "unknown"
    # Bucket by client IP only (not per-path) to prevent dict explosion from unique paths
    key = client
    now = time.monotonic()
    history = RATE_HISTORY[key]
    while history and now - history[0] > 60:
        history.popleft()
    if len(history) >= settings.rate_limit_per_minute:
        return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})
    history.append(now)

    # Periodic cleanup: purge stale entries to bound memory
    global _RATE_CHECK_COUNT
    _RATE_CHECK_COUNT += 1
    if _RATE_CHECK_COUNT % 500 == 0:
        stale = [k for k, v in RATE_HISTORY.items() if not v or (v and now - v[-1] > 120)]
        for k in stale:
            del RATE_HISTORY[k]

    return await call_next(request)


def get_current_actor(request: Request) -> ActorInfo:
    """FastAPI dependency — derive actor identity from the authenticated token.

    The middleware has already verified the token at this point, so we
    inspect the request path to determine *which* token was used and
    map it to a role.
    """
    token = request.headers.get("x-ogas-token", "")
    node_ingest = _is_node_ingest_path(request.url.path)

    if node_ingest and token == settings.node_ingest_token:
        role = "node_agent"
    else:
        # All other paths use api_access_token → system_admin
        role = "system_admin"

    permissions = ROLE_PERMISSIONS.get(role, set())
    return ActorInfo(role=role, permissions=permissions)


def require_permission(permission: str):
    """Dependency factory — gate an endpoint behind a specific permission.

    Usage:
        @router.post("/nodes/{code}/isolate")
        def isolate_node(code: str, actor: ActorInfo = Depends(require_permission(PERM_NODE_ISOLATE))):
            ...
    """
    def checker(request: Request, actor: ActorInfo = Depends(get_current_actor)) -> ActorInfo:
        if permission not in actor.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"role '{actor.role}' lacks permission '{permission}'",
            )
        return actor
    return checker
