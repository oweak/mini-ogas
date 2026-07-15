from fastapi import APIRouter

from ..core.session import get_process_identity, get_session_token
from ..core.supervisor import supervisor_health
from ..core.nats_publisher import nats_runtime
from ..core.config import settings
from ..store import store

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    session_token = get_session_token()
    supervisor = supervisor_health(session_token)
    nats = nats_runtime.health()
    overall_status = "degraded" if nats["enabled"] and nats["status"] != "live" else "ready"
    return {
        # `status` is a liveness proof consumed by the supervisor. Optional
        # integration readiness is reported separately to avoid restart loops.
        "status": "ok",
        "overall_status": overall_status,
        "service": "central-api",
        "session_token": session_token,
        "runtime_owner": "supervisor" if supervisor["status"] == "ok" else "standalone-or-degraded",
        "supervisor": supervisor,
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
