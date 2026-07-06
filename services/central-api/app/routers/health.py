from fastapi import APIRouter

from ..core.session import get_process_identity, get_session_token
from ..core.supervisor import supervisor_health
from ..store import store

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    session_token = get_session_token()
    supervisor = supervisor_health(session_token)
    return {
        "status": "ok",
        "service": "central-api",
        "session_token": session_token,
        "runtime_owner": "supervisor" if supervisor["status"] == "ok" else "standalone-or-degraded",
        "supervisor": supervisor,
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
