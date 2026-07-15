from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.security import (
    PERM_MAINTENANCE_EXECUTE,
    PERM_MAINTENANCE_MANAGE,
    PERM_MAINTENANCE_VERIFY,
    ActorInfo,
    require_permission,
)
from ..domain.maintenance import (
    AssetIn,
    CalibrationIn,
    ChecklistIn,
    ChecklistResultIn,
    MaintenanceActionIn,
    MaintenanceCodeIn,
    MaintenanceError,
    MaintenanceOrderIn,
    MaintenanceRequestIn,
    MaintenanceVerifyIn,
    PreventiveGenerateIn,
    PreventivePlanIn,
    SpareUseIn,
    ToolAssignmentIn,
    ToolIn,
    ToolLifeEventIn,
    WorkCompleteIn,
)
from ..repositories.maintenance import maintenance_repository

router = APIRouter(prefix="/maintenance", tags=["maintenance"])
T = TypeVar("T")
MaintenanceManager = Depends(require_permission(PERM_MAINTENANCE_MANAGE))
MaintenanceExecutor = Depends(require_permission(PERM_MAINTENANCE_EXECUTE))
MaintenanceVerifier = Depends(require_permission(PERM_MAINTENANCE_VERIFY))


def _actor_name(actor: ActorInfo) -> str:
    return actor.username or actor.display_name or actor.role


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except MaintenanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/assets", status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetIn, actor: ActorInfo = MaintenanceManager):
    return _execute(lambda: maintenance_repository.create_asset(payload, _actor_name(actor)))


@router.post("/codes", status_code=status.HTTP_201_CREATED)
def create_code(payload: MaintenanceCodeIn, actor: ActorInfo = MaintenanceManager):
    return _execute(lambda: maintenance_repository.create_code(payload, _actor_name(actor)))


@router.post("/checklists", status_code=status.HTTP_201_CREATED)
def create_checklist(payload: ChecklistIn, actor: ActorInfo = MaintenanceManager):
    return _execute(lambda: maintenance_repository.create_checklist(payload, _actor_name(actor)))


@router.post("/checklists/{checklist_code}/revisions/{revision}/{action}")
def transition_checklist(
    checklist_code: str,
    revision: int,
    action: str,
    payload: MaintenanceActionIn,
    actor: ActorInfo = MaintenanceManager,
):
    target = {"approve": "approved", "effective": "effective"}.get(action)
    if target is None:
        raise HTTPException(status_code=404, detail="unsupported maintenance-checklist action")
    return _execute(
        lambda: maintenance_repository.transition_checklist(
            checklist_code, revision, target, payload, _actor_name(actor)
        )
    )


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def create_request(payload: MaintenanceRequestIn, actor: ActorInfo = MaintenanceExecutor):
    return _execute(lambda: maintenance_repository.create_request(payload, _actor_name(actor)))


@router.get("/requests/{request_code}")
def get_request(request_code: str, actor: ActorInfo = MaintenanceExecutor):
    del actor
    return _execute(lambda: maintenance_repository.get_request(request_code))


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(payload: MaintenanceOrderIn, actor: ActorInfo = MaintenanceManager):
    return _execute(lambda: maintenance_repository.create_order(payload, _actor_name(actor)))


@router.post("/orders/{order_code}/approve")
def approve_order(
    order_code: str,
    payload: MaintenanceActionIn,
    actor: ActorInfo = MaintenanceManager,
):
    return _execute(
        lambda: maintenance_repository.approve_order(order_code, payload, _actor_name(actor))
    )


@router.post("/orders/{order_code}/start")
def start_order(
    order_code: str,
    payload: MaintenanceActionIn,
    actor: ActorInfo = MaintenanceExecutor,
):
    return _execute(
        lambda: maintenance_repository.start_order(order_code, payload, _actor_name(actor))
    )


@router.post("/orders/{order_code}/checklist-results", status_code=status.HTTP_201_CREATED)
def record_check_result(
    order_code: str,
    payload: ChecklistResultIn,
    actor: ActorInfo = MaintenanceExecutor,
):
    return _execute(
        lambda: maintenance_repository.record_check_result(order_code, payload, _actor_name(actor))
    )


@router.post("/orders/{order_code}/work-complete")
def complete_work(
    order_code: str,
    payload: WorkCompleteIn,
    actor: ActorInfo = MaintenanceExecutor,
):
    return _execute(
        lambda: maintenance_repository.complete_work(order_code, payload, _actor_name(actor))
    )


@router.post("/orders/{order_code}/verify")
def verify_order(
    order_code: str,
    payload: MaintenanceVerifyIn,
    actor: ActorInfo = MaintenanceVerifier,
):
    return _execute(
        lambda: maintenance_repository.verify_order(order_code, payload, _actor_name(actor))
    )


@router.post("/orders/{order_code}/spares", status_code=status.HTTP_201_CREATED)
def record_spare_use(
    order_code: str,
    payload: SpareUseIn,
    actor: ActorInfo = MaintenanceExecutor,
):
    return _execute(
        lambda: maintenance_repository.record_spare_use(order_code, payload, _actor_name(actor))
    )


@router.post("/tools", status_code=status.HTTP_201_CREATED)
def create_tool(payload: ToolIn, actor: ActorInfo = MaintenanceManager):
    return _execute(lambda: maintenance_repository.create_tool(payload, _actor_name(actor)))


@router.post("/tools/{tool_code}/assignments", status_code=status.HTTP_201_CREATED)
def assign_tool(
    tool_code: str,
    payload: ToolAssignmentIn,
    actor: ActorInfo = MaintenanceManager,
):
    return _execute(
        lambda: maintenance_repository.assign_tool(tool_code, payload, _actor_name(actor))
    )


@router.post("/tools/{tool_code}/life-events", status_code=status.HTTP_201_CREATED)
def record_tool_life(
    tool_code: str,
    payload: ToolLifeEventIn,
    actor: ActorInfo = MaintenanceExecutor,
):
    return _execute(
        lambda: maintenance_repository.record_tool_life(tool_code, payload, _actor_name(actor))
    )


@router.post("/tools/{tool_code}/calibrations", status_code=status.HTTP_201_CREATED)
def record_calibration(
    tool_code: str,
    payload: CalibrationIn,
    actor: ActorInfo = MaintenanceExecutor,
):
    return _execute(
        lambda: maintenance_repository.record_calibration(tool_code, payload, _actor_name(actor))
    )


@router.post("/preventive-plans", status_code=status.HTTP_201_CREATED)
def create_preventive_plan(payload: PreventivePlanIn, actor: ActorInfo = MaintenanceManager):
    return _execute(
        lambda: maintenance_repository.create_preventive_plan(payload, _actor_name(actor))
    )


@router.post("/preventive-plans/{plan_code}/effective")
def effective_preventive_plan(
    plan_code: str,
    payload: MaintenanceActionIn,
    actor: ActorInfo = MaintenanceManager,
):
    return _execute(
        lambda: maintenance_repository.effective_preventive_plan(
            plan_code, payload, _actor_name(actor)
        )
    )


@router.post("/preventive-plans/{plan_code}/generate")
def generate_preventive_work(
    plan_code: str,
    payload: PreventiveGenerateIn,
    actor: ActorInfo = MaintenanceManager,
):
    return _execute(
        lambda: maintenance_repository.generate_preventive_work(
            plan_code, payload, _actor_name(actor)
        )
    )
