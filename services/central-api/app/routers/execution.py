from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.security import PERM_EXECUTION_MANAGE, ActorInfo, require_permission
from ..domain.execution import (
    CompleteTaskIn,
    DowntimeEndIn,
    DowntimeStartIn,
    ExecutionActionIn,
    ExecutionError,
    HoldActionIn,
    ProductionOrderIn,
    QuantityReportIn,
    SetupCompleteIn,
)
from ..repositories.execution import execution_repository

router = APIRouter(prefix="/execution", tags=["execution"])
T = TypeVar("T")
ExecutionActor = Depends(require_permission(PERM_EXECUTION_MANAGE))


def _actor_name(actor: ActorInfo) -> str:
    return actor.username or actor.display_name or actor.role


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ExecutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/production-orders", status_code=status.HTTP_201_CREATED)
def create_production_order(payload: ProductionOrderIn, actor: ActorInfo = ExecutionActor):
    return _execute(
        lambda: execution_repository.create_production_order(payload, _actor_name(actor))
    )


@router.post("/production-orders/{production_order_code}/work-orders/{work_order_code}/attach")
def attach_work_order(
    production_order_code: str,
    work_order_code: str,
    payload: ExecutionActionIn,
    actor: ActorInfo = ExecutionActor,
):
    return _execute(
        lambda: execution_repository.attach_work_order(
            production_order_code, work_order_code, payload, _actor_name(actor)
        )
    )


@router.post("/production-orders/{production_order_code}/release")
def release_production_order(
    production_order_code: str,
    payload: ExecutionActionIn,
    actor: ActorInfo = ExecutionActor,
):
    return _execute(
        lambda: execution_repository.release_production_order(
            production_order_code, payload, _actor_name(actor)
        )
    )


@router.post("/production-orders/{production_order_code}/close")
def close_production_order(
    production_order_code: str,
    payload: ExecutionActionIn,
    actor: ActorInfo = ExecutionActor,
):
    return _execute(
        lambda: execution_repository.close_production_order(
            production_order_code, payload, _actor_name(actor)
        )
    )


@router.post("/work-orders/{work_order_code}/dispatch")
def dispatch_work_order(
    work_order_code: str,
    payload: ExecutionActionIn,
    actor: ActorInfo = ExecutionActor,
):
    return _execute(
        lambda: execution_repository.dispatch_work_order(
            work_order_code, payload, _actor_name(actor)
        )
    )


@router.get("/work-orders/{work_order_code}")
def get_work_order_execution(work_order_code: str, actor: ActorInfo = ExecutionActor):
    del actor
    return _execute(lambda: execution_repository.get_work_order_execution(work_order_code))


@router.get("/work-orders/{work_order_code}/replay")
def replay_work_order(work_order_code: str, actor: ActorInfo = ExecutionActor):
    del actor
    return _execute(lambda: execution_repository.replay_work_order(work_order_code))


@router.post("/work-orders/{work_order_code}/close")
def close_work_order(
    work_order_code: str,
    payload: ExecutionActionIn,
    actor: ActorInfo = ExecutionActor,
):
    return _execute(
        lambda: execution_repository.close_work_order(
            work_order_code, payload, _actor_name(actor)
        )
    )


@router.get("/tasks/{task_id}")
def get_task(task_id: int, actor: ActorInfo = ExecutionActor):
    del actor
    return _execute(lambda: execution_repository.get_task(task_id))


@router.get("/tasks/{task_id}/history")
def get_task_history(task_id: int, actor: ActorInfo = ExecutionActor):
    del actor
    return _execute(lambda: execution_repository.get_task_history(task_id))


@router.post("/tasks/{task_id}/setup/start")
def start_setup(
    task_id: int, payload: ExecutionActionIn, actor: ActorInfo = ExecutionActor
):
    return _execute(
        lambda: execution_repository.start_setup(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/setup/complete")
def complete_setup(
    task_id: int, payload: SetupCompleteIn, actor: ActorInfo = ExecutionActor
):
    return _execute(
        lambda: execution_repository.complete_setup(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/start")
def start_task(task_id: int, payload: ExecutionActionIn, actor: ActorInfo = ExecutionActor):
    return _execute(
        lambda: execution_repository.start_task(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/pause")
def pause_task(task_id: int, payload: ExecutionActionIn, actor: ActorInfo = ExecutionActor):
    return _execute(
        lambda: execution_repository.pause_task(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/resume")
def resume_task(task_id: int, payload: ExecutionActionIn, actor: ActorInfo = ExecutionActor):
    return _execute(
        lambda: execution_repository.resume_task(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/hold")
def hold_task(task_id: int, payload: HoldActionIn, actor: ActorInfo = ExecutionActor):
    return _execute(
        lambda: execution_repository.hold_task(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/release-hold")
def release_hold(task_id: int, payload: HoldActionIn, actor: ActorInfo = ExecutionActor):
    return _execute(
        lambda: execution_repository.release_hold(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/quantity-reports", status_code=status.HTTP_201_CREATED)
def report_quantity(
    task_id: int, payload: QuantityReportIn, actor: ActorInfo = ExecutionActor
):
    return _execute(
        lambda: execution_repository.report_quantity(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: int, payload: CompleteTaskIn, actor: ActorInfo = ExecutionActor
):
    return _execute(
        lambda: execution_repository.complete_task(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/close")
def close_task(task_id: int, payload: ExecutionActionIn, actor: ActorInfo = ExecutionActor):
    return _execute(
        lambda: execution_repository.close_task(task_id, payload, _actor_name(actor))
    )


@router.post("/tasks/{task_id}/downtime", status_code=status.HTTP_201_CREATED)
def start_downtime(
    task_id: int, payload: DowntimeStartIn, actor: ActorInfo = ExecutionActor
):
    return _execute(
        lambda: execution_repository.start_downtime(task_id, payload, _actor_name(actor))
    )


@router.post("/downtime/{downtime_id}/end")
def end_downtime(
    downtime_id: int, payload: DowntimeEndIn, actor: ActorInfo = ExecutionActor
):
    return _execute(
        lambda: execution_repository.end_downtime(downtime_id, payload, _actor_name(actor))
    )
