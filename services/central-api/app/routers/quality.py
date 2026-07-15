from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.security import (
    PERM_QUALITY_MANAGE,
    PERM_QUALITY_MEASURE,
    PERM_QUALITY_RELEASE,
    ActorInfo,
    require_permission,
)
from ..domain.quality import (
    AuthorizationIn,
    CapaCompleteIn,
    CapaIn,
    DispositionIn,
    GaugeIn,
    InspectionLotIn,
    InspectionPlanIn,
    MeasurementIn,
    QualityActionIn,
    QualityError,
)
from ..repositories.quality import quality_repository

router = APIRouter(prefix="/quality", tags=["quality"])
T = TypeVar("T")
QualityManager = Depends(require_permission(PERM_QUALITY_MANAGE))
QualityMeasurer = Depends(require_permission(PERM_QUALITY_MEASURE))
QualityReleaser = Depends(require_permission(PERM_QUALITY_RELEASE))


def _actor_name(actor: ActorInfo) -> str:
    return actor.username or actor.display_name or actor.role


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except QualityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/gauges", status_code=status.HTTP_201_CREATED)
def create_gauge(payload: GaugeIn, actor: ActorInfo = QualityManager):
    return _execute(lambda: quality_repository.create_gauge(payload, _actor_name(actor)))


@router.post("/inspection-plans", status_code=status.HTTP_201_CREATED)
def create_inspection_plan(payload: InspectionPlanIn, actor: ActorInfo = QualityManager):
    return _execute(lambda: quality_repository.create_plan(payload, _actor_name(actor)))


@router.post("/inspection-plans/{plan_code}/revisions/{revision}/{action}")
def transition_inspection_plan(
    plan_code: str,
    revision: int,
    action: str,
    payload: QualityActionIn,
    actor: ActorInfo = QualityManager,
):
    target = {"approve": "approved", "effective": "effective"}.get(action)
    if target is None:
        raise HTTPException(status_code=404, detail="unsupported inspection-plan action")
    return _execute(
        lambda: quality_repository.transition_plan(
            plan_code, revision, target, payload, _actor_name(actor)
        )
    )


@router.post("/inspection-lots", status_code=status.HTTP_201_CREATED)
def create_inspection_lot(payload: InspectionLotIn, actor: ActorInfo = QualityMeasurer):
    return _execute(lambda: quality_repository.create_inspection(payload, _actor_name(actor)))


@router.get("/inspection-lots/{inspection_lot_code}")
def get_inspection_lot(inspection_lot_code: str, actor: ActorInfo = QualityMeasurer):
    del actor
    return _execute(lambda: quality_repository.get_inspection(inspection_lot_code))


@router.post(
    "/inspection-lots/{inspection_lot_code}/measurements",
    status_code=status.HTTP_201_CREATED,
)
def record_measurement(
    inspection_lot_code: str,
    payload: MeasurementIn,
    actor: ActorInfo = QualityMeasurer,
):
    return _execute(
        lambda: quality_repository.record_measurement(
            inspection_lot_code, payload, _actor_name(actor)
        )
    )


@router.post("/nonconformances/{nc_code}/dispositions", status_code=status.HTTP_201_CREATED)
def create_disposition(nc_code: str, payload: DispositionIn, actor: ActorInfo = QualityManager):
    return _execute(
        lambda: quality_repository.create_disposition(nc_code, payload, _actor_name(actor))
    )


@router.post("/dispositions/{disposition_code}/approve")
def approve_disposition(
    disposition_code: str,
    payload: AuthorizationIn,
    actor: ActorInfo = QualityReleaser,
):
    return _execute(
        lambda: quality_repository.approve_disposition(
            disposition_code, payload, _actor_name(actor)
        )
    )


@router.post("/inspection-lots/{inspection_lot_code}/release")
def release_inspection_lot(
    inspection_lot_code: str,
    payload: AuthorizationIn,
    actor: ActorInfo = QualityReleaser,
):
    return _execute(
        lambda: quality_repository.release_inspection(
            inspection_lot_code, payload, _actor_name(actor)
        )
    )


@router.post("/nonconformances/{nc_code}/capas", status_code=status.HTTP_201_CREATED)
def create_capa(nc_code: str, payload: CapaIn, actor: ActorInfo = QualityManager):
    return _execute(lambda: quality_repository.create_capa(nc_code, payload, _actor_name(actor)))


@router.post("/capas/{capa_code}/complete")
def complete_capa(
    capa_code: str,
    payload: CapaCompleteIn,
    actor: ActorInfo = QualityReleaser,
):
    return _execute(
        lambda: quality_repository.complete_capa(capa_code, payload, _actor_name(actor))
    )
