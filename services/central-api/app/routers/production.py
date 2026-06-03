from fastapi import APIRouter

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
def create_allocation_order(order: AllocationOrderIn):
    created = store.submit_allocation_order(order)
    return {"accepted": True, "order": created, "plans": store.production_plans}


@router.post("/production-plans/generate")
def generate_production_plan():
    return store.generate_production_plan()


@router.post("/production-plans")
def submit_production_plan(plan: ProductionPlanIn):
    store.production_plans.append(plan)
    return {"accepted": True, "plan": plan}


@router.get("/production-plans")
def list_production_plans():
    return store.production_plans
