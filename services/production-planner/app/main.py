import os
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field


def _session_token() -> str:
    token = os.environ.get("OGAS_SESSION_TOKEN")
    if not token:
        token = str(uuid.uuid4())
        os.environ["OGAS_SESSION_TOKEN"] = token
    return token


app = FastAPI(title="Mini-OGAS Production Planner", version="0.1.0")

_token_scheme = APIKeyHeader(name="X-OGAS-Token", auto_error=False)
_expected_token = os.getenv("API_ACCESS_TOKEN", "")
PROCESS_ID = os.getpid()
PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()


def _verify_token(token: str | None = Depends(_token_scheme)) -> None:
    if not token or not secrets.compare_digest(token, _expected_token):
        raise HTTPException(status_code=401, detail="missing or invalid X-OGAS-Token")


class MarketSignal(BaseModel):
    product_code: str
    demand_index: float
    inventory_pressure: float


class NodeHealth(BaseModel):
    node_code: str
    workshop_type: str
    status: str
    load_score: float = Field(ge=0, le=100)


class AllocationOrder(BaseModel):
    order_id: str
    product_code: str
    required_quantity: int = Field(ge=1)
    priority: int = Field(ge=1, le=10)
    deadline_hours: int = Field(ge=1)
    status: str = "received"


class PlanningRequest(BaseModel):
    market_signals: list[MarketSignal]
    node_health: list[NodeHealth]
    allocation_orders: list[AllocationOrder] = Field(default_factory=list)


class PlanItem(BaseModel):
    product_code: str
    target_quantity: int
    priority: int
    route: list[str]
    reason: str


ROUTES = {
    "P1": ["turning", "grinding"],
    "P2": ["turning", "milling"],
    "P3": ["turning", "milling", "grinding"],
    "P4": ["turning", "grinding"],
    "P5": ["milling", "grinding"],
}


@app.get("/health")
def health() -> dict[str, str | int]:
    return {
        "status": "ok", "service": "production-planner", "session_token": _session_token(),
        "process_id": PROCESS_ID, "process_started_at": PROCESS_STARTED_AT,
    }


@app.post("/plan", response_model=list[PlanItem])
def plan(req: PlanningRequest, _: None = Depends(_verify_token)) -> list[PlanItem]:
    healthy_workshops = {
        node.workshop_type
        for node in req.node_health
        if node.status == "online" and node.load_score < 80
    }
    signals = {signal.product_code: signal for signal in req.market_signals}
    orders_by_product: dict[str, list[AllocationOrder]] = {}
    for order in req.allocation_orders:
        if order.status in {"completed", "cancelled", "rejected"}:
            continue
        orders_by_product.setdefault(order.product_code, []).append(order)

    plans: list[PlanItem] = []
    product_codes = sorted(set(signals) | set(orders_by_product))
    for product_code in product_codes:
        signal = signals.get(product_code)
        route = ROUTES.get(product_code, ["turning"])
        route_available = all(step in healthy_workshops for step in route)
        pressure = (
            signal.demand_index - signal.inventory_pressure
            if signal is not None
            else 0.0
        )
        market_priority = 2 if pressure > 60 and route_available else 6
        market_quantity = (
            max(10, int(pressure * 2))
            if route_available
            else max(5, int(pressure))
        )
        active_orders = orders_by_product.get(product_code, [])
        committed_quantity = sum(order.required_quantity for order in active_orders)
        priority = min(
            [market_priority, *(order.priority for order in active_orders)]
        )
        quantity = max(market_quantity, committed_quantity)
        order_context = ""
        if active_orders:
            order_context = (
                "; accepted_orders="
                + ",".join(order.order_id for order in active_orders)
                + f"; committed_quantity={committed_quantity}"
            )
        plans.append(
            PlanItem(
                product_code=product_code,
                target_quantity=quantity,
                priority=priority,
                route=route,
                reason=(
                    "Market demand and route capacity support the production plan"
                    if priority <= 2
                    else "Inventory pressure or node health constrains the production plan"
                ) + order_context,
            )
        )
    return sorted(plans, key=lambda item: item.priority)
