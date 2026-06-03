import secrets

from fastapi import APIRouter, HTTPException

from ..core.config import settings
from ..models import LoginRequest, LoginResponse, PreflightResult
from ..store import store

router = APIRouter(tags=["preflight"])


@router.get("/preflight", response_model=PreflightResult)
def run_preflight() -> PreflightResult:
    return store.run_preflight()


@router.post("/auth/verify", response_model=LoginResponse)
def verify_admin(payload: LoginRequest) -> LoginResponse:
    """Pre-dashboard admin verification. Accepts the API_ACCESS_TOKEN as password."""
    expected = settings.api_access_token
    if not payload.password or not secrets.compare_digest(payload.password, expected):
        raise HTTPException(status_code=401, detail="密码错误")
    return LoginResponse(ok=True, role="system_admin", message="验证通过，欢迎进入 Mini-OGAS 控制台")
