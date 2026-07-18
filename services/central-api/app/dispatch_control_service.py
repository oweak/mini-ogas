from __future__ import annotations

from fastapi import HTTPException

from .command_control_service import CommandControlService, command_control_service
from .core.security import ActorInfo, actor_identity
from .models import AllocationOrder, NodeCommand, ProductionPlanIn, Severity
from .store import MemoryStore, store


class DispatchControlService:
    """Translate an accepted order and plan into governed node commands."""

    def __init__(self, state: MemoryStore, command_service: CommandControlService) -> None:
        self.state = state
        self.command_service = command_service

    def propose_target_rates(
        self,
        *,
        actor: ActorInfo,
        order_id: str = "",
        node_code: str = "",
    ) -> dict[str, object]:
        order = self._find_order(order_id)
        plan = self._find_plan(order)
        tasks = [
            task
            for task in self.state.dispatch_tasks
            if task.product_code == order.product_code
            and task.assigned_node
            and task.status != "blocked"
            and (not node_code or task.assigned_node == node_code)
        ]
        if not tasks:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "dispatch_has_no_executable_task",
                    "message": "The selected order has no dispatch task bound to an online node.",
                    "order_id": order.order_id,
                    "node_code": node_code,
                },
            )

        tasks_by_node: dict[str, list[int]] = {}
        for task in tasks:
            tasks_by_node.setdefault(task.assigned_node, []).append(task.id)

        planning_horizon_minutes = max(1, order.deadline_hours * 60)
        requested_rate = round(order.required_quantity / planning_horizon_minutes, 3)
        requested_rate = max(0.001, requested_rate)
        validated: list[tuple[str, float, list[int]]] = []
        for target_node, task_ids in sorted(tasks_by_node.items()):
            physical_limit = self.state.reported_physical_rate_limit_per_minute(target_node)
            if physical_limit is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "node_capacity_not_reported",
                        "message": "A fresh node heartbeat must report physical capacity before dispatch control.",
                        "node_code": target_node,
                        "order_id": order.order_id,
                    },
                )
            if requested_rate > physical_limit + 1e-9:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "order_rate_exceeds_physical_capacity",
                        "message": "The order cannot meet its deadline within the reported physical capacity.",
                        "order_id": order.order_id,
                        "node_code": target_node,
                        "requested_rate": requested_rate,
                        "maximum_rate": round(physical_limit, 3),
                        "rate_unit": "parts_per_minute",
                    },
                )
            validated.append((target_node, physical_limit, task_ids))

        commands: list[NodeCommand] = []
        for target_node, physical_limit, task_ids in validated:
            commands.append(
                self.command_service.issue_dispatch_target_rate(
                    node_code=target_node,
                    target_rate=requested_rate,
                    actor=actor,
                    order_id=order.order_id,
                    product_code=order.product_code,
                    plan_target_quantity=plan.target_quantity,
                    dispatch_task_ids=task_ids,
                    planning_horizon_minutes=planning_horizon_minutes,
                    physical_limit=physical_limit,
                )
            )

        order.status = "awaiting_approval"
        self.state.persist_allocation_order_shadow()
        command_ids = [command.id for command in commands]
        self.state.add_event(
            "central-api",
            "dispatch-target-rate-proposed",
            Severity.info,
            (
                f"order_id={order.order_id} produced governed target-rate command(s) "
                f"{command_ids}; requested_rate={requested_rate} parts_per_minute."
            ),
        )
        self.state.add_audit_log(
            actor_identity(actor),
            "dispatch:propose",
            "allocation_order",
            order.order_id,
            "waiting_approval",
            (
                f"product_code={order.product_code}; plan_target_quantity={plan.target_quantity}; "
                f"command_ids={command_ids}; target_rate={requested_rate}"
            ),
        )
        return {
            "accepted": True,
            "order": order.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "commands": [command.model_dump(mode="json") for command in commands],
            "requested_rate": requested_rate,
            "rate_unit": "parts_per_minute",
            "requires_approval": True,
        }

    def _find_order(self, order_id: str) -> AllocationOrder:
        if order_id:
            order = next(
                (item for item in self.state.allocation_orders if item.order_id == order_id),
                None,
            )
        else:
            order = next(
                (
                    item
                    for item in reversed(self.state.allocation_orders)
                    if item.status in {"received", "planned", "awaiting_approval"}
                ),
                None,
            )
        if order is None:
            raise HTTPException(status_code=404, detail="allocation order not found")
        return order

    def _find_plan(self, order: AllocationOrder) -> ProductionPlanIn:
        plan = next(
            (item for item in self.state.production_plans if item.product_code == order.product_code),
            None,
        )
        if plan is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "production_plan_missing",
                    "message": "Regenerate the production plan before proposing dispatch control.",
                    "order_id": order.order_id,
                    "product_code": order.product_code,
                },
            )
        if plan.target_quantity < order.required_quantity:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "production_plan_does_not_cover_order",
                    "message": "The generated plan does not cover the accepted order quantity.",
                    "order_id": order.order_id,
                    "required_quantity": order.required_quantity,
                    "plan_target_quantity": plan.target_quantity,
                },
            )
        return plan


dispatch_control_service = DispatchControlService(store, command_control_service)
