from fastapi import APIRouter

from ..models import SimulationControl
from ..store import store

router = APIRouter(tags=["simulation"])


@router.get("/simulation/state")
def get_simulation_state():
    return store.simulation_state()


@router.post("/simulation/control")
def control_simulation(payload: SimulationControl):
    return store.configure_simulation(
        running=payload.running,
        speed=payload.speed,
        anomaly_rate=payload.anomaly_rate,
    )


@router.post("/simulation/step")
def step_simulation():
    return store.simulation_step()
