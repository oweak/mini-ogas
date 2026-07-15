from fastapi import APIRouter

from ..core.config import settings
from ..core.nats_publisher import nats_runtime
from ..core.service_client import get_json
from ..core.session import get_process_identity, get_session_token
from ..core.supervisor import supervisor_health
from ..store import store

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    session_token = get_session_token()
    # Liveness must remain below the supervisor's own health timeout even
    # while dependent services are still starting. Readiness is represented
    # by ``overall_status`` and may legitimately be degraded during startup.
    dependency_timeout = min(settings.service_probe_timeout_seconds, 0.25)
    supervisor = supervisor_health(session_token, timeout=dependency_timeout)
    worker_ok, worker_payload = get_json(
        f"{settings.background_worker_url.rstrip('/')}/health",
        timeout=dependency_timeout,
    )
    background_worker = (
        worker_payload
        if worker_ok and isinstance(worker_payload, dict)
        else {
            "status": "unavailable",
            "overall_status": "degraded",
            "error": (
                worker_payload.get("error", "invalid_response")
                if isinstance(worker_payload, dict)
                else "invalid_response"
            ),
        }
    )
    nats = (
        background_worker.get("nats")
        if worker_ok and isinstance(background_worker.get("nats"), dict)
        else nats_runtime.health()
    )
    overall_status = "ready"
    if background_worker.get("overall_status") != "ready":
        overall_status = "degraded"
    if nats["enabled"] and nats["status"] != "live":
        overall_status = "degraded"
    return {
        # `status` is a liveness proof consumed by the supervisor. Optional
        # integration readiness is reported separately to avoid restart loops.
        "status": "ok",
        "overall_status": overall_status,
        "service": "central-api",
        "session_token": session_token,
        "runtime_owner": "supervisor" if supervisor["status"] == "ok" else "standalone-or-degraded",
        "supervisor": supervisor,
        "background_worker": background_worker,
        "nats": nats,
        "environment": settings.environment_status(),
        **get_process_identity(),
    }


@router.get("/summary")
def get_summary():
    return store.summary()


@router.get("/hosts/status")
def get_host_status():
    return store.host_status()


@router.get("/integrations/status")
def get_integrations_status():
    return store.integration_status()
