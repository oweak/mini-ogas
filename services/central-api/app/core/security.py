from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .auth import decode_access_token
from .config import settings
from .errors import problem_response
from .identity import REQUEST_ID_HEADER

PUBLIC_PATHS = {
    "/health",
    "/preflight",
    "/auth/verify",
    "/auth/status",
    "/auth/login",
    "/system/preflight",
    "/api/health",
    "/api/preflight",
    "/api/auth/verify",
    "/api/auth/status",
    "/api/auth/login",
    "/api/system/preflight",
}
RATE_HISTORY: dict[str, deque[float]] = defaultdict(deque)
_RATE_CHECK_COUNT = 0

PERM_NODE_VIEW = "node:view"
PERM_NODE_ISOLATE = "node:isolate"
PERM_NODE_RESTORE = "node:restore"
PERM_COMMAND_APPROVE = "command:approve"
PERM_COMMAND_REJECT = "command:reject"
PERM_COMMAND_ISSUE = "command:issue"
PERM_AI_DIAGNOSE = "ai:diagnose"
PERM_METRIC_INGEST = "metric:ingest"
PERM_SIMULATION_CONTROL = "simulation:control"
PERM_MASTER_DATA_MANAGE = "master-data:manage"
PERM_EXECUTION_MANAGE = "execution:manage"
PERM_INVENTORY_MANAGE = "inventory:manage"
PERM_QUALITY_MANAGE = "quality:manage"
PERM_QUALITY_MEASURE = "quality:measure"
PERM_QUALITY_RELEASE = "quality:release"
PERM_MAINTENANCE_MANAGE = "maintenance:manage"
PERM_MAINTENANCE_EXECUTE = "maintenance:execute"
PERM_MAINTENANCE_VERIFY = "maintenance:verify"
PERM_TELEMETRY_MANAGE = "telemetry:manage"
PERM_TELEMETRY_INGEST = "telemetry:ingest"
PERM_TELEMETRY_READ = "telemetry:read"
PERM_TELEMETRY_RETENTION = "telemetry:retention"
PERM_PROJECTION_REBUILD = "projection:rebuild"
PERM_DOCUMENT_OBJECT_MANAGE = "document-object:manage"


class ActorInfo(BaseModel):
    """Identity derived from a verified credential, never request payloads."""

    username: str = ""
    display_name: str = ""
    role: str
    permissions: set[str]


def _is_node_ingest_path(path: str) -> bool:
    if path == "/telemetry/batches":
        return True
    if path.startswith("/nodes/"):
        return (
            path.endswith("/heartbeat")
            or path.endswith("/pending-commands")
            or path.endswith("/command-results")
        )
    return (
        path in {"/metrics", "/node-heartbeats"}
        or path.startswith("/agents/")
        or path.startswith("/node-records/")
        or path.startswith("/node-dispatches/")
        or (path.startswith("/commands/") and path.endswith("/result"))
    )


def _bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _json_error(request: Request, status_code: int, detail: str) -> JSONResponse:
    response = problem_response(request, status_code, detail)
    response.headers[REQUEST_ID_HEADER] = str(getattr(request.state, "request_id", ""))
    origin = request.headers.get("origin", "")
    if origin in settings.cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


def _rate_limit(request: Request, *, bucket: str = "api") -> Response | None:
    client = request.client.host if request.client else "unknown"
    client = f"{bucket}:{client}"
    now = time.monotonic()
    history = RATE_HISTORY[client]
    while history and now - history[0] > 60:
        history.popleft()
    if len(history) >= settings.rate_limit_per_minute:
        return _json_error(request, 429, "rate limit exceeded")
    history.append(now)

    global _RATE_CHECK_COUNT
    _RATE_CHECK_COUNT += 1
    if _RATE_CHECK_COUNT % 500 == 0:
        stale = [
            key for key, values in RATE_HISTORY.items() if not values or now - values[-1] > 120
        ]
        for key in stale:
            del RATE_HISTORY[key]
    return None


async def security_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    # The dashboard accesses the API through /api; routers use unprefixed paths.
    path = request.url.path
    if path.startswith("/api/"):
        path = path[4:]
        request.scope["path"] = path
        request.scope["raw_path"] = path.encode()

    if request.method == "OPTIONS":
        return await call_next(request)
    if path in PUBLIC_PATHS:
        if path.endswith("/auth/login"):
            limited = _rate_limit(request, bucket="auth-login")
            if limited is not None:
                return limited
        return await call_next(request)
    if path in {"/", "/index.html"} or path.startswith("/assets/"):
        return await call_next(request)

    if _is_node_ingest_path(path):
        token = request.headers.get("x-ogas-token", "")
        if not secrets.compare_digest(token, settings.node_ingest_token):
            return _json_error(request, 401, "missing or invalid node credential")
        request.state.actor = ActorInfo(
            username="node-agent",
            display_name="node-agent",
            role="node_agent",
            permissions={PERM_NODE_VIEW, PERM_METRIC_INGEST, PERM_TELEMETRY_INGEST},
        )
    else:
        claims = decode_access_token(_bearer_token(request))
        if claims is None and settings.allow_legacy_api_token_auth:
            legacy_token = request.headers.get("x-ogas-token", "")
            if secrets.compare_digest(legacy_token, settings.api_access_token):
                claims = {
                    "sub": "legacy-admin",
                    "name": "legacy-admin",
                    "roles": ["system_admin"],
                    "permissions": [
                        PERM_NODE_VIEW,
                        PERM_NODE_ISOLATE,
                        PERM_NODE_RESTORE,
                        PERM_COMMAND_APPROVE,
                        PERM_COMMAND_REJECT,
                        PERM_COMMAND_ISSUE,
                        PERM_AI_DIAGNOSE,
                        PERM_METRIC_INGEST,
                        PERM_SIMULATION_CONTROL,
                        PERM_MASTER_DATA_MANAGE,
                        PERM_EXECUTION_MANAGE,
                        PERM_INVENTORY_MANAGE,
                        PERM_QUALITY_MANAGE,
                        PERM_QUALITY_MEASURE,
                        PERM_QUALITY_RELEASE,
                        PERM_MAINTENANCE_MANAGE,
                        PERM_MAINTENANCE_EXECUTE,
                        PERM_MAINTENANCE_VERIFY,
                        PERM_TELEMETRY_MANAGE,
                        PERM_TELEMETRY_INGEST,
                        PERM_TELEMETRY_READ,
                        PERM_TELEMETRY_RETENTION,
                        PERM_PROJECTION_REBUILD,
                        PERM_DOCUMENT_OBJECT_MANAGE,
                    ],
                }
        if claims is None:
            return _json_error(request, 401, "missing or invalid bearer access token")
        roles = claims.get("roles") or []
        request.state.actor = ActorInfo(
            username=str(claims.get("sub") or ""),
            display_name=str(claims.get("name") or claims.get("sub") or ""),
            role=str(roles[0]) if roles else "viewer",
            permissions={str(item) for item in claims.get("permissions", [])},
        )

    limited = _rate_limit(request)
    if limited is not None:
        return limited
    return await call_next(request)


def get_current_actor(request: Request) -> ActorInfo:
    actor = getattr(request.state, "actor", None)
    if isinstance(actor, ActorInfo):
        return actor
    raise HTTPException(status_code=401, detail="authentication context is missing")


def require_permission(permission: str):
    def checker(actor: ActorInfo = Depends(get_current_actor)) -> ActorInfo:
        if permission not in actor.permissions:
            raise HTTPException(
                status_code=403, detail=f"role '{actor.role}' lacks permission '{permission}'"
            )
        return actor

    return checker
