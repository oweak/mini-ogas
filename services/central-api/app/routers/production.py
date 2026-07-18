from fastapi import APIRouter, Depends

from ..core.security import (
    PERM_EXECUTION_MANAGE,
    ActorInfo,
    actor_identity,
    require_permission,
)
from ..models import AllocationOrderIn, ProductionPlanIn
from ..store import store

router = APIRouter(tags=["production"])


@router.get("/inventory")
def list_inventory():
    return store.inventory


@router.get("/allocation-orders")
def list_allocation_orders():
    return store.allocation_orders


@router.post("/allocation-orders")
def create_allocation_order(
    order: AllocationOrderIn,
    actor: ActorInfo = Depends(require_permission(PERM_EXECUTION_MANAGE)),
):
    created = store.submit_allocation_order(order)
    store.add_audit_log(
        actor_identity(actor),
        "allocation-order:create",
        "allocation_order",
        created.order_id,
        created.status,
        (
            f"product_code={created.product_code}; required_quantity={created.required_quantity}; "
            f"deadline_hours={created.deadline_hours}; priority={created.priority}"
        ),
    )
    return {"accepted": True, "order": created, "plans": store.production_plans}


@router.post("/production-plans/generate")
def generate_production_plan(
    actor: ActorInfo = Depends(require_permission(PERM_EXECUTION_MANAGE)),
):
    return store.generate_production_plan()


@router.post("/production-plans")
def submit_production_plan(
    plan: ProductionPlanIn,
    actor: ActorInfo = Depends(require_permission(PERM_EXECUTION_MANAGE)),
):
    store.production_plans.append(plan)
    store.persist_production_plan_shadow()
    return {"accepted": True, "plan": plan}


@router.get("/production-plans")
def list_production_plans():
    return store.production_plans
