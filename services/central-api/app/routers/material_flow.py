from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.security import PERM_INVENTORY_MANAGE, ActorInfo, require_permission
from ..domain.material_flow import (
    ContainerIn,
    ExternalSnapshotIn,
    LocationIn,
    LotIn,
    MaterialFlowError,
    MovementIn,
    ReconciliationAdjustmentIn,
    TransformationIn,
    WarehouseIn,
)
from ..repositories.material_flow import material_flow_repository

router = APIRouter(prefix="/material-flow", tags=["material-flow"])
T = TypeVar("T")
MaterialActor = Depends(require_permission(PERM_INVENTORY_MANAGE))


def _actor_name(actor: ActorInfo) -> str:
    return actor.username or actor.display_name or actor.role


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except MaterialFlowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/warehouses", status_code=status.HTTP_201_CREATED)
def create_warehouse(payload: WarehouseIn, actor: ActorInfo = MaterialActor):
    return _execute(
        lambda: material_flow_repository.create_warehouse(payload, _actor_name(actor))
    )


@router.post("/locations", status_code=status.HTTP_201_CREATED)
def create_location(payload: LocationIn, actor: ActorInfo = MaterialActor):
    return _execute(
        lambda: material_flow_repository.create_location(payload, _actor_name(actor))
    )


@router.post("/containers", status_code=status.HTTP_201_CREATED)
def create_container(payload: ContainerIn, actor: ActorInfo = MaterialActor):
    return _execute(
        lambda: material_flow_repository.create_container(payload, _actor_name(actor))
    )


@router.post("/lots", status_code=status.HTTP_201_CREATED)
def create_lot(payload: LotIn, actor: ActorInfo = MaterialActor):
    return _execute(lambda: material_flow_repository.create_lot(payload, _actor_name(actor)))


@router.post("/movements", status_code=status.HTTP_201_CREATED)
def record_movement(payload: MovementIn, actor: ActorInfo = MaterialActor):
    return _execute(
        lambda: material_flow_repository.record_movement(payload, _actor_name(actor))
    )


@router.get("/lots/{lot_code}/balances")
def lot_balances(lot_code: str, actor: ActorInfo = MaterialActor):
    del actor
    return _execute(lambda: material_flow_repository.lot_balances(lot_code))


@router.post("/transformations", status_code=status.HTTP_201_CREATED)
def record_transformation(payload: TransformationIn, actor: ActorInfo = MaterialActor):
    return _execute(
        lambda: material_flow_repository.record_transformation(payload, _actor_name(actor))
    )


@router.get("/genealogy/{lot_code}")
def genealogy(lot_code: str, actor: ActorInfo = MaterialActor):
    del actor
    return _execute(lambda: material_flow_repository.genealogy(lot_code))


@router.post("/external-snapshots", status_code=status.HTTP_201_CREATED)
def import_external_snapshot(
    payload: ExternalSnapshotIn, actor: ActorInfo = MaterialActor
):
    return _execute(
        lambda: material_flow_repository.import_external_snapshot(
            payload, _actor_name(actor)
        )
    )


@router.post("/reconciliations/{reconciliation_id}/adjust")
def adjust_reconciliation(
    reconciliation_id: int,
    payload: ReconciliationAdjustmentIn,
    actor: ActorInfo = MaterialActor,
):
    return _execute(
        lambda: material_flow_repository.adjust_reconciliation(
            reconciliation_id, payload, _actor_name(actor)
        )
    )
