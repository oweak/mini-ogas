from fastapi import APIRouter, Depends

from ..core.security import PERM_COMMAND_ISSUE, ActorInfo, require_permission
from ..store import store

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


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
