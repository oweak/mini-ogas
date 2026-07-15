from fastapi import APIRouter, Depends, HTTPException

from ..core.config import settings
from ..core.security import PERM_SIMULATION_CONTROL, ActorInfo, require_permission
from ..core.service_client import get_json, post_json
from ..models import SimulationControl

router = APIRouter(tags=["simulation"])


def _require_simulation_control() -> None:
    if settings.app_env == "production" or settings.data_source != "simulated":
        raise HTTPException(
            status_code=409,
            detail={"code": "simulation_disabled", "message": "Simulation is disabled in this environment."},
        )
    if settings.control_mode == "read_only":
        raise HTTPException(
            status_code=409,
            detail={"code": "control_mode_read_only", "message": "CONTROL_MODE is read_only."},
        )


@router.get("/simulation/state")
def get_simulation_state():
    ok, payload = get_json(f"{settings.background_worker_url.rstrip('/')}/simulation/state")
    if not ok:
        raise HTTPException(
            status_code=503,
            detail={"code": "background_worker_unavailable", "worker": payload},
        )
    return payload


@router.post("/simulation/control")
def control_simulation(
    payload: SimulationControl,
    actor: ActorInfo = Depends(require_permission(PERM_SIMULATION_CONTROL)),
):
    _require_simulation_control()
    ok, result = post_json(
        f"{settings.background_worker_url.rstrip('/')}/simulation/configure",
        payload.model_dump(exclude_none=True),
    )
    if not ok:
        raise HTTPException(
            status_code=503,
            detail={"code": "background_worker_unavailable", "worker": result},
        )
    return result


@router.post("/simulation/step")
def step_simulation(
    actor: ActorInfo = Depends(require_permission(PERM_SIMULATION_CONTROL)),
):
    _require_simulation_control()
    ok, result = post_json(
        f"{settings.background_worker_url.rstrip('/')}/simulation/step",
        {},
    )
    if not ok:
        raise HTTPException(
            status_code=503,
            detail={"code": "background_worker_unavailable", "worker": result},
        )
    return result
