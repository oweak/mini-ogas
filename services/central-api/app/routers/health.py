from fastapi import APIRouter

from ..core.session import get_session_token
from ..store import store

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "central-api",
        "session_token": get_session_token(),
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
