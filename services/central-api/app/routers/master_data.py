from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.security import (
    PERM_MASTER_DATA_MANAGE,
    ActorInfo,
    require_permission,
)
from ..domain.master_data import (
    BomIn,
    BomRevisionIn,
    CalendarIn,
    DocumentIn,
    DocumentRevisionIn,
    EquipmentCapabilityIn,
    EquipmentIn,
    MasterDataError,
    MaterialIn,
    OrganizationUnitIn,
    PersonnelIn,
    ProductIn,
    QualificationIn,
    RoutingIn,
    RoutingRevisionIn,
    ShiftIn,
    SkillIn,
    UomIn,
    WorkOrderIn,
)
from ..repositories.master_data import master_data_repository

router = APIRouter(prefix="/master-data", tags=["master-data"])
T = TypeVar("T")


def _actor_name(actor: ActorInfo) -> str:
    return actor.username or actor.display_name or actor.role


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except MasterDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


MasterDataActor = Depends(require_permission(PERM_MASTER_DATA_MANAGE))


@router.post("/organization-units", status_code=status.HTTP_201_CREATED)
def create_organization_unit(payload: OrganizationUnitIn, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.create_organization_unit(payload, _actor_name(actor))
    )


@router.post("/uoms", status_code=status.HTTP_201_CREATED)
def create_uom(payload: UomIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_uom(payload, _actor_name(actor)))


@router.post("/materials", status_code=status.HTTP_201_CREATED)
def create_material(payload: MaterialIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_material(payload, _actor_name(actor)))


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_product(payload, _actor_name(actor)))


@router.post("/equipment", status_code=status.HTTP_201_CREATED)
def create_equipment(payload: EquipmentIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_equipment(payload, _actor_name(actor)))


@router.post(
    "/equipment/{equipment_code}/capabilities",
    status_code=status.HTTP_201_CREATED,
)
def create_equipment_capability(
    equipment_code: str,
    payload: EquipmentCapabilityIn,
    actor: ActorInfo = MasterDataActor,
):
    return _execute(
        lambda: master_data_repository.create_equipment_capability(
            equipment_code, payload, _actor_name(actor)
        )
    )


@router.post("/skills", status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_skill(payload, _actor_name(actor)))


@router.post("/personnel", status_code=status.HTTP_201_CREATED)
def create_personnel(payload: PersonnelIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_personnel(payload, _actor_name(actor)))


@router.post("/qualifications", status_code=status.HTTP_201_CREATED)
def create_qualification(payload: QualificationIn, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.create_qualification(payload, _actor_name(actor))
    )


@router.post("/calendars", status_code=status.HTTP_201_CREATED)
def create_calendar(payload: CalendarIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_calendar(payload, _actor_name(actor)))


@router.post("/calendars/{calendar_code}/shifts", status_code=status.HTTP_201_CREATED)
def create_shift(
    calendar_code: str,
    payload: ShiftIn,
    actor: ActorInfo = MasterDataActor,
):
    return _execute(
        lambda: master_data_repository.create_shift(calendar_code, payload, _actor_name(actor))
    )


@router.post("/documents", status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_document(payload, _actor_name(actor)))


@router.post("/documents/{document_code}/revisions", status_code=status.HTTP_201_CREATED)
def create_document_revision(
    document_code: str,
    payload: DocumentRevisionIn,
    actor: ActorInfo = MasterDataActor,
):
    return _execute(
        lambda: master_data_repository.create_document_revision(
            document_code, payload, _actor_name(actor)
        )
    )


@router.post("/document-revisions/{revision_id}/approve")
def approve_document_revision(revision_id: int, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.transition_revision(
            "document", revision_id, "approve", _actor_name(actor)
        )
    )


@router.post("/document-revisions/{revision_id}/effective")
def make_document_revision_effective(revision_id: int, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.transition_revision(
            "document", revision_id, "effective", _actor_name(actor)
        )
    )


@router.post("/boms", status_code=status.HTTP_201_CREATED)
def create_bom(payload: BomIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_bom(payload, _actor_name(actor)))


@router.post("/boms/{bom_code}/revisions", status_code=status.HTTP_201_CREATED)
def create_bom_revision(
    bom_code: str,
    payload: BomRevisionIn,
    actor: ActorInfo = MasterDataActor,
):
    return _execute(
        lambda: master_data_repository.create_bom_revision(bom_code, payload, _actor_name(actor))
    )


@router.get("/boms/{bom_code}/revisions")
def list_bom_revisions(bom_code: str, actor: ActorInfo = MasterDataActor):
    del actor
    return _execute(lambda: master_data_repository.list_bom_revisions(bom_code))


@router.post("/bom-revisions/{revision_id}/approve")
def approve_bom_revision(revision_id: int, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.transition_revision(
            "bom", revision_id, "approve", _actor_name(actor)
        )
    )


@router.post("/bom-revisions/{revision_id}/effective")
def make_bom_revision_effective(revision_id: int, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.transition_revision(
            "bom", revision_id, "effective", _actor_name(actor)
        )
    )


@router.post("/routings", status_code=status.HTTP_201_CREATED)
def create_routing(payload: RoutingIn, actor: ActorInfo = MasterDataActor):
    return _execute(lambda: master_data_repository.create_routing(payload, _actor_name(actor)))


@router.post("/routings/{routing_code}/revisions", status_code=status.HTTP_201_CREATED)
def create_routing_revision(
    routing_code: str,
    payload: RoutingRevisionIn,
    actor: ActorInfo = MasterDataActor,
):
    return _execute(
        lambda: master_data_repository.create_routing_revision(
            routing_code, payload, _actor_name(actor)
        )
    )


@router.post("/routing-revisions/{revision_id}/approve")
def approve_routing_revision(revision_id: int, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.transition_revision(
            "routing", revision_id, "approve", _actor_name(actor)
        )
    )


@router.post("/routing-revisions/{revision_id}/effective")
def make_routing_revision_effective(revision_id: int, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.transition_revision(
            "routing", revision_id, "effective", _actor_name(actor)
        )
    )


@router.post("/work-orders", status_code=status.HTTP_201_CREATED)
def create_work_order(payload: WorkOrderIn, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.create_work_order(payload, _actor_name(actor))
    )


@router.post("/work-orders/{work_order_code}/release")
def release_work_order(work_order_code: str, actor: ActorInfo = MasterDataActor):
    return _execute(
        lambda: master_data_repository.release_work_order(work_order_code, _actor_name(actor))
    )
