from fastapi import APIRouter, HTTPException

from ..core.auth import authenticate_user
from ..models import LoginRequest, LoginResponse, PreflightResult
from ..store import store

router = APIRouter(tags=["preflight"])


@router.get("/preflight", response_model=PreflightResult)
def run_preflight() -> PreflightResult:
    return store.run_preflight()


@router.get("/persistence/status")
def persistence_status() -> dict[str, object]:
    return store.persistence_status()


@router.post("/auth/verify", response_model=LoginResponse)
def verify_admin(payload: LoginRequest) -> LoginResponse:
    """Verify a persisted account without exposing the machine credential."""
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="密码错误")
    role = user["roles"][0] if user["roles"] else "viewer"
    return LoginResponse(ok=True, role=role, message="验证通过，欢迎进入 Mini-OGAS 控制台")
