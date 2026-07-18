from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.security import PERM_COMMAND_ISSUE, ActorInfo, require_permission
from ..dispatch_control_service import dispatch_control_service
from ..store import store

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


class DispatchTargetRateProposalIn(BaseModel):
    order_id: str = ""
    node_code: str = ""


@router.get("/tasks")
def list_dispatch_tasks():
    return store.dispatch_tasks


@router.get("/resources")
def list_resource_allocations():
    return store.resource_allocations()


@router.post("/rebuild")
def rebuild_dispatch(
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
):
    tasks = store.rebuild_dispatch()
    blocked = sum(1 for task in tasks if task.status == "blocked")
    return {
        "accepted": True,
        "total": len(tasks),
        "dispatched": len(tasks) - blocked,
        "blocked": blocked,
    }


@router.post("/target-rate-proposals")
def propose_dispatch_target_rates(
    payload: DispatchTargetRateProposalIn,
    actor: ActorInfo = Depends(require_permission(PERM_COMMAND_ISSUE)),
):
    return dispatch_control_service.propose_target_rates(
        actor=actor,
        order_id=payload.order_id,
        node_code=payload.node_code,
    )
