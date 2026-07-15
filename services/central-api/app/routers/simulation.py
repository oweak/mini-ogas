from fastapi import APIRouter, Depends, HTTPException

from ..core.config import settings
from ..core.security import PERM_SIMULATION_CONTROL, ActorInfo, require_permission
from ..models import SimulationControl
from ..store import store

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
    return store.simulation_state()


@router.post("/simulation/control")
def control_simulation(
    payload: SimulationControl,
    actor: ActorInfo = Depends(require_permission(PERM_SIMULATION_CONTROL)),
):
    _require_simulation_control()
    return store.configure_simulation(
        running=payload.running,
        speed=payload.speed,
        anomaly_rate=payload.anomaly_rate,
    )


@router.post("/simulation/step")
def step_simulation(
    actor: ActorInfo = Depends(require_permission(PERM_SIMULATION_CONTROL)),
):
    _require_simulation_control()
    return store.simulation_step()
